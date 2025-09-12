from odoo import models, fields, api
import xmlrpc.client
from odoo.exceptions import ValidationError


class ProductAttribute(models.Model):
    _inherit = 'product.attribute'

    related_attribute_id = fields.Integer(string='Related Attribute ID',
                                          help='ID of the related attribute in the external system')

    def _get_external_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'url': ICP.get_param('purchase_commission.external_server_url', ''),
            'db': ICP.get_param('purchase_commission.external_server_db', ''),
            'uid': int(ICP.get_param('purchase_commission.external_server_uid', 0)),
            'password': ICP.get_param('purchase_commission.external_server_password', '')
        }

    def _db_sync_enabled(self):
        # if data_sync is true return true else false
        ICP = self.env['ir.config_parameter'].sudo()
        return ICP.get_param('purchase_commission.data_sync', 'False') == 'True'

    @api.model
    def create(self, vals_list):
        """Handle both single and multiple record creation during import"""
        # Ensure vals_list is always a list for consistency
        single_record = isinstance(vals_list, dict)
        if single_record:
            vals_list = [vals_list]

        remote_models = db = uid = password = None
        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

        # Process each record
        for vals in vals_list:
            # Check for existing product by name (case-insensitive) in remote DB
            existing_records = remote_models.execute_kw(db, uid, password, 'product.attribute', 'search',
                                                        [[['name', '=ilike', vals.get('name')]]])
            if not existing_records:
                # No existing record found, create a new one in the remote DB
                remote_models.execute_kw(db, uid, password, 'product.attribute', 'create', [vals])

        new_attributes = super(ProductAttribute, self).create(vals_list)
        for attribute in new_attributes:
            if not attribute.related_attribute_id:
                # find related record id from remote db
                remote_record = remote_models.execute_kw(db, uid, password, 'product.attribute', 'search',
                                                         [[['name', '=', attribute.name]]], {'limit': 1})
                # write related partner id from main  database to remote record
                remote_models.execute_kw(db, uid, password, 'product.attribute', 'write',
                                         [remote_record, {'related_attribute_id': attribute.id}])
                # write related partner id from remote database to main record
                attribute.write({'related_attribute_id': remote_record[0] if remote_record else False})
        return new_attributes

    def write(self, vals):
        for record in self:
            if record._db_sync_enabled() and record.related_attribute_id:
                config = record._get_external_config()
                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                remote_record = remote_models.execute_kw(db, uid, password, 'product.attribute', 'search',
                                                         [[['id', '=', record.related_attribute_id]]], {'limit': 1})
                if remote_record:
                    remote_models.execute_kw(db, uid, password, 'product.attribute', 'write',
                                             [remote_record, vals])
        return super(ProductAttribute, self).write(vals)

    def unlink(self):
        remote_models = db = uid = password = None
        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

            for attribute in self:
                if attribute.related_attribute_id:
                    # Search for the attribute in the remote DB
                    remote_attribute_ids = remote_models.execute_kw(
                        db, uid, password, 'product.attribute', 'search',
                        [[['id', '=', attribute.related_attribute_id]]]
                    )
                    # If found, unlink it
                    if remote_attribute_ids:
                        remote_models.execute_kw(
                            db, uid, password, 'product.attribute', 'unlink',
                            [remote_attribute_ids]
                        )
        return super(ProductAttribute, self).unlink()

    @api.constrains('name')
    def _check_unique_name(self):
        """Ensure product name is unique (case-insensitive) locally"""
        for product in self:
            if product.name:
                existing = self.env['product.attribute'].search(
                    [('id', '!=', product.id), ('name', '=ilike', product.name)])
                if existing:
                    raise ValidationError("A product with the same name already exists.")



