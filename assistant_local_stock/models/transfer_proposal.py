import uuid
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AssistantStockTransferProposal(models.Model):
    _name = "assistant.stock.transfer.proposal"
    _description = "Assistant Stock Transfer Proposal"
    _order = "id desc"

    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, ondelete="cascade")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade")
    origin_location_id = fields.Many2one("stock.location", required=True, ondelete="restrict")
    destination_location_id = fields.Many2one("stock.location", required=True, ondelete="restrict")
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    quantity = fields.Float(required=True)
    uom_id = fields.Many2one("uom.uom", required=True, ondelete="restrict")
    state = fields.Selection(
        [("draft", "Draft"), ("used", "Used"), ("expired", "Expired"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )
    token = fields.Char(required=True, copy=False)
    expires_at = fields.Datetime(required=True)
    picking_id = fields.Many2one("stock.picking", ondelete="set null")
    result_message = fields.Text()

    def _check_access_owner(self):
        self.ensure_one()
        if self.user_id != self.env.user or self.company_id != self.env.company:
            raise AccessError(self.env._("This transfer proposal does not belong to the current user/company."))
        if not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(self.env._("Stock user access is required."))

    def _is_expired(self):
        self.ensure_one()
        return self.expires_at and fields.Datetime.now() > self.expires_at

    @api.model
    def create_proposal(self, origin_location, destination_location, product, quantity, uom):
        env = self.env
        if not env.user.has_group("stock.group_stock_user"):
            raise AccessError(env._("Stock user access is required."))
        if quantity <= 0:
            raise ValidationError(env._("Quantity must be positive."))
        if origin_location.company_id and origin_location.company_id != env.company:
            raise ValidationError(env._("Origin location is in another company."))
        if destination_location.company_id and destination_location.company_id != env.company:
            raise ValidationError(env._("Destination location is in another company."))
        if product.company_id and product.company_id != env.company:
            raise ValidationError(env._("Product is in another company."))

        quants = env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id", "=", origin_location.id),
        ])
        available = sum((quant.quantity - quant.reserved_quantity) for quant in quants)

        proposal = self.create({
            "user_id": env.user.id,
            "company_id": env.company.id,
            "origin_location_id": origin_location.id,
            "destination_location_id": destination_location.id,
            "product_id": product.id,
            "quantity": quantity,
            "uom_id": uom.id,
            "token": uuid.uuid4().hex,
            "expires_at": fields.Datetime.now() + timedelta(minutes=5),
            "state": "draft",
        })
        return proposal, available

    def confirm_transfer(self, token):
        self.ensure_one()
        self._check_access_owner()
        if self.state != "draft":
            raise ValueError(self.env._("This transfer proposal is no longer available."))
        if self.token != token:
            raise ValueError(self.env._("Invalid confirmation token."))
        if self._is_expired():
            self.state = "expired"
            raise ValueError(self.env._("This transfer proposal has expired."))

        origin = self.origin_location_id
        destination = self.destination_location_id
        product = self.product_id
        quantity = self.quantity
        uom = self.uom_id

        # Revalidate permissions and locations.
        if not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(self.env._("Stock user access is required."))

        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not picking_type:
            raise UserError(self.env._("No internal operation type is configured."))

        self.state = "used"
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": origin.id,
            "location_dest_id": destination.id,
            "company_id": self.company_id.id,
            "origin": "assistant transfer %s" % self.id,
        })
        self.env["stock.move"].create({
            "name": product.display_name,
            "product_id": product.id,
            "product_uom_qty": quantity,
            "product_uom": uom.id,
            "picking_id": picking.id,
            "location_id": origin.id,
            "location_dest_id": destination.id,
            "company_id": self.company_id.id,
        })
        picking.action_confirm()
        picking.action_assign()

        result_status = "ok"
        message = ""
        try:
            action = picking.button_validate()
            if isinstance(action, dict):
                result_status = "needs_confirmation"
                message = self.env._("Odoo requires an additional decision before completing the transfer.")
            else:
                message = self.env._("Transfer completed.")
        except Exception as exc:
            result_status = "error"
            message = str(exc)

        self.picking_id = picking.id
        self.result_message = message
        return {
            "status": result_status,
            "proposal_id": self.id,
            "picking_id": picking.id,
            "picking_state": picking.state,
            "message": message,
        }
