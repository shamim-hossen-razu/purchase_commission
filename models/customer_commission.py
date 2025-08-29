from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CustomerCommission(models.Model):
    _name = 'customer.commission'
    _description = 'Customer Commission'
    _order = 'fiscal_year_id desc'

    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    commission_rule_id = fields.Many2one(
        'customer.commission.config', string='Commission Rule')
    commission_amount = fields.Float(string='Commission Amount', compute='_compute_commission_amount', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid')
    ], string='Status', default='draft', required=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company)
    fiscal_year_id = fields.Many2one(
        'account.fiscal.year',
        string='Fiscal Year',
        help="Fiscal year for which this commission is recorded"
    )
    total_purchase = fields.Float(string='Total Purchases This Year', compute='_compute_total_purchase')
    total_invoiced = fields.Float(string='Total Invoiced This Year', compute='_compute_total_invoiced')
    total_paid = fields.Float(string='Total Paid This Year', compute='_compute_total_paid')
    total_due = fields.Float(string='Total Due This Year', compute='_compute_total_due')

    @api.depends('commission_rule_id', 'total_purchase', 'total_invoiced', 'total_paid', 'total_due')
    def _compute_commission_amount(self):
        for record in self:
            if record.commission_rule_id:
                commission_percent = record.commission_rule_id.commission_percent / 100.0
                # Commission based on total invoiced amount
                record.commission_amount = record.total_invoiced * commission_percent
            else:
                record.commission_amount = 0.0

    def action_update_commission_rules(self):
        for record in self:
            if record.partner_id and record.fiscal_year_id:
                total_purchases = record.total_purchase
                commission_rules = self.env['customer.commission.config'].search([
                    ('purchase_target', '<=', total_purchases),
                    ('company_id', '=', record.company_id.id),
                    '|',
                    ('fiscal_year_id', '=', record.fiscal_year_id.id),
                    ('fiscal_year_id', '=', False),
                    ('active', '=', True)
                ], order='purchase_target desc')
                if commission_rules:
                    record.commission_rule_id = commission_rules[0]
                else:
                    record.commission_rule_id = False
            else:
                record.commission_rule_id = False

    @api.depends('partner_id', 'fiscal_year_id')
    def _compute_total_purchase(self):
        for record in self:
            if record.partner_id and record.fiscal_year_id:
                start_date = record.fiscal_year_id.date_from
                end_date = record.fiscal_year_id.date_to
                sales_orders = self.env['sale.order'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('date_order', '>=', start_date),
                    ('date_order', '<=', end_date),
                    ('state', 'in', ['sale'])
                ])
                record.total_purchase = sum(sales_orders.mapped('amount_total'))
            else:
                record.total_purchase = 0.0

    @api.depends('partner_id', 'fiscal_year_id')
    def _compute_total_invoiced(self):
        for record in self:
            if record.partner_id and record.fiscal_year_id:
                start_date = record.fiscal_year_id.date_from
                end_date = record.fiscal_year_id.date_to
                invoices = self.env['account.move'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('move_type', 'in', ['out_invoice', 'out_refund']),
                    ('invoice_date', '>=', start_date),
                    ('invoice_date', '<=', end_date),
                    ('state', 'in', ['posted'])
                ])
                record.total_invoiced = sum(invoices.mapped('amount_total'))
            else:
                record.total_invoiced = 0.0

    @api.depends('partner_id', 'fiscal_year_id')
    def _compute_total_paid(self):
        for record in self:
            if record.partner_id and record.fiscal_year_id:
                start_date = record.fiscal_year_id.date_from
                end_date = record.fiscal_year_id.date_to
                payments = self.env['account.payment'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('date', '>=', start_date),
                    ('date', '<=', end_date),
                    ('state', 'in', ['paid'])
                ])
                record.total_paid = sum(payments.mapped('amount'))
            else:
                record.total_paid = 0.0

    @api.depends('total_invoiced', 'total_paid')
    def _compute_total_due(self):
        for record in self:
            record.total_due = record.total_invoiced - record.total_paid

    @api.constrains('fiscal_year_id', 'partner_id')
    def _check_duplicate_commissions(self):
        for record in self:
            domain = [
                ('fiscal_year_id', '=', record.fiscal_year_id.id),
                ('partner_id', '=', record.partner_id.id),
                ('id', '!=', record.id)
            ]
            duplicate = self.search(domain)
            if duplicate:
                raise ValidationError(f"A commission record for customer {record.partner_id.name} in fiscal year {record.fiscal_year_id.name} already exists!")
