from datetime import date

from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


def _user(env, **kwargs):
    return new_test_user(env, context={"no_reset_password": True}, **kwargs)


@tagged("post_install", "-at_install")
class TestHrVacationCapability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.basic_user = _user(
            cls.env, login="assistant_hr_basic", groups="base.group_user"
        )
        cls.peer_user = _user(
            cls.env, login="assistant_hr_peer", groups="base.group_user"
        )
        cls.no_employee_user = _user(
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

    def test_authorized_named_balance_matches_lft_field(self):
        hr_user = _user(self.env, login="assistant_hr_officer", groups="base.group_user,hr.group_hr_user")
        result = self._capability(hr_user)._execute_capability(
            "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name}
        )
        self.assertEqual(result["available_days"], self.peer_employee.with_user(hr_user).lft_available_days)
        self.assertEqual(result["employee"], self.peer_employee.name)

    def test_named_balance_performs_no_business_writes(self):
        hr_user = _user(self.env, login="assistant_hr_readonly", groups="base.group_user,hr.group_hr_user")
        employee = self.peer_employee
        before = employee.read(["lft_hire_date", "lft_allocation_id"])
        self._capability(hr_user)._execute_capability(
            "hr.vacation.balance.get_by_name", {"name": employee.name}
        )
        employee.invalidate_recordset()
        self.assertEqual(employee.read(["lft_hire_date", "lft_allocation_id"]), before)

    def test_named_balance_with_visible_and_hidden_approved_leave(self):
        hr_user = _user(self.env, login="assistant_hr_leave_visibility", groups="base.group_user,hr.group_hr_user,hr_holidays.group_hr_holidays_user")
        with patch.object(fields.Date, "today", return_value=date(2026, 9, 16)):
            leave = self.env["hr.leave"].create({
                "name": "Synthetic approved leave",
                "employee_id": self.peer_employee.id,
                "holiday_status_id": self.env.ref("l10n_mx_hr_holidays_lft.leave_type_lft_vacation").id,
                "request_date_from": date(2026, 9, 7),
                "request_date_to": date(2026, 9, 11),
            })
            leave.action_approve()
            self.assertEqual(leave.state, "validate")
            self.peer_employee.invalidate_recordset()
            expected = self.peer_employee.lft_available_days
            self.assertGreater(self.peer_employee.lft_approved_days, 0)
            result = self._capability(hr_user)._execute_capability(
                "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name}
            )
            self.assertEqual(result["available_days"], expected)
            self.env["ir.rule"].create({
                "name": "Assistant test exclude leave",
                "model_id": self.env["ir.model"]._get_id("hr.leave"),
                "domain_force": "[('id', '!=', %s)]" % leave.id,
            })
            self.env.invalidate_all()
            with self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
                self._capability(hr_user)._execute_capability(
                    "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name}
                )

    def test_named_balance_rejects_hidden_calendar_exclusion(self):
        hr_user = _user(self.env, login="assistant_hr_calendar_visibility", groups="base.group_user,hr.group_hr_user,hr_holidays.group_hr_holidays_user")
        with patch.object(fields.Date, "today", return_value=date(2026, 9, 16)):
            leave = self.env["hr.leave"].create({
                "name": "Synthetic leave for calendar",
                "employee_id": self.peer_employee.id,
                "holiday_status_id": self.env.ref("l10n_mx_hr_holidays_lft.leave_type_lft_vacation").id,
                "request_date_from": date(2026, 9, 7), "request_date_to": date(2026, 9, 11),
            })
            leave.action_approve()
            calendar_leave = self.env["resource.calendar.leaves"].create({
                "name": "Synthetic holiday",
                "calendar_id": self.peer_employee.resource_calendar_id.id,
                "date_from": "2026-09-09 00:00:00", "date_to": "2026-09-09 23:59:59",
            })
            self.env["ir.rule"].create({
                "name": "Assistant hide calendar exclusion",
                "model_id": self.env["ir.model"]._get_id("resource.calendar.leaves"),
                "domain_force": "[('id', '!=', %s)]" % calendar_leave.id,
            })
            self.env.invalidate_all()
            with self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
                self._capability(hr_user)._execute_capability(
                    "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name}
                )

    def test_named_balance_rejects_hidden_calendar_attendance(self):
        hr_user = _user(self.env, login="assistant_hr_hidden_attendance", groups="base.group_user,hr.group_hr_user,hr_holidays.group_hr_holidays_user")
        attendance = self.peer_employee.resource_calendar_id.attendance_ids.filtered(lambda item: not item.display_type)[:1]
        self.assertTrue(attendance)
        self.env["ir.rule"].create({
            "name": "Assistant hide calendar attendance",
            "model_id": self.env["ir.model"]._get_id("resource.calendar.attendance"),
            "domain_force": "[('id', '!=', %s)]" % attendance.id,
        })
        self.env.invalidate_all()
        with self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
            self._capability(hr_user)._execute_capability(
                "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name}
            )

    def test_named_balance_rejects_extra_arguments(self):
        hr_user = _user(self.env, login="assistant_hr_arguments", groups="base.group_user,hr.group_hr_user")
        with self.assertRaises(ValueError):
            self._capability(hr_user)._execute_capability(
                "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name, "employee_id": self.employee.id}
            )

    def test_regular_user_cannot_read_named_balance(self):
        with self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
            self._capability(self.basic_user)._execute_capability(
                "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name}
            )

    def test_named_balance_rejects_invalid_and_ambiguous_names(self):
        hr_user = _user(self.env, login="assistant_hr_ambiguous", groups="base.group_user,hr.group_hr_user")
        self.env["hr.employee"].create({"name": self.peer_employee.name})
        for name in ("", "A", "Nombre Inexistente", self.peer_employee.name):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
                self._capability(hr_user)._execute_capability(
                    "hr.vacation.balance.get_by_name", {"name": name}
                )

    def test_named_balance_rejects_hidden_homonym(self):
        hr_user = _user(self.env, login="assistant_hr_hidden_duplicate", groups="base.group_user,hr.group_hr_user")
        duplicate = self.env["hr.employee"].create({"name": self.peer_employee.name})
        self.env["ir.rule"].create({
            "name": "Assistant hide duplicate",
            "model_id": self.env["ir.model"]._get_id("hr.employee"),
            "domain_force": "[('id', '!=', %s)]" % duplicate.id,
        })
        with self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
            self._capability(hr_user)._execute_capability(
                "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name}
            )

    def test_named_balance_rejects_missing_lft_hire_date(self):
        hr_user = _user(self.env, login="assistant_hr_no_hire_date", groups="base.group_user,hr.group_hr_user")
        employee = self.env["hr.employee"].create({"name": "Employee No Hire Date"})
        with self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
            self._capability(hr_user)._execute_capability(
                "hr.vacation.balance.get_by_name", {"name": employee.name}
            )

    def test_named_balance_rejects_other_company(self):
        hr_user = _user(self.env, login="assistant_hr_company", groups="base.group_user,hr.group_hr_user")
        company = self.env["res.company"].create({"name": "Assistant other company"})
        employee = self.env["hr.employee"].create({"name": "Other Company Person", "company_id": company.id})
        hr_user.write({"company_ids": [(4, company.id)]})
        with self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
            self._capability(hr_user)._execute_capability(
                "hr.vacation.balance.get_by_name", {"name": employee.name}
            )

    def test_named_balance_respects_employee_record_rule(self):
        hr_user = _user(self.env, login="assistant_hr_rule", groups="base.group_user,hr.group_hr_user")
        self.env["ir.rule"].create({
            "name": "Assistant test exclude employee",
            "model_id": self.env["ir.model"]._get_id("hr.employee"),
            "domain_force": "[('id', '!=', %s)]" % self.peer_employee.id,
        })
        with self.assertRaisesRegex(ValueError, "No se puede consultar el saldo"):
            self._capability(hr_user)._execute_capability(
                "hr.vacation.balance.get_by_name", {"name": self.peer_employee.name}
            )

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
