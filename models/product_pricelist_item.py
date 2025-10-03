from odoo import api, fields, models


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    remote_pricelist_item_id = fields.Integer(string="Remote Pricelist Item ID")