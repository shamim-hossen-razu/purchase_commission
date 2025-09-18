from odoo import models, fields, api
from odoo.exceptions import ValidationError
import xmlrpc.client
import logging
_logger = logging.getLogger(__name__)


class AccountAccount(models.Model):
    _inherit = 'account.account'

    remote_account_id = fields.Integer(
        string="Remote Account ID",
        help="ID of the corresponding account in the remote database"
    )


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
                    return super(AccountAccount, self).create(vals_list)

                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']

                # Create XML-RPC connection
                try:
                    remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                except Exception as e:
                    _logger.error(f"Failed to connect to external server: {e}")
                    return super(AccountAccount, self).create(vals_list)
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
                            # No existing record found, create a new one in the remote DB

                            remote_record = remote_models.execute_kw(
                                db, uid, password,
                                'account.account', 'create',
                                [vals]
                            )
                            _logger.info(f"Created remote attribute with ID {remote_record} for {vals.get('name', 'Unknown')}")

                    except Exception as e:
                        _logger.error(f"Error processing remote record for {vals.get('name', 'Unknown')}: {e}")
                        # Create attributes in main database
                new_accounts = super(AccountAccount, self).create(vals_list)
                # Update relationships
                for account in new_accounts:
                    if not account.remote_account_id:
                        try:
                            # Find related record id from remote db
                            remote_record = remote_models.execute_kw(
                                db, uid, password,
                                'account.account', 'search',
                                [[['name', '=', account.name]]],
                                {'limit': 1}
                            )
                            _logger.info(
                                f"Linking local account '{account.name}' with remote ID {remote_record}")
                            if remote_record:
                                _logger.info(
                                    f"Linking local account '{account.name}' with remote ID {remote_record[0]}")
                                # Write related partner id from main database to remote record
                                remote_models.execute_kw(
                                    db, uid, password,
                                    'account.account', 'write',
                                    [remote_record, {'remote_account_id': account.id}]
                                )

                                # Write related account id from remote database to main record
                                account.write({'remote_account_id': remote_record[0]})

                        except Exception as e:
                            _logger.error(f"Error updating relationships for {account.name}: {e}")

                return new_accounts
            except Exception as e:
                _logger.error(f"Unexpected error during account creation sync: {e}")
                return super(AccountAccount, self).create(vals_list)
        else:
            _logger.info("Data sync disabled, creating accounts locally only")
            return super(AccountAccount, self).create(vals_list)
