from odoo import fields, models
import urllib.parse

class SendWhatsappSale(models.TransientModel):
    _name = 'send.whatsapp.sale.wizard'
    _description = 'Order / Quotation WhatsApp Message'

    order_id = fields.Many2one('sale.order', string='Order/Quotation', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    mobile = fields.Char(related='partner_id.mobile', string='Mobile', readonly=True)
    message = fields.Text(string='Message', required=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        order = self.env['sale.order'].browse(res.get('order_id'))

        if order:
            message = (
                f"Hello, {order.partner_id.name},\n"
                f"Your quotation, {order.name} is ready.\n"
                f"Total: ৳{order.amount_total},\n"
            )
            res['message'] = message

        return res


    def action_send_whatsapp_sale(self):
        """Redirect to WhatsApp Web with encoded message."""
        self.ensure_one()

        base_url = 'https://api.whatsapp.com/send'
        mobile = self.mobile or ''
        # mobile is like +880 1741-659927
        # i need to convert like 01741659927
        mobile = mobile.replace(' ', '').replace('-', '')

        encoded_msg = urllib.parse.quote(self.message)
        url = f"{base_url}?phone={mobile}&text={encoded_msg}"

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }