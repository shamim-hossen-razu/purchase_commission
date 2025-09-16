from odoo import models, fields, api
import xmlrpc.client
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    related_supplierinfo_id = fields.Integer(string='Related Supplier Info ID',
                                              help='ID of the related supplier info in the external system')

    @api.constrains('partner_id', 'product_tmpl_id')
    def _check_unique_supplierinfo(self):
        """Ensure unique supplierinfo per product-partner pair (case-insensitive) locally"""
        for info in self:
            if info.partner_id and info.product_tmpl_id:
                existing = self.env['product.supplierinfo'].search(
                    [('id', '!=', info.id),
                     ('partner_id', '=', info.partner_id.id),
                     ('product_tmpl_id', '=', info.product_tmpl_id.id)])
                if existing:
                    raise ValidationError("A supplier info with the same product and partner already exists.")

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

    def create(self, vals_list):
        """Handle both single and multiple record creation during import"""
        # Ensure vals_list is always a list for consistency
        single_record = isinstance(vals_list, dict)
        if single_record:
            vals_list = [vals_list]

        if self._db_sync_enabled():
            _logger.info("Data sync is enabled. Proceeding with external DB operations.")
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            try:
                _logger.info(f"Connecting to external server at {url}")
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
            except Exception as e:
                raise ValidationError(f"Failed to connect to external server: {e}")

            created_records = super(ProductSupplierinfo, self).create(vals_list)

            for record, vals in zip(created_records, vals_list):
                if record.product_tmpl_id.related_product_id:
                    # Check for existing supplier info in remote DB
                    existing_records = remote_models.execute_kw(
                        db, uid, password,
                        'product.supplierinfo', 'search',
                        [[['product_tmpl_id', '=', record.product_tmpl_id.related_product_id],
                          ['partner_id', '=', record.partner_id.related_partner_id]]],
                        {'limit': 1}
                    )
                    if existing_records:
                        _logger.warning(f"Supplier info already exists in remote DB for product {record.product_tmpl_id.name} and partner {record.partner_id.name}, skipping creation.")
                    if not existing_records:
                        # Prepare values for remote creation
                        remote_vals = vals.copy()
                        remote_vals['product_tmpl_id'] = record.product_tmpl_id.related_product_id
                        remote_vals['partner_id'] = record.partner_id.related_partner_id
                        try:
                            remote_id = remote_models.execute_kw(
                                db, uid, password,
                                'product.supplierinfo', 'create',
                                [remote_vals]
                            )
                            _logger.info(f"Created supplier info in remote DB with ID {remote_id} for product {record.product_tmpl_id.name} and partner {record.partner_id.name}.")
                        except Exception as e:
                            _logger.error(f"Failed to create supplier info in remote DB for product {record.product_tmpl_id.name} and partner {record.partner_id.name}: {e}")
            if created_records:
                for supplier_info in created_records:
                    if not supplier_info.related_supplierinfo_id:
                        # find related record id from remote db
                        remote_record = remote_models.execute_kw(db, uid, password, 'product.supplierinfo', 'search',
                                                                 [[['product_tmpl_id', '=', supplier_info.product_tmpl_id.related_product_id],
                                                                   ['partner_id', '=', supplier_info.partner_id.related_partner_id]]], {'limit': 1})
                        # write remote record with main database supplierinfo id
                        if remote_record:
                            remote_models.execute_kw(db, uid, password, 'product.supplierinfo', 'write',
                                                     [remote_record, {'related_supplierinfo_id': supplier_info.id}])
                            supplier_info.related_supplierinfo_id = remote_record[0]

        else:
            return super(ProductSupplierinfo, self).create(vals_list)


    def write(self, vals):
        res = super(ProductSupplierinfo, self).write(vals)
        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            try:
                _logger.info(f"Connecting to external server at {url}")
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
            except Exception as e:
                raise ValidationError(f"Failed to connect to external server: {e}")
            for line in self:
                if line.product_tmpl_id.related_product_id:
                    # Search for the supplier info in the remote DB
                    remote_line_ids = remote_models.execute_kw(
                        db, uid, password, 'product.supplierinfo', 'search',
                        [[['product_tmpl_id', '=', line.product_tmpl_id.related_product_id],
                          ['partner_id', '=', line.partner_id.related_partner_id]]]
                    )
                    _logger.warning(f"Remote line IDs to update: {remote_line_ids}")
                    # If found, update it
                    if remote_line_ids:
                        remote_models.execute_kw(
                            db, uid, password, 'product.supplierinfo', 'write',
                            [remote_line_ids, vals]
                        )
        return res

    def unlink(self):
        remote_models = db = uid = password = None
        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

            for line in self:
                if line.product_tmpl_id.related_product_id:
                    # Search for the attribute line in the remote DB
                    remote_line_ids = remote_models.execute_kw(
                        db, uid, password, 'product.supplierinfo', 'search',
                        [[['product_tmpl_id', '=', line.product_tmpl_id.related_product_id],
                          ['partner_id', '=', line.partner_id.related_partner_id]]]
                    )
                    _logger.warning(f"Remote line IDs to unlink: {remote_line_ids}")
                    # If found, unlink it
                    if remote_line_ids:
                        remote_models.execute_kw(
                            db, uid, password, 'product.supplierinfo', 'unlink',
                            [remote_line_ids]
                        )
            return super(ProductSupplierinfo, self).unlink()
        else:
            return super(ProductSupplierinfo, self).unlink()