from odoo import api, models


class AssistantMoleResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _init_store_data(self, store, /):
        super()._init_store_data(store)
        if self.env.user._is_public():
            return
        if not self.env.user._is_internal():
            return
        try:
            self.env["discuss.channel"].assistant_mole_ensure_for_current_user()
        except Exception:
            # Never break session loading if Mole channel cannot be created
            pass
