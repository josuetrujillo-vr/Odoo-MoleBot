from odoo import api, models
from odoo.exceptions import AccessError


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
        return capabilities

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
