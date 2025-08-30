from odoo import models, fields, api


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