from odoo import models, fields, api


class Upazilas(models.Model):
    _name = 'bangladesh.upazilas'
    _description = 'Bangladesh Upazilas'

    upazila_id = fields.Integer(string='Upazila ID', required=True)
    district_id = fields.Many2one('bangladesh.districts', string='District', required=True)
    name = fields.Char(string='Upazila Name', required=True)
    bn_name = fields.Char(string='Bangla Name')
    url = fields.Char(string='URL')
    union_ids = fields.One2many('bangladesh.unions', 'upazila_id', string='Unions')

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} ({record.bn_name})" if record.bn_name else record.name
