from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user


class TestConversationSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.alice = new_test_user(
            cls.env, login="assistant_alice", groups="base.group_user", context={"no_reset_password": True}
        )
        cls.bob = new_test_user(
            cls.env, login="assistant_bob", groups="base.group_user", context={"no_reset_password": True}
        )
        cls.alice_conversation = cls.env["assistant.conversation"].with_user(cls.alice).create({
            "name": "Alice private conversation",
        })

    def test_other_user_cannot_search_or_read_conversation(self):
        conversations = self.env["assistant.conversation"].with_user(self.bob)
        self.assertFalse(conversations.search([("id", "=", self.alice_conversation.id)]))
        with self.assertRaises(AccessError):
            conversations.browse(self.alice_conversation.id).read(["name"])

    def test_user_cannot_create_conversation_for_another_user(self):
        with self.assertRaises(AccessError):
            self.env["assistant.conversation"].with_user(self.bob).create({
                "name": "Forged conversation", "user_id": self.alice.id,
            })

    def test_user_cannot_change_conversation_owner(self):
        with self.assertRaises(AccessError):
            self.alice_conversation.with_user(self.alice).write({"user_id": self.bob.id})

    def test_user_cannot_create_or_move_conversation_to_unauthorized_company(self):
        other_company = self.env["res.company"].create({"name": "Other Company"})
        conversations = self.env["assistant.conversation"].with_user(self.alice)
        with self.assertRaises(AccessError):
            conversations.create({"name": "Wrong company", "company_id": other_company.id})
        with self.assertRaises(AccessError):
            self.alice_conversation.with_user(self.alice).write({"company_id": other_company.id})

    def test_conversation_is_hidden_when_its_company_is_not_active(self):
        second_company = self.env["res.company"].create({"name": "Second Company"})
        self.alice.write({"company_ids": [Command.link(second_company.id)]})
        conversations = self.env["assistant.conversation"].with_user(self.alice).with_context(
            allowed_company_ids=[second_company.id]
        )
        self.assertFalse(conversations.search([("id", "=", self.alice_conversation.id)]))
        with self.assertRaises(AccessError):
            conversations.browse(self.alice_conversation.id).read(["name"])
