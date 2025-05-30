# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import ast
import markupsafe

from odoo import _, api, fields, models, tools, Command
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.models import check_method_name
from odoo.addons.web.controllers.utils import clean_action
from odoo.tools import float_compare, float_round
from odoo.tools.misc import formatLang


class BankRecWidget(models.Model):
    _name = "bank.rec.widget"
    _inherit = "analytic.mixin"
    _description = "Bank reconciliation widget for a single statement line"

    # This model is never saved inside the database.
    # _auto=False' & _table_query = "0" prevent the ORM to create the corresponding postgresql table.
    _auto = False
    _table_query = "0"

    # ==== Business fields ====
    st_line_id = fields.Many2one(
        comodel_name='account.bank.statement.line',
        required=True,
    )
    move_id = fields.Many2one(
        related='st_line_id.move_id',
        depends=['st_line_id'],
    )
    to_check = fields.Boolean(
        related='st_line_id.move_id.to_check',
        depends=['st_line_id'],
        readonly=False,
    )
    st_line_is_reconciled = fields.Boolean(
        related='st_line_id.is_reconciled',
        depends=['st_line_id'],
    )
    st_line_narration = fields.Html(
        related='st_line_id.move_id.narration',
        depends=['st_line_id'],
    )
    transaction_currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_transaction_currency_id',
    )
    journal_currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_journal_currency_id',
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Partner",
        compute='_compute_partner_id',
        store=True,
        readonly=False,
        domain="['|', ('parent_id', '=', False), ('is_company', '=', True)]",
    )
    line_ids = fields.One2many(
        comodel_name='bank.rec.widget.line',
        inverse_name='wizard_id',
        compute='_compute_line_ids',
        store=True,
        readonly=False,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        compute='_compute_company_id',
    )
    company_currency_id = fields.Many2one(
        string="Wizard Company Currency",
        related='company_id.currency_id',
        depends=['st_line_id'],
    )
    matching_rules_allow_auto_reconcile = fields.Boolean()

    # ==== Display fields ====
    state = fields.Selection(
        selection=[
            ('invalid', "Invalid"),
            ('valid', "Valid"),
            ('reconciled', "Reconciled"),
        ],
        compute='_compute_state',
        help="Invalid: The bank transaction can't be validate since the suspense account is still involved\n"
             "Valid: The bank transaction can be validated.\n"
             "Reconciled: The bank transaction has already been processed. Nothing left to do."
    )

    # ==== JS fields ====
    lines_widget = fields.Binary(
        compute='_compute_lines_widget',
    )
    reco_models_widget = fields.Binary(
        compute='_compute_reco_models_widget',
    )
    amls_widget = fields.Binary(
        compute='_compute_amls_widget',
        readonly=False,
    )
    selected_aml_ids = fields.Many2many(
        comodel_name='account.move.line',
        compute='_compute_selected_aml_ids',
    )
    # Technical field to communicate from the JS code to the Python code
    todo_command = fields.Char(
        store=False,
    )
    next_action_todo = fields.Binary()

    # ==== Edition Form ====
    # Editable fields by the user:
    form_index = fields.Char()
    form_flag = fields.Char()
    form_name = fields.Char()
    form_date = fields.Date()
    form_account_id = fields.Many2one(
        comodel_name='account.account',
        domain="[('account_type', 'not in', ('asset_cash', 'liability_credit_card', 'off_balance')), ('company_id', '=', company_id), ('deprecated', '=', False)]",
    )
    form_partner_id = fields.Many2one(
        comodel_name='res.partner',
        domain="[('company_id', 'in', (company_id, False)), '|', ('parent_id','=', False), ('is_company','=', True)]",
    )
    form_currency_id = fields.Many2one(
        comodel_name='res.currency',
    )
    form_tax_ids = fields.Many2many(comodel_name='account.tax')
    form_amount_currency = fields.Monetary(currency_field='form_currency_id')
    form_balance = fields.Monetary(currency_field='company_currency_id')

    # Helper fields:
    form_force_negative_sign = fields.Boolean()
    form_single_currency_mode = fields.Boolean(
        compute='_compute_form_single_currency_mode',
    )

    form_extra_text = fields.Html(
        compute='_compute_amount_suggestion',
        sanitize=False,
    )
    form_suggest_amount_currency = fields.Monetary(
        currency_field='form_currency_id',
        compute='_compute_amount_suggestion',
    )
    form_suggest_balance = fields.Monetary(
        currency_field='company_currency_id',
        compute='_compute_amount_suggestion',
    )

    form_partner_currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_form_partner_info',
    )
    form_partner_receivable_account_id = fields.Many2one(
        comodel_name='account.account',
        compute='_compute_form_partner_info',
    )
    form_partner_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        compute='_compute_form_partner_info',
    )
    form_partner_receivable_amount = fields.Monetary(
        currency_field='form_partner_currency_id',
        compute='_compute_form_partner_info',
    )
    form_partner_payable_amount = fields.Monetary(
        currency_field='form_partner_currency_id',
        compute='_compute_form_partner_info',
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('st_line_id')
    def _compute_company_id(self):
        for wizard in self:
            wizard.company_id = wizard.st_line_id.company_id

    @api.depends('st_line_id')
    def _compute_line_ids(self):
        """ Convert the python dictionaries in 'lines_widget' to a bank.rec.edit.line recordset to ease the business
        computations.
        In case 'lines_widget' is empty, the default initial lines are generated.
        """
        for wizard in self:

            # The wizard already has lines.
            if wizard.line_ids:
                return

            # Protected fields by the orm like create_date should be excluded.
            protected_fields = set(models.MAGIC_COLUMNS + [self.CONCURRENCY_CHECK_FIELD])

            if wizard.lines_widget and wizard.lines_widget['lines']:
                # Create the `bank.rec.widget.line` from existing data in `lines_widget`.
                line_ids_commands = []
                for line_vals in wizard.lines_widget['lines']:
                    create_vals = {}

                    for field_name, field in wizard.line_ids._fields.items():
                        if field_name in protected_fields:
                            continue

                        value = line_vals[field_name]
                        if field.type == 'many2one':
                            create_vals[field_name] = value['id']
                        elif field.type == 'many2many':
                            create_vals[field_name] = value['ids']
                        elif field.type == 'char':
                            create_vals[field_name] = value['value'] or ''
                        else:
                            create_vals[field_name] = value['value']

                    line_ids_commands.append(Command.create(create_vals))
                wizard.line_ids = line_ids_commands
            else:
                # The wizard is opened for the first time. Create the default lines.
                line_ids_commands = [Command.clear(), Command.create(wizard._lines_widget_prepare_liquidity_line())]

                if wizard.st_line_id.is_reconciled:
                    # The statement line is already reconciled. We just need to preview the existing amls.
                    _liquidity_lines, _suspense_lines, other_lines = wizard.st_line_id._seek_for_lines()
                    for aml in other_lines:
                        exchange_diff_amls = (aml.matched_debit_ids + aml.matched_credit_ids) \
                            .exchange_move_id.line_ids.filtered(lambda l: l.account_id != aml.account_id)
                        if wizard.state == 'reconciled' and exchange_diff_amls:
                            line_ids_commands.append(
                                Command.create(wizard._lines_widget_prepare_aml_line(
                                    aml,  # Create the aml line with un-squashed amounts (aml - exchange diff)
                                    balance=aml.balance - sum(exchange_diff_amls.mapped('balance')),
                                    amount_currency=aml.amount_currency - sum(exchange_diff_amls.mapped('amount_currency')),
                                ))
                            )
                            for exchange_diff_aml in exchange_diff_amls:
                                line_ids_commands.append(
                                    Command.create(wizard._lines_widget_prepare_aml_line(exchange_diff_aml))
                                )
                        else:
                            line_ids_commands.append(Command.create(wizard._lines_widget_prepare_aml_line(aml)))
                wizard.line_ids = line_ids_commands

                wizard._lines_widget_add_auto_balance_line()

    @api.depends('company_id', 'form_currency_id')
    def _compute_form_single_currency_mode(self):
        for wizard in self:
            wizard.form_single_currency_mode = wizard.form_currency_id == wizard.company_id.currency_id

    @api.depends('st_line_id', 'line_ids.account_id')
    def _compute_state(self):
        for wizard in self:
            if wizard.st_line_id.is_reconciled:
                wizard.state = 'reconciled'
            else:
                suspense_account = wizard.st_line_id.journal_id.suspense_account_id
                if suspense_account in wizard.line_ids.account_id:
                    wizard.state = 'invalid'
                else:
                    wizard.state = 'valid'

    @api.depends('st_line_id')
    def _compute_journal_currency_id(self):
        for wizard in self:
            wizard.journal_currency_id = wizard.st_line_id.journal_id.currency_id \
                                         or wizard.st_line_id.journal_id.company_id.currency_id

    @api.depends('st_line_id')
    def _compute_transaction_currency_id(self):
        for wizard in self:
            wizard.transaction_currency_id = wizard.st_line_id.foreign_currency_id or wizard.journal_currency_id

    @api.depends('st_line_id')
    def _compute_partner_id(self):
        for wizard in self:
            wizard.partner_id = wizard.st_line_id._retrieve_partner()

    @api.depends('form_partner_id')
    def _compute_form_partner_info(self):
        for wizard in self:
            partner_currency = None
            partner_receivable_account = None
            partner_payable_account = None
            partner_receivable_amount = 0.0
            partner_payable_amount = 0.0
            partner = wizard.form_partner_id.with_company(wizard.company_id)
            if partner:
                partner_currency = wizard.company_currency_id
                partner_receivable_account = partner.property_account_receivable_id
                common_domain = [('parent_state', '=', 'posted'), ('partner_id', '=', partner.id)]
                if partner_receivable_account:
                    res = self.env['account.move.line'].read_group(
                        domain=expression.AND([common_domain, [('account_id', '=', partner_receivable_account.id)]]),
                        fields=['amount_residual:sum'],
                        groupby=['partner_id'],
                    )
                    partner_receivable_amount = res[0]['amount_residual'] if res else 0.0
                partner_payable_account = partner.property_account_payable_id
                if partner_payable_account:
                    res = self.env['account.move.line'].read_group(
                        domain=expression.AND([common_domain, [('account_id', '=', partner_payable_account.id)]]),
                        fields=['amount_residual:sum'],
                        groupby=['partner_id'],
                    )
                    partner_payable_amount = res[0]['amount_residual'] if res else 0.0
            wizard.form_partner_currency_id = partner_currency
            wizard.form_partner_receivable_account_id = partner_receivable_account
            wizard.form_partner_payable_account_id = partner_payable_account
            wizard.form_partner_receivable_amount = partner_receivable_amount
            wizard.form_partner_payable_amount = partner_payable_amount

    def _check_lines_widget_consistency(self):
        """ Check the consistency of 'line_ids' at each onchange (manually called since the wizard is never saved).
        For example, you can't duplicate a journal item in the wizard.
        """
        for wizard in self:
            seen_amls = set()
            nb_liquidity = 0
            nb_auto_balance = 0
            for line in wizard.line_ids:
                if line.flag == 'liquidity':
                    nb_liquidity += 1
                elif line.flag == 'auto_balance':
                    nb_auto_balance += 1
                if line.flag == 'new_aml' and line.source_aml_id:
                    if line.source_aml_id in seen_amls:
                        raise UserError(_("You can't have multiple times the same journal item in the bank reconciliation widget"))
                    seen_amls.add(line.source_aml_id)
            if wizard.line_ids and nb_liquidity != 1:
                raise UserError(_("You can't have multiple liquidity journal item at the same time in the bank reconciliation widget"))
            if nb_auto_balance > 1:
                raise UserError(_("You can't have maximum one auto balance line at the same time in the bank reconciliation widget"))

    @api.depends(
        'form_index',
        'state',
        'line_ids.account_id',
        'line_ids.date',
        'line_ids.name',
        'line_ids.partner_id',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.balance',
        'line_ids.analytic_distribution',
        'line_ids.tax_repartition_line_id',
        'line_ids.tax_ids',
        'line_ids.tax_tag_ids',
        'line_ids.group_tax_id',
        'line_ids.reconcile_model_id',
    )
    def _compute_lines_widget(self):
        """ Convert the bank.rec.widget.line recordset (line_ids fields) to a dictionary to fill the 'lines_widget'
        owl widget.
        """
        def format_distribution_name(display_name, percentage):
            precision = self.analytic_precision or 2

            if not float_compare(percentage, 100.00, precision):
                return display_name

            rounded_percentage = float_round(percentage, precision)
            rounded_percentage_without_trailing_zeros = str(rounded_percentage).rstrip('0').rstrip('.')

            return f"{display_name} {rounded_percentage_without_trailing_zeros}%"

        self._check_lines_widget_consistency()

        # Protected fields by the orm like create_date should be excluded.
        protected_fields = set(models.MAGIC_COLUMNS + [self.CONCURRENCY_CHECK_FIELD])

        for wizard in self:
            lines = wizard.line_ids

            # Sort the lines.
            sorted_lines = []
            auto_balance_lines = []
            epd_lines = []
            exchange_diff_map = {x.source_aml_id: x for x in lines.filtered(lambda x: x.flag == 'exchange_diff')}
            for line in lines:
                if line.flag == 'auto_balance':
                    auto_balance_lines.append(line)
                elif line.flag == 'early_payment':
                    epd_lines.append(line)
                elif line.flag != 'exchange_diff':
                    sorted_lines.append(line)
                    if line.flag == 'new_aml' and exchange_diff_map.get(line.source_aml_id):
                        sorted_lines.append(exchange_diff_map[line.source_aml_id])

            line_vals_list = []
            for line in sorted_lines + epd_lines + auto_balance_lines:
                js_vals = {}

                for field_name, field in line._fields.items():
                    if field_name in protected_fields:
                        continue

                    value = line[field_name]
                    if field.type == 'date':
                        js_vals[field_name] = {
                            'display': tools.format_date(self.env, value),
                            'value': fields.Date.to_string(value),
                        }
                    elif field.type == 'char':
                        js_vals[field_name] = {'value': value or ''}
                    elif field.type == 'monetary':
                        currency = line[field.currency_field]
                        js_vals[field_name] = {
                            'display': formatLang(self.env, value, currency_obj=currency),
                            'value': value,
                            'is_zero': currency.is_zero(value),
                        }
                    elif field.type == 'many2one':
                        record = value._origin
                        js_vals[field_name] = {
                            'display': record.display_name or '',
                            'id': record.id,
                        }
                    elif field.type == 'many2many':
                        records = value._origin
                        js_vals[field_name] = {
                            'display': records.mapped('display_name'),
                            'ids': records.ids,
                        }
                    elif field_name == 'analytic_distribution':
                        js_vals[field_name] = {'value': value}

                        if value:
                            analytic_account_ids = [int(analytic_account_id) for analytic_account_id in value]
                            analytic_accounts = self.env['account.analytic.account'].browse(analytic_account_ids).read(['id', 'display_name', 'color'])

                            js_vals[field_name]['display'] = [
                                {
                                    'id': analytic_account['id'],
                                    'text': format_distribution_name(analytic_account['display_name'], value.get(str(analytic_account['id']))),
                                    'colorIndex': analytic_account['color'],
                                } for analytic_account in analytic_accounts
                            ]
                    else:
                        js_vals[field_name] = {'value': value}
                line_vals_list.append(js_vals)

            extra_notes = []
            bank_account = wizard.st_line_id.partner_bank_id.display_name or wizard.st_line_id.account_number
            if bank_account:
                extra_notes.append(bank_account)

            bool_analytic_distribution = False
            for line in wizard.line_ids:
                if line.analytic_distribution:
                    bool_analytic_distribution = True
                    break

            wizard.lines_widget = {
                'lines': line_vals_list,

                'display_multi_currency_column': wizard.line_ids.currency_id != wizard.company_currency_id,
                'display_taxes_column': bool(wizard.line_ids.tax_ids),
                'display_analytic_distribution_column': bool_analytic_distribution,
                'form_index': wizard.form_index,
                'state': wizard.state,
                'partner_name': wizard.st_line_id.partner_name,
                'extra_notes': ' '.join(extra_notes) if extra_notes else None,
            }

    @api.depends('state', 'line_ids.reconcile_model_id')
    def _compute_reco_models_widget(self):
        for wizard in self:
            # Compute 'available_reconcile_model_ids'.
            if wizard.reco_models_widget:
                available_reconcile_model_ids = wizard.reco_models_widget['available_reconcile_model_ids']
            else:
                reconcile_models = self.env['account.reconcile.model'].search([
                    ('rule_type', '=', 'writeoff_button'),
                    ('company_id', '=', self.company_id.id),
                    '|',
                    ('match_journal_ids', '=', False),
                    ('match_journal_ids', '=', wizard.st_line_id.journal_id.id),
                ])

                available_reconcile_model_ids = [{
                    'id': x.id,
                    'display_name': x.display_name,
                } for x in reconcile_models]

            # Compute 'selected_model_id'.
            selected_reconcile_models = wizard.line_ids.reconcile_model_id.filtered(lambda x: x.rule_type == 'writeoff_button')
            if len(selected_reconcile_models) == 1:
                selected_reconcile_model_id = selected_reconcile_models.id
            else:
                selected_reconcile_model_id = None

            wizard.reco_models_widget = {
                'available_reconcile_model_ids': available_reconcile_model_ids,
                'selected_reconcile_model_id': selected_reconcile_model_id,
                'display_widget': wizard.state in ('valid', 'invalid'),
            }

    @api.depends('st_line_id')
    def _compute_amls_widget(self):
        for wizard in self:
            st_line = wizard.st_line_id

            context = {
                'search_view_ref': 'account_accountant.view_account_move_line_search_bank_rec_widget',
                'tree_view_ref': 'account_accountant.view_account_move_line_list_bank_rec_widget',
            }

            if wizard.partner_id:
                context['search_default_partner_id'] = wizard.partner_id.id

            dynamic_filters = []

            # == Dynamic Customer/Vendor filter ==
            journal = st_line.journal_id

            account_ids = set()

            inbound_accounts = journal._get_journal_inbound_outstanding_payment_accounts() - journal.default_account_id
            outbound_accounts = journal._get_journal_outbound_outstanding_payment_accounts() - journal.default_account_id

            # Matching on debit account.
            for account in inbound_accounts:
                account_ids.add(account.id)

            # Matching on credit account.
            for account in outbound_accounts:
                account_ids.add(account.id)

            rec_pay_matching_filter = {
                'name': 'receivable_payable_matching',
                'description': _("Customer/Vendor"),
                'domain': [
                    '|',
                    # Matching invoices.
                    '&',
                    ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
                    ('payment_id', '=', False),
                    # Matching Payments.
                    '&',
                    ('account_id', 'in', tuple(account_ids)),
                    ('payment_id', '!=', False),
                ],
                'no_separator': True,
                'is_default': True,
            }

            misc_matching_filter = {
                'name': 'misc_matching',
                'description': _("Miscellaneous"),
                'domain': ['!'] + rec_pay_matching_filter['domain'],
                'is_default': False,
            }

            dynamic_filters.extend([rec_pay_matching_filter, misc_matching_filter])

            # Stringify the domain.
            for dynamic_filter in dynamic_filters:
                dynamic_filter['domain'] = str(dynamic_filter['domain'])

            wizard.amls_widget = {
                'domain': st_line._get_default_amls_matching_domain(),

                'dynamic_filters': dynamic_filters,

                'context': context,
            }

    @api.depends('company_id', 'line_ids.source_aml_id')
    def _compute_selected_aml_ids(self):
        for wizard in self:
            wizard.selected_aml_ids = [Command.set(wizard.line_ids.source_aml_id.ids)]

    @api.depends('form_index', 'form_amount_currency', 'form_balance', 'form_force_negative_sign')
    def _compute_amount_suggestion(self):
        for wizard in self:
            form_extra_text = None
            form_suggest_amount_currency = None
            form_suggest_balance = None

            line = wizard._lines_widget_get_line_in_edit_form()
            if line and line.flag == 'new_aml':
                aml = line.source_aml_id
                balance_sign = -1 if wizard.form_force_negative_sign else 1

                residual_amount_before_reco = abs(aml.amount_residual_currency)
                residual_amount_after_reco = abs(aml.amount_residual_currency + line.amount_currency)
                reconciled_amount = residual_amount_before_reco - residual_amount_after_reco
                is_fully_reconciled = aml.currency_id.is_zero(residual_amount_after_reco)
                is_invoice = aml.move_id.is_invoice(include_receipts=True)

                if is_fully_reconciled:
                    lines = [
                        _("The invoice %(display_name_html)s with an open amount of %(open_amount)s will be entirely paid by the transaction.")
                        if is_invoice else
                        _("%(display_name_html)s with an open amount of %(open_amount)s will be fully reconciled by the transaction.")
                    ]
                    partial_amounts = wizard._lines_widget_check_partial_amount(line)
                    if partial_amounts:
                        lines.append(
                            _("You might want to record a %(btn_start)spartial payment%(btn_end)s.")
                            if is_invoice else
                            _("You might want to make a %(btn_start)spartial reconciliation%(btn_end)s instead.")
                         )
                        form_suggest_amount_currency = balance_sign * partial_amounts['amount_currency']
                        form_suggest_balance = balance_sign * partial_amounts['balance']
                else:
                    if is_invoice:
                        lines = [
                            _("The invoice %(display_name_html)s with an open amount of %(open_amount)s will be reduced by %(amount)s."),
                            _("You might want to set the invoice as %(btn_start)sfully paid%(btn_end)s."),
                        ]
                    else:
                        lines = [
                            _("%(display_name_html)s with an open amount of %(open_amount)s will be reduced by %(amount)s."),
                            _("You might want to %(btn_start)sfully reconcile%(btn_end)s the document."),
                        ]
                    form_suggest_amount_currency = balance_sign * line.source_amount_currency
                    form_suggest_balance = balance_sign * line.source_balance

                display_name_html = markupsafe.Markup("""
                    <button name="button_form_redirect_to_move_form"
                            class="o_bank_rec_widget_form_suggest_button"
                            method_args="%(method_args)s"
                            type="object">%(display_name)s</button>
                """) % {
                    'method_args': [aml.move_id.id],
                    'display_name': aml.move_id.display_name,
                }

                extra_text = markupsafe.Markup('<br/>').join(lines) % {
                        'amount': formatLang(self.env, reconciled_amount, currency_obj=aml.currency_id),
                        'open_amount': formatLang(self.env, residual_amount_before_reco, currency_obj=aml.currency_id),
                        'display_name_html': display_name_html,
                        'btn_start': markupsafe.Markup('<button name="button_form_apply_suggestion" class="o_bank_rec_widget_form_suggest_button" type="object">'),
                        'btn_end': markupsafe.Markup('</button>'),
                }
                form_extra_text = f"""<div class="font-italic text-muted">{extra_text}</div>"""

            wizard.form_extra_text = form_extra_text
            wizard.form_suggest_amount_currency = form_suggest_amount_currency
            wizard.form_suggest_balance = form_suggest_balance

    @api.depends('form_account_id', 'form_partner_id')
    def _compute_analytic_distribution(self):
        for wizard in self:
            distribution = self.env['account.analytic.distribution.model']._get_distribution({
                "partner_id": wizard.form_partner_id.id,
                "partner_category_id": wizard.form_partner_id.category_id.ids,
                "account_prefix": wizard.form_account_id.code,
                "company_id": wizard.company_id.id,
            })
            wizard.analytic_distribution = distribution or wizard.analytic_distribution

    # -------------------------------------------------------------------------
    # ONCHANGE METHODS
    # -------------------------------------------------------------------------

    def _process_todo_command(self, command_name, command_args):
        """ Decode the command coming from the JS-side and do the corresponding behavior accordingly.

        :param command_name: An arbitrary code representing the action to do.
        :param command_args: A list of serializable parameters.
        """
        if command_name == 'trigger_matching_rules':
            self._action_trigger_matching_rules()
        elif command_name == 'mount_line_in_edit':
            line_index = command_args[0]
            field_clicked = command_args[1:2] or None
            self._action_mount_line_in_edit(line_index, field_clicked)
        elif command_name == 'clear_edit_form':
            self._action_clear_manual_operations_form()
        elif command_name == 'remove_line':
            line_index = command_args[0]
            self._action_remove_line(line_index)
        elif command_name == 'remove_new_aml':
            aml_id = int(command_args[0])
            aml = self.env['account.move.line'].browse(aml_id)
            self._action_remove_new_amls(aml)
        elif command_name == 'add_new_amls':
            aml_ids = [int(x) for x in command_args]
            amls = self.env['account.move.line'].browse(aml_ids)
            self._action_add_new_amls(amls)
        elif command_name == 'select_reconcile_model_button':
            rec_model_id = int(command_args[0])
            rec_model = self.env['account.reconcile.model'].browse(rec_model_id)
            self._action_select_reconcile_model(rec_model)
        elif command_name == 'unselect_reconcile_model_button':
            rec_model_id = int(command_args[0])
            rec_model = self.env['account.reconcile.model'].browse(rec_model_id)
            self._action_unselect_reconcile_model(rec_model)
        elif command_name == 'button_clicked':
            method_name = command_args[0]
            check_method_name(method_name)
            getattr(self, method_name)(*command_args[1:])

    @api.onchange('todo_command')
    def _onchange_todo_command(self):
        """ Decode the command if any coming from the JS-side. The command is a string having the following pattern:
        <command_name, [arg0, [arg1, ...[argn]]]>
        """
        todo_command = (self.todo_command or '').lower()
        self.todo_command = False

        if not todo_command:
            return

        self._ensure_loaded_lines()

        command_split = todo_command.split(',')
        self._process_todo_command(command_split[0], command_split[1:])

    @api.onchange('form_name')
    def _onchange_form_name(self):
        line = self._lines_widget_get_line_in_edit_form()
        if line:

            if line.flag == 'liquidity':
                self.st_line_id.payment_ref = self.form_name
                self.invalidate_model(fnames=['partner_id'])
                self._action_reset_wizard()
                self._action_focus_liquidity_line(field_clicked='name')
                self.next_action_todo = {'type': 'refresh_liquidity'}
            else:
                self._lines_widget_form_turn_auto_balance_into_manual_line(line)
                line.name = self.form_name

    @api.onchange('form_date')
    def _onchange_form_date(self):
        line = self._lines_widget_get_line_in_edit_form()
        if line and line.flag == 'liquidity':
            self.st_line_id.date = self.form_date
            self._action_reset_wizard()
            self._action_focus_liquidity_line(field_clicked='date')
            self.next_action_todo = {'type': 'refresh_liquidity'}

    @api.onchange('form_account_id')
    def _onchange_form_account_id(self):
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)
        if self.form_account_id:
            line.account_id = self.form_account_id

        # Recompute taxes.
        if line.flag not in ('tax_line', 'early_payment') and line.tax_ids:
            self._lines_widget_recompute_taxes()
            self._lines_widget_add_auto_balance_line()
            self._action_mount_line_in_edit(line.index)

    @api.onchange('form_partner_id')
    def _onchange_form_partner_id(self):
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        if line.flag == 'liquidity':
            self.st_line_id.partner_id = self.form_partner_id
            self.invalidate_model(fnames=['partner_id'])
            self._action_reset_wizard()
            self._action_focus_liquidity_line(field_clicked='partner_id')
            self.next_action_todo = {'type': 'refresh_liquidity'}
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)
        partner = self.form_partner_id
        line.partner_id = partner

        new_account = None
        if partner:
            partner_is_customer = partner.customer_rank and not partner.supplier_rank
            partner_is_supplier = partner.supplier_rank and not partner.customer_rank
            is_partner_receivable_amount_zero = self.form_partner_currency_id.is_zero(self.form_partner_receivable_amount)
            is_partner_payable_amount_zero = self.form_partner_currency_id.is_zero(self.form_partner_payable_amount)
            if partner_is_customer or not is_partner_receivable_amount_zero and is_partner_payable_amount_zero:
                new_account = self.form_partner_receivable_account_id
            elif partner_is_supplier or is_partner_receivable_amount_zero and not is_partner_payable_amount_zero:
                new_account = self.form_partner_payable_account_id
            elif self.st_line_id.amount < 0.0:
                new_account = self.form_partner_payable_account_id or self.form_partner_receivable_account_id
            else:
                new_account = self.form_partner_receivable_account_id or self.form_partner_payable_account_id

        if new_account:
            # Set the new receivable/payable account if any.
            self.form_account_id = new_account
            self._onchange_form_account_id()
        elif line.flag not in ('tax_line', 'early_payment') and line.tax_ids:
            # Recompute taxes.
            self._lines_widget_recompute_taxes()
            self._lines_widget_add_auto_balance_line()
            self._action_mount_line_in_edit(line.index)

    @api.onchange('form_currency_id')
    def _onchange_form_currency_id(self):
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)
        if self.form_currency_id:
            line.currency_id = self.form_currency_id

        self._onchange_form_amount_currency()

    @api.onchange('analytic_distribution')
    def _onchange_analytic_distribution(self):
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)
        line.analytic_distribution = self.analytic_distribution

        # Recompute taxes.
        if line.flag not in ('tax_line', 'early_payment') and any(x.analytic for x in line.tax_ids):
            self._lines_widget_recompute_taxes()
            self._lines_widget_add_auto_balance_line()
            self._action_mount_line_in_edit(line.index)

    @api.onchange('form_tax_ids')
    def _onchange_form_tax_ids(self):
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)

        tax_base_amount_currency = line.tax_base_amount_currency
        has_exited_price_included_mode = line.tax_ids and not line.force_price_included_taxes
        line.tax_ids = [Command.set(self.form_tax_ids.ids)]

        # The user has customized the balance before adding taxes. In that case, don't force the taxes to act as
        # price included.
        if has_exited_price_included_mode:
            line.force_price_included_taxes = False

        # The user manually removes the taxes.
        if not line.tax_ids:
            self.form_amount_currency = tax_base_amount_currency
            self._onchange_form_amount_currency()

        self._lines_widget_recompute_taxes()
        self._lines_widget_add_auto_balance_line()
        self._action_mount_line_in_edit(line.index)

    @api.onchange('form_amount_currency')
    def _onchange_form_amount_currency(self):
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        if line.flag == 'liquidity':
            self.st_line_id.amount = self.form_amount_currency
            self._action_reset_wizard()
            self._action_focus_liquidity_line(field_clicked='amount_currency')
            self.next_action_todo = {'type': 'refresh_liquidity_balance'}
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)

        if line.flag == 'new_aml':
            # The balance must keep the same sign as the original aml and must not exceed its original value.
            self.form_amount_currency = max(0.0, min(self.form_amount_currency, abs(line.source_amount_currency)))

            # If the user remove completely the value, reset to the original balance.
            if not self.form_amount_currency:
                self.form_amount_currency = abs(line.source_amount_currency)

        elif not self.form_amount_currency:
            self.form_amount_currency = 0.0

        if self.form_currency_id == line.company_currency_id or not self.form_currency_id:
            # Single currency: amount_currency must be equal to balance.
            self.form_balance = self.form_amount_currency
        elif line.flag == 'new_aml':
            if line.currency_id.compare_amounts(self.form_amount_currency, abs(line.source_amount_currency)) == 0.0:
                # The value has been reset to its original value. Reset the balance as well to avoid rounding issues.
                self.form_balance = abs(line.source_balance)
            else:
                # Apply the rate.
                rate = abs(line.source_amount_currency) / abs(line.source_balance)
                self.form_balance = line.company_currency_id.round(self.form_amount_currency / rate)
        elif line.flag in ('manual', 'early_payment', 'tax_line'):
            if line.currency_id in (self.transaction_currency_id, self.journal_currency_id):
                self.form_balance = self.st_line_id\
                    ._prepare_counterpart_amounts_using_st_line_rate(self.form_currency_id, None, self.form_amount_currency)['balance']
            else:
                self.form_balance = self.form_currency_id\
                    ._convert(self.form_amount_currency, self.company_currency_id, self.company_id, self.st_line_id.date)

        sign = -1 if self.form_force_negative_sign else 1
        line.write({
            'amount_currency': sign * self.form_amount_currency,
            'balance': sign * self.form_balance,
            'manually_modified': True,
        })

        if line.flag not in ('tax_line', 'early_payment'):

            if line.tax_ids:
                # Manual edition of amounts. Disable the price_included mode.
                line.force_price_included_taxes = False

                self._lines_widget_recompute_taxes()

            self._lines_widget_recompute_exchange_diff()
            self._lines_widget_add_auto_balance_line()
            self._action_mount_line_in_edit(line.index)
        else:
            self._lines_widget_add_auto_balance_line()

    @api.onchange('form_balance')
    def _onchange_form_balance(self):
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        if line.flag == 'liquidity':
            self.st_line_id.amount = self.form_balance
            self._action_reset_wizard()
            self._action_focus_liquidity_line(field_clicked='debit')
            self.next_action_todo = {'type': 'refresh_liquidity_balance'}
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)
        if line.flag == 'new_aml':

            # The balance must keep the same sign as the original aml and must not exceed its original value.
            self.form_balance = max(0.0, min(self.form_balance, abs(line.source_balance)))

            # If the user remove completely the value, reset to the original balance.
            if not self.form_balance:
                self.form_balance = abs(line.source_balance)

        elif not self.form_balance:
            self.form_balance = 0.0

        sign = -1 if self.form_force_negative_sign else 1
        line.write({
            'balance': sign * self.form_balance,
            'manually_modified': True,
        })

        # Single currency: amount_currency must be equal to balance.
        if self.form_currency_id == line.company_currency_id:
            self.form_amount_currency = self.form_balance
            self._onchange_form_amount_currency()
        else:
            self._lines_widget_recompute_exchange_diff()
            self._lines_widget_add_auto_balance_line()

    # -------------------------------------------------------------------------
    # ORM METHODS
    # -------------------------------------------------------------------------

    def onchange(self, values, field_name, field_onchange):
        # Extends base.
        # All onchanges in this model are made because we can't replace them by computed fields.
        # We need to know exactly in which order the onchanges are triggered and be able to prevent the trigger of some
        # of them.
        return super(BankRecWidget, self.with_context(recursive_onchanges=False)).onchange(values, field_name, field_onchange)

    # -------------------------------------------------------------------------
    # LINES_WIDGET METHODS
    # -------------------------------------------------------------------------

    def _lines_widget_form_turn_auto_balance_into_manual_line(self, line):
        # When editing an auto_balance line, it becomes a custom manual line.
        if self.form_flag == 'auto_balance':
            self.form_flag = 'manual'
            line.flag = 'manual'

    def _lines_widget_get_line_in_edit_form(self):
        self.ensure_one()

        if not self.form_index:
            return

        return self.line_ids.filtered(lambda x: x.index == self.form_index)

    def _lines_widget_prepare_aml_line(self, aml, **kwargs):
        self.ensure_one()
        return {
            'flag': 'aml',
            'source_aml_id': aml,
            **kwargs,
        }

    def _lines_widget_prepare_liquidity_line(self):
        """ Create a line corresponding to the journal item having the liquidity account on the statement line."""
        self.ensure_one()
        st_line = self.st_line_id

        # In case of a different currencies on the journal and on the transaction, we need to retrieve the transaction
        # amount on the suspense line because a journal item can only have one foreign currency. Indeed, in such
        # configuration, the foreign currency amount expressed in journal's currency is set on the liquidity line but
        # the transaction amount is on the suspense account line.
        liquidity_line, _suspense_lines, _other_lines = st_line._seek_for_lines()

        return self._lines_widget_prepare_aml_line(liquidity_line, flag='liquidity')

    def _lines_widget_prepare_auto_balance_line(self):
        """ Create the auto_balance line if necessary in order to have fully balanced lines."""
        self.ensure_one()
        self._ensure_loaded_lines()
        st_line = self.st_line_id

        # Compute the current open balance.
        transaction_amount, transaction_currency, journal_amount, _journal_currency, company_amount, _company_currency \
            = self.st_line_id._get_accounting_amounts_and_currencies()
        open_amount_currency = -transaction_amount
        open_balance = -company_amount
        for line in self.line_ids:
            if line.flag in ('liquidity', 'auto_balance'):
                continue

            open_balance -= line.balance
            journal_transaction_rate = abs(transaction_amount / journal_amount) if journal_amount else 0.0
            company_transaction_rate = abs(transaction_amount / company_amount) if company_amount else 0.0
            if line.currency_id == self.transaction_currency_id:
                open_amount_currency -= line.amount_currency
            elif line.currency_id == self.journal_currency_id:
                open_amount_currency -= transaction_currency.round(line.amount_currency * journal_transaction_rate)
            else:
                open_amount_currency -= transaction_currency.round(line.balance * company_transaction_rate)

        # Create a new auto-balance line.
        account = None
        partner = self.partner_id
        if partner:
            name = _("Open balance: %s", st_line.payment_ref)
            partner_is_customer = partner.customer_rank and not partner.supplier_rank
            partner_is_supplier = partner.supplier_rank and not partner.customer_rank
            if partner_is_customer:
                account = partner.with_company(st_line.company_id).property_account_receivable_id
            elif partner_is_supplier:
                account = partner.with_company(st_line.company_id).property_account_payable_id
            elif st_line.amount > 0:
                account = partner.with_company(st_line.company_id).property_account_receivable_id
            else:
                account = partner.with_company(st_line.company_id).property_account_payable_id

        if not account:
            name = st_line.payment_ref
            account = st_line.journal_id.suspense_account_id

        return {
            'flag': 'auto_balance',

            'account_id': account.id,
            'name': name,
            'amount_currency': open_amount_currency,
            'balance': open_balance,
        }

    def _lines_widget_add_auto_balance_line(self):
        ''' Add the line auto balancing the debit/credit. '''
        self._ensure_loaded_lines()

        # Drop the existing line then re-create it to ensure this line is always the last one.
        line_ids_commands = []
        for auto_balance_line in self.line_ids.filtered(lambda x: x.flag == 'auto_balance'):
            line_ids_commands.append(Command.unlink(auto_balance_line.id))

        # Re-create a new auto-balance line if needed.
        auto_balance_line_vals = self._lines_widget_prepare_auto_balance_line()
        if not self.company_currency_id.is_zero(auto_balance_line_vals['balance']):
            line_ids_commands.append(Command.create(auto_balance_line_vals))
        self.line_ids = line_ids_commands

    def _lines_widget_prepare_new_aml_line(self, aml, **kwargs):
        return self._lines_widget_prepare_aml_line(
            aml,
            flag='new_aml',
            currency_id=aml.currency_id,
            amount_currency=-aml.amount_residual_currency,
            balance=-aml.amount_residual,
            source_amount_currency=-aml.amount_residual_currency,
            source_balance=-aml.amount_residual,
            **kwargs,
        )

    def _lines_widget_check_partial_amount(self, line):
        if line.flag != 'new_aml':
            return None

        exchange_diff_line = self.line_ids\
            .filtered(lambda x: x.flag == 'exchange_diff' and x.source_aml_id == line.source_aml_id)
        auto_balance_line_vals = self._lines_widget_prepare_auto_balance_line()

        auto_balance = auto_balance_line_vals['balance']
        current_balance = line.balance + exchange_diff_line.balance
        has_enough_comp_debit = self.company_currency_id.compare_amounts(auto_balance, 0) < 0 \
                                and self.company_currency_id.compare_amounts(current_balance, 0) > 0 \
                                and self.company_currency_id.compare_amounts(current_balance, -auto_balance) > 0
        has_enough_comp_credit = self.company_currency_id.compare_amounts(auto_balance, 0) > 0 \
                                and self.company_currency_id.compare_amounts(current_balance, 0) < 0 \
                                and self.company_currency_id.compare_amounts(-current_balance, auto_balance) > 0

        auto_amount_currency = auto_balance_line_vals['amount_currency']
        current_amount_currency = line.amount_currency
        has_enough_curr_debit = line.currency_id.compare_amounts(auto_amount_currency, 0) < 0 \
                                and line.currency_id.compare_amounts(current_amount_currency, 0) > 0 \
                                and line.currency_id.compare_amounts(current_amount_currency, -auto_amount_currency) > 0
        has_enough_curr_credit = line.currency_id.compare_amounts(auto_amount_currency, 0) > 0 \
                                and line.currency_id.compare_amounts(current_amount_currency, 0) < 0 \
                                and line.currency_id.compare_amounts(-current_amount_currency, auto_amount_currency) > 0

        if line.currency_id == self.transaction_currency_id:
            if has_enough_curr_debit or has_enough_curr_credit:
                amount_currency_after_partial = current_amount_currency + auto_amount_currency

                # Get the bank transaction rate.
                transaction_amount, _transaction_currency, _journal_amount, _journal_currency, company_amount, _company_currency \
                    = self.st_line_id._get_accounting_amounts_and_currencies()
                rate = abs(company_amount / transaction_amount) if transaction_amount else 0.0

                # Compute the amounts to make a partial.
                balance_after_partial = line.company_currency_id.round(amount_currency_after_partial * rate)
                new_line_balance = line.company_currency_id.round(balance_after_partial * abs(line.balance) / abs(current_balance))
                exchange_diff_line_balance = balance_after_partial - new_line_balance
                return {
                    'exchange_diff_line': exchange_diff_line,
                    'amount_currency': amount_currency_after_partial,
                    'balance': new_line_balance,
                    'exchange_balance': exchange_diff_line_balance,
                }
        elif has_enough_comp_debit or has_enough_comp_credit:
            # Compute the new value for balance.
            balance_after_partial = current_balance + auto_balance

            # Get the rate of the original journal item.
            rate = abs(line.source_amount_currency) / abs(line.source_balance)

            # Compute the amounts to make a partial.
            new_line_balance = line.company_currency_id.round(balance_after_partial * abs(line.balance) / abs(current_balance))
            exchange_diff_line_balance = balance_after_partial - new_line_balance
            amount_currency_after_partial = line.currency_id.round(new_line_balance * rate)
            return {
                'exchange_diff_line': exchange_diff_line,
                'amount_currency': amount_currency_after_partial,
                'balance': new_line_balance,
                'exchange_balance': exchange_diff_line_balance,
            }
        return None

    def _lines_widget_check_apply_early_payment_discount(self):
        """ Try to apply the early payment discount on the currently mounted journal items.

        :return: True if applied, False otherwise.
        """
        self._ensure_loaded_lines()

        all_aml_lines = self.line_ids.filtered(lambda x: x.flag == 'new_aml')

        # Get the balance without the 'new_aml' lines.
        auto_balance_line_vals = self._lines_widget_prepare_auto_balance_line()
        open_balance_wo_amls = auto_balance_line_vals['balance'] + sum(all_aml_lines.mapped('balance'))
        open_amount_currency_wo_amls = auto_balance_line_vals['amount_currency'] + sum(all_aml_lines.mapped('amount_currency'))

        # Get the balance after adding the 'new_aml' lines but without considering the partial amounts.
        open_balance = open_balance_wo_amls - sum(all_aml_lines.mapped('source_balance'))
        open_amount_currency = open_amount_currency_wo_amls - sum(all_aml_lines.mapped('source_amount_currency'))

        is_same_currency = all_aml_lines.currency_id == self.transaction_currency_id
        at_least_one_aml_for_early_payment = False

        early_pay_aml_values_list = []
        total_early_payment_discount = 0.0

        for aml_line in all_aml_lines:
            aml = aml_line.source_aml_id

            if aml._is_eligible_for_early_payment_discount(self.transaction_currency_id, self.st_line_id.date):
                at_least_one_aml_for_early_payment = True
                total_early_payment_discount += aml.amount_currency - aml.discount_amount_currency

                early_pay_aml_values_list.append({
                    'aml': aml,
                    'amount_currency': aml_line.amount_currency,
                    'balance': aml_line.balance,
                })

        line_ids_create_command_list = []
        is_early_payment_applied = False

        # Cleanup the existing early payment discount lines.
        for line in self.line_ids.filtered(lambda x: x.flag == 'early_payment'):
            line_ids_create_command_list.append(Command.unlink(line.id))

        if is_same_currency \
            and at_least_one_aml_for_early_payment \
            and self.transaction_currency_id.compare_amounts(open_amount_currency, total_early_payment_discount) == 0:
            # == Compute the early payment discount lines ==
            # Remove the partials on existing lines.
            for aml_line in all_aml_lines:
                aml_line.amount_currency = aml_line.source_amount_currency
                aml_line.balance = aml_line.source_balance

            # Add the early payment lines.
            early_payment_values = self.env['account.move']._get_invoice_counterpart_amls_for_early_payment_discount(
                early_pay_aml_values_list,
                open_balance,
            )

            for vals_list in early_payment_values.values():
                for vals in vals_list:
                    line_ids_create_command_list.append(Command.create({
                        'flag': 'early_payment',
                        'account_id': vals['account_id'],
                        'date': self.st_line_id.date,
                        'name': vals['name'],
                        'partner_id': vals['partner_id'],
                        'currency_id': vals['currency_id'],
                        'amount_currency': vals['amount_currency'],
                        'balance': vals['balance'],
                        'analytic_distribution': vals.get('analytic_distribution'),
                        'tax_ids': vals.get('tax_ids', []),
                        'tax_tag_ids': vals.get('tax_tag_ids', []),
                        'tax_repartition_line_id': vals.get('tax_repartition_line_id'),
                        'group_tax_id': vals.get('group_tax_id'),
                    }))
                    is_early_payment_applied = True

        if line_ids_create_command_list:
            self.line_ids = line_ids_create_command_list

        return is_early_payment_applied

    def _lines_widget_check_apply_partial_matching(self):
        """ Try to apply a partial matching on the currently mounted journal items.

        :return: True if applied, False otherwise.
        """
        self._ensure_loaded_lines()

        all_aml_lines = self.line_ids.filtered(lambda x: x.flag == 'new_aml')
        if all_aml_lines:
            last_line = all_aml_lines[-1]

            # Cleanup the existing partials if not on the last line.
            line_ids_commands = []
            for aml_line in all_aml_lines:
                is_partial = aml_line.display_stroked_amount_currency or aml_line.display_stroked_balance
                if is_partial and not aml_line.manually_modified:
                    line_ids_commands.append(Command.update(aml_line.id, {
                        'amount_currency': aml_line.source_amount_currency,
                        'balance': aml_line.source_balance,
                    }))
            if line_ids_commands:
                self.line_ids = line_ids_commands
                self._lines_widget_recompute_exchange_diff()

            # Check for a partial reconciliation.
            partial_amounts = self._lines_widget_check_partial_amount(last_line)

            if partial_amounts:
                # Make a partial: an auto-balance line is no longer necessary.
                last_line.amount_currency = partial_amounts['amount_currency']
                last_line.balance = partial_amounts['balance']
                exchange_line = partial_amounts['exchange_diff_line']
                if exchange_line:
                    exchange_line.balance = partial_amounts['exchange_balance']
                    if exchange_line.currency_id == self.company_currency_id:
                        exchange_line.amount_currency = exchange_line.balance
                return True

        return False

    def _lines_widget_load_new_amls(self, amls, reco_model=None):
        """ Create counterpart lines for the journal items passed as parameter."""
        self._ensure_loaded_lines()

        # Create a new line for each aml.
        line_ids_commands = []
        kwargs = {'reconcile_model_id': reco_model.id} if reco_model else {}
        for aml in amls:
            aml_line_vals = self._lines_widget_prepare_new_aml_line(aml, **kwargs)
            line_ids_commands.append(Command.create(aml_line_vals))

        if not line_ids_commands:
            return

        self.line_ids = line_ids_commands

    def _convert_to_tax_base_line_dict(self, line):
        """ Convert the current dictionary in order to use the generic taxes computation method defined on account.tax.

        :return: A python dictionary.
        """
        self.ensure_one()
        tax_type = line.tax_ids[0].type_tax_use if line.tax_ids else None
        is_refund = (tax_type == 'sale' and line.balance > 0.0) or (tax_type == 'purchase' and line.balance < 0.0)

        if line.force_price_included_taxes:
            handle_price_include = True
            extra_context = {'force_price_include': True}
        else:
            handle_price_include = False
            extra_context = None

        return self.env['account.tax']._convert_to_tax_base_line_dict(
            line,
            partner=line.partner_id,
            currency=line.currency_id,
            taxes=line.tax_ids,
            price_unit=line.tax_base_amount_currency,
            quantity=1.0,
            account=line.account_id,
            analytic_distribution=line.analytic_distribution,
            price_subtotal=line.tax_base_amount_currency,
            is_refund=is_refund,
            handle_price_include=handle_price_include,
            extra_context=extra_context,
        )

    def _convert_to_tax_line_dict(self, line):
        """ Convert the current dictionary in order to use the generic taxes computation method defined on account.tax.

        :return: A python dictionary.
        """
        self.ensure_one()

        return self.env['account.tax']._convert_to_tax_line_dict(
            line,
            partner=line.partner_id,
            currency=line.currency_id,
            taxes=line.tax_ids,
            tax_tags=line.tax_tag_ids,
            tax_repartition_line=line.tax_repartition_line_id,
            group_tax=line.group_tax_id,
            account=line.account_id,
            analytic_distribution=line.analytic_distribution,
            tax_amount=line.amount_currency,
        )

    def _lines_widget_prepare_tax_line(self, tax_line_vals):
        self.ensure_one()

        tax_rep = self.env['account.tax.repartition.line'].browse(tax_line_vals['tax_repartition_line_id'])
        if tax_line_vals['tax_id'] == tax_rep.tax_id.id:
            group_tax = self.env['account.tax']
        else:
            group_tax = self.env['account.tax'].browse(tax_line_vals['tax_id'])
        currency = self.env['res.currency'].browse(tax_line_vals['currency_id'])
        amount_currency = tax_line_vals['tax_amount']
        balance = self.st_line_id._prepare_counterpart_amounts_using_st_line_rate(currency, None, amount_currency)['balance']

        return {
            'flag': 'tax_line',

            'account_id': tax_line_vals['account_id'],
            'date': self.st_line_id.date,
            'name': tax_rep.tax_id.name,
            'partner_id': tax_line_vals['partner_id'],
            'currency_id': currency.id,
            'amount_currency': amount_currency,
            'balance': balance,

            'analytic_distribution': tax_line_vals['analytic_distribution'],
            'tax_repartition_line_id': tax_rep.id,
            'tax_ids': tax_line_vals['tax_ids'],
            'tax_tag_ids': tax_line_vals['tax_tag_ids'],
            'group_tax_id': group_tax.id,
        }

    def _lines_widget_recompute_taxes(self):
        self.ensure_one()
        self._ensure_loaded_lines()

        base_lines = self.line_ids.filtered(lambda x: x.flag == 'manual' and not x.tax_repartition_line_id)
        tax_lines = self.line_ids.filtered(lambda x: x.flag == 'tax_line')

        tax_results = self.env['account.tax']._compute_taxes(
            [self._convert_to_tax_base_line_dict(x) for x in base_lines],
            tax_lines=[self._convert_to_tax_line_dict(x) for x in tax_lines],
            include_caba_tags=True,
        )

        line_ids_commands = []

        # Update the base lines.
        for base_line_vals, to_update in tax_results['base_lines_to_update']:
            line = base_line_vals['record']
            amount_currency = to_update['price_subtotal']
            if line.flag == 'new_aml':
                rate = abs(line.source_amount_currency) / abs(line.source_balance)
                balance = line.company_currency_id.round(amount_currency / rate)
            else:
                balance = self.st_line_id\
                    ._prepare_counterpart_amounts_using_st_line_rate(line.currency_id, line.source_balance, amount_currency)['balance']

            line_ids_commands.append(Command.update(line.id, {
                'balance': balance,
                'amount_currency': amount_currency,
                'tax_tag_ids': to_update['tax_tag_ids'],
            }))

        # Tax lines that are no longer needed.
        for tax_line_vals in tax_results['tax_lines_to_delete']:
            line_ids_commands.append(Command.unlink(tax_line_vals['record'].id))

        # Newly created tax lines.
        for tax_line_vals in tax_results['tax_lines_to_add']:
            line_ids_commands.append(Command.create(self._lines_widget_prepare_tax_line(tax_line_vals)))

        # Update of existing tax lines.
        for tax_line_vals, to_update in tax_results['tax_lines_to_update']:
            new_line_vals = self._lines_widget_prepare_tax_line(to_update)
            line_ids_commands.append(Command.update(tax_line_vals['record'].id, {
                'amount_currency': new_line_vals['amount_currency'],
                'balance': new_line_vals['balance'],
            }))

        self.line_ids = line_ids_commands

    def _lines_widget_recompute_exchange_diff(self):
        self.ensure_one()
        self._ensure_loaded_lines()

        line_ids_commands = []

        # Clean the existing lines.
        for exchange_diff in self.line_ids.filtered(lambda x: x.flag == 'exchange_diff'):
            line_ids_commands.append(Command.unlink(exchange_diff.id))

        new_amls = self.line_ids.filtered(lambda x: x.flag == 'new_aml')
        for new_aml in new_amls:

            # Compute the balance of the line using the rate/currency coming from the bank transaction.
            amounts_in_st_curr = self.st_line_id._prepare_counterpart_amounts_using_st_line_rate(
                new_aml.currency_id,
                new_aml.balance,
                new_aml.amount_currency,
            )
            balance = amounts_in_st_curr['balance']
            if new_aml.currency_id == self.company_currency_id and self.transaction_currency_id != self.company_currency_id:
                # The reconciliation will be expressed using the rate of the statement line.
                balance = new_aml.balance
            elif new_aml.currency_id != self.company_currency_id and self.transaction_currency_id == self.company_currency_id:
                # The reconciliation will be expressed using the foreign currency of the aml to cover the Mexican
                # case.
                balance = new_aml.currency_id\
                    ._convert(new_aml.amount_currency, self.transaction_currency_id, self.company_id, self.st_line_id.date)

            # Compute the exchange difference balance.
            exchange_diff_balance = balance - new_aml.balance
            if self.company_currency_id.is_zero(exchange_diff_balance):
                continue

            expense_exchange_account = self.company_id.expense_currency_exchange_account_id
            income_exchange_account = self.company_id.income_currency_exchange_account_id

            if exchange_diff_balance > 0.0:
                account = expense_exchange_account
            else:
                account = income_exchange_account

            line_ids_commands.append(Command.create({
                'flag': 'exchange_diff',
                'source_aml_id': new_aml.source_aml_id.id,

                'account_id': account.id,
                'date': new_aml.date,
                'name': _("Exchange Difference: %s", new_aml.name),
                'partner_id': new_aml.partner_id.id,
                'currency_id': new_aml.currency_id.id,
                'amount_currency': exchange_diff_balance if new_aml.currency_id == self.company_currency_id else 0.0,
                'balance': exchange_diff_balance,
            }))

        if line_ids_commands:
            self.line_ids = line_ids_commands

            # Reorder to put each exchange line right after the corresponding new_aml.
            new_lines = self.env['bank.rec.widget.line']
            for line in self.line_ids:
                if line.flag == 'exchange_diff':
                    continue

                new_lines |= line
                if line.flag == 'new_aml':
                    exchange_diff = self.line_ids\
                        .filtered(lambda x: x.flag == 'exchange_diff' and x.source_aml_id == line.source_aml_id)
                    new_lines |= exchange_diff
            self.line_ids = new_lines

    def _lines_widget_prepare_reco_model_write_off_vals(self, reco_model, write_off_vals):
        self.ensure_one()

        balance = self.st_line_id\
            ._prepare_counterpart_amounts_using_st_line_rate(self.transaction_currency_id, None, write_off_vals['amount_currency'])['balance']

        return {
            'flag': 'manual',

            'account_id': write_off_vals['account_id'],
            'date': self.st_line_id.date,
            'name': write_off_vals['name'],
            'partner_id': write_off_vals['partner_id'],
            'currency_id': write_off_vals['currency_id'],
            'amount_currency': write_off_vals['amount_currency'],
            'balance': balance,
            'tax_base_amount_currency': write_off_vals['amount_currency'],

            'reconcile_model_id': reco_model.id,
            'analytic_distribution': write_off_vals['analytic_distribution'],
            'tax_ids': write_off_vals['tax_ids'],
        }

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def _ensure_loaded_lines(self):
        # Ensure the lines are well loaded.
        # Suppose the initial values of 'line_ids' are 2 lines,
        # "self.line_ids = [Command.create(...)]" will produce a single new line in 'line_ids' but three lines in case
        # the field is accessed before.
        self.line_ids

    def _action_clear_manual_operations_form(self):
        self.form_index = None

    def _action_reset_wizard(self):
        self.ensure_one()
        self.invalidate_model(fnames=['line_ids'])
        self._action_trigger_matching_rules()

    def _action_focus_liquidity_line(self, field_clicked=None):
        self.ensure_one()
        liquidity_line = self.line_ids.filtered(lambda x: x.flag == 'liquidity')
        self._action_mount_line_in_edit(liquidity_line.index, field_clicked=field_clicked)

    def _action_trigger_matching_rules(self):
        self.ensure_one()

        if self.st_line_id.is_reconciled:
            return

        reconcile_models = self.env['account.reconcile.model'].search([
            ('rule_type', '!=', 'writeoff_button'),
            ('company_id', '=', self.company_id.id),
        ])
        matching = reconcile_models._apply_rules(self.st_line_id, self.partner_id)

        if matching.get('amls'):
            reco_model = matching['model']
            # In case there is a write-off, keep the whole amount and let the write-off doing the auto-balancing.
            allow_partial = matching.get('status') != 'write_off'
            self._action_add_new_amls(matching['amls'], reco_model=reco_model, allow_partial=allow_partial)
        if matching.get('status') == 'write_off':
            reco_model = matching['model']
            self._action_select_reconcile_model(reco_model)
        if matching.get('auto_reconcile'):
            self.matching_rules_allow_auto_reconcile = True
        return matching

    def _action_mount_line_in_edit(self, line_index, field_clicked=None):
        self.ensure_one()

        line = self.line_ids.filtered(lambda x: x.index == line_index)

        self.form_force_negative_sign = line.flag == 'new_aml' and (line.source_balance < 0.0 or line.source_amount_currency < 0.0)
        balance_sign = -1 if self.form_force_negative_sign else 1

        self.form_index = line.index
        self.form_flag = line.flag
        self.form_name = line.name
        self.form_date = line.date
        self.form_account_id = line.account_id
        self.form_partner_id = line.partner_id
        self.form_currency_id = line.currency_id
        self.analytic_distribution = line.analytic_distribution
        self.form_tax_ids = [Command.set(line.tax_ids.ids)]
        self.form_amount_currency = balance_sign * line.amount_currency
        self.form_balance = balance_sign * line.balance

    def _action_remove_line(self, line_index):
        self.ensure_one()
        line = self.line_ids.filtered(lambda x: x.index == line_index)
        is_taxes_recomputation_needed = bool(line.tax_ids)

        # Update 'line_ids'.
        self.line_ids = [Command.unlink(line.id)]

        # Recompute taxes and auto balance the lines.
        if is_taxes_recomputation_needed:
            self._lines_widget_recompute_taxes()
        if line.flag == 'new_aml':
            if not self._lines_widget_check_apply_early_payment_discount():
                self._lines_widget_check_apply_partial_matching()
            self._lines_widget_recompute_exchange_diff()
        self._lines_widget_add_auto_balance_line()
        self._action_clear_manual_operations_form()

    def _action_add_new_amls(self, amls, reco_model=None, allow_partial=True):
        self.ensure_one()
        self._lines_widget_load_new_amls(amls, reco_model=reco_model)
        self._lines_widget_recompute_exchange_diff()
        if not self._lines_widget_check_apply_early_payment_discount() and allow_partial:
            self._lines_widget_check_apply_partial_matching()
        self._lines_widget_add_auto_balance_line()
        self._action_clear_manual_operations_form()

    def _action_remove_new_amls(self, amls):
        self.ensure_one()
        for line in self.line_ids.filtered(lambda x: x.flag == 'new_aml' and x.source_aml_id in amls):
            self._action_remove_line(line.index)

    def _action_select_reconcile_model(self, reco_model):
        self.ensure_one()

        # Cleanup a previously selected model.
        self.line_ids = [
            Command.unlink(x.id)
            for x in self.line_ids
            if x.flag not in ('new_aml', 'liquidity') and x.reconcile_model_id and x.reconcile_model_id != reco_model
        ]
        self._lines_widget_recompute_taxes()

        # Compute the residual balance on which apply the newly selected model.
        auto_balance_line_vals = self._lines_widget_prepare_auto_balance_line()
        residual_balance = auto_balance_line_vals['amount_currency']

        write_off_vals_list = reco_model._apply_lines_for_bank_widget(residual_balance, self.partner_id, self.st_line_id)

        # Apply the newly generated lines.
        self.line_ids = [
            Command.create(self._lines_widget_prepare_reco_model_write_off_vals(reco_model, x))
            for x in write_off_vals_list
        ]

        self._lines_widget_recompute_taxes()
        self._lines_widget_add_auto_balance_line()

        if reco_model.to_check != self.to_check:
            self.st_line_id.move_id.to_check = reco_model.to_check
            self.invalidate_recordset(fnames=['to_check'])

    def _lines_widget_add_reco_model_write_off_lines(self, reco_model, write_off_vals_list):
        self.line_ids = [
            Command.create(self._lines_widget_prepare_reco_model_write_off_vals(reco_model, x))
            for x in write_off_vals_list
        ]

    def _action_unselect_reconcile_model(self, reco_model):
        self.ensure_one()

    def _get_line_create_command_dict(
        self, line, i, amount_currency, balance, partner_id_to_set=None
    ):
        return {
            'name': line.name,
            'sequence': i,
            'account_id': line.account_id.id,
            'partner_id': partner_id_to_set if line.flag in ('liquidity', 'auto_balance') else line.partner_id.id,
            'currency_id': line.currency_id.id,
            'reconcile_model_id': line.reconcile_model_id.id,
            'analytic_distribution': line.analytic_distribution,
            'tax_repartition_line_id': line.tax_repartition_line_id.id,
            'tax_ids': [Command.set(line.tax_ids.ids)],
            'tax_tag_ids': [Command.set(line.tax_tag_ids.ids)],
            'group_tax_id': line.group_tax_id.id,
            "amount_currency": amount_currency,
            "balance": balance,
        }

    def button_validate(self, async_action=False):
        self.ensure_one()

        if self.state != 'valid':
            self.next_action_todo = {'type': 'move_to_next'}
            return

        partners = (self.line_ids.filtered(lambda x: x.flag != 'liquidity')).partner_id
        partner_id_to_set = partners.id if len(partners) == 1 else None

        # Prepare the lines to be created.
        to_reconcile = []
        line_ids_create_command_list = []
        aml_to_exchange_diff_vals = {}
        for i, line in enumerate(self.line_ids):
            if line.flag == 'exchange_diff':
                continue

            amount_currency = line.amount_currency
            balance = line.balance
            if line.flag == 'new_aml':
                to_reconcile.append((i, line.source_aml_id.id))
                exchange_diff = self.line_ids \
                    .filtered(lambda x: x.flag == 'exchange_diff' and x.source_aml_id == line.source_aml_id)
                if exchange_diff:
                    aml_to_exchange_diff_vals[i] = {
                        'amount_residual': exchange_diff.balance,
                        'amount_residual_currency': exchange_diff.amount_currency,
                        'analytic_distribution': exchange_diff.analytic_distribution,
                    }
                    # Squash amounts of exchange diff into corresponding new_aml
                    amount_currency += exchange_diff.amount_currency
                    balance += exchange_diff.balance
            line_ids_create_command_list.append(Command.create(
                self._get_line_create_command_dict(
                    line, i, amount_currency, balance, partner_id_to_set
                )
            ))

        self.js_action_reconcile_st_line(
            self.st_line_id.id,
            {
                'command_list': line_ids_create_command_list,
                'to_reconcile': to_reconcile,
                'exchange_diff': aml_to_exchange_diff_vals,
                'partner_id': partner_id_to_set,
            },
        )
        self.next_action_todo = {'type': 'reconcile_st_line'}

    def button_to_check(self, async_action=True):
        self.ensure_one()
        if self.state == 'valid':
            self.button_validate(async_action=async_action)
        else:
            self.next_action_todo = {'type': 'move_to_next'}
        self.st_line_id.move_id.to_check = True
        self.invalidate_recordset(fnames=['to_check'])

    def button_set_as_checked(self):
        self.ensure_one()
        self.st_line_id.move_id.to_check = False
        if self.st_line_is_reconciled:
            self.next_action_todo = {'type': 'move_to_next'}
        else:
            self.next_action_todo = {'type': 'refresh_statement_line'}
        self.invalidate_recordset(fnames=['to_check'])

    def button_reset(self):
        self.ensure_one()

        if self.state == 'reconciled':
            self.st_line_id.action_undo_reconciliation()

            self._ensure_loaded_lines()
            self._action_trigger_matching_rules()

        self.next_action_todo = {'type': 'reset_form'}

    def button_form_apply_suggestion(self):
        self.ensure_one()
        self.form_amount_currency = self.form_suggest_amount_currency
        self.form_balance = self.form_suggest_balance

        if self.form_single_currency_mode:
            self._onchange_form_balance()
        else:
            self._onchange_form_amount_currency()

    def button_form_partner_receivable(self):
        self.ensure_one()
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)
        self.form_account_id = self.form_partner_receivable_account_id
        self._onchange_form_account_id()

    def button_form_partner_payable(self):
        self.ensure_one()
        line = self._lines_widget_get_line_in_edit_form()
        if not line:
            return

        self._lines_widget_form_turn_auto_balance_into_manual_line(line)
        self.form_account_id = self.form_partner_payable_account_id
        self._onchange_form_account_id()

    def button_form_redirect_to_move_form(self, move_id):
        self.ensure_one()
        move = self.env['account.move'].browse(int(move_id))

        action = {
            'type': 'ir.actions.act_window',
            'context': {'create': False},
            'view_mode': 'form',
        }

        if move.payment_id:
            action.update({
                'res_model': 'account.payment',
                'res_id': move.payment_id.id,
            })
        else:
            action.update({
                'res_model': 'account.move',
                'res_id': move.id,
            })

        self.next_action_todo = clean_action(action, self.env)

    @api.model
    def _prepare_button_show_reconciled_action(self, records, **kwargs):
        action = {
            'type': 'ir.actions.act_window',
            'res_model': records._name,
            'context': {'create': False},
            **kwargs,
        }
        if len(records) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': records.id,
            })
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('id', 'in', records.ids)],
            })
        return action

    @api.model
    def js_action_reconcile_st_line(self, st_line_id, params):
        st_line = self.env['account.bank.statement.line'].browse(st_line_id)
        move = st_line.move_id

        # Update the move.
        move_ctx = move.with_context(
            skip_invoice_sync=True,
            skip_invoice_line_sync=True,
            skip_account_move_synchronization=True,
            force_delete=True,
        )
        move_ctx.write({'partner_id': params['partner_id'], 'line_ids': [Command.clear()] + params['command_list']})
        if move_ctx.state == 'draft':
            move_ctx.action_post()

        # Perform the reconciliation.
        for index, counterpart_aml_id in params['to_reconcile']:
            counterpart_aml = self.env['account.move.line'].browse(counterpart_aml_id)
            line_aml = move_ctx.line_ids.filtered(lambda x: x.sequence == index)
            exchange_diff_move = False
            # Create exchange difference move
            exchange_amounts = params['exchange_diff'].get(index, {})
            exchange_analytic_distribution = exchange_amounts.pop('analytic_distribution', False)
            if exchange_amounts:
                exch_diff_related_aml = line_aml if exchange_amounts['amount_residual'] * line_aml.amount_residual > 0 else counterpart_aml
                exchange_vals = exch_diff_related_aml._prepare_exchange_difference_move_vals(
                    [exchange_amounts],
                    exchange_date=max(line_aml.date, counterpart_aml.date),
                    exchange_analytic_distribution=exchange_analytic_distribution,
                )
                exchange_diff_move = self.env['account.move.line']._create_exchange_difference_move(exchange_vals)
            rec_res = (line_aml + counterpart_aml).with_context(no_exchange_difference=True).reconcile()
            rec_res['partials'].exchange_move_id = exchange_diff_move

        # Fill missing partner.
        st_line.with_context(skip_account_move_synchronization=True).partner_id = params['partner_id']

        # Create missing partner bank if necessary.
        if st_line.account_number and st_line.partner_id and not st_line.partner_bank_id:
            st_line.partner_bank_id = st_line._find_or_create_bank_account()

        # Refresh analytic lines.
        move.line_ids.analytic_line_ids.unlink()
        move.line_ids._create_analytic_lines()

    def collect_global_info_data(self, journal_id):
        self._cr.execute(f'''
            SELECT
                st_line.currency_id,
                COALESCE(SUM(st_line.amount), 0.0) AS amount
            FROM account_bank_statement_line st_line
            JOIN account_move am ON st_line.move_id = am.id
            WHERE am.state = 'posted' AND am.journal_id = %s
            GROUP BY st_line.currency_id
        ''', [journal_id])

        balance_by_currency = {}
        for currency_id, amount in self._cr.fetchall():
            balance_by_currency[currency_id] = amount

        if len(balance_by_currency) != 1:
            return {'balance_amount': None}

        for currency_id, amount in balance_by_currency.items():
            currency = self.env['res.currency'].browse(currency_id)
            return {'balance_amount': formatLang(self.env, amount, currency_obj=currency)}

    def action_open_bank_reconciliation_report(self, journal_id):
        # abstract
        raise UserError(_("Please install the 'Accounting Reports' module."))
