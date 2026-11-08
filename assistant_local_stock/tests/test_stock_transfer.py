from odoo.tests import TransactionCase, new_test_user


class TestStockTransfer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="assistant_stock_user", groups="base.group_user,stock.group_stock_user")
        cls.warehouse = cls.env["stock.warehouse"].create({"name": "Assistant Warehouse", "code": "AW"})
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.origin = cls.env["stock.location"].create({"name": "Assistant Origin", "location_id": cls.stock_loc.id, "usage": "internal"})
        cls.destination = cls.env["stock.location"].create({"name": "Assistant Destination", "location_id": cls.stock_loc.id, "usage": "internal"})
        vals = {"name": "Assistant Stock Product", "type": "consu", "is_storable": True}
        if "sale_line_warn" in cls.env["product.template"]._fields:
            vals["sale_line_warn"] = "no-message"
        if "purchase_line_warn" in cls.env["product.template"]._fields:
            vals["purchase_line_warn"] = "no-message"
        tmpl = cls.env["product.template"].create(vals)
        cls.product = tmpl.product_variant_id
        cls.uom = cls.product.uom_id
        cls.env["stock.quant"].create({
            "product_id": cls.product.id,
            "location_id": cls.origin.id,
            "quantity": 10.0,
        })

    def _cap(self):
        return self.env["assistant.capability"].with_user(self.user)

    def test_propose_transfer(self):
        result = self._cap()._execute_capability("stock.internal_transfer.propose", {
            "origin_location_id": self.origin.id,
            "destination_location_id": self.destination.id,
            "product_id": self.product.id,
            "quantity": 2.0,
            "uom_id": self.uom.id,
        })
        self.assertIn("proposal_id", result)
        self.assertIn("confirmation_token", result)
        self.assertGreaterEqual(result["available_quantity"], 2.0)

    def test_confirm_transfer(self):
        proposal = self._cap()._execute_capability("stock.internal_transfer.propose", {
            "origin_location_id": self.origin.id,
            "destination_location_id": self.destination.id,
            "product_id": self.product.id,
            "quantity": 1.0,
            "uom_id": self.uom.id,
        })
        result = self._cap()._execute_capability("stock.internal_transfer.confirm", {
            "proposal_id": proposal["proposal_id"],
            "confirmation_token": proposal["confirmation_token"],
        })
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["picking_state"], "done")

    def test_invalid_token_rejected(self):
        proposal = self._cap()._execute_capability("stock.internal_transfer.propose", {
            "origin_location_id": self.origin.id,
            "destination_location_id": self.destination.id,
            "product_id": self.product.id,
            "quantity": 1.0,
            "uom_id": self.uom.id,
        })
        with self.assertRaises(ValueError):
            self._cap()._execute_capability("stock.internal_transfer.confirm", {
                "proposal_id": proposal["proposal_id"],
                "confirmation_token": "wrong",
            })

    def test_reused_confirmation_rejected(self):
        proposal = self._cap()._execute_capability("stock.internal_transfer.propose", {
            "origin_location_id": self.origin.id,
            "destination_location_id": self.destination.id,
            "product_id": self.product.id,
            "quantity": 1.0,
            "uom_id": self.uom.id,
        })
        self._cap()._execute_capability("stock.internal_transfer.confirm", {
            "proposal_id": proposal["proposal_id"],
            "confirmation_token": proposal["confirmation_token"],
        })
        with self.assertRaises(ValueError):
            self._cap()._execute_capability("stock.internal_transfer.confirm", {
                "proposal_id": proposal["proposal_id"],
                "confirmation_token": proposal["confirmation_token"],
            })

    def test_insufficient_stock_reported(self):
        proposal = self._cap()._execute_capability("stock.internal_transfer.propose", {
            "origin_location_id": self.origin.id,
            "destination_location_id": self.destination.id,
            "product_id": self.product.id,
            "quantity": 1000.0,
            "uom_id": self.uom.id,
        })
        result = self._cap()._execute_capability("stock.internal_transfer.confirm", {
            "proposal_id": proposal["proposal_id"],
            "confirmation_token": proposal["confirmation_token"],
        })
        self.assertIn(result["status"], ("error", "needs_confirmation"))
        self.assertNotEqual(result["status"], "ok")
