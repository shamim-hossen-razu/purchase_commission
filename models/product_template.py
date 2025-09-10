from odoo import fields, models, api
from odoo.exceptions import ValidationError
import xmlrpc.client
from odoo import Command

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    related_product_id = fields.Integer(string="Remote Product ID", help="Stores the product ID of this product in the external database.")
    related_category_id = fields.Integer(string="Remote Category ID", help="Stores the category ID of this category in the external database.")

    def _get_external_config(self):
        """Fetch external server configuration from system parameters"""
        ICP = self.env['ir.config_parameter'].sudo()

        return {
            'url': ICP.get_param('purchase_commission.external_server_url'),
            'db': ICP.get_param('purchase_commission.external_server_db'),
            'uid': int(ICP.get_param('purchase_commission.external_server_uid', 0)),
            'password': ICP.get_param('purchase_commission.external_server_password'),
        }

    def _db_sync_enabled(self):
        """Check if Data Sync is enabled"""
        ICP = self.env['ir.config_parameter'].sudo()

        return ICP.get_param('purchase_commission.data_sync', 'False') == 'True'

    def _clean_vals_for_rpc(self, vals):
        """Remove fields that XML-RPC cannot serialize (Many2manyCommand, etc.)"""
        allowed_fields = {'name', 'default_code', 'type', 'list_price', 'standard_price', 'sale_ok', 'purchase_ok', 'categ_id', 'barcode', 'active'}
        cleaned = {}
        for key, value in vals.items():
            if key in allowed_fields:
                if isinstance(value, (str, int, float, bool)):
                    cleaned[key] = value
                elif isinstance(value, list) and value and isinstance(value[0], int):
                    cleaned[key] = value[0]
        return cleaned

    @api.model
    def create(self, vals_list):
        """Override create to sync product.template to external DB. Create a new product template if it doesn't already exist"""
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        records = super().create(vals_list)

        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            models_rpc = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

            for record in records:
                vals_clean = self._clean_vals_for_rpc(record.read()[0])
                remote_id = models_rpc.execute_kw(db, uid, password, 'product.template', 'create', [vals_clean])
                record.related_product_id = remote_id

        return records

    def write(self, vals):
        """Override write to update external DB product.template"""
        res = super().write(vals)

        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            models_rpc = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

            cleaned_vals = self._clean_vals_for_rpc(vals)
            if cleaned_vals:
                for record in self:
                    if record.related_product_id:
                        models_rpc.execute_kw(db, uid, password, 'product.template', 'write', [[record.related_product_id], cleaned_vals])

        return res

    @api.constrains('name')
    def _check_unique_name(self):
        """Ensure product name is unique (case-insensitive) locally"""
        for product in self:
            if product.name:
                existing = self.env['product.template'].search([('id' , '!=', product.id), ('name', '=ilike', product.name)])
                if existing:
                    raise ValidationError("A product with the same name already exists.")

    def unlink(self):
        """Override unlink to delete the product.template in external DB as well"""
        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            models_rpc = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

            for record in self:
                if record.related_product_id:
                    try:
                        models_rpc.execute_kw(db, uid, password, 'product.template', 'unlink', [[record.related_product_id]])
                    except Exception as e:
                        pass

        return super().unlink()