from datetime import date

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user
from unittest.mock import patch


class TestMoleDiscuss(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = new_test_user(cls.env, login="mole_alice", groups="base.group_user", context={"no_reset_password": True})
        cls.bob = new_test_user(cls.env, login="mole_bob", groups="base.group_user", context={"no_reset_password": True})
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

    def test_model_cannot_choose_named_employee(self):
        channel = self._ensure(self.alice)
        provider = self.env["assistant.inference"].with_user(self.alice)
        capability = self.env["assistant.capability"].with_user(self.alice)
        with patch.object(type(provider), "_chat", return_value={
            "tool_calls": [{"function": {"name": "hr.vacation.balance.get_by_name", "arguments": {"name": "Invented Person"}}}],
        }), patch.object(type(capability), "_execute_capability") as execute:
            channel.with_user(self.alice).message_post(body="Hola", message_type="comment")
        execute.assert_not_called()

    def test_named_query_ignores_forged_model_arguments(self):
        channel = self._ensure(self.alice)
        capability = self.env["assistant.capability"].with_user(self.alice)
        with patch.object(type(capability), "_execute_capability", return_value={"employee": "Ana Pérez", "available_days": 12}) as execute:
            channel.with_user(self.alice).message_post(body="Saldo de vacaciones de Ana Pérez", message_type="comment")
        execute.assert_called_once_with("hr.vacation.balance.get_by_name", {"name": "Ana Pérez"})

    def test_named_discuss_uses_real_lft_and_denies_regular_user(self):
        officer = new_test_user(self.env, login="mole_hr_officer", groups="base.group_user,hr.group_hr_user,hr_holidays.group_hr_holidays_user", context={"no_reset_password": True})
        employee = self.env["hr.employee"].create({"name": "Mole Named Employee", "lft_hire_date": date(2020, 1, 1)})
        expected = employee.lft_available_days
        before = employee.read(["lft_hire_date", "lft_allocation_id"])
        for user, permitted in ((officer, True), (self.alice, False)):
            channel = self._ensure(user)
            channel.with_user(user).message_post(body="Saldo de vacaciones de Mole Named Employee", message_type="comment")
            channel.invalidate_recordset()
            reply = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
            if permitted:
                self.assertIn("Días disponibles: %s" % expected, reply)
            else:
                self.assertIn("No se puede consultar el saldo", reply)
                self.assertNotIn("Días disponibles", reply)
        employee.invalidate_recordset()
        self.assertEqual(employee.read(["lft_hire_date", "lft_allocation_id"]), before)

    def test_general_count_discuss_uses_real_orm(self):
        channel = self._ensure(self.alice)
        provider = self.env['assistant.inference'].with_user(self.alice)
        plan = {'operation': 'count', 'model': 'res.partner', 'filters': []}
        label = self.env['assistant.general.query'].with_user(self.alice)._catalog()['res.partner']['label']
        with patch.object(type(provider), '_chat', return_value={'tool_calls': []}), patch.object(type(provider), '_general_plan', return_value=plan):
            channel.with_user(self.alice).message_post(body='¿Cuántos %s hay?' % label, message_type='comment')
        channel.invalidate_recordset()
        answer = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
        expected = self.env['res.partner'].with_user(self.alice).with_context(active_test=True).search_count([])
        self.assertIn(str(expected), answer)
        self.assertIn('activos', answer)

    def test_general_list_and_read_in_discuss(self):
        channel = self._ensure(self.alice)
        self.env['res.partner'].create({'name': 'Mole Discuss Specific Partner'})
        channel.with_user(self.alice).message_post(body='¿Cuáles son los contactos?', message_type='comment')
        channel.invalidate_recordset()
        last_msg = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
        self.assertIn('Registros visibles de Contact', last_msg)
        self.assertIn('Mole Discuss Specific Partner', last_msg)

        channel.with_user(self.alice).message_post(body='Información del contacto "Mole Discuss Specific Partner"', message_type='comment')
        channel.invalidate_recordset()
        last_msg = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
        self.assertIn('Información de Contact', last_msg)
        self.assertIn('Mole Discuss Specific Partner', last_msg)

    def test_greeting_and_help_in_discuss(self):
        channel = self._ensure(self.alice)
        channel.with_user(self.alice).message_post(body='Hola Mole', message_type='comment')
        channel.invalidate_recordset()
        last_msg = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
        self.assertIn('Soy Mole', last_msg)

    def test_sensitive_field_query_in_discuss(self):
        channel = self._ensure(self.alice)
        channel.with_user(self.alice).message_post(body='¿Cuál es la contraseña del usuario?', message_type='comment')
        channel.invalidate_recordset()
        last_msg = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
        self.assertIn('seguridad', last_msg)
        self.assertIn('campos sensibles', last_msg)


    def test_real_model_general_count(self):
        import os
        if not os.environ.get('MOLE_LLAMA_EXE') or not os.environ.get('MOLE_MODEL_PATH'):
            self.skipTest('Local model paths are not configured')
        label = self.env['assistant.general.query'].with_user(self.alice)._catalog()['product.template']['label']
        self.env['product.template'].create({'name': 'Synthetic Mole product'})
        expected = self.env['product.template'].with_user(self.alice).with_context(active_test=True).search_count([])
        channel = self._ensure(self.alice)
        with patch.dict(os.environ, {'ASSISTANT_LOCAL_BACKEND': 'llama_cpp_cli'}):
            channel.with_user(self.alice).message_post(body='¿Cuántos productos hay?', message_type='comment')
        channel.invalidate_recordset()
        reply = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
        self.assertIn('Registros activos visibles', reply)
        self.assertIn(str(expected), reply)


    def test_real_model_filtered_spanish_count(self):
        import os
        if not os.environ.get('MOLE_LLAMA_EXE') or not os.environ.get('MOLE_MODEL_PATH'):
            self.skipTest('Local model paths are not configured')
        self.env['product.template'].create({'name': 'Mole synthetic filter'})
        channel = self._ensure(self.alice)
        with patch.dict(os.environ, {'ASSISTANT_LOCAL_BACKEND': 'llama_cpp_cli'}):
            channel.with_user(self.alice).message_post(body='¿Cuántos productos con nombre "Mole synthetic filter" hay?', message_type='comment')
        channel.invalidate_recordset()
        reply = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
        self.assertIn('Registros activos visibles', reply)
        self.assertIn(': 1.', reply)

    def test_real_model_varied_natural_counts(self):
        import os
        if not os.environ.get('MOLE_LLAMA_EXE') or not os.environ.get('MOLE_MODEL_PATH'):
            self.skipTest('Local model paths are not configured')
        channel = self._ensure(self.alice)
        cases = [('¿Cuál es el número de contactos?', 'res.partner'),
                 ('Cuenta los productos', 'product.template')]
        with patch.dict(os.environ, {'ASSISTANT_LOCAL_BACKEND': 'llama_cpp_cli'}):
            for question, model in cases:
                with self.subTest(question=question):
                    expected = self.env[model].with_user(self.alice).with_context(active_test=True).search_count([])
                    channel.with_user(self.alice).message_post(body=question, message_type='comment')
                    channel.invalidate_recordset()
                    answer = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
                    self.assertIn('Registros activos visibles', answer)
                    self.assertIn(': %s.' % expected, answer)

    def test_real_model_catalog_adversarial_questions_fail_closed(self):
        import os
        if not os.environ.get('MOLE_LLAMA_EXE') or not os.environ.get('MOLE_MODEL_PATH'):
            self.skipTest('Local model paths are not configured')
        channel = self._ensure(self.alice)
        questions = ('¿Cuántos productos vendidos hay?',
                     '¿Cuántos contactos de México hay?',
                     '¿Cuántas contraseñas tienen los usuarios?')
        with patch.dict(os.environ, {'ASSISTANT_LOCAL_BACKEND': 'llama_cpp_cli'}):
            for question in questions:
                with self.subTest(question=question):
                    channel.with_user(self.alice).message_post(body=question, message_type='comment')
                    channel.invalidate_recordset()
                    answer = channel.message_ids.sorted(key=lambda item: item.id)[-1].body
                    self.assertNotIn('Registros activos visibles', answer)
