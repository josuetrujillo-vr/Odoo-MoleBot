from odoo import api, models


class AssistantResPartner(models.Model):
    _inherit = "res.partner"

    @api.model_create_multi
    def create(self, vals_list):
        if "autopost_bills" in self._fields:
            for vals in vals_list:
                vals.setdefault("autopost_bills", "ask")
        return super().create(vals_list)
