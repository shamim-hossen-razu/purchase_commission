from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    @api.constrains('name')
    def _check_unique_name(self):
        """Ensure attribute value name is unique (case-insensitive) within the same attribute locally"""
        for value in self:
            if value.name and value.attribute_id:
                existing = self.env['product.attribute.value'].search(
                    [('id', '!=', value.id),
                     ('attribute_id', '=', value.attribute_id.id),
                     ('name', '=ilike', value.name)])
                if existing:
                    raise ValidationError("An attribute value with the same name already exists for this attribute.")