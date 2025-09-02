from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    set_name = fields.Char(
        string='Qty (dozen/pieces)',
        compute='_compute_set_name',
        store=True,
        readonly=False,
        precompute=True)

    @api.depends('product_packaging_qty', 'product_packaging_id')
    def _compute_set_name(self):
        for rec in self:
            if not rec.product_packaging_qty:
                rec.set_name = ''
                continue

            whole_part = int(rec.product_packaging_qty)
            decimal_part = rec.product_packaging_qty - whole_part

            if decimal_part == 0:
                rec.set_name = str(whole_part)
            else:
                # Convert decimal to pieces (multiply by 12)
                pieces = int(round(decimal_part * 12))
                rec.set_name = f"{whole_part} / {pieces}"