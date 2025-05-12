# -*- coding: utf-8 -*-
from freezegun import freeze_time

from odoo.tests import tagged
from .common import TestMXDeliveryGuideCommon


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestCFDIPickingXml(TestMXDeliveryGuideCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.city_id = cls.env.ref('l10n_mx_edi_extended.res_city_mx_chh_032').id

        cls.partner_b.write({
            'street': 'Nevada Street',
            'city': 'Carson City',
            'country_id': cls.env.ref('base.us').id,
            'state_id': cls.env.ref('base.state_us_23').id,
            'zip': 39301,
            'vat': '123456789',
        })

    @freeze_time('2017-01-01')
    def test_delivery_guide_30_outgoing(self):
        picking = self.create_picking()
        picking.l10n_mx_edi_gross_vehicle_weight = 2.0
        cfdi = picking._l10n_mx_edi_create_delivery_guide()

        expected_cfdi = """
            <cfdi:Comprobante
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
                xmlns:cartaporte30="http://www.sat.gob.mx/CartaPorte30"
                Moneda="XXX"
                Serie="NWHOUT"
                SubTotal="0"
                TipoDeComprobante="T"
                Total="0"
                Version="4.0"
                Exportacion="01"
                xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd http://www.sat.gob.mx/CartaPorte30 http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte30.xsd http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte30/CartaPorte30.xsd"
                Fecha="___ignore___"
                Folio="___ignore___"
                LugarExpedicion="20928">
                <cfdi:Emisor Nombre="ESCUELA KEMPER URGATE" RegimenFiscal="601" Rfc="EKU9003173C9"/>
                <cfdi:Receptor UsoCFDI="S01" Nombre="ESCUELA KEMPER URGATE" Rfc="EKU9003173C9" DomicilioFiscalReceptor="20928" RegimenFiscalReceptor="601"/>
                <cfdi:Conceptos>
                    <cfdi:Concepto Importe="0.00" ValorUnitario="0.00" ObjetoImp="01" NoIdentificacion="01" Cantidad="10.000000" ClaveProdServ="56101500" ClaveUnidad="H87" Descripcion="Product A" Unidad="Units"/>
                </cfdi:Conceptos>
                <cfdi:Complemento>
                    <cartaporte30:CartaPorte Version="3.0" TranspInternac="No" TotalDistRec="120" IdCCP="___ignore___">
                        <cartaporte30:Ubicaciones>
                            <cartaporte30:Ubicacion TipoUbicacion="Origen" IDUbicacion="___ignore___" FechaHoraSalidaLlegada="___ignore___" RFCRemitenteDestinatario="EKU9003173C9">
                                <cartaporte30:Domicilio Calle="Campobasso Norte 3206 - 9000" CodigoPostal="20928" Estado="AGU" Pais="MEX" Municipio="032"/>
                            </cartaporte30:Ubicacion>
                            <cartaporte30:Ubicacion TipoUbicacion="Destino" IDUbicacion="___ignore___" DistanciaRecorrida="120" FechaHoraSalidaLlegada="___ignore___" RFCRemitenteDestinatario="ICV060329BY0">
                                <cartaporte30:Domicilio Calle="Street Calle" CodigoPostal="33826" Estado="CHH" Pais="MEX" Municipio="032"/>
                            </cartaporte30:Ubicacion>
                        </cartaporte30:Ubicaciones>
                        <cartaporte30:Mercancias NumTotalMercancias="1" PesoBrutoTotal="10.000" UnidadPeso="KGM">
                            <cartaporte30:Mercancia BienesTransp="56101500" Cantidad="10.000000" ClaveUnidad="H87" Descripcion="Product A" PesoEnKg="10.000">
                                <cartaporte30:CantidadTransporta Cantidad="10.000000" IDOrigen="___ignore___" IDDestino="DE000005"/>
                            </cartaporte30:Mercancia>
                            <cartaporte30:Autotransporte NumPermisoSCT="DEMOPERMIT" PermSCT="TPAF10">
                                <cartaporte30:IdentificacionVehicular AnioModeloVM="2020" ConfigVehicular="T3S1" PlacaVM="ABC123" PesoBrutoVehicular="2.0"/>
                                <cartaporte30:Seguros AseguraRespCivil="DEMO INSURER" PolizaRespCivil="DEMO POLICY"/>
                                <cartaporte30:Remolques>
                                    <cartaporte30:Remolque SubTipoRem="CTR003" Placa="trail1"/>
                                </cartaporte30:Remolques>
                            </cartaporte30:Autotransporte>
                        </cartaporte30:Mercancias>
                        <cartaporte30:FiguraTransporte>
                            <cartaporte30:TiposFigura TipoFigura="01" RFCFigura="VAAM130719H60" NumLicencia="a234567890" NombreFigura="Amigo Pedro">
                            </cartaporte30:TiposFigura>
                            <cartaporte30:TiposFigura TipoFigura="02" RFCFigura="EKU9003173C9" NombreFigura="ESCUELA KEMPER URGATE">
                                <cartaporte30:PartesTransporte ParteTransporte="PT05"/>
                            </cartaporte30:TiposFigura>
                        </cartaporte30:FiguraTransporte>
                    </cartaporte30:CartaPorte>
                </cfdi:Complemento>
            </cfdi:Comprobante>
        """
        current_etree = self.get_xml_tree_from_string(cfdi)
        expected_etree = self.get_xml_tree_from_string(expected_cfdi)
        self.assertXmlTreeEqual(current_etree, expected_etree)

    @freeze_time('2017-01-01')
    def test_delivery_guide_30_incoming(self):
        picking = self.create_picking(picking_type_id=self.new_wh.in_type_id.id)
        picking.l10n_mx_edi_gross_vehicle_weight = 2.0
        cfdi = picking._l10n_mx_edi_create_delivery_guide()

        expected_cfdi = """
            <cfdi:Comprobante
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
                xmlns:cartaporte30="http://www.sat.gob.mx/CartaPorte30"
                Moneda="XXX"
                Serie="NWHIN"
                SubTotal="0"
                TipoDeComprobante="T"
                Total="0"
                Version="4.0"
                Exportacion="01"
                xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd http://www.sat.gob.mx/CartaPorte30 http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte30.xsd http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte30/CartaPorte30.xsd"
                Fecha="___ignore___"
                Folio="___ignore___"
                LugarExpedicion="20928">
                <cfdi:Emisor Nombre="ESCUELA KEMPER URGATE" RegimenFiscal="601" Rfc="EKU9003173C9"/>
                <cfdi:Receptor UsoCFDI="S01" Nombre="ESCUELA KEMPER URGATE" Rfc="EKU9003173C9" DomicilioFiscalReceptor="20928" RegimenFiscalReceptor="601"/>
                <cfdi:Conceptos>
                    <cfdi:Concepto Importe="0.00" ValorUnitario="0.00" ObjetoImp="01" NoIdentificacion="01" Cantidad="10.000000" ClaveProdServ="56101500" ClaveUnidad="H87" Descripcion="Product A" Unidad="Units">
                    </cfdi:Concepto>
                </cfdi:Conceptos>
                <cfdi:Complemento>
                    <cartaporte30:CartaPorte Version="3.0" TranspInternac="No" TotalDistRec="120" IdCCP="___ignore___">
                        <cartaporte30:Ubicaciones>
                            <cartaporte30:Ubicacion TipoUbicacion="Origen" IDUbicacion="___ignore___" FechaHoraSalidaLlegada="2016-12-31T18:00:00" RFCRemitenteDestinatario="ICV060329BY0">
                                <cartaporte30:Domicilio Calle="Street Calle" CodigoPostal="33826" Estado="CHH" Pais="MEX" Municipio="032"/>
                            </cartaporte30:Ubicacion>
                            <cartaporte30:Ubicacion TipoUbicacion="Destino" IDUbicacion="___ignore___" DistanciaRecorrida="120" FechaHoraSalidaLlegada="2016-12-31T18:00:00" RFCRemitenteDestinatario="EKU9003173C9">
                                <cartaporte30:Domicilio Calle="Campobasso Norte 3206 - 9000" CodigoPostal="20928" Estado="AGU" Pais="MEX" Municipio="032"/>
                            </cartaporte30:Ubicacion>
                        </cartaporte30:Ubicaciones>
                        <cartaporte30:Mercancias NumTotalMercancias="1" PesoBrutoTotal="10.000" UnidadPeso="KGM">
                            <cartaporte30:Mercancia BienesTransp="56101500" Cantidad="10.000000" ClaveUnidad="H87" Descripcion="Product A" PesoEnKg="10.000">
                                <cartaporte30:CantidadTransporta Cantidad="10.000000" IDOrigen="___ignore___" IDDestino="___ignore___"/>
                            </cartaporte30:Mercancia>
                            <cartaporte30:Autotransporte NumPermisoSCT="DEMOPERMIT" PermSCT="TPAF10">
                                <cartaporte30:IdentificacionVehicular AnioModeloVM="2020" ConfigVehicular="T3S1" PlacaVM="ABC123" PesoBrutoVehicular="2.0"/>
                                <cartaporte30:Seguros AseguraRespCivil="DEMO INSURER" PolizaRespCivil="DEMO POLICY"/>
                                <cartaporte30:Remolques>
                                    <cartaporte30:Remolque SubTipoRem="CTR003" Placa="trail1"/>
                                </cartaporte30:Remolques>
                            </cartaporte30:Autotransporte>
                        </cartaporte30:Mercancias>
                        <cartaporte30:FiguraTransporte>
                            <cartaporte30:TiposFigura TipoFigura="01" RFCFigura="VAAM130719H60" NumLicencia="a234567890" NombreFigura="Amigo Pedro">
                            </cartaporte30:TiposFigura>
                            <cartaporte30:TiposFigura TipoFigura="02" RFCFigura="EKU9003173C9" NombreFigura="ESCUELA KEMPER URGATE">
                                <cartaporte30:PartesTransporte ParteTransporte="PT05"/>
                            </cartaporte30:TiposFigura>
                        </cartaporte30:FiguraTransporte>
                    </cartaporte30:CartaPorte>
                </cfdi:Complemento>
            </cfdi:Comprobante>
        """
        current_etree = self.get_xml_tree_from_string(cfdi)
        expected_etree = self.get_xml_tree_from_string(expected_cfdi)
        self.assertXmlTreeEqual(current_etree, expected_etree)

    @freeze_time('2017-01-01')
    def test_delivery_guide_comex_30_outgoing(self):
        self.productA.l10n_mx_edi_material_type = '05'
        self.productA.l10n_mx_edi_material_description = 'Test material description'

        picking = self.create_picking(partner_id=self.partner_b.id)

        picking.l10n_mx_edi_gross_vehicle_weight = 2.0
        picking.l10n_mx_edi_customs_document_type_id = self.env.ref('l10n_mx_edi_stock_extended_30.l10n_mx_edi_customs_document_type_02').id
        picking.l10n_mx_edi_customs_doc_identification = '0123456789'

        expected_cfdi = """
            <cfdi:Comprobante
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
                xmlns:cartaporte30="http://www.sat.gob.mx/CartaPorte30"
                Moneda="XXX"
                Serie="NWHOUT"
                SubTotal="0"
                TipoDeComprobante="T"
                Total="0"
                Version="4.0"
                Exportacion="01"
                xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd http://www.sat.gob.mx/CartaPorte30 http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte30.xsd http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte30/CartaPorte30.xsd"
                Fecha="___ignore___"
                Folio="___ignore___"
                LugarExpedicion="20928">
                <cfdi:Emisor Nombre="ESCUELA KEMPER URGATE" RegimenFiscal="601" Rfc="EKU9003173C9"/>
                <cfdi:Receptor UsoCFDI="S01" Nombre="ESCUELA KEMPER URGATE" Rfc="EKU9003173C9" DomicilioFiscalReceptor="20928" RegimenFiscalReceptor="601"/>
                <cfdi:Conceptos>
                    <cfdi:Concepto Importe="0.00" ValorUnitario="0.00" ObjetoImp="01" NoIdentificacion="01" Cantidad="10.000000" ClaveProdServ="56101500" ClaveUnidad="H87" Descripcion="Product A" Unidad="Units">
                    </cfdi:Concepto>
                </cfdi:Conceptos>
                <cfdi:Complemento>
                    <cartaporte30:CartaPorte Version="3.0" TranspInternac="Sí" TotalDistRec="120" EntradaSalidaMerc="Salida" ViaEntradaSalida="01" PaisOrigenDestino="USA" IdCCP="___ignore___">
                        <cartaporte30:Ubicaciones>
                            <cartaporte30:Ubicacion TipoUbicacion="Origen" IDUbicacion="___ignore___" FechaHoraSalidaLlegada="___ignore___" RFCRemitenteDestinatario="EKU9003173C9">
                                <cartaporte30:Domicilio Calle="Campobasso Norte 3206 - 9000" CodigoPostal="20928" Estado="AGU" Pais="MEX" Municipio="032"/>
                            </cartaporte30:Ubicacion>
                            <cartaporte30:Ubicacion TipoUbicacion="Destino" IDUbicacion="___ignore___" DistanciaRecorrida="120" FechaHoraSalidaLlegada="___ignore___" RFCRemitenteDestinatario="XEXX010101000" NumRegIdTrib="123456789" ResidenciaFiscal="USA">
                                <cartaporte30:Domicilio Calle="Nevada Street" CodigoPostal="39301" Estado="NV" Pais="USA" Municipio="Carson City"/>
                            </cartaporte30:Ubicacion>
                        </cartaporte30:Ubicaciones>
                        <cartaporte30:Mercancias NumTotalMercancias="1" PesoBrutoTotal="10.000" UnidadPeso="KGM">
                            <cartaporte30:Mercancia BienesTransp="56101500" Cantidad="10.000000" ClaveUnidad="H87" Descripcion="Product A" PesoEnKg="10.000" TipoMateria="05" DescripcionMateria="Test material description">
                                <cartaporte30:DocumentacionAduanera xmlns:cartaporte30="http://www.sat.gob.mx/CartaPorte30" TipoDocumento="02" IdentDocAduanero="0123456789"/>
                                <cartaporte30:CantidadTransporta Cantidad="10.000000" IDOrigen="___ignore___" IDDestino="DE000005"/>
                            </cartaporte30:Mercancia>
                            <cartaporte30:Autotransporte NumPermisoSCT="DEMOPERMIT" PermSCT="TPAF10">
                                <cartaporte30:IdentificacionVehicular AnioModeloVM="2020" ConfigVehicular="T3S1" PlacaVM="ABC123" PesoBrutoVehicular="2.0"/>
                                <cartaporte30:Seguros AseguraRespCivil="DEMO INSURER" PolizaRespCivil="DEMO POLICY"/>
                                <cartaporte30:Remolques>
                                    <cartaporte30:Remolque SubTipoRem="CTR003" Placa="trail1"/>
                                </cartaporte30:Remolques>
                            </cartaporte30:Autotransporte>
                        </cartaporte30:Mercancias>
                        <cartaporte30:FiguraTransporte>
                            <cartaporte30:TiposFigura TipoFigura="01" RFCFigura="VAAM130719H60" NumLicencia="a234567890" NombreFigura="Amigo Pedro">
                            </cartaporte30:TiposFigura>
                            <cartaporte30:TiposFigura TipoFigura="02" RFCFigura="EKU9003173C9" NombreFigura="ESCUELA KEMPER URGATE">
                                <cartaporte30:PartesTransporte ParteTransporte="PT05"/>
                            </cartaporte30:TiposFigura>
                        </cartaporte30:FiguraTransporte>
                    </cartaporte30:CartaPorte>
                </cfdi:Complemento>
            </cfdi:Comprobante>
        """

        current_etree = self.get_xml_tree_from_string(picking._l10n_mx_edi_create_delivery_guide())
        expected_etree = self.get_xml_tree_from_string(expected_cfdi)
        self.assertXmlTreeEqual(current_etree, expected_etree)

    @freeze_time('2017-01-01')
    def test_delivery_guide_comex_30_incoming(self):
        self.productA.l10n_mx_edi_material_type = '01'

        picking = self.create_picking(partner_id=self.partner_b.id, picking_type_id=self.new_wh.in_type_id.id)

        picking.l10n_mx_edi_gross_vehicle_weight = 2.0
        picking.l10n_mx_edi_customs_document_type_id = self.env.ref('l10n_mx_edi_stock_extended_30.l10n_mx_edi_customs_document_type_01').id
        picking.l10n_mx_edi_importer_id = self.partner_a.id

        expected_cfdi = """
            <cfdi:Comprobante
                xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
                xmlns:cartaporte30="http://www.sat.gob.mx/CartaPorte30"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                Moneda="XXX"
                Serie="NWHIN"
                SubTotal="0"
                TipoDeComprobante="T"
                Total="0"
                Version="4.0"
                Exportacion="01"
                xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd http://www.sat.gob.mx/CartaPorte30 http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte/CartaPorte30.xsd http://www.sat.gob.mx/sitio_internet/cfd/CartaPorte30/CartaPorte30.xsd"
                Fecha="___ignore___"
                Folio="___ignore___"
                LugarExpedicion="20928">
                <cfdi:Emisor Nombre="ESCUELA KEMPER URGATE" RegimenFiscal="601" Rfc="EKU9003173C9"/>
                <cfdi:Receptor UsoCFDI="S01" Nombre="ESCUELA KEMPER URGATE" Rfc="EKU9003173C9" DomicilioFiscalReceptor="20928" RegimenFiscalReceptor="601"/>
                <cfdi:Conceptos>
                    <cfdi:Concepto Importe="0.00" ValorUnitario="0.00" ObjetoImp="01" NoIdentificacion="01" Cantidad="10.000000" ClaveProdServ="56101500" ClaveUnidad="H87" Descripcion="Product A" Unidad="Units">
                    </cfdi:Concepto>
                </cfdi:Conceptos>
                <cfdi:Complemento>
                    <cartaporte30:CartaPorte Version="3.0" TranspInternac="Sí" TotalDistRec="120" EntradaSalidaMerc="Entrada" ViaEntradaSalida="01" PaisOrigenDestino="USA" IdCCP="___ignore___">
                        <cartaporte30:Ubicaciones>
                            <cartaporte30:Ubicacion TipoUbicacion="Origen" IDUbicacion="___ignore___" FechaHoraSalidaLlegada="___ignore___" RFCRemitenteDestinatario="XEXX010101000" NumRegIdTrib="123456789" ResidenciaFiscal="USA">
                                <cartaporte30:Domicilio Calle="Nevada Street" CodigoPostal="39301" Estado="NV" Pais="USA" Municipio="Carson City"/>
                            </cartaporte30:Ubicacion>
                            <cartaporte30:Ubicacion TipoUbicacion="Destino" IDUbicacion="___ignore___" DistanciaRecorrida="120" FechaHoraSalidaLlegada="___ignore___" RFCRemitenteDestinatario="EKU9003173C9">
                                <cartaporte30:Domicilio Calle="Campobasso Norte 3206 - 9000" CodigoPostal="20928" Estado="AGU" Pais="MEX" Municipio="032"/>
                            </cartaporte30:Ubicacion>
                        </cartaporte30:Ubicaciones>
                        <cartaporte30:Mercancias NumTotalMercancias="1" PesoBrutoTotal="10.000" UnidadPeso="KGM">
                            <cartaporte30:Mercancia BienesTransp="56101500" Cantidad="10.000000" ClaveUnidad="H87" Descripcion="Product A" PesoEnKg="10.000" TipoMateria="01">
                                <cartaporte30:DocumentacionAduanera xmlns:cartaporte30="http://www.sat.gob.mx/CartaPorte30" TipoDocumento="01" RFCImpo="ICV060329BY0"/>
                                <cartaporte30:CantidadTransporta Cantidad="10.000000" IDOrigen="___ignore___" IDDestino="___ignore___"/>
                            </cartaporte30:Mercancia>
                            <cartaporte30:Autotransporte NumPermisoSCT="DEMOPERMIT" PermSCT="TPAF10">
                                <cartaporte30:IdentificacionVehicular AnioModeloVM="2020" ConfigVehicular="T3S1" PlacaVM="ABC123" PesoBrutoVehicular="2.0"/>
                                <cartaporte30:Seguros AseguraRespCivil="DEMO INSURER" PolizaRespCivil="DEMO POLICY"/>
                                <cartaporte30:Remolques>
                                    <cartaporte30:Remolque SubTipoRem="CTR003" Placa="trail1"/>
                                </cartaporte30:Remolques>
                            </cartaporte30:Autotransporte>
                        </cartaporte30:Mercancias>
                        <cartaporte30:FiguraTransporte>
                            <cartaporte30:TiposFigura TipoFigura="01" RFCFigura="VAAM130719H60" NumLicencia="a234567890" NombreFigura="Amigo Pedro">
                            </cartaporte30:TiposFigura>
                            <cartaporte30:TiposFigura TipoFigura="02" RFCFigura="EKU9003173C9" NombreFigura="ESCUELA KEMPER URGATE">
                                <cartaporte30:PartesTransporte ParteTransporte="PT05"/>
                            </cartaporte30:TiposFigura>
                        </cartaporte30:FiguraTransporte>
                    </cartaporte30:CartaPorte>
                </cfdi:Complemento>
            </cfdi:Comprobante>
        """

        current_etree = self.get_xml_tree_from_string(picking._l10n_mx_edi_create_delivery_guide())
        expected_etree = self.get_xml_tree_from_string(expected_cfdi)
        self.assertXmlTreeEqual(current_etree, expected_etree)
