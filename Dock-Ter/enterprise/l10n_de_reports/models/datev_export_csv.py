# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import pycompat, float_repr
from odoo.exceptions import ValidationError
from odoo.tools.sql import column_exists, create_column

from datetime import datetime
from collections import namedtuple
import tempfile
import zipfile
import uuid
import io
import re
import os

BalanceKey = namedtuple('BalanceKey', ['from_code', 'to_code', 'partner_id', 'tax_id'])


class AccountDatevCompany(models.Model):
    _inherit = 'res.company'

    # Adding the fields as company_dependent does not break stable policy
    l10n_de_datev_consultant_number = fields.Char(company_dependent=True)
    l10n_de_datev_client_number = fields.Char(company_dependent=True)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_de_datev_identifier = fields.Integer(
        string='Datev Identifier',
        copy=False,
        tracking=True,
        index='btree_not_null',
        help="The Datev identifier is a unique identifier for exchange with the government. "
             "If you had previous exports with another identifier, you can put it here. "
             "If it is 0, then it will take the database id + the value in the system parameter "
             "l10n_de.datev_start_count. "
    )

    @api.constrains('l10n_de_datev_identifier')
    def _check_datev_identifier(self):
        self.flush_model(['l10n_de_datev_identifier'])
        self.env.cr.execute("""
            SELECT 1 FROM res_partner
            WHERE l10n_de_datev_identifier != 0
            GROUP BY l10n_de_datev_identifier
            HAVING COUNT(*) > 1
        """)

        if self.env.cr.dictfetchone():
            raise ValidationError(_('You have already defined a partner with the same Datev identifier. '))


