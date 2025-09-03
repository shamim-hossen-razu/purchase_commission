from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_commission_ids = fields.One2many(
        'customer.commission', 'partner_id', string='Customer Commissions')

    commission_count = fields.Integer(compute='_compute_commission_count', string='Commission Count')

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

    @api.model
    def create(self, vals_list):
        """Handle both single and multiple record creation during import"""
        # Ensure vals_list is always a list for consistency
        single_record = isinstance(vals_list, dict)
        if single_record:
            vals_list = [vals_list]

        # Process each record
        for vals in vals_list:
            if vals.get('mobile'):
                vals['mobile'] = self._format_mobile_number(vals['mobile'])

        # Call super with the processed data
        return super(ResPartner, self).create(vals_list)

    def write(self, vals):
        """Format mobile number during updates"""
        if vals.get('mobile'):
            vals['mobile'] = self._format_mobile_number(vals['mobile'])
        return super(ResPartner, self).write(vals)

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
