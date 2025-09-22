from odoo import models, fields, api
from odoo.exceptions import ValidationError
from copy import deepcopy
import xmlrpc.client
import logging
_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    _inherit = "product.category"

    remote_category_id = fields.Integer(
        string="Remote Category ID",
        help="ID of the corresponding category in the remote database",
    )

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
            try:
                config = self._get_external_config()
                if not config or not all(config.get(k) for k in ['url', 'db', 'uid', 'password']):
                    _logger.warning("External DB config is incomplete, skipping sync")
                    return super(ProductCategory, self).create(vals_list)

                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']

                # Create XML-RPC connection
                try:
                    remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                except Exception as e:
                    _logger.error(f"Failed to connect to external server: {e}")
                    return super(ProductCategory, self).create(vals_list)
                for values in vals_list:
                    copied_values = deepcopy(values)
                    try:
                        # Check for existing product by name (case-insensitive) in remote DB
                        existing_records = remote_models.execute_kw(
                            db, uid, password,
                            'product.category', 'search',
                            [[('name', '=ilike', copied_values.get('name'))]]
                        )
                        if existing_records:
                            values['remote_category_id'] = existing_records[0]
                            _logger.info(f"Category '{values.get('name')}' already exists in remote DB with ID {existing_records[0]}")
                        else:
                            _logger.info(f"Creating new remote record for category: {values.get('name', 'Unknown')}")
                            if copied_values.get('property_account_income_categ_id', False):
                                main_db_account_id = copied_values['property_account_income_categ_id']
                                account_id = self.env['account.account'].browse(main_db_account_id)
                                if account_id and account_id.remote_account_id:
                                    copied_values['property_account_income_categ_id'] = account_id.remote_account_id
                            if copied_values.get('property_account_expense_categ_id', False):
                                main_db_account_id = values['property_account_expense_categ_id']
                                account_id = self.env['account.account'].browse(main_db_account_id)
                                if account_id and account_id.remote_account_id:
                                    copied_values['property_account_expense_categ_id'] = account_id.remote_account_id
                            if copied_values.get('parent_id', False):
                                main_db_parent_id = copied_values['parent_id']
                                parent_category = self.env['product.category'].browse(main_db_parent_id)
                                if parent_category and parent_category.remote_category_id:
                                    copied_values['parent_id'] = parent_category.remote_category_id
                                else:
                                    copied_values['parent_id'] = False
                            if copied_values.get('property_account_downpayment_categ_id', False):
                                main_db_account_id = copied_values['property_account_downpayment_categ_id']
                                account_id = self.env['account.account'].browse(main_db_account_id)
                                if account_id and account_id.remote_account_id:
                                    copied_values['property_account_downpayment_categ_id'] = account_id.remote_account_id
                            remote_id = remote_models.execute_kw(
                                db, uid, password,
                                'product.category', 'create',
                                [copied_values]
                            )
                            values['remote_category_id'] = remote_id
                            _logger.info(f"Created remote category with ID {remote_id}")
                    except Exception as e:
                        _logger.error(f"Error syncing category '{values.get('name', 'Unknown')}': {e}")
            except Exception as e:
                _logger.error(f"Unexpected error during DB sync: {e}")
        return super(ProductCategory, self).create(vals_list)
    
    def write(self, vals):
        if self._db_sync_enabled():
            try:
                config = self._get_external_config()
                if not config or not all(config.get(k) for k in ['url', 'db', 'uid', 'password']):
                    _logger.warning("External DB config is incomplete, skipping sync")
                    return super(ProductCategory, self).write(vals)

                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']

                # Create XML-RPC connection
                try:
                    remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                except Exception as e:
                    _logger.error(f"Failed to connect to external server: {e}")
                    return super(ProductCategory, self).write(vals)

                for record in self:
                    if not record.remote_category_id:
                        _logger.warning(f"Record '{record.name}' does not have a remote_category_id, skipping update")
                        continue
                    try:
                        # Update the corresponding record in the remote DB
                        copied_vals = deepcopy(vals)
                        if copied_vals.get('property_account_income_categ_id', False):
                            main_db_account_id = copied_vals['property_account_income_categ_id']
                            account_id = self.env['account.account'].browse(main_db_account_id)
                            if account_id and account_id.remote_account_id:
                                copied_vals['property_account_income_categ_id'] = account_id.remote_account_id
                        if copied_vals.get('property_account_expense_categ_id', False):
                            main_db_account_id = copied_vals['property_account_expense_categ_id']
                            account_id = self.env['account.account'].browse(main_db_account_id)
                            if account_id and account_id.remote_account_id:
                                copied_vals['property_account_expense_categ_id'] = account_id.remote_account_id
                        if copied_vals.get('parent_id', False):
                            main_db_parent_id = copied_vals['parent_id']
                            parent_category = self.env['product.category'].browse(main_db_parent_id)
                            if parent_category and parent_category.remote_category_id:
                                copied_vals['parent_id'] = parent_category.remote_category_id
                            else:
                                copied_vals['parent_id'] = False
                        if copied_vals.get('property_account_downpayment_categ_id', False):
                            main_db_account_id = copied_vals['property_account_downpayment_categ_id']
                            account_id = self.env['account.account'].browse(main_db_account_id)
                            if account_id and account_id.remote_account_id:
                                copied_vals['property_account_downpayment_categ_id'] = account_id.remote_account_id

                        remote_models.execute_kw(
                            db, uid, password,
                            'product.category', 'write',
                            [[record.remote_category_id], copied_vals]
                        )
                        _logger.info(f"Updated remote category ID {record.remote_category_id} for local category '{record.name}'")
                        return super(ProductCategory, self).write(vals)
                    except Exception as e:
                        _logger.error(f"Error updating remote category ID {record.remote_category_id}: {e}")
                        return super(ProductCategory, self).write(vals)
            except Exception as e:
                _logger.error(f"Unexpected error during DB sync: {e}")
                return super(ProductCategory, self).write(vals)
        return super(ProductCategory, self).write(vals)