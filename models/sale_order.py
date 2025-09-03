from odoo import models
from odoo.tools.misc import format_amount

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _report_paginated_lines(self, first_page_count=17, other_page_count=25):
        self.ensure_one()

        lines_to_report = self._get_order_lines_to_report()
        printable_lines = lines_to_report.filtered(lambda l: not l.display_type)

        pages = []
        total_lines = len(printable_lines)
        if not total_lines:
            return pages

        def _chunk_subtotal(chunk):
            raw = sum(l.price_subtotal for l in chunk)

            return raw, format_amount(self.env, raw, self.currency_id)

        start = 0
        end = min(first_page_count, total_lines)
        first_chunk = printable_lines[start:end]
        if first_chunk:
            more_pages = total_lines > end
            sub_val, sub_disp = _chunk_subtotal(first_chunk) if more_pages else (0.0, "")
            pages.append({
                'lines': first_chunk,
                'show_subtotal': more_pages,
                'subtotal': sub_val,
                'subtotal_display': sub_disp,
            })
        start = end

        while start < total_lines:
            end = min(start + other_page_count, total_lines)
            chunk = printable_lines[start:end]
            start = end

            is_last_page = (start >= total_lines)
            if not is_last_page:
                sub_val, sub_disp = _chunk_subtotal(chunk)
                show_subtotal = True
            else:
                sub_val, sub_disp = (0.0, "")
                show_subtotal = False

            pages.append({
                'lines': chunk,
                'show_subtotal': show_subtotal,
                'subtotal': sub_val,
                'subtotal_display': sub_disp,
            })

        return pages