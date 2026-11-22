from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user


class TestInference(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="assistant_model_user", groups="base.group_user")

    def test_unconfigured_model_is_reported(self):
        provider = self.env["assistant.inference"].with_user(self.user)
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(UserError):
                provider._chat([], [])

    def test_configured_transport_receives_local_model_request(self):
        provider = self.env["assistant.inference"].with_user(self.user)
        env = {"ASSISTANT_LOCAL_URL": "http://127.0.0.1:11434", "ASSISTANT_LOCAL_MODEL": "test"}
        reply = {"role": "assistant", "content": "Hi", "tool_calls": []}
        with patch.dict("os.environ", env, clear=True), patch(
            "odoo.addons.assistant_local.models.inference.chat", return_value=reply
        ) as transport:
            self.assertEqual(provider._chat([{"role": "user", "content": "Hi"}], []), reply)
        self.assertEqual(transport.call_args.args[:2], (env["ASSISTANT_LOCAL_URL"], "test"))
