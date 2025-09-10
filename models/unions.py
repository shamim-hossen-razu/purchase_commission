from odoo import models, fields, api


class Unions(models.Model):
    _name = 'bangladesh.unions'
    _description = 'Bangladesh Unions'

    union_id = fields.Integer(string='Union ID', required=True)
    upazila_id = fields.Many2one('bangladesh.upazilas', string='Upazila', required=True)
    name = fields.Char(string='Union Name', required=True)
    bn_name = fields.Char(string='Bangla Name')
    url = fields.Char(string='URL')

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} ({record.bn_name})" if record.bn_name else record.name
