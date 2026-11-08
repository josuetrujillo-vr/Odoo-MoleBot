import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


MAX_CHAT_MESSAGE_LENGTH = 4000
MODEL_CAPABILITIES = frozenset({"hr.vacation.balance.get_own"})


class AssistantConversation(models.Model):
    _name = "assistant.conversation"
    _description = "Assistant Conversation"

    name = fields.Char(required=True)
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user,
                              index=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", required=True,
                                  default=lambda self: self.env.company, index=True)
    message_ids = fields.One2many("assistant.message", "conversation_id", string="Messages")

    def write(self, vals):
        if "user_id" in vals and any(record.user_id.id != vals["user_id"] for record in self):
            raise AccessError(self.env._("The conversation owner cannot be changed."))
        if "company_id" in vals and any(record.company_id.id != vals["company_id"] for record in self):
            raise AccessError(self.env._("The conversation company cannot be changed."))
        return super().write(vals)

    def get_chat_messages(self):
        self.ensure_one()
        self.check_access("read")
        return [
            {"id": message.id, "role": message.role, "body": message.body}
            for message in self.message_ids
        ]

    def submit_chat_message(self, text):
        self.ensure_one()
        self.check_access("write")

        if not isinstance(text, str):
            raise ValidationError(self.env._("The message must be text."))
        text = text.strip()
        if not text:
            raise ValidationError(self.env._("The message cannot be empty."))
        if len(text) > MAX_CHAT_MESSAGE_LENGTH:
            raise ValidationError(self.env._("The message is too long."))

        self.env["assistant.message"].create({
            "conversation_id": self.id,
            "body": text,
        })

        status = "unavailable"
        try:
            provider = self.env["assistant.inference"]
            conversation_messages = [
                {"role": message.role, "content": message.body}
                for message in self.message_ids
            ]
            tools = self._assistant_tool_definitions()
            reply = provider._chat(conversation_messages, tools)
            self._apply_model_reply(reply)
            status = "ok"
        except (UserError, ValidationError, ValueError, OSError, RuntimeError):
            status = "unavailable"

        return {
            "messages": self.get_chat_messages(),
            "status": status,
        }

    def action_open_chat(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.client",
            "tag": "assistant_local.chat",
            "name": self.env._("Assistant"),
            "params": {"context": {"conversationId": self.id}},
        }

    def _assistant_tool_definitions(self):
        capabilities = self.env["assistant.capability"]._get_capabilities()
        tools = []
        for name, (schema, _handler) in capabilities.items():
            if name not in MODEL_CAPABILITIES:
                continue
            properties = {}
            required = []
            for key, expected_type in schema.items():
                json_type = "string"
                if expected_type is int:
                    json_type = "integer"
                elif expected_type is float:
                    json_type = "number"
                elif expected_type is bool:
                    json_type = "boolean"
                elif expected_type is dict:
                    json_type = "object"
                elif expected_type is list:
                    json_type = "array"
                properties[key] = {"type": json_type}
                required.append(key)
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": name,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                },
            })
        return tools

    def _apply_model_reply(self, reply):
        if not isinstance(reply, dict):
            return
        executed = False
        for tool_call in reply.get("tool_calls", []) or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            arguments = function.get("arguments", {})
            if name not in MODEL_CAPABILITIES or not isinstance(arguments, dict):
                continue
            try:
                result = self.env["assistant.capability"]._execute_capability(name, arguments)
                executed = True
                self.env["assistant.message"]._create_assistant_message(
                    self,
                    "Resultado de %s: %s" % (name, json.dumps(result, ensure_ascii=False, default=str)),
                )
            except (UserError, ValidationError, ValueError, AccessError):
                executed = True
                self.env["assistant.message"]._create_assistant_message(
                    self,
                    "No se pudo ejecutar la capacidad solicitada.",
                )
        if not executed:
            self.env["assistant.message"]._create_assistant_message(
                self, "Por ahora solo puedo consultar tu saldo de vacaciones."
            )
