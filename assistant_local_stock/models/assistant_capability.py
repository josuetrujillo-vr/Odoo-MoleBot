import uuid

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AssistantStockCapability(models.AbstractModel):
    _inherit = "assistant.capability"
    _description = "Assistant Capability: Stock Transfer"

    @api.model
    def _get_capabilities(self):
        capabilities = super()._get_capabilities()
        capabilities["stock.internal_transfer.propose"] = (
            {
                "origin_location_id": int,
                "destination_location_id": int,
                "product_id": int,
                "quantity": [int, float],
                "uom_id": int,
            },
            self._propose_internal_transfer,
        )
        capabilities["stock.internal_transfer.confirm"] = (
            {"proposal_id": int, "confirmation_token": str},
            self._confirm_internal_transfer,
        )
        return capabilities

    @api.model
    def _propose_internal_transfer(self, _model, arguments):
        env = _model.env
        origin = env["stock.location"].browse(arguments["origin_location_id"])
        destination = env["stock.location"].browse(arguments["destination_location_id"])
        product = env["product.product"].browse(arguments["product_id"])
        uom = env["uom.uom"].browse(arguments["uom_id"])
        quantity = arguments["quantity"]

        if not origin.exists() or not destination.exists() or not product.exists() or not uom.exists():
            raise ValidationError(env._("Unknown location, product or unit of measure."))
        if origin == destination:
            raise ValidationError(env._("Origin and destination must be different."))
        if quantity <= 0:
            raise ValidationError(env._("Quantity must be positive."))

        Proposal = env["assistant.stock.transfer.proposal"]
        proposal, available = Proposal.create_proposal(origin, destination, product, quantity, uom)
        return {
            "proposal_id": proposal.id,
            "confirmation_token": proposal.token,
            "product": product.display_name,
            "origin": origin.display_name,
            "destination": destination.display_name,
            "quantity": quantity,
            "uom": uom.name,
            "available_quantity": available,
            "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
            "criteria": {
                "company_id": env.company.id,
                "user_id": env.user.id,
            },
            "references": ["stock.location", "product.product", "assistant.stock.transfer.proposal"],
        }

    @api.model
    def _confirm_internal_transfer(self, _model, arguments):
        env = _model.env
        proposal = env["assistant.stock.transfer.proposal"].browse(arguments["proposal_id"])
        if not proposal.exists():
            raise ValidationError(env._("Unknown transfer proposal."))
        proposal._check_access_owner()
        result = proposal.confirm_transfer(arguments["confirmation_token"])
        return result
