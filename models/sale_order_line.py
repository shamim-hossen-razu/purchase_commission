from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    set_name = fields.Char(
        string='QTY',
        compute='_compute_set_name',
        inverse='_inverse_set_name',
        default='0 / 1',
        store=True,
        readonly=False,
        precompute=True)

    @api.onchange('product_packaging_id')
    def _onchange_product_packaging_id(self):
        for rec in self:
            if rec.product_packaging_id and rec.product_packaging_id.qty:
                rec.product_uom_qty = rec.product_packaging_id.qty

    @api.depends('product_uom_qty')
    def _compute_set_name(self):
        for rec in self:
            if not rec.product_uom_qty:
                rec.set_name = ''
                continue
            if rec.product_packaging_id:
                packaging_qty = rec.product_packaging_id.qty
                packs = int(rec.product_uom_qty // packaging_qty)
                pieces = int(rec.product_uom_qty % packaging_qty)
                rec.set_name = f"{packs} / {pieces}"
                continue

    def _inverse_set_name(self):
        for rec in self:
            if not rec.set_name:
                rec.product_uom_qty = 0
                continue
            try:
                if rec.product_packaging_id.qty:
                    base_qty = rec.product_packaging_id.qty
                    packs, pieces = map(int, rec.set_name.split('/'))
                    if pieces >= base_qty:
                        quotient = pieces // base_qty
                        reminder = pieces % base_qty
                        rec.product_uom_qty = (packs * base_qty) + quotient + reminder
                        rec.set_name = f"{int(packs + quotient)} / {int(reminder)}"
                    rec.product_uom_qty = (packs * base_qty) + pieces
            except ValueError:
                rec.product_uom_qty = 0