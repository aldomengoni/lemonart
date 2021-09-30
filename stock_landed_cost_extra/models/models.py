# -*- coding: utf-8 -*-

import logging
from collections import defaultdict, Counter

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from odoo.tools.misc import groupby

_logger = logging.getLogger(__name__)


class LandedCost(models.Model):
    _inherit = 'stock.landed.cost'
    
    no_cost_lines = fields.One2many('stock.landed.cost.lines.remove', 'cost_id')
    product_list_ids = fields.One2many('stock.landed.cost.product.list', 'cost_id')
    cost_summary_ids = fields.One2many('stock.landed.cost.summary', 'cost_id')
    
    def get_valuation_lines(self):
        company_currency = self.company_id.currency_id
        self.ensure_one()
        lines = []

        for move in self.picking_ids.move_lines:
            if move.product_id.valuation != 'real_time' or move.product_id.cost_method not in ('fifo', 'average') or move.state == 'cancel':
                continue

            vals = {
                'product_id': move.product_id.id,
                'move_id': move.id,
                'quantity': move.product_qty,
                'former_cost': sum(move.stock_valuation_layer_ids.mapped('value')),
                'weight': move.product_id.weight * move.product_qty,
                'volume': move.product_id.volume * move.product_qty
            }
            
#             if vals.get('former_cost', 0) <= 0.01:
            for i in move.stock_valuation_layer_ids:
                purchase_line = i.stock_move_id.purchase_line_id
                purchase_currency = purchase_line.order_id.currency_id

                date = purchase_line.order_id.invoice_ids[-1].date if purchase_line.order_id.invoice_ids else self.date

                amount = purchase_currency._convert(purchase_line.price_subtotal, company_currency, self.company_id, date)
            vals['former_cost'] = amount
                
            lines.append(vals)

        if not lines:
            target_model_descriptions = dict(self._fields['target_model']._description_selection(self.env))
            raise UserError(_("You cannot apply landed costs on the chosen %s(s). Landed costs can only be applied for products with automated inventory valuation and FIFO or average costing method.", target_model_descriptions[self.target_model]))
        return lines

    def get_product(self):
        if not self.picking_ids:
            raise UserError(_('You must select at least one transfer.'))
        
        self.product_list_ids.unlink()
        
        listado = []
        products = []
        for pick in self.picking_ids:
            for line in pick.move_lines:
                products.append((0, 0, {
                    'move_id':line.id,
                    'product_id': line.product_id.id,
                    'cost_id': self.id,
                    'name': line.product_id.name,
                }))
        
        self.product_list_ids = products

    def remove_arancel(self):
        arancel = self.cost_lines.filtered(lambda l: l.arancel_product_id)
        arancel.unlink()

    def set_aranceles(self):
        product = self.env['product.product'].search([('default_code' ,'=', 'arancel')])
        if not product:
            raise UserError(_('You do not have an additional cost configured with an internal reference "arancel".'))

        self.remove_arancel()

        account_id = product.property_account_expense_id or product.categ_id.property_account_expense_categ_id
        aranceles = []
        for product_list in self.product_list_ids:
            if product_list.arancel:
                aranceles.append(
                    (0, 0, {
                        'move_id': product_list.move_id.id,
                        'product_id': product.id,
                        'account_id': account_id.id,
                        'price_unit': product_list.arancel,
                        'arancel_product_id': product_list.product_id.id,
                        'split_method': 'arancel',
                        'name': 'Arancel: %s' % product_list.product_id.display_name
                    })
                )
        if aranceles:
            self.cost_lines = aranceles
                
    def compute_landed_cost(self):
        AdjustementLines = self.env['stock.valuation.adjustment.lines']
        AdjustementLines.search([('cost_id', 'in', self.ids)]).unlink()

        NoCost = self.env['stock.landed.cost.lines.remove']
        
        cost_totals_type = {}
        digits = self.env['decimal.precision'].precision_get('Product Price')
        towrite_dict = {}
        for cost in self.filtered(lambda cost: cost.picking_ids):

            total_line = 0.0
            all_val_line_values = cost.get_valuation_lines()
            for val_line_values in all_val_line_values:
                for cost_line in cost.cost_lines:
                    #para prevenir que otros productos tengan el arancel que no le corresponde en cero (0)
                    if cost_line.split_method  == 'arancel':
                        if cost_line.move_id.id != val_line_values.get('move_id'):
                            continue
                            
                    totals = {
                        'total_qty': 0.0,
                        'total_cost': 0.0,
                        'total_weight': 0.0,
                        'total_volume': 0.0,
                        'total_line': 0.0,
                    }
                    
                    no_cost = NoCost.search([
                        ('cost_line_id', '=', cost_line.id),
                        ('product_list_id.product_id', '=', val_line_values.get('product_id'))
                    ])
                    
                    if no_cost: continue
                    
                    totals.update({
                        'total_qty': val_line_values.get('quantity', 0.0),
                        'total_cost': val_line_values.get('former_cost', 0.0),
                        'total_weight': val_line_values.get('weight', 0.0),
                        'total_volume': val_line_values.get('volume', 0.0),
                        'total_line': 1,
                    })
                    
                    temp = Counter(totals)
                    if cost_line.id not in cost_totals_type:
                        cost_totals_type[cost_line.id] = temp
                        
                    else:
                        cost_totals_type[cost_line.id] += temp
                        
                    val_line_values.update({'cost_id': cost.id, 'cost_line_id': cost_line.id})
                    self.env['stock.valuation.adjustment.lines'].create(val_line_values)

                total_line += 1

            for line in cost.cost_lines:
                value_split = 0.0
                for valuation in cost.valuation_adjustment_lines:
                    value = 0.0
                   
                    if valuation.cost_line_id and valuation.cost_line_id.id == line.id:
                        cost_totals = cost_totals_type[line.id]
                        
                        if line.split_method == 'by_quantity' and cost_totals.get('total_qty'):
                            per_unit = (line.price_unit / cost_totals.get('total_qty'))
                            value = valuation.quantity * per_unit
                            
                        elif line.split_method == 'by_weight' and cost_totals.get('total_weight'):
                            per_unit = (line.price_unit / cost_totals.get('total_weight'))
                            value = valuation.weight * per_unit
                            
                        elif line.split_method == 'by_volume' and cost_totals.get('total_volume'):
                            per_unit = (line.price_unit / cost_totals.get('total_volume'))
                            value = valuation.volume * per_unit
                            
                        elif line.split_method == 'equal':
                            value = (line.price_unit / cost_totals.get('total_line'))
                            
                        elif line.split_method == 'by_current_cost_price' and cost_totals.get('total_cost'):
                        #    per_unit = (line.price_unit / cost_totals.get('total_cost'))
                        #    value = valuation.former_cost * per_unit

                        #elif line.split_method == 'custom' and cost_totals.get('total_cost'):
                            porcent = valuation.former_cost / cost_totals.get('total_cost')
                            value = line.price_unit * porcent
                            

                        elif line.split_method == 'arancel':
                            if line.move_id.id == valuation.move_id.id:
                                value = line.price_unit
                    
                            else:
                                continue
                            
                        else:
                            value = (line.price_unit / total_line)
                       
                        if digits:
                            value = tools.float_round(value, precision_digits=digits, rounding_method='UP')
                            fnc = min if line.price_unit > 0 else max
                            value = fnc(value, line.price_unit - value_split)
                            value_split += value
                        
                        if valuation.id not in towrite_dict:
                            towrite_dict[valuation.id] = value
                        else:
                            towrite_dict[valuation.id] += value
                            
        for key, value in towrite_dict.items():
            AdjustementLines.browse(key).write({'additional_landed_cost': value})

        self.set_cost_summary()
        return True

    def set_cost_summary(self):
        self.cost_summary_ids.unlink()
        group_adj_lines = groupby(self.valuation_adjustment_lines, lambda l: l.move_id)

        lines_data = []
        for group, values in group_adj_lines:
            additional_cost = sum([i.additional_landed_cost for i in values])
            adjustment_product = values[0]
            former_cost = adjustment_product.former_cost
            final_cost = former_cost + additional_cost

            lines_data.append(
                (0, 0, {'product_id': adjustment_product.product_id.id,
                        'quantity': adjustment_product.quantity,
                        'former_cost': former_cost,
                        'additional_cost': additional_cost,
                        'final_cost': final_cost,
                        'cost_unit': final_cost / adjustment_product.quantity,
                      }
                )
            )

        self.cost_summary_ids = lines_data



