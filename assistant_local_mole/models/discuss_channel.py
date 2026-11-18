import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import html2plaintext
from odoo.addons.assistant_local.general_query import format_result, format_vacation_balance
from odoo.addons.assistant_local.mole_local import (
    is_safe_own_vacation_query, named_vacation_target, supported_plans, classify_social,
)
from odoo.addons.assistant_local.stock_nl import detect_language


MOLE_PARTNER_XMLID = "assistant_local_mole.partner_mole"
ALLOWED_CAPABILITY = "hr.vacation.balance.get_own"
_PROTECTED_FIELDS = frozenset({
    "assistant_mole_owner_id",
    "assistant_mole_pending_transfer_id",
    "assistant_mole_pending_transfer_token",
    "assistant_mole_pending_transfer_lang",
})


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
    assistant_mole_pending_transfer_id = fields.Integer(
        string="Mole Pending Transfer Proposal",
        default=0,
        readonly=True,
        copy=False,
    )
    assistant_mole_pending_transfer_token = fields.Char(
        string="Mole Pending Transfer Token",
        readonly=True,
        copy=False,
    )
    assistant_mole_pending_transfer_lang = fields.Char(
        string="Mole Pending Transfer Language",
        readonly=True,
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and (
            "default_assistant_mole_owner_id" in self.env.context
            or any(_PROTECTED_FIELDS & set(vals) for vals in vals_list)
        ):
            raise AccessError(self.env._("Mole conversation state is managed by the server."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and _PROTECTED_FIELDS & set(vals):
            raise AccessError(self.env._("Mole conversation state is managed by the server."))
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
        if self.env["assistant.mole.stock"]._handle_message(self, question):
            return
        target = named_vacation_target(question)
        if target:
            try:
                result = self.env["assistant.capability"]._execute_capability(
                    "hr.vacation.balance.get_by_name", {"name": target}
                )
                lang = detect_language(question)
                self._assistant_mole_post_message(self._format_vacation_balance(result, language=lang))
            except (UserError, ValidationError, ValueError, AccessError):
                self._assistant_mole_post_error(
                    "No se puede consultar el saldo con esos datos o permisos."
                )
            return

        if not is_safe_own_vacation_query(question):
            self._assistant_mole_general(question)
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
                lang = detect_language(question)
                self._assistant_mole_post_message(self._format_vacation_balance(result, language=lang))
            except (UserError, ValidationError, ValueError, AccessError) as exc:
                self._assistant_mole_post_error(
                    "No se pudo obtener el saldo de vacaciones: %s" % (exc,)
                )
                executed_any = True

        if not executed_any:
            self._assistant_mole_post_error("No se pudo interpretar la consulta de vacaciones.")

    def _assistant_mole_general(self, question):
        language = detect_language(question)
        english = language == "en"
        engine = self.env["assistant.general.query"]
        provider = self.env["assistant.inference"]
        try:
            from odoo.addons.assistant_local.models.general_query import SENSITIVE
            from odoo.addons.assistant_local.mole_local import _normalize

            norm_q = _normalize(question)
            sensitive_terms = list(SENSITIVE) + [
                'contrasena', 'secreto', 'clave', 'tarjeta',
                'cuenta bancaria', 'bancario', 'bancaria', 'credencial',
                'nip', 'pin', 'sueldo', 'nomina', 'password', 'secret',
                'token', 'bank', 'credit card', 'social security',
            ]
            sensitive_pattern = re.compile(
                r"(?<!\w)(?:" + "|".join(
                    re.escape(term) for term in sensitive_terms
                ) + r")"
            )
            if sensitive_pattern.search(norm_q):
                self._assistant_mole_post_error(
                    "For security reasons, sensitive or private fields cannot be queried."
                    if english else
                    "Por motivos de seguridad, no está permitido consultar campos sensibles o privados."
                )
                return

            social_intent = classify_social(question)
            if social_intent == "greeting":
                if english:
                    self._assistant_mole_post_message(
                        "Hi! I am Mole, your Odoo assistant. I can look up information your "
                        "user is allowed to see (contacts, products, sale orders, purchases, "
                        "tasks, your vacation balance and more), answer stock quantity and "
                        "location questions, and prepare internal stock transfers for your "
                        "confirmation. How can I help you today?"
                    )
                else:
                    self._assistant_mole_post_message(
                        "¡Hola! Soy Mole, tu asistente en Odoo. Puedo ayudarte a consultar información según tus permisos en el sistema "
                        "(contactos, productos, pedidos de venta, compras, tareas, inventario, tu saldo de vacaciones y más). "
                        "¿En qué te puedo apoyar hoy?"
                    )
                return
            elif social_intent == "gratitude":
                if english:
                    self._assistant_mole_post_message(
                        "You're very welcome! Feel free to ask if you need anything else."
                    )
                else:
                    self._assistant_mole_post_message(
                        "¡Con mucho gusto! Quedo a tu disposición si necesitas consultar algo más."
                    )
                return
            elif social_intent == "farewell":
                if english:
                    self._assistant_mole_post_message(
                        "Goodbye! Have a great day."
                    )
                else:
                    self._assistant_mole_post_message(
                        "¡Hasta luego! Que tengas un excelente día."
                    )
                return
            elif social_intent == "acknowledgment":
                if english:
                    self._assistant_mole_post_message(
                        "Great! Let me know whenever you need anything else."
                    )
                else:
                    self._assistant_mole_post_message(
                        "¡Excelente! Dime si requieres consultar alguna otra información."
                    )
                return

            policy = engine._catalog(include_denied=True)
            candidates = supported_plans(question, policy)
            if len(candidates) == 1 and policy[candidates[0]['model']].get('denied'):
                raise AccessError("Read access denied")
            catalog = {name: item for name, item in policy.items() if not item.get('denied')}
            plan = None
            try:
                plan = provider._general_plan(question, catalog)
            except Exception:
                pass
            if plan is None and len(candidates) == 1:
                plan = candidates[0]
            if plan is None:
                self._assistant_mole_post_error(
                    "I did not understand the request. You can ask, for example: how many "
                    "products/contacts there are, show or list records, get a record by its "
                    "quoted name, your vacation balance, or a product's stock and location."
                    if english else
                    "No entendí la consulta. Puedes pedirme, por ejemplo: cuántos productos/contactos hay, "
                    "mostrar/listar registros, información de un registro con nombre entre comillas, "
                    "o tu saldo de vacaciones / el saldo de vacaciones de una persona (nombre completo)."
                )
                return
            result = engine._execute(plan, question)
            reply = format_result(result, language=language)
            if not isinstance(reply, str) or not reply.strip():
                self._assistant_mole_post_error(
                    "The general query could not be rendered."
                    if english else
                    "No se pudo procesar la respuesta de la consulta general."
                )
                return
            self._assistant_mole_post_message(reply)
        except AccessError:
            self._assistant_mole_post_error(
                "You do not have permission to read those records."
                if english else
                "No tienes permiso para consultar esos registros."
            )
        except (UserError, ValidationError, ValueError, OSError, RuntimeError):
            self._assistant_mole_post_error(
                "The general query could not be processed; no data was invented."
                if english else
                "No se pudo procesar la consulta general; no se inventaron datos."
            )

    def _format_vacation_balance(self, result, language="es"):
        return format_vacation_balance(result, language=language)

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
