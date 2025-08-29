from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_commission_ids = fields.One2many(
        'customer.commission', 'partner_id', string='Customer Commissions')
