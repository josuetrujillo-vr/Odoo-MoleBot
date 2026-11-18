from unittest import SkipTest

from odoo.tests import TransactionCase, new_test_user


class TestMoleStockChat(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "stock.quant" not in cls.env.registry:
            raise SkipTest("stock is not installed")

        cls.warehouse = cls.env["stock.warehouse"].create({
            "name": "Mole Chat Warehouse",
            "code": "MCW",
        })
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.origin = cls.env["stock.location"].create({
            "name": "Mole Chat Origin",
            "location_id": cls.stock_loc.id,
            "usage": "internal",
        })
        cls.destination = cls.env["stock.location"].create({
            "name": "Mole Chat Destination",
            "location_id": cls.stock_loc.id,
            "usage": "internal",
        })
        vals = {"name": "Mole Chat Stock Product", "type": "consu", "is_storable": True}
        if "sale_line_warn" in cls.env["product.template"]._fields:
            vals["sale_line_warn"] = "no-message"
        if "purchase_line_warn" in cls.env["product.template"]._fields:
            vals["purchase_line_warn"] = "no-message"
        cls.product = cls.env["product.template"].create(vals).product_variant_id
        cls.env["stock.quant"].create({
            "product_id": cls.product.id,
            "location_id": cls.origin.id,
            "quantity": 10.0,
        })

        cls.alice = new_test_user(
            cls.env, login="mole_stock_plain",
            groups="base.group_user", context={"no_reset_password": True},
        )
        cls.stock_user = new_test_user(
            cls.env, login="mole_stock_user",
            groups="base.group_user,stock.group_stock_user",
            context={"no_reset_password": True},
        )
        cls.admin = new_test_user(
            cls.env, login="mole_stock_admin",
            groups="base.group_user,base.group_system",
            context={"no_reset_password": True},
        )

    def _channel(self, user):
        return self.env["discuss.channel"].with_user(user).assistant_mole_ensure_for_current_user()

    def _ask(self, user, text):
        channel = self._channel(user)
        channel.with_user(user).message_post(body=text, message_type="comment")
        channel.invalidate_recordset()
        return channel.message_ids.sorted(key=lambda message: message.id)[-1].body

    def _quantity_at(self, location):
        quants = self.env["stock.quant"].search([
            ("product_id", "=", self.product.id),
            ("location_id", "=", location.id),
        ])
        return sum(quant.quantity for quant in quants)

    def _transfer_text(self, quantity, product=None, origin=None, destination=None):
        return 'Transfer %s units of "%s" from "%s" to "%s"' % (
            quantity,
            product or self.product.display_name,
            origin or self.origin.complete_name,
            destination or self.destination.complete_name,
        )

    def test_english_stock_quantity_and_location(self):
        answer = self._ask(
            self.stock_user, 'How much of "%s" is there?' % self.product.display_name
        )
        self.assertIn("Stock of", answer)
        self.assertIn("10", answer)
        self.assertIn("on hand", answer)
        self.assertIn(self.origin.complete_name, answer)

        answer = self._ask(
            self.stock_user, 'Where is "%s" located?' % self.product.display_name
        )
        self.assertIn("is stored in:", answer)
        self.assertIn(self.origin.complete_name, answer)
        self.assertIn("Total visible: 10", answer)

    def test_english_transfer_proposal_and_confirmation(self):
        answer = self._ask(self.stock_user, self._transfer_text(2))
        self.assertIn("Transfer proposal", answer)
        self.assertIn("Reply \"confirm\"", answer)
        self.assertEqual(self._quantity_at(self.origin), 10.0)

        answer = self._ask(self.stock_user, "confirm")
        self.assertIn("Transfer completed", answer)
        self.assertEqual(self._quantity_at(self.origin), 8.0)
        self.assertEqual(self._quantity_at(self.destination), 2.0)

    def test_cancel_does_not_change_stock(self):
        self._ask(self.stock_user, self._transfer_text(3))
        answer = self._ask(self.stock_user, "cancel")
        self.assertIn("cancelled", answer)
        self.assertEqual(self._quantity_at(self.origin), 10.0)
        self.assertEqual(self._quantity_at(self.destination), 0.0)

    def test_plain_user_cannot_transfer(self):
        answer = self._ask(self.alice, self._transfer_text(1))
        self.assertIn("You need Inventory access", answer)
        self.assertIn("No records were changed", answer)
        self.assertEqual(self._quantity_at(self.origin), 10.0)
        self.assertEqual(self._quantity_at(self.destination), 0.0)

    def test_admin_without_stock_group_can_transfer(self):
        self.assertFalse(self.admin.has_group("stock.group_stock_user"))
        self.assertTrue(self.admin.has_group("base.group_system"))
        answer = self._ask(self.admin, self._transfer_text(1))
        self.assertIn("Transfer proposal", answer)
        answer = self._ask(self.admin, "confirm")
        self.assertIn("Transfer completed", answer)
        self.assertEqual(self._quantity_at(self.origin), 9.0)
        self.assertEqual(self._quantity_at(self.destination), 1.0)

    def test_unsupported_unit_is_not_silently_converted(self):
        answer = self._ask(
            self.stock_user,
            'Transfer 2 boxes of "%s" from "%s" to "%s"' % (
                self.product.display_name, self.origin.complete_name,
                self.destination.complete_name,
            ),
        )
        self.assertIn("not supported", answer)
        self.assertIn("No transfer was created", answer)
        self.assertEqual(self._quantity_at(self.origin), 10.0)

    def test_english_generic_count_is_not_claimed_by_stock(self):
        answer = self._ask(self.alice, "How many contacts are there?")
        self.assertIn("active Contact records", answer)
        self.assertIn("Contact", answer)
        self.assertNotIn("Stock of", answer)

    def test_english_greeting(self):
        answer = self._ask(self.alice, "Hello Mole")
        self.assertIn("I am Mole", answer)
        self.assertIn("stock", answer)

    def test_pending_transfer_is_cleared_by_new_question(self):
        self._ask(self.stock_user, self._transfer_text(2))
        self._ask(self.stock_user, "How many contacts are there?")
        channel = self._channel(self.stock_user)
        self.assertEqual(channel.assistant_mole_pending_transfer_id, 0)
        self.assertFalse(channel.assistant_mole_pending_transfer_token)
        answer = self._ask(self.stock_user, "confirm")
        self.assertNotIn("Transfer completed", answer)
        self.assertEqual(self._quantity_at(self.origin), 10.0)
