# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.tools import float_compare, float_round


class Task(models.Model):
    _inherit = "project.task"

    def _prepare_materials_delivery(self):
        """ Prepare the materials delivery

            We validate the stock and generates/updates delivery order.
            This method is called at the end of the action_fsm_validate method in industry_fsm_sale.
        """
        for task in self.filtered(lambda x: x.allow_billable and x.sale_order_id):
            exception = False
            sale_line = self.env['sale.order.line'].sudo().search([('order_id', '=', task.sale_order_id.id), ('task_id', '=', task.id)])
            for order_line in sale_line:
                to_log = {}
                total_qty = sum(order_line.move_ids.filtered(lambda p: p.state not in ['cancel']).mapped('product_uom_qty'))
                if float_compare(order_line.product_uom_qty, total_qty, precision_rounding=order_line.product_uom.rounding) < 0:
                    to_log[order_line] = (order_line.product_uom_qty, total_qty)

                if to_log:
                    exception = True
                    documents = self.env['stock.picking']._log_activity_get_documents(to_log, 'move_ids', 'UP')
                    documents = {k: v for k, v in documents.items() if k[0].state not in ['cancel', 'done']}
                    self.env['sale.order']._log_decrease_ordered_quantity(documents)
            if not exception:
                task.sudo()._validate_stock()

    def _validate_stock(self):
        self.ensure_one()
        all_fsm_sn_moves = self.env['stock.move']
        ml_to_create = []
        for so_line in self.sale_order_id.order_line:
            if not (so_line.task_id.is_fsm or so_line.project_id.is_fsm or so_line.fsm_lot_id):
                continue
            qty = so_line.product_uom_qty - so_line.qty_delivered
            fsm_sn_moves = self.env['stock.move']
            if not qty:
                continue
            for last_move in so_line.move_ids.filtered(lambda p: p.state not in ['done', 'cancel'] and p.quantity_done < qty):
                move = last_move
                fsm_sn_moves |= last_move
                while move.move_orig_ids.filtered(lambda m: m.quantity_done < qty):
                    move = move.move_orig_ids
                    fsm_sn_moves |= move
            for fsm_sn_move in fsm_sn_moves:
                ml_vals = fsm_sn_move._prepare_move_line_vals(quantity=0)
                task = fsm_sn_move.sale_line_id.task_id
                # if the move_line of the delivery is linked to the current task or is a taskless product, set his qty_done accordinlgy
                if not task or task == self:
                    ml_vals['qty_done'] = qty - fsm_sn_move.quantity_done
                ml_vals['lot_id'] = so_line.fsm_lot_id.id
                if fsm_sn_move.product_id.tracking == "serial":
                    quants = self.env['stock.quant']._gather(fsm_sn_move.product_id, fsm_sn_move.location_id, lot_id=so_line.fsm_lot_id)
                    quant = quants.filtered(lambda q: q.quantity == 1.0)[:1]
                    ml_vals['location_id'] = quant.location_id.id or fsm_sn_move.location_id.id
                ml_to_create.append(ml_vals)
            all_fsm_sn_moves |= fsm_sn_moves
        self.env['stock.move.line'].create(ml_to_create)
        for so_line in self.sale_order_id.order_line:
            # set the quantity delivered of the sol to the quantity ordered for the product linked to the task
            if so_line.task_id == self and not so_line.product_id.service_policy == 'delivered_timesheet':
                so_line.qty_delivered = so_line.product_uom_qty

        def is_fsm_material_picking(picking, task):
            """ this function returns if the picking is a picking ready to be validated. """
            moves = picking.move_ids
            while moves.move_dest_ids:
                moves = moves.move_dest_ids
            for move in moves:
                sol = move.sale_line_id
                if sol.fsm_lot_id:
                    continue
                if not (sol.product_id != task.project_id.timesheet_product_id \
                and sol != task.sale_line_id \
                and sol.product_uom_qty != 0 \
                # On the last and, we check if the task is either done (and thus already done for the delivery) or the current one (and thus about to be validated)
                # if not, we can not validate the delivery
                and (sol.task_id == task or sol.task_id.fsm_done)):
                    return False
            return True

        pickings_to_do = self.sale_order_id.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel'] and is_fsm_material_picking(p, self))
        # set the quantity done as the initial demand before validating the pickings
        for move in pickings_to_do.move_ids:
            if move.state in ('done', 'cancel') or move in all_fsm_sn_moves:
                continue
            rounding = move.product_uom.rounding
            if float_compare(move.quantity_done, move.product_uom_qty, precision_rounding=rounding) < 0:
                qty_to_do = float_round(
                    move.product_uom_qty - move.quantity_done,
                    precision_rounding=rounding,
                    rounding_method='HALF-UP')
                move._set_quantity_done(qty_to_do)
        pickings_to_do.with_context(skip_sms=True, cancel_backorder=True).button_validate()

    def write(self, vals):
        result = super().write(vals)
        if 'user_ids' in vals:
            for sale_order in self.filtered("is_fsm").sale_order_id.sudo().filtered(lambda order: order.state in ['draft', 'sent']):
                user = self.user_ids[:1]
                if user != sale_order.user_id:
                    sale_order.write({'user_id': user.id})
        return result

    def action_fsm_view_material(self):
        action = super(Task, self).action_fsm_view_material()
        action['context'].update({"warehouse": self.env.user._get_default_warehouse_id().id})
        return action
