from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user


class TestChatApi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = new_test_user(cls.env, login="assistant_chat_alice", groups="base.group_user")
        cls.bob = new_test_user(cls.env, login="assistant_chat_bob", groups="base.group_user")
        cls.thread = cls.env["assistant.conversation"].with_user(cls.alice).create({"name": "Chat"})

    def test_submit_stores_user_message_and_reports_unavailable(self):
        thread = self.thread.with_user(self.alice)
        result = thread.submit_chat_message("  Hola  ")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual([message["body"] for message in result["messages"]], ["Hola"])
        self.assertEqual(result["messages"], thread.get_chat_messages())

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