split_method = [
    ('equal', 'Equal'),
    ('by_quantity', 'By Quantity'),
    ('by_current_cost_price', 'By Current Cost'),
    ('by_weight', 'By Weight'),
    ('by_volume', 'By Volume'),
    ('arancel', 'Arancel')
]
    
class LandedCostLine(models.Model):
    _inherit = 'stock.landed.cost.lines'

    split_method = fields.Selection(split_method)
    arancel_product_id = fields.Many2one('product.product')
    move_id = fields.Many2one('stock.move', string='Movimiento de Existencia')

    
class LandedCostLinesRemove(models.Model):
    _name = 'stock.landed.cost.lines.remove'
    _description = 'Stock Landed Cost Lines Remove'
    
    cost_id = fields.Many2one('stock.landed.cost', string='Landed Cost')
    cost_line_id = fields.Many2one('stock.landed.cost.lines', string='Costo')
    product_list_id = fields.Many2one('stock.landed.cost.product.list', string='Product')


class LandedCostProductList(models.Model):
    _name = 'stock.landed.cost.product.list'
    _description = 'Landed Cost Product List'
    
    name = fields.Char()
    cost_id = fields.Many2one('stock.landed.cost', string='Landed Cost')
    product_id = fields.Many2one('product.product', string='Product')
    arancel = fields.Float(string='Arancel')
    move_id = fields.Many2one('stock.move', string='Movimiento de Existencia')
    picking_id = fields.Many2one('stock.picking', string='Conduce', related='move_id.picking_id')


class LandedCostSummary(models.Model):
    _name = 'stock.landed.cost.summary'
    _description = 'Landed Cost Sumarry'

    cost_id = fields.Many2one('stock.landed.cost', string='Landed Cost')
    product_id = fields.Many2one('product.product', string='Product')
    quantity = fields.Float(string='Quantity')
    former_cost = fields.Float(string='Former Cost')
    additional_cost = fields.Float(string='Additional Cost')
    final_cost = fields.Float(string='Final Cost')
    cost_unit = fields.Float(string='Cost Unit')
