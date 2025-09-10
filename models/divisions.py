from odoo import models, fields, api


class Divisions(models.Model):
    _name = 'bangladesh.divisions'
    _description = 'Bangladesh Divisions'

    name = fields.Char(string='Division Name', required=True)
    bn_name = fields.Char(string='Bangla Name')
    url = fields.Char(string='URL')
    division_id = fields.Integer(string='Division ID', required=True)
    district_ids = fields.One2many('bangladesh.districts', 'division_id', string='Districts')

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} ({record.bn_name})" if record.bn_name else record.name
