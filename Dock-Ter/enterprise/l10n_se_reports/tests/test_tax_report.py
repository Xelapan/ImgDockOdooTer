# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.account_reports.tests.account_sales_report_common import AccountSalesReportCommon
from odoo.tests import tagged
from freezegun import freeze_time


@tagged('post_install_l10n', 'post_install', '-at_install')
class SwedishTaxReportTest(AccountSalesReportCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref='l10n_se.l10nse_chart_template'):
        super().setUpClass(chart_template_ref=chart_template_ref)

    @classmethod
    def setup_company_data(cls, company_name, chart_template=None, **kwargs):
        res = super().setup_company_data(company_name, chart_template=chart_template, **kwargs)
        res['company'].update({
            'country_id': cls.env.ref('base.se').id,
            'vat': 'SE123456789701',
        })
        res['company'].partner_id.update({
            'email': 'jsmith@mail.com',
            'phone': '+32475123456',
        })
        return res

    @freeze_time('2019-12-31')
    def test_generate_xml(self):
        first_tax = self.env['account.tax'].search([('name', '=', 'Beskattningsunderlag vid import 25%'), ('company_id', '=', self.company_data['company'].id)], limit=1)
        second_tax = self.env['account.tax'].search([('name', '=', 'Ingående moms 6%'), ('company_id', '=', self.company_data['company'].id)], limit=1)

        # Create and post a move with two move lines to get some data in the report
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
            'partner_id': self.partner_a.id,
            'invoice_date': '2019-11-12',
            'date': '2019-11-12',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'quantity': 1.0,
                'name': 'product test 1',
                'price_unit': 300,
                'tax_ids': first_tax.ids,
            }), (0, 0, {
                'product_id': self.product_b.id,
                'quantity': 1.0,
                'name': 'product test 2',
                'price_unit': 200,
                'tax_ids': second_tax.ids,
            })]
        })
        move.action_post()

        report = self.env.ref('l10n_se.tax_report')
        options = report._get_options()

        expected_xml = """
        <!DOCTYPE eSKDUpload PUBLIC "-//Skatteverket, Sweden//DTD Skatteverket eSKDUpload-DTD Version 6.0//SV" "https://www1.skatteverket.se/demoeskd/eSKDUpload_6p0.dtd">
        <eSKDUpload Version="6.0">
            <OrgNr>123456-7897</OrgNr>
            <Moms>
                <Period>201911</Period>
                <ForsMomsEjAnnan>0</ForsMomsEjAnnan>
                <UttagMoms>0</UttagMoms>
                <UlagMargbesk>0</UlagMargbesk>
                <HyrinkomstFriv>0</HyrinkomstFriv>
                <InkopVaruAnnatEg>0</InkopVaruAnnatEg>
                <InkopTjanstAnnatEg>0</InkopTjanstAnnatEg>
                <InkopTjanstUtomEg>0</InkopTjanstUtomEg>
                <InkopVaruSverige>0</InkopVaruSverige>
                <InkopTjanstSverige>0</InkopTjanstSverige>
                <MomsUlagImport>300</MomsUlagImport>
                <ForsVaruAnnatEg>0</ForsVaruAnnatEg>
                <ForsVaruUtomEg>0</ForsVaruUtomEg>
                <InkopVaruMellan3p>0</InkopVaruMellan3p>
                <ForsVaruMellan3p>0</ForsVaruMellan3p>
                <ForsTjSkskAnnatEg>0</ForsTjSkskAnnatEg>
                <ForsTjOvrUtomEg>0</ForsTjOvrUtomEg>
                <ForsKopareSkskSverige>0</ForsKopareSkskSverige>
                <ForsOvrigt>0</ForsOvrigt>
                <MomsUtgHog>0</MomsUtgHog>
                <MomsUtgMedel>0</MomsUtgMedel>
                <MomsUtgLag>0</MomsUtgLag>
                <MomsInkopUtgHog>0</MomsInkopUtgHog>
                <MomsInkopUtgMedel>0</MomsInkopUtgMedel>
                <MomsInkopUtgLag>0</MomsInkopUtgLag>
                <MomsImportUtgHog>75</MomsImportUtgHog>
                <MomsImportUtgMedel>0</MomsImportUtgMedel>
                <MomsImportUtgLag>0</MomsImportUtgLag>
                <MomsIngAvdr>-12</MomsIngAvdr>
                <MomsBetala>87</MomsBetala>
                <TextUpplysningMoms />
            </Moms>
        </eSKDUpload>
        """

        self.assertXmlTreeEqual(
            self.get_xml_tree_from_string(self.env[report.custom_handler_model_name].l10n_se_export_tax_report_to_xml(options)['file_content']),
            self.get_xml_tree_from_string(expected_xml)
        )
