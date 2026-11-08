from odoo import api, fields, models
from odoo.exceptions import AccessError


class AssistantAudit(models.Model):
    _name = "assistant.audit"
    _description = "Assistant Audit"
    _order = "id desc"

    capability = fields.Char(required=True)
    outcome = fields.Char(required=True)
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, ondelete="cascade")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade")
    created_at = fields.Datetime(default=fields.Datetime.now, readonly=True)

    @api.model
    def _record(self, capability, outcome):
        if not isinstance(capability, str) or not isinstance(outcome, str):
            raise ValueError("Invalid audit entry")
        record = self.sudo().create({
            "capability": capability,
            "outcome": outcome,
            "user_id": self.env.user.id,
            "company_id": self.env.company.id,
        })
        return self.env["assistant.audit"].browse(record.id)
