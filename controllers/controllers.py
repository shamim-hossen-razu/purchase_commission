# -*- coding: utf-8 -*-
# from odoo import http


# class DbSync(http.Controller):
#     @http.route('/db_sync/db_sync', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/db_sync/db_sync/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('db_sync.listing', {
#             'root': '/db_sync/db_sync',
#             'objects': http.request.env['db_sync.db_sync'].search([]),
#         })

#     @http.route('/db_sync/db_sync/objects/<model("db_sync.db_sync"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('db_sync.object', {
#             'object': obj
#         })

