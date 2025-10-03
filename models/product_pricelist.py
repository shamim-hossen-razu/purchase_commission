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

