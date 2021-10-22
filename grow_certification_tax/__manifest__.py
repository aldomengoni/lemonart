# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
{
    'name': "Carta Certificacion",

    'summary': """
        Imprime carta de certificacion de retencion.
    """,

    'description': """
       
    """,

    'author': "GrowIT",

    'category': 'Uncategorized',
    'version': '0.1',
    'depends': ['account'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/certification.tax.csv',
        'views/views.xml',
        'views/templates.xml',
    ],

}

