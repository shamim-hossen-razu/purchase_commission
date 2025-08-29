from odoo import models, fields, api
from odoo.exceptions import ValidationError
from num2words import num2words
from odoo.addons.purchase_commission.utils.number_utils import number_to_words_bangladesh



class CustomerDiscountConfig(models.Model):
    _name = 'customer.commission.config'
    _description = 'Customer Commission Configuration'
    _order = 'purchase_target desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Rule Name', compute='_compute_name', store=True, readonly=False, tracking=True)
    purchase_target = fields.Float(string='Purchase Target', copy=False, tracking=True)
    commission_percent = fields.Float(string='Discount %', required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company, tracking=True)
    fiscal_year_id = fields.Many2one(
        'account.fiscal.year',
        string='Fiscal Year',
        default=lambda self: self._get_default_fiscal_year(),
        help="Leave empty to apply to current fiscal year",
        tracking=True
    )

    @api.model
    def _get_default_fiscal_year(self):
        today = fields.Date.today()
        fiscal_year = self.env['account.fiscal.year'].search([
            ('date_from', '<=', today),
            ('date_to', '>=', today)
        ], limit=1)
        return fiscal_year.id if fiscal_year else False

    @staticmethod
    def number_to_words_bangladesh(number):
        """Convert number to Bangladeshi Bengali format words"""
        return number_to_words_bangladesh(number)

    @api.depends('commission_percent', 'purchase_target')
    def _compute_name(self):
        for record in self:
            if record.commission_percent and record.purchase_target:
                target_words = record.number_to_words_bangladesh(record.purchase_target) + "++"
                record.name = f"{record.commission_percent}% on {target_words}"
            else:
                record.name = "New Commission Rule"

    @api.constrains('purchase_target', 'commission_percent')
    def _check_values(self):
        for record in self:
            if record.purchase_target <= 0:
                raise ValidationError("Sales target must be greater than zero!")
            if record.commission_percent < 1 or record.commission_percent > 100:
                raise ValidationError("Discount percentage must be between 1 and 100!")

    @api.constrains('purchase_target', 'fiscal_year_id')
    def _check_duplicate_targets(self):
        for record in self:
            domain = [
                ('purchase_target', '=', record.purchase_target),
                ('company_id', '=', record.company_id.id),
                ('active', '=', True),
                ('id', '!=', record.id)
            ]

            # Add fiscal year condition
            if record.fiscal_year_id:
                domain.append(('fiscal_year_id', '=', record.fiscal_year_id.id))
            else:
                domain.append(('fiscal_year_id', '=', False))

            duplicate = self.search(domain)
            if duplicate:
                fiscal_year_name = record.fiscal_year_id.name or "current fiscal year"
                raise ValidationError(f"A commission rule with purchase target {record.purchase_target} already exists for {fiscal_year_name}!")