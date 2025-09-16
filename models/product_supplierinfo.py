from odoo import models, fields, api
import xmlrpc.client
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

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