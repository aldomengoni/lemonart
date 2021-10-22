# Part of Domincana Premium.
# See LICENSE file for full copyright and licensing details.

import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class InvoiceServiceTypeDetail(models.Model):
    _name = 'invoice.service.type.detail'
    _description = "Invoice Service Type Detail"

    name = fields.Char()
    code = fields.Char(size=2)
    parent_code = fields.Char()

    _sql_constraints = [
        ('code_unique', 'unique(code)', _('Code must be unique')),
    ]


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_invoice_payment_widget(self):
        j = json.loads(self.invoice_payments_widget)
        return j['content'] if j else []

    def _compute_invoice_payment_date(self):
        for inv in self:
            if inv.payment_state in ['in_payment','paid']:
                dates = [
                    payment['date'] for payment in inv._get_invoice_payment_widget()
                ]
                
                if dates:
                    max_date = fields.Date.to_date(max(dates))
                    date_invoice = inv.invoice_date
                    inv.payment_date = max_date if max_date >= date_invoice \
                        else date_invoice

    @api.constrains('line_ids')
    def _check_isr_tax(self):
        """Restrict one ISR tax per invoice"""
        for inv in self:
            isr_count = []
            taxes = inv.line_ids.filtered(lambda line: line.tax_line_id)
            for tax in taxes:
                if tax.tax_group_id.name in ['ISR', 'Retenciones']:
                    isr_count.append(tax.tax_group_id.name)

            if len(isr_count) != len(set(isr_count)):
                raise ValidationError(_('An invoice cannot have multiple'
                                        'withholding taxes.'))

    def _convert_to_local_currency(self, amount):
        sign = -1 if self.move_type in ['in_refund', 'out_refund'] else 1
        if self.currency_id != self.company_id.currency_id:
            currency_id = self.currency_id.with_context(date=self.invoice_date)
            round_curr = currency_id.round
            amount = round_curr(
                currency_id.compute(amount, self.company_id.currency_id))

        return amount * sign

    def _get_tax_line_ids(self):
        return self.line_ids.filtered(lambda line: line.tax_line_id)

    @api.depends('line_ids', 'line_ids.price_subtotal', 'state', 'payment_state')
    def _compute_taxes_fields(self):
        """Compute invoice common taxes fields"""
        for inv in self:
            totals = {}
            proportionality_tax = 0.0
            cost_itbis = 0.0
            invoiced_itbis = 0.0
            if inv.state != 'draft':
                tax_line_ids = inv.line_ids.filtered(lambda line: line.tax_line_id)

                for line in tax_line_ids:
                    group_name = line.tax_line_id.tax_group_id.name
                    totals.setdefault(group_name, 0.0)

                    price_subtotal = inv._convert_to_local_currency(
                        line.price_subtotal
                    )

                    totals[group_name] += price_subtotal
                    
                    if line.tax_line_id.amount > 0 and group_name in ['ITBIS', 'ITBIS 18%']:
                        invoiced_itbis += price_subtotal
                        
                    if line.account_id.account_fiscal_type in ['A29', 'A30']:
                        proportionality_tax += price_subtotal

                    elif line.account_id.account_fiscal_type == 'A51':
                        cost_itbis += price_subtotal

                inv.selective_tax = totals.get('ISC', 0.0)
                inv.other_taxes = totals.get('Otros Impuestos', 0.0)
                inv.legal_tip = totals.get('Propina', 0.0)
                inv.invoiced_itbis = invoiced_itbis
                inv.proportionality_tax = proportionality_tax
                inv.cost_itbis = cost_itbis


                if inv.move_type == 'out_invoice' and any([
                    inv.third_withheld_itbis, inv.third_income_withholding
                ]):
                    inv._compute_invoice_payment_date()

                if inv.move_type == 'in_invoice' and any([
                    inv.withholded_itbis, inv.income_withholding
                ]):
                    inv._compute_invoice_payment_date()

    @api.depends('invoice_line_ids', 'invoice_line_ids.product_id', 'state', 'payment_state')
    def _compute_amount_fields(self):
        """Compute Purchase amount by product type"""
        for inv in self:
            if inv.move_type in ['in_invoice', 'in_refund'] \
                    and inv.state != 'draft':

                service_amount = 0
                good_amount = 0

                for line in inv.invoice_line_ids:
                    if line.product_id.type in ['product', 'consu']:
                        good_amount += line.price_subtotal

                    elif not line.product_id or line.product_id.type == 'service':
                        service_amount += line.price_subtotal

                inv.service_total_amount = inv._convert_to_local_currency(
                    service_amount)
                inv.good_total_amount = inv._convert_to_local_currency(
                    good_amount)

    @api.depends('line_ids', 'line_ids.product_id', 'state', 'payment_state')
    def _compute_isr_withholding_type(self):
        """Compute ISR Withholding Type

        Keyword / Values:
        01 -- Alquileres
        02 -- Honorarios por Servicios
        03 -- Otras Rentas
        04 -- Rentas Presuntas
        05 -- Intereses Pagados a Personas Jurídicas
        06 -- Intereses Pagados a Personas Físicas
        07 -- Retención por Proveedores del Estado
        08 -- Juegos Telefónicos
        """

        for inv in self:
            if inv.move_type == 'in_invoice' and inv.payment_state in ['paid', 'in_payment']:
        
                isr = [
                    tax_line.tax_line_id
                    for tax_line in inv.line_ids
                    if tax_line.tax_line_id.tax_group_id.name == 'ISR'
                ]
                if isr:
                    inv.isr_withholding_type = isr.pop(0).l10n_do_isr_retention_type

    def _get_payment_string(self):
        """Compute Vendor Bills payment method string

        Keyword / Values:
        cash        -- Efectivo
        bank        -- Cheques / Transferencias / Depósitos
        card        -- Tarjeta Crédito / Débito
        credit      -- Compra a Crédito
        swap        -- Permuta
        credit_note -- Notas de Crédito
        mixed       -- Mixto
        """
        payments = []
        p_string = ""
        
        for payment in self._get_invoice_payment_widget():
            payment_id = self.env['account.payment'].browse(
                payment.get('account_payment_id'))
            
            move_id = False
            if payment_id:
                if payment_id.journal_id.type in ['cash', 'bank']:
                    p_string = payment_id.journal_id.l10n_do_payment_form

                if payment_id.journal_id.type in ['purchase']:
                    p_string = 'credit_note'  # payment_id.journal_id.l10n_do_payment_form

            if not payment_id:
                move_id = self.env['account.move'].browse(
                    payment.get('move_id'))
                if move_id.journal_id.type == 'purchase':
                    p_string = 'credit_note'
                elif move_id:
                    p_string = 'swap'

            # If invoice is paid, but the payment doesn't come from
            # a journal, assume it is a credit note
            payment = p_string if payment_id or move_id else 'credit_note'
            payments.append(payment)

        methods = {p for p in payments}
        if len(methods) == 1:
            return list(methods)[0]
        elif len(methods) > 1:
            return 'mixed'

    @api.depends('state', 'payment_state')
    def _compute_in_invoice_payment_form(self):
        for inv in self:
            if inv.move_type == 'in_refund':
                inv.payment_form = '06'

            elif inv.payment_state in ['in_payment','paid']:
                payment_dict = {'cash': '01', 'bank': '02', 'card': '03',
                                'credit': '04', 'swap': '05',
                                'credit_note': '06', 'mixed': '07'}
                inv.payment_form = payment_dict.get(inv._get_payment_string())
                              
            else:
                inv.payment_form = '04'

    def _get_payment_move_iterator(self, payment, inv_type, witheld_type):
        payment_id = self.env['account.payment'].browse(
            payment.get('account_payment_id')
        )
        if payment_id:
            # Retenciones en el pago
            if inv_type == 'out_invoice':
                return [
                    move_line.debit
                    for move_line in payment_id.line_ids
                    if move_line.account_id.account_fiscal_type in witheld_type
                ]
            else:
                return [
                    move_line.credit
                    for move_line in payment_id.line_ids
                    if move_line.account_id.account_fiscal_type in witheld_type
                ]
        else:
            # Retenciones en el Pago
            move_id = self.env['account.move'].browse(payment.get('move_id'))
            if move_id:
                if inv_type == 'out_invoice':
                    return [
                        move_line.debit
                        for move_line in move_id.line_ids
                        if move_line.account_id.account_fiscal_type in
                        witheld_type
                    ]
                else:
                    return [
                        move_line.credit
                        for move_line in move_id.line_ids
                        if move_line.account_id.account_fiscal_type in
                        witheld_type
                    ]
            # Retenciones en la factura
            else:
                if inv_type == 'out_invoice':
                    return [move_line.debit
                            for move_line in self.line_ids
                            if move_line.account_id.account_fiscal_type in witheld_type]
                elif inv_type == 'in_invoice':
                    return [move_line.credit 
                            for move_line in self.line_ids
                            if move_line.account_id.account_fiscal_type in witheld_type]


    @api.depends('line_ids.tax_line_id', 'state', 'payment_state')
    def _compute_withheld_taxes(self):
        for inv in self:
            if inv.payment_state in ['in_payment','paid']:
                inv.third_withheld_itbis = 0
                inv.third_income_withholding = 0

                witheld_itbis_types = ['A34', 'A36']
                witheld_isr_types = ['ISR', 'A38']

                if inv.move_type == 'in_invoice':
                    tax_line_ids = inv._get_tax_line_ids()

                    totals = {}
                    for line in tax_line_ids:
                        group_name = line.tax_line_id.tax_group_id.name
                        totals.setdefault(group_name, 0.0)
                        totals.setdefault('Retenciones', 0.0)

                        price_subtotal = inv._convert_to_local_currency(
                            line.price_subtotal
                        )

                        totals[group_name] += price_subtotal
                        
                        if line.tax_line_id.amount < 0 and group_name == 'ITBIS':
                            totals['Retenciones'] += price_subtotal

                    # Monto ITBIS Retenido por impuesto
                    inv.withholded_itbis = totals.get('Retenciones')
                    # Monto Retención Renta por impuesto
                    inv.income_withholding = totals.get('ISR')

                if inv.move_type == 'out_invoice':
                    tax_line_ids = inv._get_tax_line_ids()

                    totals = {}
                    for line in tax_line_ids:

                        # ITBIS Retenido por Terceros
                        inv.third_withheld_itbis += sum([line.debit 
                            if line.account_id.account_fiscal_type in witheld_itbis_types else 0]
                        )

                        # Retención de Renta pr Terceros
                        inv.third_income_withholding += sum([line.debit 
                            if line.account_id.account_fiscal_type in witheld_isr_types else 0]
                        )

                for payment in inv._get_invoice_payment_widget():

                    if inv.move_type == 'out_invoice':
                        # ITBIS Retenido por Terceros
                        inv.third_withheld_itbis += sum(
                            self._get_payment_move_iterator(
                                payment, inv.move_type, witheld_itbis_types))

                        # Retención de Renta pr Terceros
                        inv.third_income_withholding += sum(
                            self._get_payment_move_iterator(
                                payment, inv.move_type, witheld_isr_types))

                    elif inv.move_type == 'in_invoice':
                        # ITBIS Retenido a Terceros
                        inv.withholded_itbis += sum(
                            self._get_payment_move_iterator(
                                payment, inv.move_type, witheld_itbis_types))

                        # Retención de Renta a Terceros
                        inv.income_withholding += sum(
                            self._get_payment_move_iterator(
                                payment, inv.move_type, witheld_isr_types))

    @api.depends('invoiced_itbis', 'cost_itbis', 'state', 'payment_state')
    def _compute_advance_itbis(self):
        for inv in self:
            if inv.state != 'draft':
                inv.advance_itbis = inv.invoiced_itbis - inv.cost_itbis

    #@api.depends('journal_id.purchase_type')
    def _compute_is_exterior(self):
        for inv in self:
            inv.is_exterior = False #True if inv.journal_id.purchase_type == \
                #'exterior' else False

    @api.onchange('service_type')
    def onchange_service_type(self):
        self.service_type_detail = False
        return {
            'domain': {
                'service_type_detail': [
                    ('parent_code', '=', self.service_type)
                    ]
            }
        }

    @api.onchange('journal_id')
    def ext_onchange_journal_id(self):
        self.service_type = False
        self.service_type_detail = False
    
    payment_date = fields.Date(compute='_compute_taxes_fields', store=True)   
    service_total_amount = fields.Monetary(
        compute='_compute_amount_fields',
        store=True,
        currency_field='company_currency_id')
    good_total_amount = fields.Monetary(compute='_compute_amount_fields',
                                        store=True,
                                        currency_field='company_currency_id')
    invoiced_itbis = fields.Monetary(compute='_compute_taxes_fields',
                                     store=True,
                                     currency_field='company_currency_id')
    withholded_itbis = fields.Monetary(compute='_compute_withheld_taxes',
                                       store=True,
                                       currency_field='company_currency_id')
    proportionality_tax = fields.Monetary(compute='_compute_taxes_fields',
                                          store=True,
                                          currency_field='company_currency_id')
    cost_itbis = fields.Monetary(compute='_compute_taxes_fields',
                                 store=True,
                                 currency_field='company_currency_id')
    advance_itbis = fields.Monetary(compute='_compute_advance_itbis',
                                    store=True,
                                    currency_field='company_currency_id')
    isr_withholding_type = fields.Char(compute='_compute_isr_withholding_type',
                                       store=True)
    income_withholding = fields.Monetary(compute='_compute_withheld_taxes',
                                         store=True,
                                         currency_field='company_currency_id')
    selective_tax = fields.Monetary(compute='_compute_taxes_fields',
                                    store=True,
                                    currency_field='company_currency_id')
    other_taxes = fields.Monetary(compute='_compute_taxes_fields',
                                  store=True,
                                  currency_field='company_currency_id')
    legal_tip = fields.Monetary(compute='_compute_taxes_fields',
                                store=True,
                                currency_field='company_currency_id')
    payment_form = fields.Selection([('01', '01 - EFECTIVO'),
                                     ('02', '02 - CHEQUES/TRANSFERENCIAS/DEPÓSITO'),
                                     ('03', '03 - TARJETA CRÉDITO/DÉBITO'),
                                     ('04', '04 - COMPRA A CREDITO'), ('05', '05 -  PERMUTA'),
                                     ('06', '06 - NOTA DE CREDITO'), ('07', '07 - MIXTO')],
                                    compute='_compute_in_invoice_payment_form',
                                    store=True)
    third_withheld_itbis = fields.Monetary(
        compute='_compute_withheld_taxes',
        store=True,
        currency_field='company_currency_id')
    third_income_withholding = fields.Monetary(
        compute='_compute_withheld_taxes',
        store=True,
        currency_field='company_currency_id')
    is_exterior = fields.Boolean(compute='_compute_is_exterior', store=True)
    service_type = fields.Selection([
        ('01', 'Gastos de Personal'),
        ('02', 'Gastos por Trabajos, Suministros y Servicios'),
        ('03', 'Arrendamientos'), ('04', 'Gastos de Activos Fijos'),
        ('05', 'Gastos de Representación'), ('06', 'Gastos Financieros'),
        ('07', 'Gastos de Seguros'),
        ('08', 'Gastos por Regalías y otros Intangibles')
    ])
    service_type_detail = fields.Many2one('invoice.service.type.detail')
    fiscal_status = fields.Selection(
        [('normal', 'Partial'), ('done', 'Reported'), ('blocked', 'Not Sent')],
        copy=False,
        help="* The \'Grey\' status means Partially sent to the dgii,"
        " the retention must be sent when the invoice is paid \n"
        "* The \'Green\' status means reported to the DGII \n"
        "* The \'Red\' status means Not sent to the DGII \n"
        "* The blank status means that the invoice have"
        "not been included in a report."
    )


    @api.model
    def norma_recompute(self):
        """
        This method add all compute fields into []env
        add_todo and then recompute
        all compute fields in case dgii config change and need to recompute.
        :return:
        """
        active_ids = self._context.get("active_ids")
        invoice_ids = self.browse(active_ids)
        for k, v in self.fields_get().items():
            if v.get("store") and v.get("depends"):
                self.env.add_to_compute(self._fields[k], invoice_ids)

        self.recompute()
