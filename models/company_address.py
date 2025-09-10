from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    road_no = fields.Char(string='Road No')
    house_no = fields.Char(string='House No')
    division_id = fields.Many2one(
        'bangladesh.divisions',
        string='Division'
    )
    district_id = fields.Many2one(
        'bangladesh.districts',
        string='District',
        domain="[('division_id', '=', division_id)]"
    )
    upazila_id = fields.Many2one(
        'bangladesh.upazilas',
        string='Upazila',
        domain="[('district_id', '=', district_id)]"
    )
    union_id = fields.Many2one(
        'bangladesh.unions',
        string='Union',
        domain="[('upazila_id', '=', upazila_id)]"
    )
    bd_format_address = fields.Boolean(
        string='Use Bangladesh Format Address',
        compute='_compute_bd_format_address',
        default=True
    )

    def _compute_bd_format_address(self):
        param = self.env['ir.config_parameter'].sudo().get_param('bangladesh_geocode.bd_format_address',
                                                                 default='False')
        for record in self:
            record.bd_format_address = param == 'True'

    @api.onchange('division_id')
    def _onchange_division_id(self):
        self.district_id = False
        self.upazila_id = False
        self.union_id = False

    @api.onchange('district_id')
    def _onchange_district_id(self):
        self.upazila_id = False
        self.union_id = False

    @api.onchange('upazila_id')
    def _onchange_upazila_id(self):
        self.union_id = False
