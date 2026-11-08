from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError, UserError


def _parse_date(value):
    if not isinstance(value, str):
        raise ValueError("Invalid date")
    try:
        return fields.Date.from_string(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid date")


class AssistantBusinessCapability(models.AbstractModel):
    _inherit = "assistant.capability"
    _description = "Assistant Capability: Business Queries"

    @api.model
    def _get_capabilities(self):
        capabilities = super()._get_capabilities()
        capabilities["account.invoices.count"] = (
            {"date_from": str, "date_to": str, "move_types": list, "states": list, "date_basis": str},
            self._count_customer_invoices,
        )
        capabilities["account.supplier.spend"] = (
            {"date_from": str, "date_to": str, "supplier_id": int, "include_refunds": bool, "amount_basis": str, "date_basis": str},
            self._supplier_spend,
        )
        capabilities["sale.product.sales"] = (
            {"date_from": str, "date_to": str, "product_id": int, "source": str, "date_basis": str},
            self._product_sales,
        )
        return capabilities

    @api.model
    def _count_customer_invoices(self, _model, arguments):
        env = _model.env
        date_from = _parse_date(arguments["date_from"])
        date_to = _parse_date(arguments["date_to"])
        if date_from > date_to:
            raise ValueError("Invalid date range")

        move_types = arguments.get("move_types") or ["out_invoice"]
        states = arguments.get("states") or ["posted"]
        date_basis = arguments.get("date_basis") or "invoice_date"
        if date_basis not in ("invoice_date", "date"):
            raise ValueError("Invalid date basis")
        if not isinstance(move_types, list) or not all(isinstance(x, str) for x in move_types):
            raise ValueError("Invalid move types")
        if not isinstance(states, list) or not all(isinstance(x, str) for x in states):
            raise ValueError("Invalid states")

        date_field = "invoice_date" if date_basis == "invoice_date" else "date"
        domain = [
            ("move_type", "in", move_types),
            ("state", "in", states),
            ("company_id", "=", env.company.id),
            (date_field, ">=", date_from),
            (date_field, "<=", date_to),
        ]
        moves = env["account.move"].search(domain)
        by_type = {}
        for move in moves:
            by_type[move.move_type] = by_type.get(move.move_type, 0) + 1
        return {
            "count": len(moves),
            "by_type": by_type,
            "currency": env.company.currency_id.name,
            "criteria": {
                "date_from": arguments["date_from"],
                "date_to": arguments["date_to"],
                "date_basis": date_basis,
                "move_types": move_types,
                "states": states,
                "company_id": env.company.id,
            },
            "references": ["account.move"],
        }

    @api.model
    def _supplier_spend(self, _model, arguments):
        env = _model.env
        date_from = _parse_date(arguments["date_from"])
        date_to = _parse_date(arguments["date_to"])
        if date_from > date_to:
            raise ValueError("Invalid date range")

        include_refunds = bool(arguments.get("include_refunds", False))
        move_types = ["in_invoice", "in_refund"] if include_refunds else ["in_invoice"]
        amount_basis = arguments.get("amount_basis") or "total"
        if amount_basis not in ("total", "untaxed"):
            raise ValueError("Invalid amount basis")
        date_basis = arguments.get("date_basis") or "invoice_date"
        if date_basis not in ("invoice_date", "date"):
            raise ValueError("Invalid date basis")
        date_field = "invoice_date" if date_basis == "invoice_date" else "date"

        domain = [
            ("move_type", "in", move_types),
            ("state", "=", "posted"),
            ("company_id", "=", env.company.id),
            (date_field, ">=", date_from),
            (date_field, "<=", date_to),
        ]
        supplier_id = arguments.get("supplier_id")
        if supplier_id:
            domain.append(("partner_id", "=", supplier_id))

        moves = env["account.move"].search(domain)
        raw_field_name = "amount_total" if amount_basis == "total" else "amount_untaxed"
        total = 0.0
        by_supplier = {}
        for move in moves:
            value = getattr(move, raw_field_name) or 0.0
            if move.move_type.endswith("refund"):
                value = -value
            total += value
            key = move.commercial_partner_id.id or move.partner_id.id
            by_supplier.setdefault(key, {"partner_id": key, "amount": 0.0, "count": 0})
            by_supplier[key]["amount"] += value
            by_supplier[key]["count"] += 1

        return {
            "amount": total,
            "currency": env.company.currency_id.name,
            "count": len(moves),
            "by_supplier": list(by_supplier.values()),
            "criteria": {
                "date_from": arguments["date_from"],
                "date_to": arguments["date_to"],
                "date_basis": date_basis,
                "amount_basis": amount_basis,
                "include_refunds": include_refunds,
                "company_id": env.company.id,
            },
            "references": ["account.move"],
        }

    @api.model
    def _product_sales(self, _model, arguments):
        env = _model.env
        date_from = _parse_date(arguments["date_from"])
        date_to = _parse_date(arguments["date_to"])
        if date_from > date_to:
            raise ValueError("Invalid date range")

        product_id = arguments.get("product_id")
        source = arguments.get("source") or "invoiced"
        if source not in ("invoiced", "ordered"):
            raise ValueError("Invalid source")
        date_basis = arguments.get("date_basis") or ("invoice_date" if source == "invoiced" else "order_date")
        include_credit_notes = bool(arguments.get("include_credit_notes", False))

        if source == "invoiced":
            move_types = ["out_invoice", "out_refund"] if include_credit_notes else ["out_invoice"]
            date_field = "invoice_date" if date_basis in ("invoice_date", "date") else "date"
            domain = [
                ("move_id.move_type", "in", move_types),
                ("move_id.state", "=", "posted"),
                ("move_id.company_id", "=", env.company.id),
                ("display_type", "=", "product"),
                ("move_id." + date_field, ">=", date_from),
                ("move_id." + date_field, "<=", date_to),
            ]
            if product_id:
                domain.append(("product_id", "=", product_id))
            lines = env["account.move.line"].search(domain)
            quantity = sum(line.quantity for line in lines)
            amount_untaxed = sum(line.price_subtotal for line in lines)
            amount_total = sum(line.price_total for line in lines)
            by_product = {}
            for line in lines:
                key = line.product_id.id
                by_product.setdefault(key, {"product_id": key, "quantity": 0.0, "amount_untaxed": 0.0, "amount_total": 0.0})
                by_product[key]["quantity"] += line.quantity
                by_product[key]["amount_untaxed"] += line.price_subtotal
                by_product[key]["amount_total"] += line.price_total
            return {
                "quantity": quantity,
                "amount_untaxed": amount_untaxed,
                "amount_total": amount_total,
                "currency": env.company.currency_id.name,
                "by_product": list(by_product.values()),
                "criteria": {
                    "date_from": arguments["date_from"],
                    "date_to": arguments["date_to"],
                    "date_basis": date_basis,
                    "source": source,
                    "include_credit_notes": include_credit_notes,
                    "company_id": env.company.id,
                },
                "references": ["account.move", "account.move.line"],
            }

        # source == ordered
        date_field = "date_order"
        domain = [
            ("order_id.state", "=", "sale"),
            ("order_id.company_id", "=", env.company.id),
            (date_field, ">=", fields.Datetime.to_datetime(date_from)),
            (date_field, "<=", fields.Datetime.to_datetime(date_to)),
        ]
        if product_id:
            domain.append(("product_id", "=", product_id))
        lines = env["sale.order.line"].search(domain)
        quantity = sum(line.product_uom_qty for line in lines)
        amount_untaxed = sum(line.price_subtotal for line in lines)
        amount_total = sum(line.price_total for line in lines)
        by_product = {}
        for line in lines:
            key = line.product_id.id
            by_product.setdefault(key, {"product_id": key, "quantity": 0.0, "amount_untaxed": 0.0, "amount_total": 0.0})
            by_product[key]["quantity"] += line.product_uom_qty
            by_product[key]["amount_untaxed"] += line.price_subtotal
            by_product[key]["amount_total"] += line.price_total
        return {
            "quantity": quantity,
            "amount_untaxed": amount_untaxed,
            "amount_total": amount_total,
            "currency": env.company.currency_id.name,
            "by_product": list(by_product.values()),
            "criteria": {
                "date_from": arguments["date_from"],
                "date_to": arguments["date_to"],
                "date_basis": "order_date",
                "source": source,
                "company_id": env.company.id,
            },
            "references": ["sale.order", "sale.order.line"],
        }
