from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user
from unittest.mock import patch


class TestMoleDiscuss(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = new_test_user(cls.env, login="mole_alice", groups="base.group_user")
        cls.bob = new_test_user(cls.env, login="mole_bob", groups="base.group_user")
        cls.mole_partner = cls.env.ref("assistant_local_mole.partner_mole")

    def _ensure(self, user):
        return self.env["discuss.channel"].with_user(user).assistant_mole_ensure_for_current_user()

    def test_channel_created_and_idempotent(self):
        ch1 = self._ensure(self.alice)
        self.assertTrue(ch1)
        self.assertEqual(ch1.channel_type, "chat")
        self.assertEqual(ch1.assistant_mole_owner_id, self.alice)
        ch2 = self._ensure(self.alice)
        self.assertEqual(ch1.id, ch2.id)

    def test_channel_has_exactly_two_members(self):
        ch = self._ensure(self.alice)
        partners = ch.channel_member_ids.mapped("partner_id")
        self.assertEqual(len(partners), 2)
        self.assertIn(self.alice.partner_id, partners)
        self.assertIn(self.mole_partner, partners)

    def test_other_user_cannot_search_channel(self):
        ch = self._ensure(self.alice)
        channels = self.env["discuss.channel"].with_user(self.bob)
        self.assertFalse(channels.search([("id", "=", ch.id)]))

    def test_channel_belongs_to_owner(self):
        ch = self._ensure(self.alice)
        self.assertEqual(ch.assistant_mole_owner_id, self.alice)
        with self.assertRaises(AccessError):
            ch.with_user(self.bob).write({"assistant_mole_owner_id": self.bob.id})
        with self.assertRaises(AccessError):
            ch.with_user(self.alice).write({"assistant_mole_owner_id": self.bob.id})

    def test_user_cannot_forge_owner_in_context_defaults(self):
        channels = self.env["discuss.channel"].with_user(self.alice).with_context(
            default_assistant_mole_owner_id=self.bob.id
        )
        with self.assertRaises(AccessError):
            channels.create({"name": "Fake", "channel_type": "group"})

    def test_no_duplicate_across_users(self):
        cha = self._ensure(self.alice)
        chb = self._ensure(self.bob)
        self.assertNotEqual(cha.id, chb.id)

    def test_is_mole_channel_flag(self):
        ch = self._ensure(self.alice)
        self.assertTrue(ch._is_mole_channel())
        group = self.env["discuss.channel"].with_user(self.alice).create({
            "name": "Group",
            "channel_type": "group",
            "channel_member_ids": [
                Command.create({"partner_id": self.alice.partner_id.id}),
                Command.create({"partner_id": self.mole_partner.id}),
            ],
        })
        self.assertFalse(group._is_mole_channel())

    def test_mole_does_not_respond_to_own_message(self):
        ch = self._ensure(self.alice)
        before = len(ch.message_ids)
        ch.sudo().message_post(
            body="hello from mole", author_id=self.mole_partner.id, message_type="comment"
        )
        ch.invalidate_recordset()
        # Only the posted message, no extra reply from Mole
        self.assertEqual(len(ch.message_ids), before + 1)

    def test_forged_author_does_not_trigger_dispatch(self):
        ch = self._ensure(self.alice)
        before = len(ch.message_ids)
        # Post as bob (forged author) into alice's channel via sudo
        ch.sudo().message_post(
            body="saldo de vacaciones", author_id=self.bob.partner_id.id, message_type="comment"
        )
        ch.invalidate_recordset()
        # No Mole reply should have been generated
        self.assertEqual(len(ch.message_ids), before + 1)

    def test_no_model_posts_clear_error(self):
        ch = self._ensure(self.alice)
        before = len(ch.message_ids)
        ch.with_user(self.alice).message_post(body="saldo de vacaciones", message_type="comment")
        ch.invalidate_recordset()
        self.assertGreater(len(ch.message_ids), before)
        last = ch.message_ids.sorted(key=lambda m: m.id)[-1]
        self.assertEqual(last.author_id, self.mole_partner)

    def test_reused_confirmation_single_channel(self):
        ch1 = self._ensure(self.alice)
        ch2 = self._ensure(self.alice)
        self.assertEqual(ch1.id, ch2.id)

    def test_model_text_cannot_invent_a_vacation_balance(self):
        channel = self._ensure(self.alice)
        provider = self.env["assistant.inference"].with_user(self.alice)
        with patch.object(type(provider), "_chat", return_value={
            "content": "Tienes 500 días de vacaciones", "tool_calls": [],
        }):
            channel.with_user(self.alice).message_post(body="¿Cuántos días me quedan?", message_type="comment")
        channel.invalidate_recordset()
        last = channel.message_ids.sorted(key=lambda item: item.id)[-1]
        self.assertNotIn("500", last.body)
