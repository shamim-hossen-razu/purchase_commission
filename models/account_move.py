from odoo import api, fields, models
from odoo.tools.misc import format_amount


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
        return super(AccountMove, self).write(vals)

    def _report_paginated_lines(self, first_page_count=22, other_page_count=30):

        self.ensure_one()

        all_lines = self.invoice_line_ids.sorted(
            key=lambda l: (-l.sequence, l.date, l.move_name, -l.id), reverse=True
        )

        def _is_product_line(l):
            return (l.display_type in (False, 'product'))

        lines = all_lines.filtered(_is_product_line)

        pages, total = [], len(lines)
        if not total:
            return pages

        def _parse_dozen_piece(val):
            if not val:
                return 0, 0
            try:
                parts = val.split('/')
                dz = int(parts[0].strip()) if parts and parts[0].strip() else 0
                pc = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 0
                return dz, pc
            except Exception:
                return 0, 0

        def _normalize(dz, pc):
            return dz + (pc // 12), pc % 12

        def _chunk_totals(chunk):
            raw = sum((l.price_subtotal or 0.0) for l in chunk)
            dz_sum, pc_sum = 0, 0
            for l in chunk:
                dz, pc = _parse_dozen_piece(getattr(l, 'dozen_piece_qty', None))
                dz_sum += dz
                pc_sum += pc
            dz_sum, pc_sum = _normalize(dz_sum, pc_sum)
            return raw, format_amount(self.env, raw, self.currency_id), dz_sum, pc_sum, f"{dz_sum} / {pc_sum}"

        # First page
        start, end = 0, min(first_page_count, total)
        first_chunk = lines[start:end]
        if first_chunk:
            more_pages = total > end
            sub_val, sub_disp, qdz, qpc, qty_disp = _chunk_totals(first_chunk)
            pages.append({
                'lines': first_chunk,
                'show_subtotal': more_pages,
                'subtotal': sub_val if more_pages else 0.0,
                'subtotal_display': sub_disp if more_pages else "",
                'qty_dz': qdz,
                'qty_pc': qpc,
                'qty_display': qty_disp,
            })
        start = end

        # Next pages
        while start < total:
            end = min(start + other_page_count, total)
            chunk = lines[start:end]
            start = end
            is_last = (start >= total)
            sub_val, sub_disp, qdz, qpc, qty_disp = _chunk_totals(chunk)
            pages.append({
                'lines': chunk,
                'show_subtotal': not is_last,
                'subtotal': sub_val if not is_last else 0.0,
                'subtotal_display': sub_disp if not is_last else "",
                'qty_dz': qdz,
                'qty_pc': qpc,
                'qty_display': qty_disp,
            })

        return pages
