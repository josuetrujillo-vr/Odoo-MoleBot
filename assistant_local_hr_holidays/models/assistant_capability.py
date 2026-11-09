from datetime import datetime, time, timedelta

from odoo import api, models
from odoo.exceptions import AccessError
import re


class AssistantHrHolidaysCapability(models.AbstractModel):
    _inherit = "assistant.capability"
    _description = "Assistant Capability: HR Holidays"

    @api.model
    def _get_capabilities(self):
        capabilities = super()._get_capabilities()
        capabilities["hr.vacation.balance.get_own"] = (
            {},
            self._get_own_vacation_balance,
        )
        capabilities["hr.vacation.balance.get_by_name"] = (
            {"name": str}, self._get_named_vacation_balance,
        )
        return capabilities

    @api.model
    def _get_named_vacation_balance(self, model, arguments):
        env = model.env
        denied = env._("No se puede consultar el saldo con esos datos o permisos.")
        name = arguments["name"]
        if (not env.user.has_group("hr.group_hr_user") or
                not isinstance(name, str) or len(name.strip()) < 3 or
                len(name) > 150 or not re.fullmatch(r"[^\W\d_]+(?:[ '\-][^\W\d_]+)*", name, re.UNICODE)):
            raise ValueError(denied)
        try:
            employees = env["hr.employee"].search([
                ("company_id", "=", env.company.id), ("name", "=ilike", name),
            ], limit=2)
            if len(employees) != 1:
                raise ValueError(denied)
            employee = employees[0]
            employee.check_access("read")
            if env["hr.employee"].sudo().search_count([
                ("company_id", "=", env.company.id), ("name", "=ilike", name),
            ], limit=2) != 1:
                raise ValueError(denied)
            employee.read(["lft_hire_date", "resource_id", "resource_calendar_id"])
            if not employee.lft_hire_date or not employee.resource_calendar_id or not employee.resource_id:
                raise ValueError(denied)
            calendar = employee.resource_calendar_id
            calendar.read(["tz", "two_weeks_calendar"])
            employee.resource_id.read(["tz", "calendar_id", "company_id"])
            _, period_start, period_end = employee._lft_period_values()
            vacation_type = env.ref(
                "l10n_mx_hr_holidays_lft.leave_type_lft_vacation", raise_if_not_found=False
            )
            if not vacation_type:
                raise ValueError(denied)
            if period_start and vacation_type:
                domain = [
                    ("employee_id", "=", employee.id),
                    ("holiday_status_id", "=", vacation_type.id),
                    ("state", "=", "validate"),
                    ("request_date_to", ">=", period_start),
                    ("request_date_from", "<", period_end),
                ]
                leaves = env["hr.leave"].with_context(allowed_company_ids=[env.company.id])
                # A scoped count detects hidden relevant leave; never calculate or expose it with sudo.
                if leaves.search_count(domain) != leaves.sudo().search_count(domain):
                    raise ValueError(denied)
            attendance_domain = [
                ("calendar_id", "=", calendar.id),
                ("resource_id", "in", [False, employee.resource_id.id]),
                ("display_type", "=", False),
                ("day_period", "!=", "lunch"),
            ]
            attendances = env["resource.calendar.attendance"]
            if attendances.search_count(attendance_domain) != attendances.sudo().search_count(attendance_domain):
                raise ValueError(denied)
            calendar_domain = [
                ("company_id", "=", env.company.id),
                ("calendar_id", "in", [False, calendar.id]),
                ("resource_id", "in", [False, employee.resource_id.id]),
                ("time_type", "=", "leave"),
                ("date_from", "<=", datetime.combine(period_end + timedelta(days=2), time.max)),
                ("date_to", ">=", datetime.combine(period_start - timedelta(days=2), time.min)),
            ]
            calendar_leaves = env["resource.calendar.leaves"]
            if calendar_leaves.search_count(calendar_domain) != calendar_leaves.sudo().search_count(calendar_domain):
                raise ValueError(denied)
            fields = ["name", "lft_service_years", "lft_entitlement_days", "lft_approved_days", "lft_available_days", "lft_next_anniversary"]
            employee.invalidate_recordset(fields)
            values = employee.read(fields)[0]
        except AccessError:
            raise ValueError(denied) from None
        return {
            "employee": values["name"],
            "service_years": values["lft_service_years"],
            "entitlement_days": values["lft_entitlement_days"],
            "approved_days": values["lft_approved_days"],
            "available_days": values["lft_available_days"],
            "next_anniversary": values["lft_next_anniversary"],
        }

    @api.model
    def _get_own_vacation_balance(self, _model, _arguments):
        """Return only the authenticated user's own LFT vacation balance.

        The employee is resolved on the server from the authenticated user and
        the active company.  No ``employee_id`` argument is accepted or used.
        """
        env = _model.env
        user = env.user

        employees = user.employee_ids.filtered(
            lambda employee: employee.company_id == env.company
        )
        if not employees:
            raise ValueError(
                env._("No employee is linked to the current user in this company.")
            )
        if len(employees) > 1:
            raise ValueError(
                env._("The current user has more than one employee in this company.")
            )
        employee = employees[0]

        balance_employee = employee._lft_balance_employee()
        if not balance_employee:
            raise AccessError(
                env._("The current user is not authorized to read this vacation balance.")
            )

        def date_value(value):
            return value.isoformat() if value else None

        return {
            "employee": balance_employee.name,
            "company_id": balance_employee.company_id.id,
            "company": balance_employee.company_id.name,
            "hire_date": date_value(balance_employee.lft_hire_date),
            "service_years": float(balance_employee.lft_service_years or 0.0),
            "period_start": date_value(balance_employee.lft_period_start),
            "next_anniversary": date_value(balance_employee.lft_next_anniversary),
            "entitlement_days": float(balance_employee.lft_entitlement_days or 0.0),
            "approved_days": float(balance_employee.lft_approved_days or 0.0),
            "pending_approved_days": float(
                balance_employee.lft_pending_approved_days or 0.0
            ),
            "migration_applied_days": float(
                balance_employee.lft_migration_applied_days or 0.0
            ),
            "available_days": float(balance_employee.lft_available_days or 0.0),
            "days_to_reset": float(balance_employee.lft_days_to_reset or 0.0),
            "criteria": {
                "capability": "hr.vacation.balance.get_own",
                "source": "l10n_mx_hr_holidays_lft.models.hr_employee._compute_lft_balance",
                "identity_source": "env.user",
                "company_source": "env.company",
                "employee_resolution": "user.employee_ids filtered by company",
                "sudo_scope": (
                    "Only the employee linked to env.user; "
                    "_lft_balance_employee returns sudo only for that employee"
                ),
                "functional_writes": "none",
            },
        }
