from odoo import models, fields


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
    external_server_password = fields.Char(
        string='External Server Password',
        config_parameter='purchase_commission.external_server_password'
    )
    data_sync = fields.Boolean(
        string='Data Sync',
        config_parameter='purchase_commission.data_sync',
        default=False
    )
