from odoo import models, api, fields
from odoo.tools.misc import format_amount
import re
import xmlrpc.client
import logging
_logger = logging.getLogger(__name__)
from copy import deepcopy


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    order_method = fields.Selection([
        ('onsite', 'On Site'),
        ('phone_call', 'Phone Call'),
    ], string='Order Method', default='onsite')
    remote_sale_order_id = fields.Integer(string='Remote Sale Order ID')

    def _report_paginated_lines(self, first_page_count=22, other_page_count=30):
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

    def _get_external_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'url': ICP.get_param('purchase_commission.external_server_url', ''),
            'db': ICP.get_param('purchase_commission.external_server_db', ''),
            'uid': int(ICP.get_param('purchase_commission.external_server_uid', 0)),
            'password': ICP.get_param('purchase_commission.external_server_password', '')
        }

    def _db_sync_enabled(self):
        # if data_sync is true return true else false
        ICP = self.env['ir.config_parameter'].sudo()
        return ICP.get_param('purchase_commission.data_sync', 'False') == 'True'

    @api.model
    def create(self, vals_list):
        """Handle both single and multiple record creation during import"""
        # Ensure vals_list is always a list for consistency
        _logger.info(f'Creating partners with vals: {vals_list}')
        single_record = isinstance(vals_list, dict)
        if single_record:
            vals_list = [vals_list]

        if self._db_sync_enabled():
            _logger.warning('Data sync is enabled, attempting to sync partners to external DB')
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            try:
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                # create record in remote database
                for vals in vals_list:
                    copied_vals = deepcopy(vals)
                    # update vals to match remote db
                    if copied_vals.get('partner_id', False):
                        main_db_partner = self.env['res.partner'].browse(vals['partner_id'])
                        copied_vals['partner_id'] = main_db_partner.related_partner_id
                        copied_vals['partner_invoice_id'] = main_db_partner.related_partner_id
                    # Handle case when sale order line is added at the time of sale order creation
                    if copied_vals.get('order_line', False):
                        for line in copied_vals['order_line']:
                            # product template is to replaced by remote product tempate
                            line[2]['product_template_id'] = self.env['product.template'].browse(
                                line[2]['product_template_id']).related_product_id
                            # product is to be replaced by remote product
                            if line[2].get('product_id', False):
                                line[2]["product_id"] = self.env['product.product'].search([('id', '=', line[2]['product_id'])]).remote_product_id
                            # Handle case when product packaging is set
                            if line[2].get('product_packaging_id', False):
                                main_db_packaging_id = self.env['product.packaging'].browse(
                                    line[2]['product_packaging_id'])
                                remote_product_id = main_db_packaging_id.product_id.remote_product_id
                                qty = main_db_packaging_id.qty
                                remote_packaging_id = remote_models.execute_kw(db, uid, password, 'product.packaging',
                                                                               'search', [[['product_id', '=',
                                                                                            remote_product_id],
                                                                                           ['qty', '=', qty]]],
                                                                               {'limit': 1})
                                line[2]['product_packaging_id'] = remote_packaging_id[
                                    0] if remote_packaging_id else False
                    # TODO: need to handle this case of pricelist
                    if copied_vals.get('pricelist_id', False):
                        copied_vals.pop('pricelist_id')
                    # create record in remote database with above prepared copied_vals
                    remote_id = remote_models.execute_kw(db, uid, password, 'sale.order', 'create', [copied_vals])

                    # list sale order line ids from remote db for setting remote_sale_order_line_id in main db
                    remote_sale_order_line_ids = remote_models.execute_kw(db, uid, password, 'sale.order.line',
                                                                          'search', [[['order_id', '=', remote_id]]])
                    # in main db we have to set remote_sale_order_line_id for each sale order line
                    for rsol, msol in zip(remote_sale_order_line_ids, vals['order_line']):
                        msol[2]['remote_sale_order_line_id'] = rsol
                    # set remote_sale_order_id in main db vals
                    vals['remote_sale_order_id'] = remote_id
                # create record in main db
                new_sale_orders = super().create(vals_list)
                # after creating record in main db search the record in remote db with partner_id and date_order and set remote_sale_order_id in remote db
                for sale_order in new_sale_orders:
                    main_db_partner_id = sale_order.partner_id
                    remote_db_partner_id = main_db_partner_id.related_partner_id
                    quotation_date = sale_order.date_order
                    remote_sale_order_id = remote_models.execute_kw(db, uid, password, 'sale.order', 'search', [[['partner_id', '=', remote_db_partner_id], ['date_order', '=', quotation_date]]], {'limit': 1})
                    remote_models.execute_kw(db, uid, password, 'sale.order', 'write', [[remote_sale_order_id[0]], {'remote_sale_order_id': sale_order.id}])
                    return new_sale_orders
            except Exception as e:
                _logger.error(f'Failed to connect to external server: {e}')
                return super().create(vals_list)
        else:
            return super().create(vals_list)

    def write(self, vals):
        if self._db_sync_enabled():
            _logger.warning('Data sync is enabled, attempting to sync partners to external DB')
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            try:
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                for order in self:
                    if not order.remote_sale_order_id:
                        _logger.info(f'Skipping sync for Sale Order {order.name} as it has no remote ID')
                        continue
                    update_vals = deepcopy(vals)
                    # update vals to match remote db
                    if update_vals.get('partner_id', False):
                        main_db_partner = self.env['res.partner'].browse(vals['partner_id'])
                        update_vals['partner_id'] = main_db_partner.related_partner_id
                        update_vals['partner_invoice_id'] = main_db_partner.related_partner_id
                    # Handle case when sale order line is added/updated at the time of sale order updation
                    if update_vals.get('order_line', False):
                        for line in update_vals['order_line']:
                            # Handle case when adding new sale order line
                            if line[0] == 0:
                                if line[2].get('product_template_id', False):
                                    line[2]['product_template_id'] = self.env['product.template'].browse(
                                        line[2]['product_template_id']).related_product_id
                                if line[2].get('product_id', False):
                                    line[2]["product_id"] = self.env['product.product'].search(
                                        [('id', '=', line[2]['product_id'])]).remote_product_id
                                if line[2].get('product_packaging_id', False):
                                    main_db_packaging_id = self.env['product.packaging'].browse(
                                        line[2]['product_packaging_id'])
                                    remote_product_id = main_db_packaging_id.product_id.remote_product_id
                                    qty = main_db_packaging_id.qty
                                    remote_packaging_id = remote_models.execute_kw(db, uid, password,'product.packaging', 'search', [[['product_id', '=', remote_product_id], ['qty', '=', qty]]],
                                                                                   {'limit': 1})
                                    line[2]['product_packaging_id'] = remote_packaging_id[0] if remote_packaging_id else False
                            # Handle case when updating existing sale order line
                            if line[0] == 1:
                                main_db_sale_order_line_id = line[1]
                                main_db_sale_order_line = self.env['sale.order.line'].browse(main_db_sale_order_line_id)
                                remote_db_sale_order_line_id = main_db_sale_order_line.remote_sale_order_line_id
                                line[1] = remote_db_sale_order_line_id if remote_db_sale_order_line_id else False
                    # TODO : need to handle this case of pricelist
                    if update_vals.get('pricelist_id', False):
                        update_vals.pop('pricelist_id')
                    # with updated vals write to remote db
                    remote_models.execute_kw(db, uid, password, 'sale.order', 'write', [[order.remote_sale_order_id], update_vals])
                    # in main db we have to set remote_sale_order_line_id for each sale order line
                    main_sol_ids = [sale_order_line.remote_sale_order_line_id for sale_order_line in order.order_line]
                    remote_sol_ids = remote_models.execute_kw(db, uid, password, 'sale.order.line', 'search', [[['order_id', '=', order.remote_sale_order_id]]])
                    remote_sol_ids = list(set(remote_sol_ids) - set(main_sol_ids))
                    if vals.get('order_line'):
                        for i, rid in enumerate(remote_sol_ids):
                            if i < len(vals['order_line']) and vals['order_line'][i][2]:
                                vals['order_line'][i][2]['remote_sale_order_line_id'] = rid
                    return super(SaleOrder, self).write(vals)
            except Exception as e:
                _logger.error(f'Failed to connect to external server: {e}')
        else:
            _logger.info('Data sync is disabled, skipping external DB update')
            return super(SaleOrder, self).write(vals)

    def unlink(self):
        if self._db_sync_enabled():
            _logger.warning('Data sync is enabled, attempting to delete partners from external DB')
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            try:
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                for order in self:
                    if not order.remote_sale_order_id:
                        _logger.info(f'Skipping sync for Sale Order {order.name} as it has no remote ID')
                        continue
                    remote_models.execute_kw(db, uid, password, 'sale.order', 'unlink', [[order.remote_sale_order_id]])
                return super(SaleOrder, self).unlink()
            except Exception as e:
                _logger.error(f'Failed to connect to external server: {e}')
                return super(SaleOrder, self).unlink()
        else:
            _logger.info('Data sync is disabled, skipping external DB deletion')
            return super(SaleOrder, self).unlink()




