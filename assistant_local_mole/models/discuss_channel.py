from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import html2plaintext
from odoo.addons.assistant_local.mole_local import (
    is_safe_own_vacation_query, named_vacation_target,
)


MOLE_PARTNER_XMLID = "assistant_local_mole.partner_mole"
ALLOWED_CAPABILITY = "hr.vacation.balance.get_own"


class AssistantMoleDiscussChannel(models.Model):
    _inherit = "discuss.channel"
    _description = "Mole Discuss Channel (extension)"

    assistant_mole_owner_id = fields.Many2one(
        "res.users",
        string="Mole Owner",
        ondelete="cascade",
        index=True,
        readonly=True,
        copy=False,
        help="Authenticated user who owns this private Mole conversation.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and (
            "default_assistant_mole_owner_id" in self.env.context
            or any("assistant_mole_owner_id" in vals for vals in vals_list)
        ):
            raise AccessError(self.env._("Mole ownership is managed by the server."))
        return super().create(vals_list)

    def write(self, vals):
        if "assistant_mole_owner_id" in vals and not self.env.su:
            raise AccessError(self.env._("Mole ownership is managed by the server."))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _mole_partner(self):
        try:
            return self.env.ref(MOLE_PARTNER_XMLID)
        except ValueError:
            return self.env["res.partner"]

    def _is_mole_channel(self):
        self.ensure_one()
        mole = self._mole_partner()
        if not mole:
            return False
        if self.channel_type != "chat":
            return False
        if not self.assistant_mole_owner_id:
            return False
        member_partners = self.channel_member_ids.mapped("partner_id")
        return mole in member_partners and len(member_partners) == 2

    # ------------------------------------------------------------------
    # Creation / idempotency
    # ------------------------------------------------------------------
    @api.model
    def assistant_mole_ensure_for_current_user(self):
        """Get or create the private Mole chat for the current user.

        Returns the discuss.channel (pinned for the current user). Idempotent:
        reuses the existing direct chat between the user and the Mole bot.
        """
        user = self.env.user
        if user._is_public() or not user._is_internal():
            return self.browse()
        mole_partner = self._mole_partner()
        if not mole_partner:
            return self.browse()
        partners_to = [user.partner_id.id, mole_partner.id]
        channel = self.channel_get(partners_to, pin=True)
        if not channel.assistant_mole_owner_id:
            # channel_get runs as current user; safe to set owner
            channel.sudo().write({"assistant_mole_owner_id": user.id})
        elif channel.assistant_mole_owner_id != user:
            # Should not happen for a genuine Mole channel; do not leak
            raise AccessError(self.env._("This Mole conversation does not belong to the current user."))
        return channel

    # ------------------------------------------------------------------
    # Response hook
    # ------------------------------------------------------------------
    def _message_post_after_hook(self, message, msg_values):
        super()._message_post_after_hook(message, msg_values)
        for channel in self:
            try:
                channel._assistant_mole_maybe_respond(message)
            except Exception:
                # Never break message posting; surface a generic error instead
                try:
                    channel._assistant_mole_post_error(
                        "No se pudo procesar la respuesta de Mole."
                    )
                except Exception:
                    pass

    def _assistant_mole_maybe_respond(self, message):
        self.ensure_one()
        if not self._is_mole_channel():
            return
        owner = self.assistant_mole_owner_id
        # Only the owner triggers responses
        if owner != self.env.user:
            return
        # Avoid loops: never respond to Mole's own messages
        mole_partner = self._mole_partner()
        if not mole_partner or message.author_id == mole_partner:
            return
        # Only react to genuine user comments, not notifications/system messages
        if message.message_type != "comment":
            return
        # Forged sender protection: author must be the owner's partner
        if message.author_id != owner.partner_id:
            return
        # Re-check channel membership for the posting user
        if not self.channel_member_ids.filtered(lambda m: m.partner_id == owner.partner_id):
            return

        self._assistant_mole_handle_user_message(message)

    def _assistant_mole_handle_user_message(self, message):
        self.ensure_one()
        owner = self.assistant_mole_owner_id
        mole_partner = self._mole_partner()

        question = html2plaintext(message.body or "")
        target = named_vacation_target(question)
        if target:
            try:
                result = self.env["assistant.capability"]._execute_capability(
                    "hr.vacation.balance.get_by_name", {"name": target}
                )
                self._assistant_mole_post_message(self._format_vacation_balance(result))
            except (UserError, ValidationError, ValueError, AccessError):
                self._assistant_mole_post_error(
                    "No se puede consultar el saldo con esos datos o permisos."
                )
            return

        # Build a short conversation from recent messages
        recent = self.message_ids.sorted(key=lambda m: m.id)[-8:]
        messages = []
        for m in recent:
            if m.author_id == mole_partner:
                messages.append({"role": "assistant", "content": html2plaintext(m.body or "")})
            else:
                messages.append({"role": "user", "content": html2plaintext(m.body or "")})

        # Only the vacation capability is exposed to the model
        caps = {}
        try:
            caps = self.env["assistant.capability"]._get_capabilities()
        except Exception:
            caps = {}
        tools = []
        if ALLOWED_CAPABILITY in caps:
            schema, _handler = caps[ALLOWED_CAPABILITY]
            properties = {}
            required = []
            for key, expected in schema.items():
                json_type = "string"
                if expected is int:
                    json_type = "integer"
                elif expected is float:
                    json_type = "number"
                elif expected is bool:
                    json_type = "boolean"
                elif expected in (list, tuple, set):
                    json_type = "array"
                elif expected is dict:
                    json_type = "object"
                properties[key] = {"type": json_type}
                required.append(key)
            tools.append({
                "type": "function",
                "function": {
                    "name": ALLOWED_CAPABILITY,
                    "description": "Consultar el saldo de vacaciones propio del usuario autenticado",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                },
            })

        provider = self.env["assistant.inference"]
        try:
            reply = provider._chat(messages, tools)
        except Exception:
            self._assistant_mole_post_error(
                "Mole no está disponible: no hay modelo local configurado o falló la inferencia. "
                "No se inventaron datos."
            )
            return

        if not isinstance(reply, dict):
            self._assistant_mole_post_error("Mole devolvió una respuesta inválida.")
            return

        # Execute only the explicitly allowed capability, as the real user
        tool_calls = reply.get("tool_calls") or []
        executed_any = False
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            arguments = function.get("arguments", {})
            if name != ALLOWED_CAPABILITY:
                # Hard block: never run stock/accounting/other capabilities from Mole
                continue
            if not is_safe_own_vacation_query(question):
                continue
            if not isinstance(arguments, dict):
                continue
            try:
                result = self.env["assistant.capability"]._execute_capability(name, arguments)
                executed_any = True
                self._assistant_mole_post_message(self._format_vacation_balance(result))
            except (UserError, ValidationError, ValueError, AccessError) as exc:
                self._assistant_mole_post_error(
                    "No se pudo obtener el saldo de vacaciones: %s" % (exc,)
                )
                executed_any = True

        if not executed_any:
            self._assistant_mole_post_error(
                "Por ahora solo puedo consultar tu saldo de vacaciones."
            )

    def _format_vacation_balance(self, result):
        if not isinstance(result, dict):
            return "Saldo de vacaciones no disponible."
        lines = ["Saldo de vacaciones (LFT):"]
        if result.get("employee"):
            lines.append("Empleado: %s" % result.get("employee"))
        if result.get("service_years") is not None:
            lines.append("Antigüedad (años): %s" % result.get("service_years"))
        if result.get("entitlement_days") is not None:
            lines.append("Días de derecho: %s" % result.get("entitlement_days"))
        if result.get("approved_days") is not None:
            lines.append("Días aprobados: %s" % result.get("approved_days"))
        if result.get("available_days") is not None:
            lines.append("Días disponibles: %s" % result.get("available_days"))
        if result.get("next_anniversary"):
            lines.append("Próximo aniversario: %s" % result.get("next_anniversary"))
        return "\n".join(lines)

    def _assistant_mole_post_message(self, body):
        self.ensure_one()
        mole_partner = self._mole_partner()
        if not mole_partner:
            return
        # Post as Mole (bot partner). Use sudo only to set author_id to the bot partner,
        # since the bot has no user. This sudo is narrowly scoped to message authorship.
        self.sudo().message_post(
            body=body,
            author_id=mole_partner.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def _assistant_mole_post_error(self, body):
        self._assistant_mole_post_message("⚠ %s" % body)
