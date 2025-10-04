from odoo import models, api, fields
from odoo.tools.misc import format_amount
import re
import xmlrpc.client
import logging
_logger = logging.getLogger(__name__)
from copy import deepcopy


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'
    remote_pricelist_id = fields.Integer(string='Remote Pricelist ID')

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
        if self._db_sync_enabled():
            _logger.warning('Data sync is enabled, attempting to sync partners to external DB')
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            try:
                remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                for pricelist in self:
                    remote_vals = deepcopy(vals)
                    if 'name' in remote_vals:
                        remote_vals['name'] = vals['name']
                    if 'currency_id' in remote_vals:
                        currency_name = self.env['res.currency'].browse(vals['currency_id']).name
                        # search currency name in remote db
                        remote_currency_id = remote_models.execute_kw(db, uid, password, 'res.currency', 'search',
                                                                      [[['name', '=', currency_name]]])
                        if remote_currency_id:
                            remote_vals['currency_id'] = remote_currency_id[0]
                        else:
                            remote_vals.pop('currency_id', None)
                    if 'company_id' in remote_vals:
                        company_name = self.env['res.company'].browse(vals['company_id']).name
                        remote_company_id = remote_models.execute_kw(db, uid, password, 'res.company', 'search',
                                                                     [[['name', '=', company_name]]])
                        if remote_company_id:
                            remote_vals['company_id'] = remote_company_id[0]
                        else:
                            remote_vals.pop('company_id', None)
                    if remote_vals.get('item_ids', False):
                        for i, item in enumerate(remote_vals['item_ids']):
                            if len(item) == 3 and item[0] == 0:
                                if item[2].get('categ_id', False):
                                    categ_id = self.env['product.category'].browse(item[2]['categ_id'])
                                    remote_categ_id = categ_id.remote_category_id
                                    if remote_categ_id:
                                        item[2]['categ_id'] = remote_categ_id
                                    else:
                                        item[2]['categ_id'] = False
                                        del vals['item_ids'][i]
                                        logging.info("This category is not synced yet. Please sync the category first before adding to pricelist item.")
                                if item[2].get('product_tmpl_id', False):
                                    product_tmpl_id = self.env['product.template'].browse(item[2]['product_tmpl_id'])
                                    remote_product_tmpl_id = product_tmpl_id.related_product_id
                                    if remote_product_tmpl_id:
                                        item[2]['product_tmpl_id'] = remote_product_tmpl_id
                                    else:
                                        item[2]['product_tmpl_id'] = False
                                        logging.error("Product Template must be synced before adding to pricelist item.")                                        # if product template is not synced remove this item from vals
                                        del vals['item_ids'][i]

                                if item[2].get('product_id', False):
                                    main_db_product_id = self.env['product.product'].browse(item[2].get('product_id'))
                                    remote_product_id = main_db_product_id.remote_product_id
                                    if remote_product_id:
                                        item[2]['product_id'] = remote_product_id
                                    else:
                                        item[2]['product_id'] = False
                                        del vals['item_ids'][i]
                                        logging.info('This product is not synced yet. Please sync the product first before adding to pricelist item.')
                                if item[2].get('pricelist_id', False):
                                    item[2]['pricelist_id'] = pricelist.remote_pricelist_id
                            if len(item) == 3 and item[0] == 1:
                                remote_pricelist_item_id = self.env['product.pricelist.item'].browse(item[1]).remote_pricelist_item_id
                                if remote_pricelist_item_id:
                                    item[1] = remote_pricelist_item_id
                                else:
                                    logging.error("Pricelist item must be synced before updating.")
                                    del vals['item_ids'][i]
                                if item[2].get('categ_id', False):
                                    categ_id = self.env['product.category'].browse(item[2]['categ_id'])
                                    remote_categ_id = categ_id.remote_category_id
                                    if remote_categ_id:
                                        item[2]['categ_id'] = remote_categ_id
                                    else:
                                        item[2]['categ_id'] = False
                                        del vals['item_ids'][i]
                                        logging.info(
                                            "This category is not synced yet. Please sync the category first before adding to pricelist item.")
                                if item[2].get('product_tmpl_id', False):
                                    product_tmpl_id = self.env['product.template'].browse(item[2]['product_tmpl_id'])
                                    remote_product_tmpl_id = product_tmpl_id.related_product_id
                                    if remote_product_tmpl_id:
                                        item[2]['product_tmpl_id'] = remote_product_tmpl_id
                                    else:
                                        item[2]['product_tmpl_id'] = False
                                        logging.error(
                                            "Product Template must be synced before adding to pricelist item.")  # if product template is not synced remove this item from vals
                                        del vals['item_ids'][i]

                                if item[2].get('product_id', False):
                                    main_db_product_id = self.env['product.product'].browse(item[2].get('product_id'))
                                    remote_product_id = main_db_product_id.remote_product_id
                                    if remote_product_id:
                                        item[2]['product_id'] = remote_product_id
                                    else:
                                        item[2]['product_id'] = False
                                        del vals['item_ids'][i]
                                        logging.info(
                                            'This product is not synced yet. Please sync the product first before adding to pricelist item.')
                                if item[2].get('pricelist_id', False):
                                    item[2]['pricelist_id'] = pricelist.remote_pricelist_id
                            if len(item) == 2 and item[0] == 2:
                                remote_pricelist_item_id = self.env['product.pricelist.item'].browse(item[1]).remote_pricelist_item_id
                                if remote_pricelist_item_id:
                                    item[1] = remote_pricelist_item_id
                                else:
                                    logging.error("Pricelist item must be synced before deleting.")
                                    del vals['item_ids'][i]
                    print('Remote Vals:', remote_vals)
                    remote_models.execute_kw(db, uid, password, 'product.pricelist', 'write', [[pricelist.remote_pricelist_id], remote_vals])
                return super(ProductPricelist, self).write(vals)

            except Exception as e:
                _logger.error(f"Failed to sync pricelist to external DB: {e}")
        return super(ProductPricelist, self).write(vals)

    def sync_pricelist(self):
        if self._db_sync_enabled():
            config = self._get_external_config()
            url = config['url']
            db = config['db']
            uid = config['uid']
            password = config['password']
            remote_models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
            for pricelist in self:
                if pricelist.remote_pricelist_id:
                    main_db_pricelist_items = self.env['product.pricelist.item'].search(
                        [('pricelist_id', '=', pricelist.id)])
                    remote_db_pricelist_items = remote_models.execute_kw(db, uid, password,
                                                                        'product.pricelist.item', 'search_read',
                                                                        [[['pricelist_id', '=', pricelist.remote_pricelist_id]]],
                                                                         {'fields':['id']})
                    remote_db_pricelist_item_ids = [item['id'] for item in remote_db_pricelist_items]
                    main_db_pricelist_item_ids = [item.id for item in main_db_pricelist_items]
                    for remote_id, main_id in zip(remote_db_pricelist_item_ids, main_db_pricelist_item_ids):
                        try:
                            remote_models.execute_kw(db, uid, password, 'product.pricelist.item', 'write',
                                                        [[remote_id], {'remote_pricelist_item_id' : main_id}])
                            _logger.info(f'Successfully updated remote pricelist item {remote_id} with main DB ID {main_id}')
                        except Exception as e:
                            _logger.error(f"Failed to update remote pricelist item {remote_id}: {e}")
                        self.env['product.pricelist.item'].browse(main_id).write({'remote_pricelist_item_id' : remote_id})
