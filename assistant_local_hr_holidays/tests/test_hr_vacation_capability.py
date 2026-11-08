from datetime import date

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestHrVacationCapability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.basic_user = new_test_user(
            cls.env, login="assistant_hr_basic", groups="base.group_user"
        )
        cls.peer_user = new_test_user(
            cls.env, login="assistant_hr_peer", groups="base.group_user"
        )
        cls.no_employee_user = new_test_user(
            cls.env, login="assistant_hr_no_employee", groups="base.group_user"
        )

        cls.employee = cls.env["hr.employee"].create({
            "name": "Assistant HR Basic Employee",
            "user_id": cls.basic_user.id,
            "lft_hire_date": date(2020, 1, 1),
        })
        cls.peer_employee = cls.env["hr.employee"].create({
            "name": "Assistant HR Peer Employee",
            "user_id": cls.peer_user.id,
            "lft_hire_date": date(2021, 6, 1),
        })

    def _capability(self, user):
        return self.env["assistant.capability"].with_user(user)

    def test_capability_is_registered_with_empty_schema(self):
        capabilities = self.env["assistant.capability"]._get_capabilities()
        self.assertIn("hr.vacation.balance.get_own", capabilities)
        self.assertEqual(capabilities["hr.vacation.balance.get_own"][0], {})

    def test_basic_user_receives_own_balance(self):
        result = self._capability(self.basic_user)._execute_capability(
            "hr.vacation.balance.get_own", {}
        )

        self.assertEqual(result["employee"], "Assistant HR Basic Employee")
        self.assertEqual(result["company_id"], self.env.company.id)
        self.assertIn("available_days", result)
        self.assertIn("period_start", result)
        self.assertIn("next_anniversary", result)
        self.assertEqual(result["criteria"]["identity_source"], "env.user")
        self.assertEqual(result["criteria"]["functional_writes"], "none")

    def test_peer_user_receives_only_its_own_balance(self):
        result = self._capability(self.peer_user)._execute_capability(
            "hr.vacation.balance.get_own", {}
        )

        self.assertEqual(result["employee"], "Assistant HR Peer Employee")
        self.assertNotEqual(result["employee"], "Assistant HR Basic Employee")

    def test_extra_argument_is_rejected(self):
        with self.assertRaises(ValueError):
            self._capability(self.basic_user)._execute_capability(
                "hr.vacation.balance.get_own", {"employee_id": self.employee.id}
            )

    def test_user_without_employee_is_rejected(self):
        with self.assertRaises(ValueError):
            self._capability(self.no_employee_user)._execute_capability(
                "hr.vacation.balance.get_own", {}
            )

    def test_balance_is_company_scoped(self):
        second_company = self.env["res.company"].create({"name": "Second HR Company"})
        second_employee = self.env["hr.employee"].create({
            "name": "Assistant HR Second Company Employee",
            "user_id": self.basic_user.id,
            "company_id": second_company.id,
            "lft_hire_date": date(2019, 3, 1),
        })
        self.basic_user.write({"company_ids": [(4, second_company.id)]})

        result = self._capability(self.basic_user).with_company(
            second_company
        )._execute_capability("hr.vacation.balance.get_own", {})

        self.assertEqual(result["employee"], "Assistant HR Second Company Employee")
        self.assertEqual(result["company_id"], second_company.id)
        self.assertNotEqual(result["employee"], "Assistant HR Basic Employee")

    def test_capability_does_not_expose_peer_employee_data(self):
        result = self._capability(self.basic_user)._execute_capability(
            "hr.vacation.balance.get_own", {}
        )

        self.assertNotIn("peer_employee", str(result))
        self.assertNotEqual(result["employee"], "Assistant HR Peer Employee")

    def test_capability_performs_no_functional_writes(self):
        hire_date_before = self.employee.lft_hire_date
        allocation_before = self.employee.lft_allocation_id

        self._capability(self.basic_user)._execute_capability(
            "hr.vacation.balance.get_own", {}
        )

        self.assertEqual(self.employee.lft_hire_date, hire_date_before)
        self.assertEqual(self.employee.lft_allocation_id, allocation_before)

    def test_result_contains_balance_fields_and_criteria(self):
        result = self._capability(self.basic_user)._execute_capability(
            "hr.vacation.balance.get_own", {}
        )

        for field_name in (
            "service_years",
            "entitlement_days",
            "approved_days",
            "pending_approved_days",
            "migration_applied_days",
            "available_days",
            "days_to_reset",
        ):
            self.assertIn(field_name, result)
        self.assertEqual(result["criteria"]["functional_writes"], "none")
        self.assertEqual(result["criteria"]["sudo_scope"].startswith("Only the employee"), True)
