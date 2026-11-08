from datetime import date

from odoo.tests import TransactionCase, new_test_user


class TestBusinessCapabilities(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="assistant_business_user", groups="base.group_user,account.group_account_invoice,account.group_account_readonly")
        cls.receivable_account = cls.env["account.account"].create({"name": "Receivable", "code": "REC", "account_type": "asset_receivable"})
        cls.payable_account = cls.env["account.account"].create({"name": "Payable", "code": "PAY", "account_type": "liability_payable"})
        cls.partner = cls.env["res.partner"].create({"name": "Business Customer", "property_account_receivable_id": cls.receivable_account.id, "property_payment_term_id": False})
        cls.supplier = cls.env["res.partner"].create({"name": "Business Supplier", "property_account_payable_id": cls.payable_account.id, "property_supplier_payment_term_id": False})
        cls.product = cls.env["product.product"].create({"name": "Business Product", "list_price": 10.0})
        cls.sale_journal = cls.env["account.journal"].create({"name": "Sales Journal", "type": "sale", "code": "SJ"})
        cls.purchase_journal = cls.env["account.journal"].create({"name": "Purchase Journal", "type": "purchase", "code": "PJ"})
        cls.income_account = cls.env["account.account"].create({"name": "Income", "code": "INC", "account_type": "income"})
        cls.expense_account = cls.env["account.account"].create({"name": "Expense", "code": "EXP", "account_type": "expense"})

        cls.customer_invoice = cls.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": cls.partner.id,
            "journal_id": cls.sale_journal.id,
            "invoice_date": date(2026, 1, 15),
            "invoice_payment_term_id": False,
            "invoice_line_ids": [(0, 0, {
                "name": "Line",
                "product_id": cls.product.id,
                "account_id": cls.income_account.id,
                "quantity": 2,
                "price_unit": 10.0,
            })],
        })
        cls.customer_invoice.action_post()

        cls.vendor_bill = cls.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": cls.supplier.id,
            "journal_id": cls.purchase_journal.id,
            "invoice_date": date(2026, 2, 10),
            "invoice_payment_term_id": False,
            "invoice_line_ids": [(0, 0, {
                "name": "Purchase",
                "product_id": cls.product.id,
                "account_id": cls.expense_account.id,
                "quantity": 3,
                "price_unit": 5.0,
            })],
        })
        cls.vendor_bill.action_post()

    def _cap(self):
        return self.env["assistant.capability"].with_user(self.user)

    def test_invoice_count(self):
        result = self._cap()._execute_capability("account.invoices.count", {
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "move_types": ["out_invoice"],
            "states": ["posted"],
            "date_basis": "invoice_date",
        })
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(result["criteria"]["move_types"], ["out_invoice"])

    def test_supplier_spend(self):
        result = self._cap()._execute_capability("account.supplier.spend", {
            "date_from": "2026-02-01",
            "date_to": "2026-02-28",
            "supplier_id": self.supplier.id,
            "include_refunds": False,
            "amount_basis": "total",
            "date_basis": "invoice_date",
        })
        self.assertGreaterEqual(result["amount"], 15.0)
        self.assertEqual(result["count"], 1)

    def test_product_sales_invoiced(self):
        result = self._cap()._execute_capability("sale.product.sales", {
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "product_id": self.product.id,
            "source": "invoiced",
            "date_basis": "invoice_date",
        })
        self.assertGreaterEqual(result["quantity"], 2.0)
        self.assertGreaterEqual(result["amount_total"], 20.0)

    def test_unknown_capability_rejected(self):
        with self.assertRaises(ValueError):
            self._cap()._execute_capability("account.move.write", {})

    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):
            self._cap()._execute_capability("account.invoices.count", {
                "date_from": "bad",
                "date_to": "2026-01-31",
                "move_types": ["out_invoice"],
                "states": ["posted"],
                "date_basis": "invoice_date",
            })
