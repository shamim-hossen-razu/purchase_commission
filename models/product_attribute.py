from odoo import models, fields, api
import xmlrpc.client
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)
from copy import deepcopy


class ProductAttribute(models.Model):
    _inherit = 'product.attribute'

    remote_attribute_id = fields.Integer(string='Remote Attribute ID',
                                          help='ID of the related attribute in the external system',
                                         readonly=True)

    @api.constrains('name')
    def _check_unique_name(self):
        """Ensure attribute name is unique (case-insensitive) locally"""
        for attribute in self:
            if attribute.name:
                existing = self.env['product.attribute'].search(
                    [('id', '!=', attribute.id), ('name', '=ilike', attribute.name)])
                if existing:
                    raise ValidationError("An attribute with the same name already exists.")
        
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

        if self._db_sync_enabled():
            try:
                config = self._get_external_config()
                if not config or not all(config.get(k) for k in ['url', 'db', 'uid', 'password']):
                    _logger.warning("External DB config is incomplete, skipping sync")
                    return super(ProductAttribute, self).create(vals_list)

                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']

                # Create XML-RPC connection
                try:
                    remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                except Exception as e:
                    _logger.error(f"Failed to connect to external server: {e}")
                    return super(ProductAttribute, self).create(vals_list)
                # create attribute with same name in remote databae
                for vals in vals_list:
                    try:
                        # Check for existing product by name (case-insensitive) in remote DB
                        existing_records = remote_models.execute_kw(
                            db, uid, password,
                            'product.attribute', 'search',
                            [[['name', '=ilike', vals.get('name')]]]
                        )

                        if not existing_records:
                            _logger.info(f"Creating new remote record for attribute: {vals.get('name', 'Unknown')}")
                            # No existing record found, create a new one in the remote DB

                            remote_record = remote_models.execute_kw(
                                db, uid, password,
                                'product.attribute', 'create',
                                [vals]
                            )
                            _logger.info(f"Created remote attribute with ID {remote_record} for {vals.get('name', 'Unknown')}")
                    except Exception as e:
                        _logger.error(f"Error processing remote record for {vals.get('name', 'Unknown')}: {e}")

                # Create attributes in main database
                new_attributes = super(ProductAttribute, self).create(vals_list)

                # Update relationships
                for attribute in new_attributes:
                    if not attribute.remote_attribute_id:
                        try:
                            # Find related record id from remote db
                            remote_record = remote_models.execute_kw(
                                db, uid, password,
                                'product.attribute', 'search',
                                [[['name', '=', attribute.name]]],
                                {'limit': 1}
                            )
                            _logger.info(f"Linking local attribute '{attribute.name}' with remote ID {remote_record}")
                            if remote_record:
                                _logger.info(f"Linking local attribute '{attribute.name}' with remote ID {remote_record[0]}")
                                # Write related partner id from main database to remote record
                                remote_models.execute_kw(
                                    db, uid, password,
                                    'product.attribute', 'write',
                                    [remote_record, {'remote_attribute_id': attribute.id}]
                                )

                                # Write related partner id from remote database to main record
                                attribute.write({'remote_attribute_id': remote_record[0]})

                        except Exception as e:
                            _logger.error(f"Error updating relationships for {attribute.name}: {e}")

                return new_attributes

            except Exception as e:
                _logger.error(f"Error in external DB sync: {e}")
                # Fall back to normal creation if external sync fails
                return super(ProductAttribute, self).create(vals_list)
        else:
            _logger.info('Data sync disabled, creating locally only')
            return super(ProductAttribute, self).create(vals_list)

    def write(self, vals):
        for record in self:
            if record._db_sync_enabled() and record.remote_attribute_id:
                config = record._get_external_config()
                url = config['url']
                db = config['db']
                uid = config['uid']
                password = config['password']
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                remote_record = remote_models.execute_kw(db, uid, password, 'product.attribute', 'search',
                                                         [[['id', '=', record.remote_attribute_id]]], {'limit': 1})

                if vals.get('value_ids'):
                    copied_vals = deepcopy(vals)
                    for i, value_data in enumerate(copied_vals['value_ids']):
                        # Handle case when vendor line is being edited
                        if len(value_data) > 2 and value_data[0] == 1 and isinstance(value_data[2], dict):
                            main_db_attribute_value_id = value_data[1]
                            main_db_attribute_value = self.env['product.attribute.value'].browse(
                                main_db_attribute_value_id)
                            # search on remote db main_db_attribute_value name
                            remote_db_attribute_value_id = remote_models.execute_kw(db, uid, password,
                                                                                    'product.attribute.value', 'search',
                                                                                    [[['name', '=ilike',
                                                                                       main_db_attribute_value.name]]])
                            value_data[1] = remote_db_attribute_value_id[0] if remote_db_attribute_value_id else False

                        # Handle case when vendors are being added newly
                        # if len(value_data) > 2 and value_data[0] == 0 and isinstance(value_data[2], dict):
                        #     value_data[2]['attribute_id'] = record.remote_attribute_id
                    remote_models.execute_kw(db, uid, password, 'product.attribute', 'write', [remote_record, copied_vals])
                else:
                    remote_models.execute_kw(db, uid, password, 'product.attribute', 'write', [remote_record, vals])
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
                if attribute.remote_attribute_id:
                    # Search for the attribute in the remote DB
                    remote_attribute_ids = remote_models.execute_kw(
                        db, uid, password, 'product.attribute', 'search',
                        [[['id', '=', attribute.remote_attribute_id]]]
                    )
                    # If found, unlink it
                    if remote_attribute_ids:
                        remote_models.execute_kw(
                            db, uid, password, 'product.attribute', 'unlink',
                            [remote_attribute_ids]
                        )
        return super(ProductAttribute, self).unlink()

    # @api.constrains('name')
    # def _check_unique_name(self):
    #     """Ensure product name is unique (case-insensitive) locally"""
    #     for product in self:
    #         if product.name:
    #             existing = self.env['product.attribute'].search(
    #                 [('id', '!=', product.id), ('name', '=ilike', product.name)])
    #             if existing:
    #                 raise ValidationError("A product with the same name already exists.")



