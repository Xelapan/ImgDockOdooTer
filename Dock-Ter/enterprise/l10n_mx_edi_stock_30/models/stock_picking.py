# -*- coding: utf-8 -*-
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Picking(models.Model):
    _inherit = 'stock.picking'

    l10n_mx_edi_is_cfdi_needed = fields.Boolean(
        compute='_compute_l10n_mx_edi_is_cfdi_needed',
        store=True,
    )
    l10n_mx_edi_idccp = fields.Char(
        string="IdCCP",
        help="Additional UUID for the Delivery Guide.",
        compute='_compute_l10n_mx_edi_idccp',
    )
    l10n_mx_edi_gross_vehicle_weight = fields.Float(
        string="Gross Vehicle Weight",
        compute="_compute_l10n_mx_edi_gross_vehicle_weight",
        store=True,
        readonly=False,
    )

    @api.depends('company_id', 'picking_type_code')
    def _compute_l10n_mx_edi_is_cfdi_needed(self):
        for picking in self:
            picking.l10n_mx_edi_is_cfdi_needed = \
                picking.country_code == 'MX' \
                and picking.picking_type_code in ('incoming', 'outgoing')

    @api.depends('l10n_mx_edi_is_cfdi_needed')
    def _compute_l10n_mx_edi_idccp(self):
        for picking in self:
            if picking.l10n_mx_edi_is_cfdi_needed and not picking.l10n_mx_edi_idccp:
                # The IdCCP must be a 36 characters long RFC 4122 identifier starting with 'CCC'.
                picking.l10n_mx_edi_idccp = f'CCC{str(uuid.uuid4())[3:]}'
            else:
                picking.l10n_mx_edi_idccp = False

    @api.depends('l10n_mx_edi_vehicle_id')
    def _compute_l10n_mx_edi_gross_vehicle_weight(self):
        for picking in self:
            if picking.l10n_mx_edi_vehicle_id and not picking.l10n_mx_edi_gross_vehicle_weight:
                picking.l10n_mx_edi_gross_vehicle_weight = picking.l10n_mx_edi_vehicle_id.gross_vehicle_weight
            else:
                picking.l10n_mx_edi_gross_vehicle_weight = picking.l10n_mx_edi_gross_vehicle_weight

    def _l10n_mx_edi_check_required_data(self):
        # EXTENDS 'l10n_mx_edi_stock'
        super()._l10n_mx_edi_check_required_data()

        for picking in self:
            if picking.l10n_mx_edi_vehicle_id and not picking.l10n_mx_edi_gross_vehicle_weight:
                raise UserError(_("Please define a gross vehicle weight."))

    def _l10n_mx_edi_get_picking_cfdi_values(self):
        # EXTENDS 'l10n_mx_edi_stock'
        cfdi_values = super()._l10n_mx_edi_get_picking_cfdi_values()
        cfdi_values['idccp'] = self.l10n_mx_edi_idccp

        if self.l10n_mx_edi_vehicle_id:
            cfdi_values['peso_bruto_vehicular'] = self.l10n_mx_edi_gross_vehicle_weight

        return cfdi_values

    def _l10n_mx_edi_dg_render(self, values):
        # OVERRIDES 'l10n_mx_edi_stock'
        cfdi = self.env['ir.qweb']._render('l10n_mx_edi_stock_30.cfdi_cartaporte_30', values)
        carta_porte_20 = str(cfdi)
        # Since we are inheriting version 2.0 of the Carta Porte template,
        # we need to update both the namespace prefix and its URI to version 3.0.
        carta_porte_30 = carta_porte_20 \
            .replace('cartaporte20', 'cartaporte30') \
            .replace('CartaPorte20', 'CartaPorte30')
        return bytes(carta_porte_30, 'utf-8')

    def _l10n_mx_edi_get_municipio(self, partner):
        """ To be overridden as we do not have the city code without extended"""
        return None
