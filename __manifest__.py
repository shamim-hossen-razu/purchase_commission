# -*- coding: utf-8 -*-
{
    'name': "Purchase Commission",

    'summary': "This module allow a commission for customer upon achieving a target amount of purchase at the end of the fiscal year",

    'description': """
        Sale manager can set rules for purchase target commission.
        Rule consists of a name, a purchase target amount, a percentage of commission, fiscal year.
        A commission record is automatically linked to the customer record when they are eligiable.
        A manual mode for creating customer wise commission is also available.
    """,

    'author': "Shamim Hossen Razu",
    'website': "https://www.myodootest.space",
    'category': 'Sales/CRM',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'contacts', 'product', 'sale_management', 'accountant', 'purchase'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/bangladesh.divisions.csv',
        'data/bangladesh.districts.csv',
        'data/bangladesh.upazilas.csv',
        'data/bangladesh.unions.csv',
        'views/customer_commission_config_views.xml',
        'views/res_partner_views.xml',
        'views/res_company_address_views.xml',
        'views/customer_commission_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/product_template_views.xml',
        'views/report_saleorder_inherit.xml',
        'views/report_invoice.xml',
        'views/setting_views.xml',
        'views/commission_menu.xml',
        'views/divisions_views.xml',
        'views/districts_views.xml',
        'views/upazila_views.xml',
        'views/union_views.xml',
        'views/contact_setting_views.xml',
        'views/product_attribute_view_form.xml',
        'views/inherited_account_views.xml',
        'views/product_category_views.xml',
        'views/hide_menues_from_sales_setting.xml',
        'views/product_variant_views.xml',
        'views/sale_order_template_inherit.xml',
        'views/product_pricelist.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
