from odoo import models, fields, api
import xmlrpc.client


class ProductTemplateAttributeLine(models.Model):
    _inherit = 'product.template.attribute.line'

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
                        db, uid, password, 'product.template.attribute.line', 'search',
                        [[['product_tmpl_id', '=', line.product_tmpl_id.related_product_id],
                          ['attribute_id', '=', line.attribute_id.related_attribute_id.id]]]
                    )
                    # If found, unlink it
                    if remote_line_ids:
                        remote_models.execute_kw(
                            db, uid, password, 'product.template.attribute.line', 'unlink',
                            [remote_line_ids]
                        )
        return super(ProductTemplateAttributeLine, self).unlink()
