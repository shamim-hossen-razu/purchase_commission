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
                        copied_vals = deepcopy(vals)
                        if copied_vals.get('attribute_line_ids', False):
                            for attr_line in copied_vals['attribute_line_ids']:
                                if len(attr_line) > 2 and isinstance(attr_line[2], dict):
                                    # Process attribute_id
                                    attribute_id = attr_line[2].get('attribute_id', False)
                                    if attribute_id:
                                        attribute = self.env['product.attribute'].browse(attribute_id)
                                        remote_attribute_id = remote_models.execute_kw(
                                            db, uid, password, 'product.attribute', 'search',
                                            [[['name', '=', attribute.name]]], {'limit': 1}
                                        )
                                        if remote_attribute_id:
                                            attr_line[2]['attribute_id'] = remote_attribute_id[0]
                                        else:
                                            new_remote_attribute_id = remote_models.execute_kw(
                                                db, uid, password, 'product.attribute', 'create',
                                                [{'name': attribute.name}]
                                            )
                                            attr_line[2]['attribute_id'] = new_remote_attribute_id

                                    # Process value_ids
                                    if 'value_ids' in attr_line[2]:
                                        for value in attr_line[2]['value_ids']:
                                            if len(value) > 1:
                                                main_value_id = value[1]
                                                main_value = self.env['product.attribute.value'].browse(main_value_id)
                                                remote_value_id = remote_models.execute_kw(
                                                    db, uid, password, 'product.attribute.value', 'search',
                                                    [[['name', '=', main_value.name]]], {'limit': 1}
                                                )
                                                if remote_value_id:
                                                    value[1] = remote_value_id[0]
                                                else:
                                                    new_remote_value_id = remote_models.execute_kw(
                                                        db, uid, password, 'product.attribute.value', 'create',
                                                        [{'name': main_value.name}]
                                                    )
                                                    value[1] = new_remote_value_id

                        if copied_vals.get('seller_ids', False):
                            for i, seller_data in enumerate(copied_vals['seller_ids']):
                                if len(seller_data) > 2 and isinstance(seller_data[2], dict):
                                    partner_id = seller_data[2].get('partner_id', False)
                                    if partner_id:
                                        partner = self.env['res.partner'].browse(partner_id)
                                        if partner.related_partner_id:
                                            copied_vals['seller_ids'][i][2]['partner_id'] = partner.related_partner_id
                        # Handle case when income/expense account is set
                        if copied_vals.get('property_account_income_id', False):
                            account_id = copied_vals['property_account_income_id']
                            account = self.env['account.account'].browse(account_id)
                            if account.remote_account_id:
                                copied_vals['property_account_income_id'] = account.remote_account_id
                        if copied_vals.get('property_account_expense_id', False):
                            account_id = copied_vals['property_account_expense_id']
                            account = self.env['account.account'].browse(account_id)
                            if account.remote_account_id:
                                copied_vals['property_account_expense_id'] = account.remote_account_id
                        if copied_vals.get('categ_id', False):
                            category_id = copied_vals['categ_id']
                            category = self.env['product.category'].browse(category_id)
                            if category.remote_category_id:
                                copied_vals['categ_id'] = category.remote_category_id
                        remote_models.execute_kw(db, uid, password, 'product.template', 'create', [copied_vals])
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

                    if product.product_variant_ids:
                        for variant in product.product_variant_ids:
                            if not variant.remote_product_id:
                                remote_attr_id = variant.attribue_id.remote_attribute_id
                                attr_val_name = self.env['product.attribute.value'].browse(variant.product_attribute_value_id).name
                                remote_attr_val_id = remote_models.execute_kw(db, uid, password, 'product.attribute.value', 'search',
                                                         [[['name', '=', attr_val_name],
                                                           ['attribute_id', '=', remote_attr_id]]], {'limit': 1})
                                remote_variant = remote_models.execute_kw(db, uid, password, 'product.product', 'search',
                                            [[['product_tmpl_id', '=', product.related_product_id],
                                              ['attribute_id', '=', remote_attr_id],
                                              ['product_attribute_value_id', '=', remote_attr_val_id]
                                              ]], {'limit': 1})
                                variant.write({'remote_product_id': remote_variant if remote_variant else False})
                                remote_models.execute_kw(db, uid, password, 'product.product', 'write',
                                                [remote_variant, {'related_product_id': variant.id}])

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
                copied_vals = deepcopy(vals)
                if copied_vals.get('seller_ids', False):
                    for i, seller_data in enumerate(copied_vals['seller_ids']):
                        _logger.info(f"Processing seller_data: {seller_data}")
                        # Handle case when vendors are being added newly
                        if len(seller_data) > 2 and seller_data[0] == 0 and isinstance(seller_data[2], dict):
                            partner_id = seller_data[2].get('partner_id', False)
                            if partner_id:
                                partner = self.env['res.partner'].browse(partner_id)
                                if partner.related_partner_id:
                                    copied_vals['seller_ids'][i][2]['partner_id'] = partner.related_partner_id
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
                                    else:
                                        raise ValidationError(f"Related supplier info not found in remote DB for product_tmpl_id {related_product_id} and partner_id {related_partner_id}")
                                else:
                                    raise ValidationError("Related product or partner ID not found for supplier info update.")
                        else:
                            copied_vals.pop('seller_ids', None)

                if copied_vals.get('attribute_line_ids', False):
                    for i, attr_data in enumerate(copied_vals['attribute_line_ids']):
                        # Handle case when attribute lines are being added newly
                        if len(attr_data) > 2 and attr_data[0] == 0 and isinstance(attr_data[2], dict):
                            for value_id in attr_data[2].get('value_ids', []):
                                main_db_value_id = value_id[1] if len(value_id) > 1 else None
                                if main_db_value_id:
                                    main_value = self.env['product.attribute.value'].browse(main_db_value_id)
                                    # search on remote db by main_value.name in 'product.attribute.value' model with limit = 1
                                    remote_value_id = models_rpc.execute_kw(
                                        db, uid, password, 'product.attribute.value', 'search',
                                        [[['name', '=', main_value.name]]], {'limit': 1}
                                    )
                                    value_id[1] = remote_value_id[0] if remote_value_id else None
                            # map attribute_id with remote attribute_id
                            attribute_id = attr_data[2].get('attribute_id', False)
                            if attribute_id:
                                attribute = self.env['product.attribute'].browse(attribute_id)
                                if attribute.remote_attribute_id:
                                    copied_vals['attribute_line_ids'][i][2]['attribute_id'] = attribute.remote_attribute_id
                        if len(attr_data) > 2 and attr_data[0] == 1 and isinstance(attr_data[2], dict):
                            for value_id in attr_data[2].get('value_ids', []):
                                main_db_value_id = value_id[1] if len(value_id) > 1 else None
                                if main_db_value_id:
                                    main_value = self.env['product.attribute.value'].browse(main_db_value_id)
                                    # search on remote db by main_value.name in 'product.attribute.value' model with limit = 1
                                    remote_value_id = models_rpc.execute_kw(
                                        db, uid, password, 'product.attribute.value', 'search',
                                        [[['name', '=', main_value.name]]], {'limit': 1}
                                    )
                                    value_id[1] = remote_value_id[0] if remote_value_id else None

                    models_rpc.execute_kw(db, uid, password, 'product.template', 'write',
                                          [[rec.related_product_id], copied_vals])
                    return super(ProductTemplate, self).write(vals)

                if copied_vals.get('property_account_income_id', False):
                    account_id = copied_vals['property_account_income_id']
                    account = self.env['account.account'].browse(account_id)
                    if account.remote_account_id:
                        copied_vals['property_account_income_id'] = account.remote_account_id
                if copied_vals.get('property_account_expense_id', False):
                    account_id = copied_vals['property_account_expense_id']
                    account = self.env['account.account'].browse(account_id)
                    if account.remote_account_id:
                        copied_vals['property_account_expense_id'] = account.remote_account_id
                if copied_vals.get('categ_id', False):
                    category_id = copied_vals['categ_id']
                    category = self.env['product.category'].browse(category_id)
                    if category.remote_category_id:
                        copied_vals['categ_id'] = category.remote_category_id

                models_rpc.execute_kw(db, uid, password, 'product.template', 'write',
                                      [[rec.related_product_id], copied_vals])
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
