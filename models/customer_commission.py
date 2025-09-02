from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CustomerCommission(models.Model):
    _name = 'customer.commission'
    _description = 'Customer Commission'
    _order = 'fiscal_year_id desc'

    name = fields.Char(string='Name', compute='_compute_name')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    commission_rule_id = fields.Many2one(
        'customer.commission.config', string='Commission Rule')
    commission_amount = fields.Float(string='Commission Amount', compute='_compute_commission_amount', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('applicable', 'Applicable'),
        ('eligible', 'Eligible'),
        ('in_payment', 'In Payment'),
        ('paid', 'Paid')
    ], string='Status', default='draft', compute='_compute_state', required=True)
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
    invoice_count = fields.Integer(compute='_compute_invoice_count')
    payment_date = fields.Date(string='Payment Date', compute='_compute_payment_date', store=True)
    account_move_id = fields.Many2one('account.move', string='Credit Note', readonly=True)

    @api.constrains('payment_date')
    def _check_payment_date(self):
        """payment date must be after the fiscal year end date"""
        for record in self:
            if record.payment_date and record.fiscal_year_id:
                if record.payment_date < record.fiscal_year_id.date_to:
                    raise ValidationError("Payment date must be after the fiscal year end date!")

    def _compute_invoice_count(self):
        for record in self:
            if record.partner_id:
                invoices = self.env['account.move'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('move_type', 'in', ['out_refund']),
                    ('commission_id', '=', record.id)
                ])
                record.invoice_count = len(invoices)
            else:
                record.invoice_count = 0

    def action_view_credit_notes(self):
        self.ensure_one()
        return {
            'name': 'Commission Credit Notes',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'res_model': 'account.move',
            'domain': [('commission_id', '=', self.id)],
        }

    @api.depends('commission_rule_id', 'commission_amount')
    def _compute_name(self):
        for record in self:
            if record.partner_id and record.fiscal_year_id:
                record.name = f"Purchase Commission for {record.partner_id.name} - {record.fiscal_year_id.name}"
            else:
                record.name = "New Commission Record"

    @api.depends('commission_rule_id', 'total_purchase', 'total_invoiced', 'total_paid', 'total_due')
    def _compute_commission_amount(self):
        for record in self:
            if record.commission_rule_id:
                commission_percent = record.commission_rule_id.commission_percent / 100.0
                # Commission based on total invoiced amount
                record.commission_amount = record.total_invoiced * commission_percent
            else:
                record.commission_amount = 0.0

    @api.onchange('partner_id', 'fiscal_year_id', 'total_purchase', 'total_invoiced', 'total_paid', 'total_due')
    def update_commission_rule(self):
        self.action_update_commission_rules()

    def action_update_commission_rules(self):
        for record in self:
            if record.partner_id and record.fiscal_year_id:
                commission_rules = self.env['customer.commission.config'].search([
                    ('purchase_target', '<=', record.total_invoiced),
                    ('company_id', '=', record.company_id.id),
                    ('fiscal_year_id', '=', record.fiscal_year_id.id),
                    ('active', '=', True)
                ], order='purchase_target desc')
                if commission_rules:
                    record.commission_rule_id = commission_rules[0]
                else:
                    record.commission_rule_id = False
            else:
                record.commission_rule_id = False

    @api.depends('commission_rule_id', 'commission_amount', 'total_due', 'invoice_count', 'account_move_id.status_in_payment')
    def _compute_state(self):
        for record in self:
            if not record.commission_rule_id or record.total_due > 0:
                record.state = 'draft'
            if record.commission_rule_id and record.total_due > 0 and record.commission_amount > 0:
                record.state = 'applicable'
            if record.commission_amount > 0 and record.total_due == 0 and record.invoice_count == 0:
                record.state = 'eligible'
            if record.commission_amount > 0 and record.total_due == 0 and record.invoice_count > 0:
                if record.account_move_id and record.account_move_id.status_in_payment == 'paid':
                    record.state = 'paid'
                else:
                    record.state = 'in_payment'

    def recompute_all(self):
        for record in self:
            record._compute_total_purchase()
            record._compute_total_invoiced()
            record._compute_total_paid()
            record._compute_total_due()
            record.action_update_commission_rules()
            record._compute_commission_amount()

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
                    ('move_type', 'in', ['out_invoice']),
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
                    ('payment_type', '=', 'inbound'),
                    ('state', 'in', ['paid'])
                ])
                record.total_paid = sum(payments.mapped('amount'))
            else:
                record.total_paid = 0.0

    @api.depends('total_invoiced', 'total_paid')
    def _compute_total_due(self):
        for record in self:
            record.total_due = record.total_invoiced - record.total_paid
            if record.total_due == 0 and record.commission_amount > 0 and record.state != 'paid':
                record.state = 'eligible'

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

    def action_make_payment(self):
        """Create a credit note for commission payment to customer"""
        self.ensure_one()
        # if todays date in not after fiscal year end date, raise error
        if fields.Date.today() <= self.fiscal_year_id.date_to:
            raise ValidationError("You can only make a payment after the fiscal year end date!")

        # Check if commission product exists, create if not
        commission_product = self.env['product.product'].search([
            ('name', '=', 'Purchase Commission'),
            ('type', '=', 'service'),
            ('company_id', 'in', [self.company_id.id, False])
        ], limit=1)

        if not commission_product:
            commission_product = self.env['product.product'].create({
                'name': 'Purchase Commission',
                'type': 'service',
                'invoice_policy': 'order',
                'company_id': False,
            })

        # Create credit note
        invoice_vals = {
            'move_type': 'out_refund',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'journal_id': self.env['account.journal'].search([
                ('type', '=', 'sale'),
                ('company_id', '=', self.company_id.id)
            ], limit=1).id,
            'commission_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': commission_product.id,
                'name': f"Commission for {self.fiscal_year_id.name}",
                'price_unit': self.commission_amount,
                'quantity': 1.0,
                'tax_ids': [],
            })],
            'ref': f"Commission for {self.partner_id.name} - {self.fiscal_year_id.name}"
        }

        credit_note = self.env['account.move'].create(invoice_vals)
        credit_note.action_post()

        # Update commission state
        self.write({'account_move_id': credit_note.id, 'state': 'in_payment'})

        # Return action to view the created credit note
        return {
            'name': 'Commission Credit Note',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': credit_note.id,
        }

    @api.depends('state', 'account_move_id.status_in_payment', 'account_move_id.matched_payment_ids')
    def _compute_payment_date(self):
        for record in self:
            if record.account_move_id and record.account_move_id.status_in_payment == 'paid':
                payment = record.account_move_id.matched_payment_ids.filtered(lambda p: p.payment_type == 'outbound' and p.state == 'paid')
                if payment:
                    record.payment_date = payment[0].date
                else:
                    record.payment_date = False
            else:
                record.payment_date = False

