from odoo import models, api, fields
from odoo.tools.misc import format_amount
import re


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    order_method = fields.Selection([
        ('onsite', 'On Site'),
        ('phone_call', 'Phone Call'),
    ], string='Order Method', default='onsite')

    def _report_paginated_lines(self, first_page_count=17, other_page_count=25):
        self.ensure_one()

        lines_to_report = self._get_order_lines_to_report()
        printable_lines = lines_to_report.filtered(lambda l: not l.display_type)

        pages, total_lines = [], len(printable_lines)
        if not total_lines:
            return pages

        def _parse_set_name(val):
            if not val:
                return 0, 0
            try:
                parts = val.split('/')
                dz = int(parts[0].strip()) if parts[0].strip() else 0
                pc = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 0
                return dz, pc
            except Exception:
                return 0, 0

        def _normalize(dz, pc):
            return dz + (pc // 12), pc % 12

        def _chunk_subtotals(chunk):
            # money
            raw = sum((l.price_subtotal or 0.0) for l in chunk)
            # dz/pc from set_name
            dz_sum = pc_sum = 0
            for l in chunk:
                dz, pc = _parse_set_name(l.set_name)
                dz_sum += dz
                pc_sum += pc
            dz_sum, pc_sum = _normalize(dz_sum, pc_sum)
            return raw, format_amount(self.env, raw, self.currency_id), dz_sum, pc_sum, f"{dz_sum} / {pc_sum}"

        # first page
        start, end = 0, min(first_page_count, total_lines)
        first_chunk = printable_lines[start:end]
        if first_chunk:
            more_pages = total_lines > end
            sub_val, sub_disp, qdz, qpc, qty_disp = _chunk_subtotals(first_chunk)
            pages.append({
                'lines': first_chunk,
                'show_subtotal': more_pages,  # control ONLY the row visibility
                'subtotal': sub_val if more_pages else 0.0,  # amount shown only if more pages
                'subtotal_display': sub_disp if more_pages else "",
                'qty_dz': qdz,  # <-- ALWAYS keep qty for grand total
                'qty_pc': qpc,
                'qty_display': qty_disp,
            })
        start = end

        # subsequent pages
        while start < total_lines:
            end = min(start + other_page_count, total_lines)
            chunk = printable_lines[start:end]
            start = end

            is_last = (start >= total_lines)
            sub_val, sub_disp, qdz, qpc, qty_disp = _chunk_subtotals(chunk)
            pages.append({
                'lines': chunk,
                'show_subtotal': not is_last,  # hide row on last page
                'subtotal': sub_val if not is_last else 0.0,
                'subtotal_display': sub_disp if not is_last else "",
                'qty_dz': qdz,  # <-- KEEP qty even on last page
                'qty_pc': qpc,
                'qty_display': qty_disp,
            })

        return pages

    # bangladesh standard mobile/phone number constraint
    _re_bd_mobile = re.compile(r'^(?:\+?880|0)?1[3-9]\d{8}$')  # BD mobile: 01XXXXXXXXX with 2nd digit 3–9; allow +880 / 880 / 0 prefixes
    _re_bd_phone = re.compile(r'^(?:\+?880|0)\d{8,11}$')  # BD landline (broad): allow +880 / 880 / 0 then 8–11 digits (area codes vary)

    @staticmethod
    def _sanitize_phone(num):
        if not num:
            return ''
        num = num.strip()

        if num.startswith('+'):
            return '+' + re.sub(r'\D', '', num[1:])

        return re.sub(r'\D', '', num)

    def _is_valid_bd_number(self, number):
        n = self._sanitize_phone(number)
        if not n:
            return False

        return bool(self._re_bd_mobile.match(n) or self._re_bd_phone.match(n))

    @api.onchange('partner_id')
    def _onchange_partner_id_bd_phone_check(self):
        for order in self:
            partner = order.partner_id
            if not partner:
                continue

            cp = partner.commercial_partner_id or partner
            candidates = [partner.phone, partner.mobile, cp.phone, cp.mobile]

            is_bd = any(order._is_valid_bd_number(v) for v in candidates if v)

            if not is_bd:
                order.partner_id = False
                return {
                    'warning': {
                        'title': 'Bangladeshi Number Required',
                        'message': (
                            'The selected customer does not have a valid Bangladeshi phone/mobile.\n'
                            'Accepted examples:\n'
                            '  Mobile: +8801XXXXXXXXX, 8801XXXXXXXXX, 01XXXXXXXXX\n'
                            '  Landline: +880XXXXXXXXX (8–11 digits after prefix)\n'
                            'Please correct the number on the Contact before assigning.'
                        ),
                    }
                }