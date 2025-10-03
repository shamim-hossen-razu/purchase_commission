import xmlrpc.client
from copy import deepcopy
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Pricelist(models.Model):
    _inherit = 'product.pricelist'

    remote_pricelist_id = fields.Integer(string="Remote Pricelist ID")

    def _get_external_config(self):
        ICP = self.env['ir.config_parameter'].sudo()

        return {
            'url': ICP.get_param('purchase_commission.external_server_url', ''),
            'db': ICP.get_param('purchase_commission.external_server_db', ''),
            'uid': int(ICP.get_param('purchase_commission.external_server_uid', '')),
            'password': ICP.get_param('purchase_commission.external_server_password', ''),
        }

    def _db_sync_enabled(self):
        ICP = self.env['ir.config_parameter'].sudo()

        return ICP.get_param('purchase_commission.data_sync', 'False') == 'True'

    @api.model_create_multi
    def create(self, vals_list):
        """ This helper function handles the creation of a pricelist from local database to original databases """
        single = isinstance(vals_list, dict)
        if single:
            vals_list = [vals_list]

        if self._db_sync_enabled():

            cfg = self._get_external_config()
            try:
                models_rpc = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object")
            except Exception as e:
                raise ValidationError(f"Failed to connect to external server: {e}")


            # -------- Prepare remote payloads -------- #
            for vals in vals_list:
                copied = deepcopy(vals)
                if not isinstance(copied, dict):
                    raise ValueError("copied must be a dict")
                print(copied)
                if copied.get('currency_id'):
                    currency = self.env['res.currency'].browse(copied['currency_id'])
                    remote_currency = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'res.currency', 'search', [[['name', '=', currency.name]]], {'limit': 1})

                    if remote_currency:
                        copied['currency_id'] = remote_currency[0]
                    else:
                        copied.pop('currency_id', None)

                if copied.get('item_ids'):
                    for cmd in copied['item_ids']:
                        if len(cmd) > 2 and cmd[0] == 0 and isinstance(cmd[2], dict):
                            self._pl_mapping_vals_create_remote(cmd[2], models_rpc, cfg)

                print(copied)

                existing = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.pricelist', 'search', [[['name', '=ilike', copied.get('name')]]], {'limit': 1})
                if existing:
                    vals['remote_pricelist_id'] = existing[0]
                else:
                    try:
                        remote_id = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.pricelist', 'create', [vals])
                    except Exception as e:
                        raise ValidationError(f"Failed to connect to external server: {e}")
                    vals['remote_pricelist_id'] = remote_id

            records = super().create(vals_list)

            for record in records:
                if  record.remote_pricelist_id:
                    try:
                        remote_pricelist_id = models_rpc.execute_kw(
                            cfg['db'], cfg['uid'], cfg['password'],
                            'product.pricelist', 'search',
                            [[['name', '=ilike', record.name]]], {'limit': 1})
                        record.write({'remote_pricelist_id': remote_pricelist_id})
                    except Exception as e:
                        raise ValidationError(f"Could not write back local reference id to remote pricelist {record.id}: {e}")
            return records
        else:
            super().create(vals_list)

    def _pl_mapping_vals_create_remote(self, vals, models_rpc, cfg):
        """ This helper function handles the related fields of pricelists and maps, cleans values to create on remote servers """

        """ This is for product.template """
        if vals.get('product_tmpl_id'):
            prod_temp = self.env['product.template'].browse(vals['product_tmpl_id'])

            if not prod_temp.related_product_id or prod_temp.related_product_id == 0:
                remote_ids = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.template', 'search', [[['name', '=', prod_temp.name]]], {'limit': 1})

                if remote_ids:
                    prod_temp.related_product_id = remote_ids[0]
                else:
                    new_remote_id = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.template', 'create', [{'name': prod_temp.name}])
                    prod_temp.related_product_id = new_remote_id
            vals['product_tmpl_id'] = prod_temp.related_product_id

        """ This is for product.product """
        if vals.get('product_id'):
            prod_id = self.env['product.product'].browse(vals['product_id'])

            if not prod_id.remote_product_id or prod_id.remote_product_id == 0:
                if prod_id.product_tmpl_id and prod_id.product_tmpl_id.related_product_id:
                    remote_ids = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.product', 'search', [[['product_tmpl_id', '=', prod_id.product_tmpl_id.related_product_id]]], {'limit': 1})

                    if remote_ids:
                        prod_id.remote_product_id = remote_ids[0]
                    else:
                        new_remote_id = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.product', 'create', [{'product_tmpl_id': prod_id.product_tmpl_id.related_product_id, 'name': prod_id.name}])
                        prod_id.remote_product_id = new_remote_id
                vals['product_id'] = prod_id.remote_product_id

        """ This is for product.product category """
        if vals.get('categ_id'):
            cat = self.env['product.category'].browse(vals['categ_id'])
            if not cat.remote_category_id or cat.remote_category_id == 0:
                remote_ids = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.category', 'search', [[['name', '=', cat.name]]], {'limit': 1})

                if remote_ids:
                    cat.remote_category_id = remote_ids[0]
                else:
                    new_remote_id = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.category', 'create', [{'name': cat.name}])
                    cat.remote_category_id = new_remote_id
            vals['categ_id'] = cat.remote_category_id

        """ This is for product.pricelist """
        if vals.get('base_pricelist_id'):
            if vals.get('base_pricelist_id'):
                pricelist = self.env['product.pricelist'].browse(vals['base_pricelist_id'])
                if not pricelist.remote_pricelist_id or pricelist.remote_pricelist_id == 0:
                    remote_ids = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.pricelist', 'search', [[['name', '=', pricelist.name]]], {'limit': 1})
                    if remote_ids:
                        pricelist.remote_pricelist_id = remote_ids[0]
                    else:
                        new_remote_id = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.pricelist', 'create', [{'name': pricelist.name}])
                        pricelist.remote_pricelist_id = new_remote_id
                vals['base_pricelist_id'] = pricelist.remote_pricelist_id

        return vals