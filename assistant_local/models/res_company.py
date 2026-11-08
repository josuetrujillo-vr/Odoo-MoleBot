from odoo import api, models


class AssistantResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("fiscalyear_last_day", 31)
            vals.setdefault("fiscalyear_last_month", "12")
        return super().create(vals_list)
