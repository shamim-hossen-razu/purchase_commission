from odoo import models, fields
import xmlrpc.client


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    external_server_url = fields.Char(
        string='External Server URL',
        config_parameter='purchase_commission.external_server_url'
    )
    external_server_db = fields.Char(
        string='External Server Database',
        config_parameter='purchase_commission.external_server_db'
    )
    external_server_uid = fields.Integer(
        string='External Server User ID',
        config_parameter='purchase_commission.external_server_uid'
    )
    external_server_user_name = fields.Char(
        string='External Server User Name',
        config_parameter='purchase_commission.external_server_user_name'
    )
    external_server_password = fields.Char(
        string='External Server Password',
        config_parameter='purchase_commission.external_server_password'
    )
    data_sync = fields.Boolean(
        string='Data Sync',
        config_parameter='purchase_commission.data_sync',
        default=False
    )

    bd_format_address = fields.Boolean(
        string='BD Format Address',
        config_parameter='purchase_commission.bd_format_address',
        default=False
    )

    transaction_decrease_percentage = fields.Float(
        string='Transaction Decrease Percentage',
        config_parameter='purchase_commission.trxn_decrease_percentage',
        default=0.0
    )

    def _get_external_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'url': ICP.get_param('purchase_commission.external_server_url', ''),
            'db': ICP.get_param('purchase_commission.external_server_db', ''),
            'uid': int(ICP.get_param('purchase_commission.external_server_uid', 0)),
            'password': ICP.get_param('purchase_commission.external_server_password', ''),
            'user_name': ICP.get_param('purchase_commission.external_server_user_name', '')
        }

    def _db_sync_enabled(self):
        # if data_sync is true return true else false
        ICP = self.env['ir.config_parameter'].sudo()
        return ICP.get_param('purchase_commission.data_sync', 'False') == 'True'

    def test_connection(self):
        config = self._get_external_config()
        try:
            common = xmlrpc.client.ServerProxy(f"{config['url']}/xmlrpc/2/common")
            uid = common.authenticate(config['db'], config['user_name'], config['password'], {})
            if uid:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Successful',
                        'message': 'Successfully connected to the external server.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Failed',
                        'message': 'Failed to authenticate with the external server. Please check your credentials.',
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Error',
                    'message': f'An error occurred while trying to connect: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
