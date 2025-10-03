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
                   copied.pop('item_ids', None)

                if copied.get('country_group_ids'):
                    copied.pop('country_group_ids', None)

                print(copied)

                existing = models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.pricelist', 'search', [[['name', '=ilike', copied.get('name')]]], {'limit': 1})
                if not existing:
                    try:
                        models_rpc.execute_kw(cfg['db'], cfg['uid'], cfg['password'], 'product.pricelist', 'create', [copied])
                    except Exception as e:
                        raise ValidationError(f"Failed to connect to external server: {e}")
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
            return super().create(vals_list)