class AccountMoveL10NDe(models.Model):
    _inherit = 'account.move'

    l10n_de_datev_main_account_id = fields.Many2one('account.account', compute='_get_datev_account', store=True)

    def _auto_init(self):
        if column_exists(self.env.cr, "account_move", "l10n_de_datev_main_account_id"):
            return super()._auto_init()

        cr = self.env.cr
        create_column(cr, "account_move", "l10n_de_datev_main_account_id", "int4")
        # If move has an invoice, return invoice's account_id
        cr.execute(
            """
                UPDATE account_move
                   SET l10n_de_datev_main_account_id = r.aid
                  FROM (
                          SELECT l.move_id mid,
                                 FIRST_VALUE(l.account_id) OVER(PARTITION BY l.move_id ORDER BY l.id DESC) aid
                            FROM account_move_line l
                            JOIN account_move m
                              ON m.id = l.move_id
                            JOIN account_account a
                              ON a.id = l.account_id
                           WHERE m.move_type in ('out_invoice', 'out_refund', 'in_refund', 'in_invoice', 'out_receipt', 'in_receipt')
                             AND a.account_type in ('asset_receivable', 'liability_payable')
                       ) r
                WHERE id = r.mid
            """)

        # If move belongs to a bank journal, return the journal's account (debit/credit should normally be the same)
        cr.execute(
            """
            UPDATE account_move
               SET l10n_de_datev_main_account_id = r.aid
              FROM (
                    SELECT m.id mid,
                           j.default_account_id aid
                     FROM account_move m
                     JOIN account_journal j
                       ON m.journal_id = j.id
                    WHERE j.type = 'bank'
                      AND j.default_account_id IS NOT NULL
                   ) r
             WHERE id = r.mid
               AND l10n_de_datev_main_account_id IS NULL
            """)

        # If the move is an automatic exchange rate entry, take the gain/loss account set on the exchange journal
        cr.execute("""
            UPDATE account_move m
               SET l10n_de_datev_main_account_id = r.aid
              FROM (
                    SELECT l.move_id AS mid,
                           l.account_id AS aid
                      FROM account_move_line l
                      JOIN account_move m
                        ON l.move_id = m.id
                      JOIN account_journal j
                        ON m.journal_id = j.id
                      JOIN res_company c
                        ON c.currency_exchange_journal_id = j.id
                     WHERE j.type='general'
                       AND l.account_id = j.default_account_id
                     GROUP BY l.move_id,
                              l.account_id
                    HAVING count(*)=1
                   ) r
             WHERE id = r.mid
               AND l10n_de_datev_main_account_id IS NULL
            """)

        # Look for an account used a single time in the move, that has no originator tax
        query = """
            UPDATE account_move m
               SET l10n_de_datev_main_account_id = r.aid
              FROM (
                    SELECT l.move_id AS mid,
                           min(l.account_id) AS aid
                      FROM account_move_line l
                     WHERE {}
                     GROUP BY move_id
                    HAVING count(*)=1
                   ) r
             WHERE id = r.mid
               AND m.l10n_de_datev_main_account_id IS NULL
            """
        cr.execute(query.format("l.debit > 0"))
        cr.execute(query.format("l.credit > 0"))
        cr.execute(query.format("l.debit > 0 AND l.tax_line_id IS NULL"))
        cr.execute(query.format("l.credit > 0 AND l.tax_line_id IS NULL"))

        return super()._auto_init()

    @api.depends('journal_id', 'line_ids', 'journal_id.default_account_id')
    def _get_datev_account(self):
        for move in self:
            move.l10n_de_datev_main_account_id = value = False
            # If move has an invoice, return invoice's account_id
            if move.is_invoice(include_receipts=True):
                payment_term_lines = move.line_ids.filtered(
                    lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable'))
                if payment_term_lines:
                    move.l10n_de_datev_main_account_id = payment_term_lines[0].account_id
                continue
            # If move belongs to a bank journal, return the journal's account (debit/credit should normally be the same)
            if move.journal_id.type == 'bank' and move.journal_id.default_account_id:
                move.l10n_de_datev_main_account_id = move.journal_id.default_account_id
                continue
            # If the move is an automatic exchange rate entry, take the gain/loss account set on the exchange journal
            elif move.journal_id.type == 'general' and move.journal_id == self.env.company.currency_exchange_journal_id:
                lines = move.line_ids.filtered(lambda r: r.account_id == move.journal_id.default_account_id)

                if len(lines) == 1:
                    move.l10n_de_datev_main_account_id = lines.account_id
                    continue

            # Look for an account used a single time in the move, that has no originator tax
            aml_debit = self.env['account.move.line']
            aml_credit = self.env['account.move.line']
            for aml in move.line_ids:
                if aml.debit > 0:
                    aml_debit += aml
                if aml.credit > 0:
                    aml_credit += aml
            if len(aml_debit.account_id) == 1:
                value = aml_debit.account_id
            elif len(aml_credit.account_id) == 1:
                value = aml_credit.account_id
            else:
                aml_debit_wo_tax_accounts = [a.account_id for a in aml_debit if not a.tax_line_id]
                aml_credit_wo_tax_accounts = [a.account_id for a in aml_credit if not a.tax_line_id]
                if len(aml_debit_wo_tax_accounts) == 1:
                    value = aml_debit_wo_tax_accounts[0]
                elif len(aml_credit_wo_tax_accounts) == 1:
                    value = aml_credit_wo_tax_accounts[0]
            move.l10n_de_datev_main_account_id = value

    def _l10n_de_datev_get_guid(self):
        """ Get the unique identifier for the move based on the db UUID and the move id """
        self.ensure_one()
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        guid = uuid.uuid5(namespace=uuid.UUID(dbuuid), name=str(self.id))
        return str(guid)


class GeneralLedgerCustomHandler(models.AbstractModel):
    _inherit = 'account.general.ledger.report.handler'

    def _custom_options_initializer(self, report, options, previous_options=None):
        """
        Add the invoice lines search domain that common for all countries.
        :param dict options: Report options
        :param dict previous_options: Previous report options
        """
        super()._custom_options_initializer(report, options, previous_options)
        if self.env.company.country_code in ('DE', 'CH', 'AT'):
            options.setdefault('buttons', []).extend((
                {
                    'name': _('Datev (zip)'),
                    'sequence': 30,
                    'action': 'export_file',
                    'action_param': 'l10n_de_datev_export_to_zip',
                    'file_export_type': _('Datev zip'),
                },
                {
                    'name': _('Datev + ATCH (zip)'),
                    'sequence': 40,
                    'action': 'export_file',
                    'action_param': 'l10_de_datev_export_to_zip_and_attach',
                    'file_export_type': _('Datev + batch zip'),
                },
            ))

    def l10_de_datev_export_to_zip_and_attach(self, options):
        options['add_attachments'] = True
        return self.l10n_de_datev_export_to_zip(options)

    def l10n_de_datev_export_to_zip(self, options):
        """
        Check ir_attachment for method _get_path
        create a sha and replace 2 first letters by something not hexadecimal
        Return full_path as 2nd args, use it as name for Zipfile
        Don't need to unlink as it will be done automatically by garbage collector
        of attachment cron
        """
        report = self.env['account.report'].browse(options['report_id'])
        with tempfile.NamedTemporaryFile(mode='w+b', delete=True) as buf:
            with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=False) as zf:
                move_line_ids = []
                for line in report.with_context(print_mode=True)._get_lines({**options, 'unfold_all': True}):
                    model, model_id = report._get_model_info_from_id(line['id'])
                    if model == 'account.move.line':
                        move_line_ids.append(model_id)

                domain = [
                    ('line_ids', 'in', move_line_ids),
                    ('company_id', 'in', report.get_report_company_ids(options)),
                ]
                if options.get('all_entries'):
                    domain += [('state', '!=', 'cancel')]
                else:
                    domain += [('state', '=', 'posted')]
                if options.get('date'):
                    domain += [('date', '<=', options['date']['date_to'])]
                    # cannot set date_from on move as domain depends on the move line account if "strict_range" is False
                domain += report._get_options_journals_domain(options)
                moves = self.env['account.move'].search(domain)
                set_move_line_ids = set(move_line_ids)
                zf.writestr('EXTF_accounting_entries.csv', self._l10n_de_datev_get_csv(options, moves))
                zf.writestr('EXTF_customer_accounts.csv', self._l10n_de_datev_get_partner_list(options, set_move_line_ids, customer=True))
                zf.writestr('EXTF_vendor_accounts.csv', self._l10n_de_datev_get_partner_list(options, set_move_line_ids, customer=False))
                if options.get('add_attachments'):
                    # add all moves attachments in zip file, this is not part of DATEV specs
                    slash_re = re.compile('[\\/]')
                    documents = []
                    for move in moves:
                        # rename files by move name + sequence number (if more than 1 file)
                        # '\' is not allowed in file name, replace by '-'
                        base_name = slash_re.sub('-', move.name)
                        if len(move.attachment_ids) > 1:
                            name_pattern = f'%(base)s-%(index)0.{len(str(len(move.attachment_ids)))}d%(extension)s'
                        else:
                            name_pattern = '%(base)s%(extension)s'
                        for i, attachment in enumerate(move.attachment_ids.sorted('id'), 1):
                            extension = os.path.splitext(attachment.name)[1]
                            name = name_pattern % {'base': base_name, 'index': i, 'extension': extension}
                            zf.writestr(name, attachment.raw)
                            documents.append({
                                'guid': move._l10n_de_datev_get_guid(),
                                'filename': name,
                                'type': 2 if move.is_sale_document() else 1 if move.is_purchase_document() else None,
                            })
                    if documents:
                        metadata_document = self.env['ir.qweb']._render(
                            'l10n_de_reports.datev_export_metadata',
                            values={
                                'documents': documents,
                                'date': fields.Date.today(),
                            },
                        )
                        zf.writestr('document.xml', "<?xml version='1.0' encoding='UTF-8'?>" + str(metadata_document))
            buf.seek(0)
            content = buf.read()
        return {
            'file_name': report.get_default_report_filename('ZIP'),
            'file_content': content,
            'file_type': 'zip'
        }

    def _l10n_de_datev_get_client_number(self):
        consultant_number = self.env.company.l10n_de_datev_consultant_number
        client_number = self.env.company.l10n_de_datev_client_number
        if not consultant_number:
            consultant_number = 99999
        if not client_number:
            client_number = 999
        return [consultant_number, client_number]

    def _l10n_de_datev_get_partner_list(self, options, move_line_ids, customer=True):
        date_to = fields.Date.from_string(options.get('date').get('date_to'))
        fy = self.env.company.compute_fiscalyear_dates(date_to)

        fy = datetime.strftime(fy.get('date_from'), '%Y%m%d')
        datev_info = self._l10n_de_datev_get_client_number()
        account_length = self._l10n_de_datev_get_account_length()

        output = io.BytesIO()
        writer = pycompat.csv_writer(output, delimiter=';', quotechar='"', quoting=2)
        preheader = ['EXTF', 510, 16, 'Debitoren/Kreditoren', 4, None, None, '', '', '', datev_info[0], datev_info[1], fy, account_length,
            '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '']
        header = ['Konto', 'Name (AdressatentypUnternehmen)', 'Name (Adressatentypnatürl. Person)', '', '', '', 'Adressatentyp']
        lines = [preheader, header]

        if len(move_line_ids):
            if customer:
                move_types = ('out_refund', 'out_invoice', 'out_receipt')
            else:
                move_types = ('in_refund', 'in_invoice', 'in_receipt')
            select = """SELECT distinct(aml.partner_id)
                        FROM account_move_line aml
                        LEFT JOIN account_move m
                        ON aml.move_id = m.id
                        WHERE aml.id IN %s
                            AND aml.tax_line_id IS NULL
                            AND aml.debit != aml.credit
                            AND m.move_type IN %s
                            AND aml.account_id != m.l10n_de_datev_main_account_id"""
            self.env.cr.execute(select, (tuple(move_line_ids), move_types))
        partners = self.env['res.partner'].browse([p.get('partner_id') for p in self.env.cr.dictfetchall()])
        for partner in partners:
            if customer:
                code = self._l10n_de_datev_find_partner_account(partner.property_account_receivable_id, partner)
            else:
                code = self._l10n_de_datev_find_partner_account(partner.property_account_payable_id, partner)
            line_value = {
                'code': code,
                'company_name': partner.name if partner.is_company else '',
                'person_name': '' if partner.is_company else partner.name,
                'natural': partner.is_company and '2' or '1'
            }
            # Idiotic program needs to have a line with 243 elements ordered in a given fashion as it
            # does not take into account the header and non mandatory fields
            array = ['' for x in range(243)]
            array[0] = line_value.get('code')
            array[1] = line_value.get('company_name')
            array[2] = line_value.get('person_name')
            array[6] = line_value.get('natural')
            lines.append(array)
        writer.writerows(lines)
        return output.getvalue()

    def _l10n_de_datev_get_account_length(self):
        param_start = self.env['ir.config_parameter'].sudo().get_param('l10n_de.datev_start_count', "100000000")[:9]
        param_start_vendors = self.env['ir.config_parameter'].sudo().get_param('l10n_de.datev_start_count_vendors', "700000000")[:9]

        # The gegenkonto should be 1 length higher than the account length, so we have to substract 1 to the params length
        return max(param_start.isdigit() and len(param_start) or 9, param_start_vendors.isdigit() and len(param_start_vendors) or 9, 5) - 1

    def _l10n_de_datev_find_partner_account(self, account, partner):
        len_param = self._l10n_de_datev_get_account_length() + 1
        if (account.account_type in ('asset_receivable', 'liability_payable') and partner):
            # Check if we have a property as receivable/payable on the partner
            # We use the property because in datev and in germany, partner can be of 2 types
            # important partner which have a specific account number or a virtual partner
            # Which has only a number. To differentiate between the two, if a partner in Odoo
            # explicitely has a receivable/payable account set, we use that account, otherwise
            # we assume it is not an important partner and his datev virtual id will be the
            # l10n_de_datev_identifier set or the id + the start count parameter.
            account = partner.property_account_receivable_id if account.account_type == 'asset_receivable' else partner.property_account_payable_id
            fname = "property_account_receivable_id"         if account.account_type == 'asset_receivable' else "property_account_payable_id"
            prop = self.env['ir.property']._get(fname, "res.partner", partner.id)
            force_datev_id = self.env['ir.config_parameter'].sudo().get_param('l10n_de.force_datev_id', False)
            if not force_datev_id and prop == account:
                return str(account.code).ljust(len_param - 1, '0') if account else ''
            return self._l10n_de_datev_get_account_identifier(account, partner)
        return str(account.code).ljust(len_param - 1, '0') if account else ''

    def _l10n_de_datev_get_account_identifier(self, account, partner):
        len_param = self._l10n_de_datev_get_account_length() + 1
        if account.account_type == 'asset_receivable':
            param_start = self.env['ir.config_parameter'].sudo().get_param('l10n_de.datev_start_count', "100000000")[:9]
            start_count = param_start.isdigit() and int(param_start) or 100000000
        else:
            param_start_vendors = self.env['ir.config_parameter'].sudo().get_param('l10n_de.datev_start_count_vendors', "700000000")[:9]
            start_count = param_start_vendors.isdigit() and int(param_start_vendors) or 700000000
        start_count = int(str(start_count).ljust(len_param, '0'))
        return partner.l10n_de_datev_identifier or start_count + partner.id

    # Source: http://www.datev.de/dnlexom/client/app/index.html#/document/1036228/D103622800029
    def _l10n_de_datev_get_csv(self, options, moves):
        # last 2 element of preheader should be filled by "consultant number" and "client number"
        date_from = fields.Date.from_string(options.get('date').get('date_from'))
        date_to = fields.Date.from_string(options.get('date').get('date_to'))
        fy = self.env.company.compute_fiscalyear_dates(date_to)

        date_from = datetime.strftime(date_from, '%Y%m%d')
        date_to = datetime.strftime(date_to, '%Y%m%d')
        fy = datetime.strftime(fy.get('date_from'), '%Y%m%d')
        datev_info = self._l10n_de_datev_get_client_number()
        account_length = self._l10n_de_datev_get_account_length()

        output = io.BytesIO()
        writer = pycompat.csv_writer(output, delimiter=';', quotechar='"', quoting=2)
        preheader = ['EXTF', 510, 21, 'Buchungsstapel', 7, '', '', '', '', '', datev_info[0], datev_info[1], fy, account_length,
            date_from, date_to, '', '', '', '', 0, 'EUR', '', '', '', '', '', '', '', '', '']
        header = [
            'Umsatz (ohne Soll/Haben-Kz)', 'Soll/Haben-Kennzeichen', 'WKZ Umsatz', 'Kurs', 'Basis-Umsatz',
            'WKZ Basis-Umsatz', 'Konto', 'Gegenkonto (ohne BU-Schlüssel)', 'BU-Schlüssel', 'Belegdatum',
            'Belegfeld 1', 'Belegfeld 2', 'Skonto', 'Buchungstext', 'Postensperre', 'Diverse Adressnummer',
            'Geschäftspartnerbank', 'Sachverhalt', 'Zinssperre', 'Beleglink'
        ]

        lines = [preheader, header]

        for m in moves:
            payment_account = 0  # Used for non-reconciled payments

            move_balance = 0
            counterpart_amount = 0
            last_tax_line_index = 0
            for aml in m.line_ids:
                if aml.debit == aml.credit:
                    # Ignore debit = credit = 0
                    continue

                # account and counterpart account
                to_account_code = str(self._l10n_de_datev_find_partner_account(aml.move_id.l10n_de_datev_main_account_id, aml.partner_id))
                account_code = u'{code}'.format(code=self._l10n_de_datev_find_partner_account(aml.account_id, aml.partner_id))

                # We don't want to have lines with our outstanding payment/receipt as they don't represent real moves
                # So if payment skip one move line to write, while keeping the account
                # and replace bank account for outstanding payment/receipt for the other line

                if aml.payment_id:
                    if payment_account == 0:
                        payment_account = account_code
                        counterpart_amount += aml.balance
                        continue
                    else:
                        to_account_code = payment_account

                # If both account and counteraccount are the same, ignore the line
                if aml.account_id == aml.move_id.l10n_de_datev_main_account_id:
                    if aml.statement_line_id and not aml.payment_id:
                        counterpart_amount += aml.balance
                    continue
                # If line is a tax ignore it as datev requires single line with gross amount and deduct tax itself based
                # on account or on the control key code
                if aml.tax_line_id:
                    continue

                aml_taxes = aml.tax_ids.compute_all(aml.balance, aml.company_id.currency_id, partner=aml.partner_id, handle_price_include=False)
                line_amount = aml_taxes['total_included']
                move_balance += line_amount

                code_correction = ''
                if aml.tax_ids:
                    last_tax_line_index = len(lines)
                    last_tax_line_amount = line_amount
                    codes = set(aml.tax_ids.mapped('l10n_de_datev_code'))
                    if len(codes) == 1:
                        # there should only be one max, else skip code
                        code_correction = codes.pop() or ''

                # reference
                receipt1 = ref = aml.move_id.name
                if aml.move_id.journal_id.type == 'purchase' and aml.move_id.ref:
                    ref = aml.move_id.ref

                # on receivable/payable aml of sales/purchases
                receipt2 = ''
                if to_account_code == account_code and aml.date_maturity:
                    receipt2 = aml.date

                currency = aml.company_id.currency_id

                # Idiotic program needs to have a line with 116 elements ordered in a given fashion as it
                # does not take into account the header and non mandatory fields
                array = ['' for x in range(116)]
                # For DateV, we can't have negative amount on a line, so we need to inverse the amount and inverse the
                # credit/debit symbol.
                array[1] = 'h' if aml.currency_id.compare_amounts(line_amount, 0) < 0 else 's'
                line_amount = abs(line_amount)
                array[0] = float_repr(line_amount, aml.company_id.currency_id.decimal_places).replace('.', ',')
                array[2] = currency.name
                if aml.currency_id != currency:
                    array[3] = str(aml.currency_id.rate).replace('.', ',')
                    array[4] = float_repr(aml.price_total, aml.currency_id.decimal_places).replace('.', ',')
                    array[5] = aml.currency_id.name
                array[6] = account_code
                array[7] = to_account_code
                array[8] = code_correction
                array[9] = datetime.strftime(aml.move_id.date, '%-d%m')
                array[10] = receipt1[-36:]
                array[11] = receipt2
                array[13] = aml.name or ref
                if options.get('add_attachments') and m.attachment_ids:
                    array[19] = f'BEDI"{m._l10n_de_datev_get_guid()}"'
                lines.append(array)
            # In case of epd we actively fix rounding issues by checking the base line and tax line
            # amounts against the move amount missing cent and adjust the vals accordingly.
            # Since here we have to recompute the tax values for each line with tax, we need
            # to replicate the rounding fix logic adding the difference on the last tax line
            # to avoid creating a difference with the source payment move
            if (m.payment_id or m.statement_line_id) and move_balance and counterpart_amount and last_tax_line_index:
                delta_balance = move_balance + counterpart_amount
                if delta_balance:
                    lines[last_tax_line_index][0] = float_repr(abs(last_tax_line_amount - delta_balance), m.company_id.currency_id.decimal_places).replace('.', ',')

        writer.writerows(lines)
        return output.getvalue()
