from odoo import api, fields, models
import xmlrpc.client
import logging
_logger = logging.getLogger(__name__)



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
    remote_sale_order_line_id = fields.Integer(string='Remote Sale Order Line ID')

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


    def unlink(self):
        if self._db_sync_enabled():
            config = self._get_external_config()
            models = xmlrpc.client.ServerProxy(f"{config['url']}/xmlrpc/2/object")
            for rec in self:
                if rec.remote_sale_order_line_id:
                    try:
                        models.execute_kw(
                            config['db'], config['uid'], config['password'],
                            'sale.order.line', 'unlink',
                            [[rec.remote_sale_order_line_id]]
                        )
                        _logger.info('Successfully deleted remote sale order line with ID %s', rec.remote_sale_order_line_id)
                    except Exception as e:
                        # Log the exception or handle it as needed
                        _logger.error(f"Failed to delete remote sale order line {rec.remote_sale_order_line_id}: {e}")
        return super(SaleOrderLine, self).unlink()