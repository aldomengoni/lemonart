# -*- coding: utf-8 -*-

import logging
from collections import defaultdict

from odoo import api, fields, models
# from odoo.addons import decimal_precision as dp
# from odoo.addons.stock_landed_costs.models import product
# from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)



class PartnerXlsx(models.AbstractModel):
    _name = 'report.stock_landed_cost_extra.report_landed_cost_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = "Stock Landed Cost Report XLSX"
    
    def _get_ws_params(self, wb, data, run_ids):
        costo_ids = self.env['stock.landed.cost.lines'].search([('cost_id', '=', run_ids.id)])
        
        _template = {}
        for i in costo_ids:
            if i.split_method == 'arancel':
                continue
                
            line = "line.get('%d', 0)" % i.id
            _template[i.id] = {
                'header': {
                    'value': i.name.upper(),
                },
                'data': {
                    'value': self._render(line),
                    'format': self.format_amount_right,
                },
                'width': 14,
            }

        rule_template = {
            'product': {
                'header': {
                    'value': 'PRODUCTO',
                },
                'data': {
                    'value': self._render("line['product']"),
                },
                'width': 33,
                'total': {
                    'value': 'TOTAL',
                }
            },
            'qty': {
                'header': {
                    'value': 'CANT.',

                },
                'data': {
                    'value': self._render("line['qty']"),
                    'format': self.format_amount_right,
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'valor': {
                'header': {
                    'value': 'VALOR DOP',
                },
                'data': {
                    'value': self._render("line['valor']"),
                    'format': self.format_tcell_amount_right_bold,

                },
                'width': 14,
            },'porcent': {
                'header': {
                    'value': '%',
                },
                'data': {
                    'value': self._render("porcent"),
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'price_unit': {
                'header': {
                    'value': 'COSTO FOB',
                },
                'data': {
                    'value': self._render("line['price_unit']"),
                    'format': self.format_amount_right,
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'price_total': {
                'header': {
                    'value': 'VALOR.',
                },
                'data': {
                    'value': self._render("line['price_total']"),
                    'format': self.format_amount_right,
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'arancel': {
                'header': {
                    'value': 'ARANCEL.',
                },
                'data': {
                    'value': self._render("line['arancel']"),
                    'format': self.format_amount_right,
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },
            'moneda': {
                'header': {
                    'value': '$.',
                },
                'data': {
                    'value': self._render("line['moneda']"),
                },
                 'width': 14,
                'total': {
                    'value': '',
                }
            },'coste_unidad': {
                'header': {
                    'value': 'COSTE UNID.',
                },
                'data': {
                    'value':  self._render("coste_unidad"),
                    'format': self.format_amount_right,
                },
                 'width': 14,
                'total': {
                    'value': '',
                }
            },'coste_ant': {
                'header': {
                    'value': 'COSTE ANT.',
                },
                'data': {
                    'value': self._render("line['coste_ant']"),
                    'format': self.format_amount_right,
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'ref': {
                'header': {
                    'value': 'CODIGO.',
                },
                'data': {
                    'value': self._render("line['ref']"),
                },
                'width': 20,
                'total': {
                    'value': '',
                }
            },'cost_total': {
                'header': {
                    'value': 'GASTOS TOTALES.',
                },
                'data': {
                    'value': self._render("cost_total"),
                    'format': self.format_amount_right,
                },
                'width': 20,
                'total': {
                    'value': '',
                }
            },'precio_ant': {
                'header': {
                    'value': 'PRECIO VENTA.',
                },
                'data': {
                    'value': self._render("line['precio_ant']"),
                    'format': self.format_amount_right,
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'tasa': {
                'header': {
                    'value': 'TASA',
                },
                'data': {
                    'value': self._render("line['valor']/(line['price_total'] or 1)"),
                    'format': self.format_amount_right,
                },
                'width': 9,
                'total': {
                    'value': '',
                }
            },
        }

        rule_template.update(_template)

        codes = [col.id for col in costo_ids if col.split_method != 'arancel']

        wanted_list = ['ref','product', 'qty','price_unit', 'moneda', 
                       'price_total','tasa', 'valor', 'porcent'] + codes + ['arancel', 'cost_total', 'coste_unidad', 'coste_ant', 'precio_ant']

        ws_params = {
            'ws_name': 'Liquidacion',
            'generate_ws_method': 'generate_report',
            'title': 'Reporte de Liquidacion',
            'wanted_list': wanted_list,
            'rules': codes,
            'col_specs': rule_template,
        }

        return [ws_params]
    
       
    def _get_extras_params(self):

        _template = {
            'name': {
                'header': {
                    'value': 'Liquidacion',
                },
                'data': {
                    'value': self._render("line['name']"),
                    
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'date': {
                'header': {
                    'value': 'Fecha',
                },
                'data': {
                    'value': self._render("line['date']"),
                    'format': self.format_date_left,
                    
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'po': {
                'header': {
                    'value': 'Ordenes de Compras',
                },
                'data': {
                    'value': self._render("line['po']"),
                    
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'supplier': {
                'header': {
                    'value': 'Proveedores',
                },
                'data': {
                    'value': self._render("line['supplier']"),
                    
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },
        }

        wanted_list = ['name', 'supplier', 'po', 'date']

        ws_params = {
            'wanted_list': wanted_list,
            'col_specs': _template,
        }

        return [ws_params]


    
    def _get_costes_params(self):

        _template = {
            'costo': {
                'header': {
                    'value': 'Costes Adicionales.',
                },
                'data': {
                    'value': self._render("line['costo']"),
                    
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },'price': {
                'header': {
                    'value': 'Monto.',
                },
                'data': {
                    'value': self._render("line['price']"),
                    'format': self.format_amount_right,
                },
                'width': 14,
                'total': {
                    'value': '',
                }
            },
        }

        wanted_list = ['costo', 'price']

        ws_params = {
            'wanted_list': wanted_list,
            'col_specs': _template,
        }

        return [ws_params]

    def generate_report(self, workbook, ws, ws_params, data, run_ids):
        """
        :param workbook:
        :param data:
        :param inputs:
        :return:
        """
        ws.set_portrait()
        ws.fit_to_pages(1, 0)
        ws.set_header(self.xls_headers['standard'])
        ws.set_footer(self.xls_footers['standard'])

        self._set_column_width(ws, ws_params)

        row_pos = 0
        row_pos = self._write_ws_title(ws, row_pos, ws_params, merge_range=True)

        purchase_numbers = [i.origin for i in run_ids.picking_ids]
        purchase = self.env['purchase.order'].search([('name', 'in', purchase_numbers)])
        po = ",".join([i.name for i in purchase])
        supplier = ",".join(set([i.partner_id.name for i in purchase]))
        
        params = self._get_extras_params()[0]
        data_dict = {'name': run_ids.name, 'date': run_ids.date, 'po': po, 'supplier': supplier}
        #row_pos += 1
        row_pos = self._write_line(
            ws, row_pos, params, col_specs_section='header',
            default_format=self.format_theader_yellow_left)
        row_pos = self._write_line(
            ws, row_pos, params, col_specs_section='data',
            render_space={
                'line': data_dict,
            },
            default_format=self.format_tcell_left)
        
        row_pos += 1

        row_pos = self._write_line(
            ws, row_pos, ws_params, col_specs_section='header',
            default_format=self.format_theader_yellow_left)

        #ws.set_row(row_pos-1, 50)
        ws.freeze_panes(row_pos, 1)
        
        adjustment_ids = self.env['stock.valuation.adjustment.lines'].search(
            [('cost_id','=', run_ids.id)]
        )
                
        cost_total_by_product = {}
        datos = {}
        for line in adjustment_ids:
            currency_id = line.move_id.purchase_line_id.order_id.currency_id
#             purchase = line.move_id.purchase_line_id.order_id
#             last_invoice = line.move_id.purchase_line_id.order_id.invoice_ids[-1] if line.move_id.purchase_line_id.order_id.invoice_ids else False
#             date = run_ids.date
            
#             tasa = currency_id._get_rates(purchase.company_id, date)#last_invoice.invoice_date or date)
#             tasa2 = self.env['res.currency']._get_conversion_rate(currency_id, purchase.company_id.currency_id, purchase.company_id, date)
#             _logger.info((tasa, tasa2))
            datos.setdefault(line.move_id.id, {}).update({
                'ref': line.product_id.default_code,
                'product': line.product_id.name,
                'qty': line.quantity,
                'valor': line.former_cost,
                'price_unit': line.move_id.purchase_line_id.price_unit,
                'moneda': currency_id.name,
                'price_total':line.move_id.purchase_line_id.price_subtotal,#price_unit * line.quantity, 
                'coste_ant': line.former_cost/line.quantity, 
                'precio_ant': line.product_id.list_price,
                'arancel': 0,
                'product_id': line.product_id.id
            })
            
            if line.cost_line_id.split_method == 'arancel':
                datos[line.move_id.id].update({
                    'arancel': line.additional_landed_cost,
                })
            
            else:
                datos[line.move_id.id].update({
                   str(line.cost_line_id.id): line.additional_landed_cost,
                })
                cost_total_by_product.setdefault(line.move_id.id, 0)
                cost_total_by_product[line.move_id.id] += line.additional_landed_cost
                 
        cost_total = sum([i['valor'] for i in datos.values()])
       
        for move_id, data_dict in datos.items():
          
            product_id = datos.get(move_id).get('product_id')
          
            row_pos = self._write_line(
                ws, row_pos, ws_params, col_specs_section='data',
                render_space={
                    'line': data_dict,
                    'porcent': data_dict['valor'] / cost_total,
                    'cost_total': cost_total_by_product[move_id],
                    'coste_unidad': (
                        data_dict['valor']
                        + cost_total_by_product[move_id]
                        + data_dict['arancel']
                    ) / (data_dict['qty'] or 1)
                },
                default_format=self.format_tcell_left)
        
        costo_ids = self.env['stock.landed.cost.lines'].search([('cost_id', '=', run_ids.id)])
        coste_data = []
        arancel_total = 0
        for i in costo_ids:
            if i.split_method == 'arancel':
                arancel_total += i.price_unit
                continue

            coste_data.append(
                {
                    'costo': i.name,
                    'price': i.price_unit

                }
            )

        if arancel_total:
            coste_data.append(
                {
                    'costo': 'Arancel',
                    'price': arancel_total

                }
            )
            
        params = self._get_costes_params()[0]
        
        row_pos += 3
        row_pos = self._write_line(
            ws, row_pos, params, col_specs_section='header',
            default_format=self.format_theader_yellow_left)
        for data_dict in coste_data:
            row_pos = self._write_line(
                ws, row_pos, params, col_specs_section='data',
                render_space={
                    'line': data_dict,
                },
                default_format=self.format_tcell_left)
