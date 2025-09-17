from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re
import xmlrpc.client
import logging
_logger = logging.getLogger(__name__)
from copy import deepcopy


class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_commission_ids = fields.One2many(
        'customer.commission', 'partner_id', string='Customer Commissions')
    related_partner_id = fields.Integer(string='Related Partner ID')

    commission_count = fields.Integer(compute='_compute_commission_count', string='Commission Count')
    # mobile = fields.Char(string='Mobile', help='Mobile number in format +880 XXXX-XXXXXX')

    def _compute_commission_count(self):
        for partner in self:
            partner.commission_count = self.env['customer.commission'].search_count([('partner_id', '=', partner.id)])

    def action_view_partner_commission(self):
        self.ensure_one()
        return {
            'name': 'Customer Commissions',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'res_model': 'customer.commission',
            'domain': [('partner_id', '=', self.id)],
        }

    @api.onchange('mobile')
    def _onchange_mobile(self):
        """Format mobile number in UI"""
        if self.mobile:
            self.mobile = self._format_mobile_number(self.mobile)

    @staticmethod
    def _format_mobile_number(mobile):
        if not mobile:
            return mobile
        # if mobile starts with '01' and of total 11 digits, convert to +8801XXXXXXXXX
        if mobile.startswith('01') and len(mobile) == 11:
            return '+880 ' + mobile[1:5] + '-' + mobile[5:]
        # if given number already starts with +880 and is of correct format +880 XXXX-XXXXXX but problem is with the spacing and use of hyfen, correct it to previous format
        elif mobile.startswith('+880') and re.match(r'^\+880\d{10}$', mobile):
            return '+880 ' + mobile[4:8] + '-' + mobile[8:]
        return mobile

    def _get_external_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'url': ICP.get_param('purchase_commission.external_server_url', ''),
            'db': ICP.get_param('purchase_commission.external_server_db', ''),
            'uid': int(ICP.get_param('purchase_commission.external_server_uid', 0)),
            'password': ICP.get_param('purchase_commission.external_server_password', '')
        }

    def _db_sync_enabled(self):
        # if data_sync is true return true else false
        ICP = self.env['ir.config_parameter'].sudo()
        return ICP.get_param('purchase_commission.data_sync', 'False') == 'True'

    def create(self, vals_list):
        """Handle both single and multiple record creation during import"""
        # Ensure vals_list is always a list for consistency
        _logger.info(f'Creating partners with vals: {vals_list}')
        single_record = isinstance(vals_list, dict)
        if single_record:
            vals_list = [vals_list]

        if self._db_sync_enabled():
            _logger.warning('Data sync is enabled, attempting to sync partners to external DB')
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            try:
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                # create record in remote database
                for vals in vals_list:
                    # remove key avalara_partner_code and avalara_exemption_id if exists
                    if vals.get('mobile'):
                        vals['mobile'] = self._format_mobile_number(vals['mobile'])
                        # when user with same name and mobile already available in remote db, do nothing
                        try:
                            existing_records = remote_models.execute_kw(db, uid, password, 'res.partner', 'search',
                                                                        [[['name', '=', vals.get('name')],
                                                                          ['mobile', '=', vals.get('mobile')]]])
                            # If no existing record found, create a new one in the remote DB
                            if not existing_records:
                                # Need to handle case when a company has many child contatc
                                if vals.get('child_ids', False):
                                    child_ids = deepcopy(vals['child_ids'])
                                    # remove child_ids before creating company record
                                    vals.pop('child_ids')
                                    # create company record in remote db
                                    remote_record_id = remote_models.execute_kw(db, uid, password, 'res.partner',
                                                                                'create', [vals])
                                    # revert child_ids info on vals
                                    vals['child_ids'] = child_ids
                                    # create child record in remote database
                                    for child in child_ids:
                                        child[2]['parent_id'] = remote_record_id
                                        remote_models.execute_kw(db, uid, password, 'res.partner', 'create', [child[2]])
                                else:
                                    remote_models.execute_kw(db, uid, password, 'res.partner', 'create', [vals])
                                _logger.info(f'Created remote partner for {vals.get("name")}')
                        except Exception as e:
                            _logger.error(f'Error during remote partner creation: {e}')
                # create record in main database
                new_partners = super(ResPartner, self).create(vals_list)
                # map new partners with remote records
                for partner in new_partners:
                    if not partner.related_partner_id:
                        # find related record id from remote db
                        try:
                            remote_record = remote_models.execute_kw(db, uid, password, 'res.partner', 'search',
                                                                     [[['name', '=', partner.name],
                                                                       ['mobile', '=', partner.mobile]]], {'limit': 1})
                            # write related partner id from main  database to remote record
                            remote_models.execute_kw(db, uid, password, 'res.partner', 'write',
                                                     [remote_record, {'related_partner_id': partner.id}])
                            # write related partner id from remote database to main record
                            partner.write({'related_partner_id': remote_record[0] if remote_record else False})

                        except Exception as e:
                            _logger.error(f'Error mapping related_partner_id: {e}')
                return new_partners
            except Exception as e:
                _logger.error(f'Error connecting to external DB: {e}')
        else:
            _logger.warning('Data sync is disabled, proceeding without sync')
            return super(ResPartner, self).create(vals_list)

    def write(self, vals):
        """Format mobile number during updates"""
        for rec in self:
            if vals.get('mobile'):
                vals['mobile'] = rec._format_mobile_number(vals['mobile'])
            if rec._db_sync_enabled():
                config = rec._get_external_config()
                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']
                res_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                res_models.execute_kw(db, uid, password, 'res.partner', 'write', [[rec.related_partner_id], vals])
        return super(ResPartner, self).write(vals)

    @api.constrains('mobile', 'name')
    def _check_unique_customer(self):
        """Ensure unique combination of name and mobile"""
        for partner in self:
            if partner.name and partner.mobile:
                existing_partners = self.env['res.partner'].search([
                    ('id', '!=', partner.id),
                    ('name', '=', partner.name),
                    ('mobile', '=', partner.mobile)
                ])
                if existing_partners:
                    raise ValidationError("A partner with the same name and mobile number already exists.")

    @api.constrains('mobile')
    def _check_mobile_number(self):
        """Check mobile number format: +880 XX-XXXXXX with valid operator codes"""
        for partner in self:
            if partner.mobile:
                # Valid operator codes for Bangladesh
                valid_operators = ['13', '14', '15', '16', '17', '18', '19']

                match = re.match(r'^\+880 (\d{4})-\d{6}$', partner.mobile)
                if not match:
                    raise ValidationError("Mobile number must be of format +880 XXXX-XXXXXX")
                operator_code = match.group(1)[:2]
                if operator_code not in valid_operators:
                    raise ValidationError(
                        f"Invalid operator code: {operator_code}. Valid codes are: {', '.join(valid_operators)}")

                # check if same mobile number already exists in other partner
                existing_partners = self.env['res.partner'].search([
                    ('id', '!=', partner.id),
                    ('mobile', '=', partner.mobile)
                ])
                if existing_partners:
                    raise ValidationError("A partner with the same mobile number already exists.")

    @api.constrains('email')
    def _check_email_format(self):
        """Check if email format is valid and unique"""
        for partner in self:
            if partner.email:
                # Check for duplicate emails
                existing_partners = self.env['res.partner'].search([
                    ('id', '!=', partner.id),
                    ('email', '=', partner.email)
                ])
                if existing_partners:
                    raise ValidationError("A partner with the same email address already exists.")

    def unlink(self):
        """Override unlink to delete the partner in external DB as well"""
        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            models_rpc = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

            for partner in self:
                if partner.related_partner_id:
                    try:
                        models_rpc.execute_kw(db, uid, password, 'res.partner', 'unlink',
                                              [[partner.related_partner_id]])
                    except Exception:
                        pass

        return super().unlink()
