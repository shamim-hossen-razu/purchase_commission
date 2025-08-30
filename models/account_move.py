from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'
    commission_id = fields.Many2one('customer.commission', string='Customer Commission', readonly=True, copy=False)

    def write(self, vals):
        for move in self:
            if move.move_type in ['out_invoice']:
                partner = move.partner_id
                # Find the current fiscal year
                fiscal_year = self.env['account.fiscal.year'].search([
                    ('date_from', '<=', move.invoice_date),
                    ('date_to', '>=', move.invoice_date),
                    ('company_id', '=', move.company_id.id)
                ], limit=1)

                if fiscal_year and partner:
                    # Check if commission record exists
                    commission = self.env['customer.commission'].search([
                        ('partner_id', '=', partner.id),
                        ('fiscal_year_id', '=', fiscal_year.id),
                        ('company_id', '=', move.company_id.id)
                    ], limit=1)

                    if not commission:
                        # Create a new commission record
                        new_commission_record = self.env['customer.commission'].create({
                            'partner_id': partner.id,
                            'fiscal_year_id': fiscal_year.id,
                            'company_id': move.company_id.id,
                            'state': 'draft'
                        })
                        new_commission_record.recompute_all()
                    else:
                        commission.recompute_all()
            if move.move_type == 'out_refund' and move.commission_id:
                if move.payment_state == 'paid':
                    move.commission_id.write({'state': 'paid'})
        return super(AccountMove, self).write(vals)
