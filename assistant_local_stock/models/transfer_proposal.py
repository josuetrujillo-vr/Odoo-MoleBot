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
        if not self._can_transfer():
            raise AccessError(self.env._("Inventory or administrator access is required."))

    @api.model
    def _can_transfer(self):
        user = self.env.user
        return (user.has_group("stock.group_stock_user")
                or user.has_group("base.group_system"))

    @api.model
    def _stock_env(self):
        """Return an environment allowed to write stock records.

        Inventory users already have those rights. A Settings administrator is
        explicitly allowed by this assistant, but Odoo only grants
        stock.picking/stock.move writes to Inventory users, so only the stock
        operations use sudo while the proposal stays owned by the real user.
        """
        if self.env.user.has_group("stock.group_stock_user"):
            return self.env
        if self.env.user.has_group("base.group_system"):
            return self.env(su=True)
        return self.env

    def _is_expired(self):
        self.ensure_one()
        return self.expires_at and fields.Datetime.now() > self.expires_at

    @api.model
    def create_proposal(self, origin_location, destination_location, product, quantity, uom):
        env = self.env
        if not self._can_transfer():
            raise AccessError(env._("Inventory or administrator access is required."))
        if quantity <= 0:
            raise ValidationError(env._("Quantity must be positive."))
        if origin_location.company_id and origin_location.company_id != env.company:
            raise ValidationError(env._("Origin location is in another company."))
        if destination_location.company_id and destination_location.company_id != env.company:
            raise ValidationError(env._("Destination location is in another company."))
        if product.company_id and product.company_id != env.company:
            raise ValidationError(env._("Product is in another company."))

        quants = self._stock_env()["stock.quant"].search([
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
        if not self._can_transfer():
            raise AccessError(self.env._("Inventory or administrator access is required."))

        stock_env = self._stock_env()
        picking_type = stock_env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not picking_type:
            raise UserError(self.env._("No internal operation type is configured."))

        self.state = "used"
        picking = stock_env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": origin.id,
            "location_dest_id": destination.id,
            "company_id": self.company_id.id,
            "origin": "assistant transfer %s" % self.id,
        })
        stock_env["stock.move"].create({
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
