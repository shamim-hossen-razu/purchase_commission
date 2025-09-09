from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    set_name = fields.Char(
        string='Dozens / Pieces',
        compute='_compute_set_name',
        inverse='_inverse_set_name',
        store=True,
        readonly=False,
        precompute=True)


    @api.depends('product_uom_qty')
    def _compute_set_name(self):
        for rec in self:
            if not rec.product_uom_qty:
                rec.set_name = ''
                continue
            dozen = int(rec.product_uom_qty // 12)
            pieces = int(rec.product_uom_qty % 12)
            rec.set_name = f"{dozen} / {pieces}"


    def _inverse_set_name(self):
        for rec in self:
            if not rec.set_name:
                rec.product_uom_qty = 0
                continue
            try:
                dozen, pieces = map(int, rec.set_name.split('/'))
                rec.product_uom_qty = (dozen * 12) + pieces
            except ValueError:
                rec.product_uom_qty = 0