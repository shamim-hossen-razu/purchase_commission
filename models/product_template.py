from odoo import models, fields, api
from odoo.exceptions import ValidationError
import xmlrpc.client
from copy import deepcopy
import logging
_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    related_product_id = fields.Integer(
        string="Remote Product ID",
        help="Stores the product ID of this product in the external database.")

    @api.constrains('name')
    def _check_unique_name(self):
        """Ensure product name is unique (case-insensitive) locally"""
        for product in self:
            if product.name:
                existing = self.env['product.template'].search(
                    [('id', '!=', product.id), ('name', '=ilike', product.name)])
                if existing:
                    raise ValidationError("A product with the same name already exists.")

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

    @api.model
    def create(self, vals_list):
        """Handle both single and multiple record creation during import"""
        # Ensure vals_list is always a list for consistency
        single_record = isinstance(vals_list, dict)
        if single_record:
            vals_list = [vals_list]
        if self._db_sync_enabled():
            _logger.info("Data sync is enabled. Proceeding with external DB operations.")
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            try:
                _logger.info(f"Connecting to external server at {url}")
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
            except Exception as e:
                raise ValidationError(f"Failed to connect to external server: {e}")

            # Process each record
            for vals in vals_list:
                # Check for existing product by name (case-insensitive) in remote DB
                try:
                    vals.pop('combo_ids', None)
                    existing_records = remote_models.execute_kw(db, uid, password, 'product.template', 'search',
                                                                [[['name', '=ilike', vals.get('name')]]])
                    if not existing_records:
                        # No existing record found, create a new one in the remote DB
                        if vals.get('seller_ids', False):
                            copied_vals = deepcopy(vals)
                            for i, seller_data in enumerate(copied_vals['seller_ids']):
                                if len(seller_data) > 2 and isinstance(seller_data[2], dict):
                                    partner_id = seller_data[2].get('partner_id', False)
                                    if partner_id:
                                        partner = self.env['res.partner'].browse(partner_id)
                                        if partner.related_partner_id:
                                            copied_vals['seller_ids'][i][2]['partner_id'] = partner.related_partner_id
                            remote_models.execute_kw(db, uid, password, 'product.template', 'create', [copied_vals])
                        else:
                            remote_models.execute_kw(db, uid, password, 'product.template', 'create', [vals])
                except Exception as e:
                    raise ValidationError(f"Error during creating product in remote database: {e}")
            # Create the records in main database
            new_products = super(ProductTemplate, self).create(vals_list)
            for product in new_products:
                if not product.related_product_id:
                    # find related record id from remote db
                    remote_record = remote_models.execute_kw(db, uid, password, 'product.template', 'search',
                                                             [[['name', '=', product.name]]], {'limit': 1})

                    # write related partner id from main  database to remote record
                    remote_models.execute_kw(db, uid, password, 'product.template', 'write',
                                             [remote_record, {'related_product_id': product.id}])

                    # write related partner id from remote database to main record
                    product.write({'related_product_id': remote_record[0] if remote_record else False})
            return new_products
        else:
            _logger.info("Data sync not enabled; skipping external DB operation.")
            return super(ProductTemplate, self).create(vals_list)

    def write(self, vals):
        vals.pop('combo_ids', None)
        for rec in self:
            if rec._db_sync_enabled() and rec.related_product_id:
                config = rec._get_external_config()
                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']
                try:
                    _logger.info(f"Connecting to external server at {url} for write operation")
                    models_rpc = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                except Exception as e:
                    raise ValidationError(f"Failed to connect to external server: {e}")
                # handle case when vendors are added in product template
                if vals.get('seller_ids', False):
                    copied_vals = deepcopy(vals)
                    for i, seller_data in enumerate(copied_vals['seller_ids']):
                        _logger.info(f"Processing seller_data: {seller_data}")
                        # Handle case when vendors are being added newly
                        if len(seller_data) > 2 and seller_data[0] == 0 and isinstance(seller_data[2], dict):
                            partner_id = seller_data[2].get('partner_id', False)
                            if partner_id:
                                partner = self.env['res.partner'].browse(partner_id)
                                if partner.related_partner_id:
                                    copied_vals['seller_ids'][i][2]['partner_id'] = partner.related_partner_id
                                    models_rpc.execute_kw(db, uid, password, 'product.template',
                                                                              'write',
                                                                              [[rec.related_product_id], copied_vals])
                        # Handle case when vendor line is being edited
                        elif len(seller_data) > 2 and seller_data[0] == 1 and isinstance(seller_data[2], dict):
                            main_db_supplier_info_id = seller_data[1]
                            main_supplier_info = self.env['product.supplierinfo'].browse(main_db_supplier_info_id)
                            main_supplier_tmpl_id = main_supplier_info.product_tmpl_id.id
                            main_supplier_related_partner_id = main_supplier_info.partner_id.id
                            if main_supplier_tmpl_id and main_supplier_related_partner_id:
                                related_product_id = self.env['product.template'].browse(main_supplier_tmpl_id).related_product_id
                                related_partner_id = self.env['res.partner'].browse(main_supplier_related_partner_id).related_partner_id
                                if related_product_id and related_partner_id:
                                    remote_supplier_info_ids = models_rpc.execute_kw(
                                        db, uid, password, 'product.supplierinfo', 'search',
                                        [[['product_tmpl_id', '=', related_product_id],
                                          ['partner_id', '=', related_partner_id]]]
                                    )
                                    if remote_supplier_info_ids:
                                        copied_vals['seller_ids'][i][1] = remote_supplier_info_ids[0]
                                        models_rpc.execute_kw(db, uid, password, 'product.template', 'write',
                                                              [[rec.related_product_id], copied_vals])
                                    else:
                                        raise ValidationError(f"Related supplier info not found in remote DB for product_tmpl_id {related_product_id} and partner_id {related_partner_id}")
                                else:
                                    raise ValidationError("Related product or partner ID not found for supplier info update.")
                        else:
                            copied_vals.pop('seller_ids', None)
                            models_rpc.execute_kw(db, uid, password, 'product.template', 'write',
                                                  [[rec.related_product_id], copied_vals])

                    return super(ProductTemplate, self).write(vals)
                else:
                    # remove combo_ids from vals if combo_ids any tuple has CLEAR command at tuple[0]
                    models_rpc.execute_kw(db, uid, password, 'product.template', 'write',
                                          [[rec.related_product_id], vals])
                    return super(ProductTemplate, self).write(vals)
            else:
                _logger.info(vals)
                _logger.info("Data sync not enabled or no related_product_id; skipping external DB operation.")
                return super(ProductTemplate, self).write(vals)

    def unlink(self):
        """Override unlink to delete the product.template in external DB as well"""
        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            models_rpc = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
            for record in self:

                if record.related_product_id:
                    try:
                        models_rpc.execute_kw(db, uid, password, 'product.template', 'unlink',
                                              [[record.related_product_id]])
                    except Exception as e:
                        pass
        return super().unlink()
