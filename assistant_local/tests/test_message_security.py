from odoo.exceptions import AccessError, ValidationError
from odoo.service.model import get_public_method
from odoo.tests import TransactionCase, new_test_user


class TestMessageSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.alice = new_test_user(
            cls.env, login="assistant_message_alice", groups="base.group_user", context={"no_reset_password": True}
        )
        cls.bob = new_test_user(
            cls.env, login="assistant_message_bob", groups="base.group_user", context={"no_reset_password": True}
        )
        cls.thread = cls.env["assistant.conversation"].with_user(cls.alice).create({"name": "Private"})

    def test_user_can_create_and_read_own_message(self):
        message = self.env["assistant.message"].with_user(self.alice).create({
            "conversation_id": self.thread.id, "body": "How many?",
        })
        self.assertEqual(message.role, "user")
        self.assertEqual(message.body, "How many?")

    def test_other_user_cannot_read_or_write_in_thread(self):
        message = self.env["assistant.message"].with_user(self.alice).create({
            "conversation_id": self.thread.id, "body": "Private",
        })
        messages = self.env["assistant.message"].with_user(self.bob)
        self.assertFalse(messages.search([("id", "=", message.id)]))
        with self.assertRaises(AccessError):
            messages.browse(message.id).read(["body"])
        with self.assertRaises(AccessError):
            messages.create({"conversation_id": self.thread.id, "body": "Intrusion"})

    def test_user_cannot_forge_assistant_message(self):
        with self.assertRaises(AccessError):
            self.env["assistant.message"].with_user(self.alice).create({
                "conversation_id": self.thread.id, "body": "Forged", "role": "assistant",
            })
        message = self.env["assistant.message"].with_user(self.alice).with_context(
            default_role="assistant"
        ).create({"conversation_id": self.thread.id, "body": "Still a user message"})
        self.assertEqual(message.role, "user")

    def test_assistant_message_helper_checks_access_and_is_private(self):
        messages = self.env["assistant.message"].with_user(self.alice)
        message = messages._create_assistant_message(self.thread.with_user(self.alice), "Result")
        self.assertEqual(message.role, "assistant")
        with self.assertRaises(AccessError):
            get_public_method(messages, "_create_assistant_message")
        with self.assertRaises(AccessError):
            messages.with_user(self.bob)._create_assistant_message(self.thread.with_user(self.bob), "No")
        with self.assertRaises(AccessError):
            messages.with_user(self.bob)._create_assistant_message(self.thread.sudo(), "No")

    def test_message_cannot_be_moved_or_rewritten(self):
        messages = self.env["assistant.message"].with_user(self.alice)
        message = messages.create({"conversation_id": self.thread.id, "body": "Original"})
        with self.assertRaises(AccessError):
            message.write({"body": "Altered"})

    def test_direct_create_rejects_blank_or_oversized_body(self):
        messages = self.env["assistant.message"].with_user(self.alice)
        for body in (" ", "x" * 4001):
            with self.subTest(length=len(body)), self.assertRaises(ValidationError):
                messages.create({"conversation_id": self.thread.id, "body": body})
