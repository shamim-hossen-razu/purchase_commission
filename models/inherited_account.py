from odoo import models, fields, api
from odoo.exceptions import ValidationError
from copy import deepcopy
import xmlrpc.client
import logging
_logger = logging.getLogger(__name__)


class InheritedAccount(models.Model):
    _inherit = "account.account"

    remote_account_id = fields.Integer(
        string="Remote Account ID",
        help="ID of the corresponding account in the remote database",
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
                    return super(InheritedAccount, self).create(vals_list)

                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']

                # Create XML-RPC connection
                try:
                    remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                except Exception as e:
                    _logger.error(f"Failed to connect to external server: {e}")
                    return super(InheritedAccount, self).create(vals_list)
                for vals in vals_list:
                    try:
                        # Check for existing product by name (case-insensitive) in remote DB
                        existing_records = remote_models.execute_kw(
                            db, uid, password,
                            'account.account', 'search',
                            [[['name', '=ilike', vals.get('name')]]]
                        )
                        if not existing_records:
                            _logger.info(f"Creating new remote record for attribute: {vals.get('name', 'Unknown')}")
                            copied_vals = deepcopy(vals)
                            main_company_name = self.env.user.company_id.name
                            remote_company_id = remote_models.execute_kw(
                                db, uid, password,
                                'res.company', 'search',
                                [[['name', '=', main_company_name]]],
                                {'limit': 1}
                            )
                            if vals.get('code_mapping_ids', False):
                                for item in copied_vals['code_mapping_ids']:
                                    if len(item) > 2 and 'company_id' in item[2]:
                                        item[2]['company_id'] = remote_company_id[0] if remote_company_id else False
                                    else:
                                        copied_vals['code_mapping_ids'].remove(item)
                            remote_record = remote_models.execute_kw(
                                db, uid, password,
                                'account.account', 'create',
                                [copied_vals]
                            )
                            _logger.info(f"Created remote attribute with ID {remote_record} for {vals.get('name', 'Unknown')}")

                    except Exception as e:
                        _logger.error(f"Error processing remote record for {vals.get('name', 'Unknown')}: {e}")
                        # Create attributes in main database
                new_accounts = super(InheritedAccount, self).create(vals_list)
                # Update relationships
                for account in new_accounts:
                    if not account.remote_account_id:
                        try:
                            # search remote database with account name limit 1
                            remote_account_id = remote_models.execute_kw(
                                db, uid, password,
                                'account.account', 'search',
                                [[['name', '=ilike', account.name]]],
                                {'limit': 1}
                            )
                            if remote_account_id:
                                account.remote_account_id = remote_account_id[0]
                                _logger.info(f"Linked local account {account.name} with remote ID {account.remote_account_id}")
                            else:
                                _logger.warning(f"No remote account found for {account.name}")
                            # write back local account id to remote

                            remote_models.execute_kw(
                                db, uid, password,
                                'account.account', 'write',
                                [[account.remote_account_id], {'remote_account_id': account.id}]
                            )
                        except Exception as e:
                            _logger.error(f"Error updating relationships for {account.name}: {e}")

                return new_accounts
            except Exception as e:
                _logger.error(f"Unexpected error during account creation sync: {e}")
                return super(InheritedAccount, self).create(vals_list)
        else:
            _logger.info("Data sync disabled, creating accounts locally only")
            return super(InheritedAccount, self).create(vals_list)
