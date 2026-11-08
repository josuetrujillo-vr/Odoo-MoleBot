from odoo import api, models


class AssistantResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("calendar_default_privacy", "public")
        return super().create(vals_list)
