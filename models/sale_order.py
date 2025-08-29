from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    total_purchase_in_running_year = fields.Float(
        string="Total Purchase This FY",
        compute="_compute_customer_total_purchase_in_running_fiscal_year",
        help="Total confirmed sales for this customer in current fiscal year"
    )
    purchase_target_achievement_discount = fields.Float(
        string="Target Achievement Discount %",
        compute="_compute_purchase_target_achievement_discount",
        help="Automatic discount based on customer's fiscal year purchases"
    )
    purchase_target_achievement_discount_rule = fields.Char(
        string="Target Achievement Discount Rule",
        compute="_compute_purchase_target_achievement_discount",
        help="Name of the discount rule being applied"
    )
    purchase_target_achievement_discount_rule_applied = fields.Boolean(
        string="Purchase Target Discount Applied",
        default=False,
        help="Indicates if purchase target discount has been applied to this order"
    )

    @api.depends('partner_id', 'date_order')
    def _compute_customer_total_purchase_in_running_fiscal_year(self):
        for order in self:
            if order.partner_id:
                # Get current fiscal year
                fiscal_year = self._get_current_fiscal_year(order.date_order or fields.Date.today())

                if fiscal_year:
                    # Get total sales for this customer in fiscal year
                    confirmed_orders = self.env['sale.order'].search([
                        ('partner_id', '=', order.partner_id.id),
                        ('state', 'in', ['sale', 'done']),
                        ('date_order', '>=', fiscal_year.date_from),
                        ('date_order', '<=', fiscal_year.date_to),
                        ('id', '!=', order.id),  # Exclude current order
                        ('company_id', '=', order.company_id.id)
                    ])
                    order.total_purchase_in_running_year = sum(confirmed_orders.mapped('amount_total'))
                else:
                    order.total_purchase_in_running_year = 0
            else:
                order.total_purchase_in_running_year = 0

    @api.depends('total_purchase_in_running_year', 'partner_id')
    def _compute_purchase_target_achievement_discount(self):
        for order in self:
            discount = 0
            rule_name = ''

            if order.total_purchase_in_running_year > 0:
                # Get applicable discount rules
                applicable_rules = self.env['customer.discount.config'].search([
                    ('purchase_target', '<=', order.total_purchase_in_running_year),
                    ('active', '=', True),
                    ('company_id', '=', order.company_id.id)
                ], order='purchase_target desc', limit=1)

                if applicable_rules:
                    discount = applicable_rules.commission_percent
                    rule_name = applicable_rules.name

            order.purchase_target_achievement_discount = discount
            order.purchase_target_achievement_discount_rule = rule_name

    def _get_current_fiscal_year(self, date=None):
        """Get fiscal year for given date"""
        if not date:
            date = fields.Date.today()

        fiscal_year = self.env['account.fiscal.year'].search([
            ('date_from', '<=', date),
            ('date_to', '>=', date),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        return fiscal_year

    def action_update_prices(self):
        """Override to ensure discounts are updated when prices are updated"""
        res = super().action_update_prices()
        for order in self:
            order._compute_customer_total_purchase_in_running_fiscal_year()
            order._compute_purchase_target_achievement_discount()
            if order.partner_id and order.purchase_target_achievement_discount > 0:
                order.apply_discount_to_lines()
                order.purchase_target_achievement_discount_rule_applied = True
            else:
                order.purchase_target_achievement_discount_rule_applied = False
        return res

    @api.onchange('partner_id')
    def _onchange_partner_id_discount(self):
        """Automatically apply discount when customer changes"""
        _logger.info(f"Partner changed to: {self.partner_id.name if self.partner_id else 'None'}")

        if self.partner_id:
            # Force recompute of discount fields
            self._compute_customer_total_purchase_in_running_fiscal_year()
            self._compute_purchase_target_achievement_discount()

            # Automatically apply discount if available
            if self.purchase_target_achievement_discount > 0:
                self.apply_discount_to_lines()
                self.purchase_target_achievement_discount_rule_applied = True
                _logger.info(f"Auto-applied discount: {self.purchase_target_achievement_discount}%")
            else:
                self.purchase_target_achievement_discount_rule_applied = False
        else:
            # Clear discount if no customer
            for line in self.order_line:
                line.discount = 0
            self.purchase_target_achievement_discount_rule_applied = False

    # @api.onchange('order_line')
    # def _onchange_order_line_discount(self):
    #     """Apply auto discount to new lines if already applied"""
    #     if (self.partner_id and self.purchase_target_achievement_discount > 0 and
    #             self.purchase_target_achievement_discount_rule_applied):
    #         # Apply discount to any new lines that don't have it
    #         if self.purchase_target_achievement_discount > 0:
    #             for line in self.order_line:
    #                 line.discount += self.purchase_target_achievement_discount

    def apply_discount_to_lines(self):
        """Internal method to apply discount to all lines"""
        if self.purchase_target_achievement_discount > 0:
            for line in self.order_line:
                line.discount += self.purchase_target_achievement_discount
                _logger.info(f"Applied {self.purchase_target_achievement_discount}% discount to {line.product_id.name}")

    def _remove_discount_from_lines(self):
        """Internal method to remove discount from all lines"""
        for line in self.order_line:
            line.discount -= self.purchase_target_achievement_discount
            _logger.info(f"Removed discount from {line.product_id.name}")
        self.purchase_target_achievement_discount_rule_applied = False

    def apply_purchase_target_achievement_discount(self):
        """Manual button to apply discount to all lines"""
        _logger.info(f"Manual discount application - Auto discount: {self.purchase_target_achievement_discount}")

        if self.purchase_target_achievement_discount > 0:
            self.apply_discount_to_lines()
            self.purchase_target_achievement_discount_rule_applied = True

    def withdraw_auto_discount(self):
        """Remove discount from all lines"""
        _logger.info("Withdrawing auto discount from all lines")

        self._remove_discount_from_lines()
        self.purchase_target_achievement_discount_rule_applied = False

    def write(self, vals):
        """Handle partner changes in write method"""
        res = super().write(vals)
        if 'partner_id' in vals:
            for order in self:
                if order.partner_id and order.purchase_target_achievement_discount > 0:
                    order.apply_discount_to_lines()
                    order.purchase_target_achievement_discount_rule_applied = True
                else:
                    order.purchase_target_achievement_discount_rule_applied = False
        return res
