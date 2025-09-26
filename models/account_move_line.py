from odoo import fields, models, api
from odoo.exceptions import ValidationError

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    dozen_piece_qty = fields.Char(
        string="Dozens / Pieces",
        compute='_compute_dozen_piece_qty',
        inverse='_inverse_dozen_piece_qty',
        store=True,
        readonly=False,
        precompute=True)

    @api.depends('quantity')
    def _compute_dozen_piece_qty(self):
        for line in self:
            if not line.quantity:
                line.dozen_piece_qty = ''
                continue

            dozen = int(line.quantity // 12)
            pieces = int(line.quantity % 12)

            line.dozen_piece_qty = f"{dozen} / {pieces}"

    def _inverse_dozen_piece_qty(self):
        for line in self:
            if not line.dozen_piece_qty:
                line.quantity = 0
                continue
            try:
                dozen, pieces = map(int, line.dozen_piece_qty.strip().split('/'))
                if dozen < 0 or pieces < 0 or pieces >= 12:
                    raise ValueError
            except Exception:
                line.quantity = 0