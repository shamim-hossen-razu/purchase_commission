from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    remote_product_id = fields.Integer(string='Remote Product ID')