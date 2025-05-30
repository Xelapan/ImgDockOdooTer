# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime

from odoo import Command, models, fields, api
from odoo.addons.resource.models.resource import Intervals
from odoo.osv import expression
from odoo.http import request


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    employee_id = fields.Many2one('hr.employee', string="Employee", compute='_compute_employee_id')
    employee_ids = fields.Many2many('hr.employee', string='Working Employees', copy=False)
    employee_name = fields.Char(compute='_compute_employee_id')
    allow_employee = fields.Boolean(related='workcenter_id.allow_employee')

    def _compute_duration(self):
        wo_ids_without_employees = set()
        for wo in self:
            if not wo.workcenter_id.allow_employee:
                wo_ids_without_employees.add(wo.id)
                continue
            now = datetime.now()
            loss_type_times = defaultdict(lambda: self.env['mrp.workcenter.productivity'])
            for time in wo.time_ids:
                loss_type_times[time.loss_id.loss_type] |= time
            duration = 0
            for dummy, times in loss_type_times.items():
                duration += self._intervals_duration([(t.date_start, t.date_end or now, t) for t in times])
            wo.duration = duration
            wo.duration_unit = round(wo.duration / max(wo.qty_produced, 1), 2)
            if wo.duration_expected:
                wo.duration_percent = max(-2147483648, min(2147483647, 100 * (wo.duration_expected - wo.duration) / wo.duration_expected))
            else:
                wo.duration_percent = 0
        return super(MrpWorkorder, self.env['mrp.workorder'].browse(wo_ids_without_employees))._compute_duration()

    @api.depends('employee_ids')
    def _compute_employee_id(self):
        self.employee_id = self.env['hr.employee']
        self.employee_name = False
        if request and 'employee_id' in request.session:
            employee_id = request.session.get('employee_id')
        else:
            employee_id = 0
        for workorder in self:
            if employee_id in workorder.employee_ids.ids:
                workorder.employee_id = employee_id
                workorder.employee_name = self.env['hr.employee'].browse(employee_id).name

    def start_employee(self, employee_id):
        self.ensure_one()
        if not self.allow_employee or employee_id in self.employee_ids.ids and any(not t.date_end for t in self.time_ids if t.employee_id.id == employee_id):
            return
        self.employee_ids = [Command.link(employee_id)]
        time_data = self._prepare_timeline_vals(self.duration, fields.Datetime.now())
        time_data['employee_id'] = employee_id
        self.env['mrp.workcenter.productivity'].create(time_data)

    def stop_employee(self, employee_id):
        self.ensure_one()
        if employee_id not in self.employee_ids.ids:
            return
        self.employee_ids = [Command.unlink(employee_id)]
        self.env['mrp.workcenter.productivity'].search([
            ('employee_id', '=', employee_id),
            ('workorder_id', '=', self.id),
            ('date_end', '=', False)
        ])._close()
        self.employee_ids = [Command.unlink(employee_id)]

    def get_workorder_data(self):
        # Avoid to get the products full name because code and name are separate in the barcode app.
        data = super().get_workorder_data() or {}
        if not self.workcenter_id.allow_employee:
            data['employee_id'] = False
            data['employee_ids'] = []
            data['employee_list'] = []
            return data
        employee_domain = [('company_id', '=', self.company_id.id)]
        if self.workcenter_id.employee_ids:
            employee_domain = [('id', 'in', self.workcenter_id.employee_ids.ids)]
        fields_to_read = self.env['hr.employee']._get_employee_fields_for_tablet()
        data.update({
            "employee_id": self.employee_id.id,
            "employee_ids": self.employee_ids.ids,
            "employee_list": self.env['hr.employee'].search_read(employee_domain, fields_to_read, load=False),
        })
        return data

    def record_production(self):
        action = super().record_production()
        if action is not True and self.employee_id:
            action.get('context', {})['employee_id'] = self.employee_id.id
        return action

    def _domain_mrp_workcenter_productivity(self, doall):
        domain = super()._domain_mrp_workcenter_productivity(doall)
        employee_ids = []
        for wo in self:
            if wo.workcenter_id.allow_employee and wo.employee_id:
                employee_ids.append(wo.employee_id.id)
        if not employee_ids:
            return domain
        return expression.AND([domain, [
            '|',
                ('workorder_id.allow_employee', '=', False),
                '&',
                    ('workorder_id.allow_employee', '=', True),
                    ('employee_id', 'in', employee_ids)
        ]])

    def action_back(self):
        action = super().action_back()
        if self.employee_id:
            action['context']['employee_id'] = self.employee_id.id
            action['context']['employee_name'] = self.employee_id.name
        return action

    def _should_start_timer(self):
        """ Return True if the timer should start once the workorder is opened."""
        self.ensure_one()
        if self.workcenter_id.allow_employee:
            return False
        return super()._should_start_timer()

    def _intervals_duration(self, intervals):
        """ Return the duration of the given intervals.
        If intervals overlaps the duration is only counted once.

        The timer could be share between several intervals. However it is not
        an issue since the purpose is to make a difference between employee time and
        blocking time.

        :param list intervals: list of tuple (date_start, date_end, timer)
        """
        if not intervals:
            return 0.0
        duration = 0
        for date_start, date_stop, timer in Intervals(intervals):
            duration += timer.loss_id._convert_to_duration(date_start, date_stop, timer.workcenter_id)
        return duration

    def get_working_duration(self):
        self.ensure_one()
        if self.workcenter_id.allow_employee:
            now = fields.Datetime.now()
            return self._intervals_duration([(t.date_start, now, t) for t in self.time_ids if not t.date_end])
        return super().get_working_duration()

    def _cal_cost(self, times=None):
        res = super()._cal_cost(times=times)
        times = times or self.time_ids
        res += sum(times.mapped('total_cost'))
        return res
