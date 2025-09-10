from odoo import models, fields, api


class Districts(models.Model):
    _name = 'bangladesh.districts'
    _description = 'Bangladesh Districts'

    district_id = fields.Integer(string='District ID', required=True)
    division_id = fields.Many2one('bangladesh.divisions', string='Division')
    name = fields.Char(string='District Name', required=True)
    bn_name = fields.Char(string='Bangla Name')
    lat = fields.Float(string='Latitude')
    lon = fields.Float(string='Longitude')
    url = fields.Char(string='URL')
    upazila_ids = fields.One2many('bangladesh.upazilas', 'district_id', string='Upazilas')

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} ({record.bn_name})" if record.bn_name else record.name
