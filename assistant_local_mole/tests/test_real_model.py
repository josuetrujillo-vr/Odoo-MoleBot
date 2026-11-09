import os
from datetime import date
from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import html2plaintext


@tagged("post_install", "-at_install", "mole_real_model")
class TestMoleRealModel(TransactionCase):
    def test_own_vacation_question_uses_real_local_model_and_odoo_balance(self):
        executable = os.environ.get("MOLE_LLAMA_EXE")
        model = os.environ.get("MOLE_MODEL_PATH")
        if not executable or not model:
            self.skipTest("Local model paths were not provided")
        user = new_test_user(self.env, login="mole_real_user", groups="base.group_user", context={"no_reset_password": True})
        employee = self.env["hr.employee"].create({
            "name": "Synthetic Mole Employee", "user_id": user.id,
            "company_id": self.env.company.id, "lft_hire_date": date(2020, 1, 1),
        })
        expected = employee.sudo().lft_available_days
        channel = self.env["discuss.channel"].with_user(user).assistant_mole_ensure_for_current_user()
        with patch.dict(os.environ, {"ASSISTANT_LOCAL_BACKEND": "llama_cpp_cli"}):
            channel.with_user(user).message_post(
                body="¿Cuántos días de vacaciones me quedan?", message_type="comment"
            )
        channel.invalidate_recordset()
        answer = channel.message_ids.sorted(key=lambda item: item.id)[-1]
        self.assertEqual(answer.author_id, self.env.ref("assistant_local_mole.partner_mole"))
        self.assertIn("Días disponibles: %s" % expected, html2plaintext(answer.body))
