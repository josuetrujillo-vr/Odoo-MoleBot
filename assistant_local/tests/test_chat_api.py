from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user


class TestChatApi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.alice = new_test_user(
            cls.env,
            login="assistant_chat_alice",
            groups="base.group_user",
            context={"no_reset_password": True},
        )
        cls.bob = new_test_user(
            cls.env,
            login="assistant_chat_bob",
            groups="base.group_user",
            context={"no_reset_password": True},
        )
        cls.thread = cls.env["assistant.conversation"].with_user(cls.alice).create({"name": "Chat"})

    def test_submit_stores_user_message_and_reports_unavailable(self):
        thread = self.thread.with_user(self.alice)
        with patch.dict("os.environ", {}, clear=True):
            result = thread.submit_chat_message("  Hola  ")
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual([message["body"] for message in result["messages"]], ["Hola"])
            self.assertEqual(result["messages"], thread.get_chat_messages())

    def test_submit_stores_user_message_and_reports_ok_when_model_configured(self):
        thread = self.thread.with_user(self.alice)
        env = {
            "ASSISTANT_LOCAL_BACKEND": "llama_cpp_cli",
            "MOLE_LLAMA_EXE": "llama-completion.exe",
            "MOLE_MODEL_PATH": "model.gguf",
        }
        reply = {"role": "assistant", "content": "", "tool_calls": []}
        with patch.dict("os.environ", env, clear=True), patch(
            "odoo.addons.assistant_local.models.inference._local_interpret", return_value=reply
        ):
            result = thread.submit_chat_message("Hola")
            self.assertEqual(result["status"], "ok")
            messages = [m["body"] for m in result["messages"]]
            self.assertIn("Hola", messages)
            self.assertIn("Por ahora solo puedo consultar tu saldo de vacaciones.", messages)

    def test_other_user_cannot_read_or_post(self):
        thread = self.thread.with_user(self.bob)
        with self.assertRaises(AccessError):
            thread.get_chat_messages()
        with self.assertRaises(AccessError):
            thread.submit_chat_message("Hello")
        self.assertFalse(self.env["assistant.message"].sudo().search([
            ("conversation_id", "=", self.thread.id)
        ]))

    def test_blank_and_oversized_messages_are_rejected(self):
        thread = self.thread.with_user(self.alice)
        for text in ("", "   ", "x" * 4001, False):
            with self.subTest(text=text[:10] if isinstance(text, str) else text):
                with self.assertRaises(ValidationError):
                    thread.submit_chat_message(text)
        self.assertFalse(thread.get_chat_messages())

    def test_open_chat_action_checks_conversation_access(self):
        action = self.thread.with_user(self.alice).action_open_chat()
        self.assertEqual(action["tag"], "assistant_local.chat")
        self.assertEqual(action["params"]["context"]["conversationId"], self.thread.id)
        with self.assertRaises(AccessError):
            self.thread.with_user(self.bob).action_open_chat()

    def test_chat_assets_are_registered_in_backend_bundle(self):
        assets, _ = self.env["ir.qweb"]._get_asset_content("web.assets_backend")
        urls = {asset["url"] for asset in assets}
        self.assertIn("/assistant_local/static/src/chat/assistant_chat.js", urls)
        self.assertIn("/assistant_local/static/src/chat/assistant_chat.xml", urls)

    def test_model_cannot_confirm_stock_through_legacy_chat(self):
        thread = self.thread.with_user(self.alice)
        engine = self.env["assistant.capability"].with_user(self.alice)
        reply = {"content": "", "tool_calls": [{"function": {
            "name": "stock.internal_transfer.confirm", "arguments": {}
        }}]}
        with patch.object(type(engine), "_execute_capability") as dispatch:
            thread._apply_model_reply(reply)
        dispatch.assert_not_called()

    def test_ungrounded_model_claim_is_not_displayed(self):
        thread = self.thread.with_user(self.alice)
        thread._apply_model_reply({"content": "Tienes 500 días de vacaciones", "tool_calls": []})
        self.assertNotIn("500", " ".join(item["body"] for item in thread.get_chat_messages()))

    def test_unauthorized_tools_fallback_to_safe_vacation_message(self):
        thread = self.thread.with_user(self.alice)
        forbidden_calls = [
            {"function": {"name": "res.partner.create", "arguments": {"name": "Evil"}}},
            {"function": {"name": "stock.quant.write", "arguments": {}}},
            {"function": {"name": "unknown.tool", "arguments": {}}},
        ]
        for call in forbidden_calls:
            with self.subTest(tool=call["function"]["name"]):
                thread._apply_model_reply({"content": "done", "tool_calls": [call]})
                last_msg = thread.get_chat_messages()[-1]["body"]
                self.assertIn("Por ahora solo puedo consultar tu saldo de vacaciones", last_msg)
