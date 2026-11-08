from odoo import api, models


class AssistantResUsers(models.Model):
    _inherit = "res.users"

    @api.depends("share", "groups_id")
    def _compute_notification_type(self):
        super()._compute_notification_type()
        self.filtered(lambda user: not user.notification_type).notification_type = "email"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("notification_type", "email")
        return super().create(vals_list)
