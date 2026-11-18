"""Inventory questions and confirmed transfers for the Mole chat.

The parser only produces literal names and intent. Every product, location and
quantity is resolved again against the authenticated user's Odoo environment,
and the final numbers are rendered from Odoo records.
"""

import re

from odoo import api, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare

from odoo.addons.assistant_local.stock_nl import (
    normalize,
    parse_stock_intent,
    parse_transfer_reply,
)


TRANSFER_PROPOSE = "stock.internal_transfer.propose"
TRANSFER_CONFIRM = "stock.internal_transfer.confirm"
TRANSFER_MODEL = "assistant.stock.transfer.proposal"

_UOM_ALIASES = {
    "unit": "unit", "units": "unit", "unidad": "unit", "unidades": "unit",
    "piece": "piece", "pieces": "piece", "pieza": "piece", "piezas": "piece",
    "pcs": "piece", "pc": "piece",
    "box": "box", "boxes": "box", "caja": "box", "cajas": "box",
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "kilogramo": "kg", "kilogramos": "kg",
    "l": "l", "liter": "l", "liters": "l", "litro": "l", "litros": "l",
    "m": "m", "meter": "m", "meters": "m", "metro": "m", "metros": "m",
}



class AssistantMoleStock(models.AbstractModel):
    _name = "assistant.mole.stock"
    _description = "Mole Inventory Queries"

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    @api.model
    def _handle_message(self, channel, question):
        """Handle stock questions and transfer confirmations.

        Returns ``True`` when the message was consumed by this handler.
        """
        if not self._stock_available():
            return False

        pending = bool(channel.assistant_mole_pending_transfer_id)
        if pending:
            reply = parse_transfer_reply(question)
            if reply == "confirm":
                self._confirm_pending(channel)
                return True
            if reply == "cancel":
                self._cancel_pending(channel)
                return True
            # A new question invalidates the old proposal so a later "yes"
            # cannot confirm an operation the user has moved on from.
            self._clear_pending(channel)

        intent = parse_stock_intent(question)
        if not intent:
            return False
        if intent["intent"] == "transfer":
            if TRANSFER_MODEL not in self.env.registry:
                self._post(
                    channel, intent["language"],
                    "Inventory transfers are not available in this database. "
                    "Install the local stock assistant module first.",
                    "Las transferencias de inventario no están disponibles en esta base. "
                    "Instala primero el módulo local de inventario.",
                )
                return True
            self._propose_transfer(channel, intent)
            return True
        if intent["intent"] == "quantity":
            return self._answer_quantity(channel, intent)
        if intent["intent"] == "location":
            return self._answer_location(channel, intent)
        return False

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------
    @api.model
    def _stock_available(self):
        return "stock.quant" in self.env.registry and "stock.location" in self.env.registry

    @api.model
    def _can_transfer(self):
        user = self.env.user
        return (user.has_group("stock.group_stock_user")
                or user.has_group("base.group_system"))

    @api.model
    def _uom_matches(self, product, uom_name):
        """Accept only the product's unit or an unambiguous count synonym.

        Odoo does not define a conversion between arbitrary named units, so a
        request for "2 boxes" is rejected instead of silently moving 2 units.
        """
        if not uom_name:
            return True
        requested = normalize(uom_name).strip()
        actual = normalize(product.uom_id.name or "").strip()
        if requested == actual:
            return True
        requested_key = _UOM_ALIASES.get(requested, requested.rstrip("s"))
        actual_key = _UOM_ALIASES.get(actual, actual.rstrip("s"))
        return requested_key == actual_key

    # ------------------------------------------------------------------
    # Entity resolution
    # ------------------------------------------------------------------
    @api.model
    def _escaped(self, value):
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @api.model
    def _find_products(self, name):
        Product = self.env["product.product"].with_context(active_test=True)
        Product.check_access("read")
        products = Product.search([("name", "=", name)], limit=8)
        if not products:
            products = Product.search(
                ["|", ("default_code", "=", name), ("name", "=ilike", name)], limit=8
            )
        if not products:
            products = Product.search([("name", "ilike", self._escaped(name))], limit=8)
        if not products:
            ids = [item[0] for item in Product.name_search(name, operator="ilike", limit=8)]
            if ids:
                products = Product.browse(ids)
        if len(products) > 1:
            target = normalize(name)
            exact = products.filtered(
                lambda product: normalize(product.name) == target
                or normalize(product.display_name) == target
            )
            if exact:
                products = exact
        return products

    @api.model
    def _find_locations(self, name):
        Location = self.env["stock.location"].with_context(active_test=True)
        Location.check_access("read")
        candidates = [name]
        for candidate in (
            re.sub(
                r"^(?:the|la|el|los|las)\s+"
                r"(?:(?:stock\s+)?locations?|ubicaciones?|warehouses?|almacenes?|bodegas?)\s+",
                "", name, flags=re.IGNORECASE,
            ).strip(),
            re.sub(
                r"^(?:(?:stock\s+)?locations?|ubicaciones?|warehouses?|almacenes?|bodegas?)\s+",
                "", name, flags=re.IGNORECASE,
            ).strip(),
        ):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        locations = Location.browse()
        for candidate in candidates:
            locations = Location.search([("complete_name", "=", candidate)], limit=8)
            if not locations:
                locations = Location.search([("name", "=", candidate)], limit=8)
            if not locations:
                locations = Location.search(
                    ["|", ("complete_name", "ilike", self._escaped(candidate)),
                     ("name", "ilike", self._escaped(candidate))],
                    limit=8,
                )
            if locations:
                break
        if len(locations) > 1:
            target = normalize(name)
            exact = locations.filtered(
                lambda location: normalize(location.complete_name) == target
                or normalize(location.name) == target
            )
            if exact:
                locations = exact
        return locations

    @api.model
    def _visible_quants(self, products):
        Quant = self.env["stock.quant"]
        Quant.check_access("read")
        return Quant.search([
            ("product_id", "in", products.ids),
            ("location_id.usage", "in", ["internal", "transit"]),
        ])

    # ------------------------------------------------------------------
    # Read answers
    # ------------------------------------------------------------------
    @api.model
    def _answer_quantity(self, channel, intent):
        language = intent["language"]
        try:
            products = self._find_products(intent["product"])
        except AccessError:
            self._post(
                channel, language,
                "You do not have permission to read product stock.",
                "No tienes permiso para consultar existencias de productos.",
            )
            return True
        if not products:
            if not (intent.get("product_quoted") or intent.get("explicit_stock")):
                # Not clearly a stock question: let the general handler try.
                return False
            self._post(
                channel, language,
                'No product was found with the name "%s". Use the exact product name in quotes.'
                % intent["product"],
                'No se encontró un producto con el nombre "%s". Usa el nombre exacto entre comillas.'
                % intent["product"],
            )
            return True
        if len(products.product_tmpl_id) > 1:
            self._ambiguous_products(channel, language, intent["product"], products)
            return True
        quants = self._visible_quants(products)
        if not quants:
            self._post(
                channel, language,
                'There is no visible stock for "%s" in internal locations.'
                % self._product_label(products),
                'No hay existencias visibles de "%s" en ubicaciones internas.'
                % self._product_label(products),
            )
            return True
        by_location = {}
        total_on_hand = 0.0
        total_available = 0.0
        for quant in quants:
            total_on_hand += quant.quantity
            total_available += quant.available_quantity
            key = (quant.location_id.id, quant.lot_id.id if quant.lot_id else 0)
            entry = by_location.setdefault(
                key,
                {"location": quant.location_id, "lot": quant.lot_id,
                 "quantity": 0.0, "available": 0.0},
            )
            entry["quantity"] += quant.quantity
            entry["available"] += quant.available_quantity
        unit = products[0].uom_id.name or "Units"
        lines = [
            (
                'Stock of "%s": %s %s on hand, %s %s available.'
                % (self._product_label(products), self._qty(total_on_hand), unit,
                   self._qty(total_available), unit)
            ) if language == "en" else (
                'Existencias de "%s": %s %s en mano, %s %s disponibles.'
                % (self._product_label(products), self._qty(total_on_hand), unit,
                   self._qty(total_available), unit)
            ),
            "By location:" if language == "en" else "Por ubicación:",
        ]
        for entry in sorted(by_location.values(),
                            key=lambda item: item["location"].complete_name):
            lot = ""
            if entry["lot"]:
                lot = " / %s" % entry["lot"].display_name
            lines.append(
                "• %s%s: %s %s (%s %s)"
                % (entry["location"].complete_name, lot, self._qty(entry["quantity"]),
                   unit, self._qty(entry["available"]), unit)
            )
        lines.append(
            "Your permissions and record rules apply."
            if language == "en"
            else "Se aplican tus permisos y reglas de registro."
        )
        self._post(channel, language, "\n".join(lines))
        return True

    @api.model
    def _answer_location(self, channel, intent):
        language = intent["language"]
        try:
            products = self._find_products(intent["product"])
        except AccessError:
            self._post(
                channel, language,
                "You do not have permission to read product stock.",
                "No tienes permiso para consultar existencias de productos.",
            )
            return True
        if not products:
            if not (intent.get("product_quoted") or intent.get("explicit_stock")):
                # Not clearly a stock question: let the general handler try.
                return False
            self._post(
                channel, language,
                'No product was found with the name "%s". Use the exact product name in quotes.'
                % intent["product"],
                'No se encontró un producto con el nombre "%s". Usa el nombre exacto entre comillas.'
                % intent["product"],
            )
            return True
        if len(products.product_tmpl_id) > 1:
            self._ambiguous_products(channel, language, intent["product"], products)
            return True
        quants = self._visible_quants(products)
        if not quants:
            self._post(
                channel, language,
                'There is no visible stock for "%s" in internal locations.'
                % self._product_label(products),
                'No hay existencias visibles de "%s" en ubicaciones internas.'
                % self._product_label(products),
            )
            return True
        by_location = {}
        total = 0.0
        for quant in quants:
            total += quant.quantity
            key = (quant.location_id.id, quant.lot_id.id if quant.lot_id else 0)
            entry = by_location.setdefault(
                key,
                {"location": quant.location_id, "lot": quant.lot_id,
                 "quantity": 0.0, "available": 0.0},
            )
            entry["quantity"] += quant.quantity
            entry["available"] += quant.available_quantity
        unit = products[0].uom_id.name or "Units"
        lines = [
            (
                '"%s" is stored in:' % self._product_label(products)
            ) if language == "en" else (
                '"%s" se encuentra en:' % self._product_label(products)
            )
        ]
        for entry in sorted(by_location.values(),
                            key=lambda item: item["location"].complete_name):
            lot = ""
            if entry["lot"]:
                lot = " / %s" % entry["lot"].display_name
            lines.append(
                "• %s%s: %s %s (%s %s)"
                % (entry["location"].complete_name, lot, self._qty(entry["quantity"]),
                   unit, self._qty(entry["available"]), unit)
            )
        lines.append(
            ("Total visible: %s %s. Your permissions and record rules apply."
             % (self._qty(total), unit))
            if language == "en"
            else ("Total visible: %s %s. Se aplican tus permisos y reglas de registro."
                  % (self._qty(total), unit))
        )
        self._post(channel, language, "\n".join(lines))
        return True

    # ------------------------------------------------------------------
    # Transfers
    # ------------------------------------------------------------------
    @api.model
    def _propose_transfer(self, channel, intent):
        language = intent["language"]
        if not self._can_transfer():
            self._post(
                channel, language,
                "You need Inventory access (stock user) or administrator rights "
                "to transfer stock. No records were changed.",
                "Necesitas acceso a Inventario (usuario de almacén) o permisos de "
                "administrador para transferir existencias. No se modificó ningún registro.",
            )
            return
        try:
            products = self._find_products(intent["product"])
        except AccessError:
            self._post(
                channel, language,
                "You do not have permission to read products.",
                "No tienes permiso para consultar productos.",
            )
            return
        if len(products) != 1:
            self._ambiguous_products(channel, language, intent["product"], products)
            return
        product = products[0]
        if not self._uom_matches(product, intent.get("uom_name")):
            self._post(
                channel, language,
                'The requested unit "%s" is not supported for "%s" (unit: %s). '
                'Repeat the transfer using the product unit. No transfer was created.'
                % (intent["uom_name"], product.display_name,
                   product.uom_id.name or "Units"),
                'La unidad solicitada "%s" no es compatible con "%s" (unidad: %s). '
                'Repite la transferencia usando la unidad del producto. '
                'No se creó ninguna transferencia.'
                % (intent["uom_name"], product.display_name,
                   product.uom_id.name or "Unidades"),
            )
            return
        origin, destination = self._resolve_transfer_locations(channel, intent)
        if not origin or not destination:
            return
        if origin == destination:
            self._post(
                channel, language,
                "Origin and destination must be different locations.",
                "El origen y el destino deben ser ubicaciones diferentes.",
            )
            return
        if origin.usage != "internal" or destination.usage != "internal":
            self._post(
                channel, language,
                "Internal transfers require internal stock locations. "
                "Origin: %s; destination: %s." % (origin.usage, destination.usage),
                "Las transferencias internas requieren ubicaciones internas. "
                "Origen: %s; destino: %s." % (origin.usage, destination.usage),
            )
            return
        if (origin.company_id and origin.company_id != self.env.company) or (
                destination.company_id and destination.company_id != self.env.company):
            self._post(
                channel, language,
                "Both locations must belong to the active company.",
                "Ambas ubicaciones deben pertenecer a la compañía activa.",
            )
            return
        if product.company_id and product.company_id != self.env.company:
            self._post(
                channel, language,
                "The product belongs to another company.",
                "El producto pertenece a otra compañía.",
            )
            return
        available = self._available_in_location(product, origin)
        quantity = intent["quantity"]
        auto = quantity is None
        if auto:
            quantity = available
        if float_compare(quantity, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
            self._post(
                channel, language,
                'There is no available stock of "%s" in %s. No transfer was created.'
                % (product.display_name, origin.complete_name),
                'No hay existencias disponibles de "%s" en %s. No se creó ninguna transferencia.'
                % (product.display_name, origin.complete_name),
            )
            return
        if float_compare(quantity, available, precision_rounding=product.uom_id.rounding) > 0:
            self._post(
                channel, language,
                'Only %s %s of "%s" are available in %s. No transfer was created.'
                % (self._qty(available), product.uom_id.name or "Units",
                   product.display_name, origin.complete_name),
                'Solo hay %s %s de "%s" disponibles en %s. No se creó ninguna transferencia.'
                % (self._qty(available), product.uom_id.name or "Units",
                   product.display_name, origin.complete_name),
            )
            return
        try:
            result = self.env["assistant.capability"]._execute_capability(
                TRANSFER_PROPOSE,
                {
                    "origin_location_id": origin.id,
                    "destination_location_id": destination.id,
                    "product_id": product.id,
                    "quantity": quantity,
                    "uom_id": product.uom_id.id,
                },
            )
        except (AccessError, UserError, ValidationError, ValueError) as exc:
            self._post(
                channel, language,
                "The transfer proposal could not be created: %s" % (exc,),
                "No se pudo crear la propuesta de transferencia: %s" % (exc,),
            )
            return
        proposal_id = result.get("proposal_id")
        token = result.get("confirmation_token")
        if not proposal_id or not token:
            self._post(
                channel, language,
                "The server did not return a valid transfer proposal. No transfer was created.",
                "El servidor no devolvió una propuesta válida. No se creó ninguna transferencia.",
            )
            return
        channel.sudo().write({
            "assistant_mole_pending_transfer_id": proposal_id,
            "assistant_mole_pending_transfer_token": token,
            "assistant_mole_pending_transfer_lang": language,
        })
        unit = product.uom_id.name or "Units"
        auto_note = (
            " No quantity was specified, so the full available quantity is proposed."
            if auto else ""
        )
        auto_note_es = (
            " No indicaste cantidad, así que se propone toda la cantidad disponible."
            if auto else ""
        )
        if language == "en":
            body = (
                "Transfer proposal #%s\n"
                "Product: %s\nQuantity: %s %s\nFrom: %s\nTo: %s\n"
                "Reply \"confirm\" to execute or \"cancel\" to discard. "
                "The proposal expires in 5 minutes.%s"
            ) % (proposal_id, product.display_name, self._qty(quantity), unit,
                 origin.complete_name, destination.complete_name, auto_note)
        else:
            body = (
                "Propuesta de transferencia #%s\n"
                "Producto: %s\nCantidad: %s %s\nDesde: %s\nHacia: %s\n"
                "Responde \"confirmar\" para ejecutar o \"cancelar\" para descartar. "
                "La propuesta caduca en 5 minutos.%s"
            ) % (proposal_id, product.display_name, self._qty(quantity), unit,
                 origin.complete_name, destination.complete_name, auto_note_es)
        self._post(channel, language, body)

    @api.model
    def _resolve_transfer_locations(self, channel, intent):
        language = intent["language"]
        origin_candidates = self._find_locations(intent["origin"])
        if not origin_candidates:
            self._post(
                channel, language,
                'No location was found with the name "%s". Use the exact location name in quotes.'
                % intent["origin"],
                'No se encontró una ubicación con el nombre "%s". Usa el nombre exacto entre comillas.'
                % intent["origin"],
            )
            return None, None
        origin_candidates = origin_candidates.filtered(lambda loc: loc.usage == "internal")
        if len(origin_candidates) != 1:
            self._ambiguous_locations(channel, language, intent["origin"], origin_candidates)
            return None, None
        destination_candidates = self._find_locations(intent["destination"])
        if not destination_candidates:
            self._post(
                channel, language,
                'No location was found with the name "%s". Use the exact location name in quotes.'
                % intent["destination"],
                'No se encontró una ubicación con el nombre "%s". Usa el nombre exacto entre comillas.'
                % intent["destination"],
            )
            return None, None
        destination_candidates = destination_candidates.filtered(
            lambda loc: loc.usage == "internal"
        )
        if len(destination_candidates) != 1:
            self._ambiguous_locations(
                channel, language, intent["destination"], destination_candidates
            )
            return None, None
        return origin_candidates, destination_candidates

    @api.model
    def _available_in_location(self, product, location):
        Quant = self.env["stock.quant"]
        Quant.check_access("read")
        quants = Quant.search([
            ("product_id", "=", product.id),
            ("location_id", "=", location.id),
        ])
        return sum(max(quant.available_quantity, 0.0) for quant in quants)

    @api.model
    def _confirm_pending(self, channel):
        proposal_id = channel.assistant_mole_pending_transfer_id
        token = channel.assistant_mole_pending_transfer_token or ""
        language = channel.assistant_mole_pending_transfer_lang or "en"
        try:
            result = self.env["assistant.capability"]._execute_capability(
                TRANSFER_CONFIRM,
                {"proposal_id": proposal_id, "confirmation_token": token},
            )
        except (AccessError, UserError, ValidationError, ValueError) as exc:
            self._clear_pending(channel)
            self._post(
                channel, language,
                "The transfer could not be completed: %s" % (exc,),
                "No se pudo completar la transferencia: %s" % (exc,),
            )
            return
        self._clear_pending(channel)
        status = result.get("status") if isinstance(result, dict) else None
        picking = result.get("picking_id") if isinstance(result, dict) else None
        state = result.get("picking_state") if isinstance(result, dict) else None
        if status == "ok":
            self._post(
                channel, language,
                "Transfer completed. Reference: #%s (state: %s)." % (picking, state),
                "Transferencia completada. Referencia: #%s (estado: %s)." % (picking, state),
            )
        elif status == "needs_confirmation":
            self._post(
                channel, language,
                "Odoo requires an additional decision before the transfer can finish. "
                "It was not reported as completed.",
                "Odoo requiere una decisión adicional antes de terminar la transferencia. "
                "No se informó como completada.",
            )
        else:
            message = result.get("message") if isinstance(result, dict) else ""
            self._post(
                channel, language,
                "The transfer did not complete%s."
                % (": %s" % message if message else ""),
                "La transferencia no se completó%s."
                % (": %s" % message if message else ""),
            )

    @api.model
    def _cancel_pending(self, channel):
        language = channel.assistant_mole_pending_transfer_lang or "en"
        self._clear_pending(channel)
        self._post(
            channel, language,
            "Transfer proposal cancelled. No records were changed.",
            "Propuesta de transferencia cancelada. No se modificó ningún registro.",
        )

    @api.model
    def _clear_pending(self, channel):
        channel.sudo().write({
            "assistant_mole_pending_transfer_id": 0,
            "assistant_mole_pending_transfer_token": False,
            "assistant_mole_pending_transfer_lang": False,
        })

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------
    @api.model
    def _product_label(self, products):
        templates = products.product_tmpl_id
        if len(templates) == 1:
            return templates[0].display_name or templates[0].name
        return products[0].display_name if len(products) == 1 else "\n".join(
            product.display_name for product in products
        )

    @api.model
    def _ambiguous_products(self, channel, language, name, products):
        if products:
            listed = "\n".join("• %s" % product.display_name for product in products[:8])
            self._post(
                channel, language,
                'Several products match "%s":\n%s\nUse the exact name in quotes.'
                % (name, listed),
                'Varios productos coinciden con "%s":\n%s\nUsa el nombre exacto entre comillas.'
                % (name, listed),
            )
        else:
            self._post(
                channel, language,
                'No product was found with the name "%s". Use the exact product name in quotes.'
                % name,
                'No se encontró un producto con el nombre "%s". Usa el nombre exacto entre comillas.'
                % name,
            )

    @api.model
    def _ambiguous_locations(self, channel, language, name, locations):
        if locations:
            listed = "\n".join("• %s" % location.complete_name for location in locations[:8])
            self._post(
                channel, language,
                'Several internal locations match "%s":\n%s\nUse the exact name in quotes.'
                % (name, listed),
                'Varias ubicaciones internas coinciden con "%s":\n%s\nUsa el nombre exacto entre comillas.'
                % (name, listed),
            )
        else:
            self._post(
                channel, language,
                'No internal location was found with the name "%s". '
                'Use the exact location name in quotes.' % name,
                'No se encontró una ubicación interna con el nombre "%s". '
                'Usa el nombre exacto entre comillas.' % name,
            )

    @api.model
    def _qty(self, value):
        text = "%.4f" % float(value or 0.0)
        text = text.rstrip("0").rstrip(".")
        return text or "0"

    @api.model
    def _post(self, channel, language, english, spanish=None):
        body = english if language == "en" else (spanish or english)
        channel._assistant_mole_post_message(body)
