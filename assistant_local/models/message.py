from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


def validated_body(body):
    if not isinstance(body, str) or not body.strip() or len(body) > 4000:
        raise ValidationError("Enter a message of at most 4,000 characters.")
    return body.strip()


class AssistantMessage(models.Model):
    _name = "assistant.message"
    _description = "Assistant Message"
    _order = "id"

    conversation_id = fields.Many2one("assistant.conversation", required=True,
                                      ondelete="cascade", index=True)
    role = fields.Selection([("user", "User"), ("assistant", "Assistant")], required=True)
    body = fields.Text(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        safe_values = []
        for vals in vals_list:
            if vals.get("role", "user") != "user":
                raise AccessError(self.env._("Assistant messages cannot be created directly."))
            safe_values.append({**vals, "role": "user", "body": validated_body(vals.get("body"))})
        return super().create(safe_values)

    def write(self, vals):
        raise AccessError(self.env._("Assistant messages cannot be changed."))

    @api.model
    def _create_assistant_message(self, conversation, body):
        conversation.ensure_one()
        conversation = self.env["assistant.conversation"].browse(conversation.id)
        conversation.check_access("write")
        return super(AssistantMessage, self).create({
            "conversation_id": conversation.id,
            "role": "assistant",
            "body": validated_body(body),
        })
