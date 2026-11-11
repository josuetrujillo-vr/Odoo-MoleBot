from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user


class TestGeneralQuery(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='general_query_user', groups='base.group_user', context={'no_reset_password': True})

    def test_catalog_and_count_respect_access_and_active(self):
        engine = self.env['assistant.general.query'].with_user(self.user)
        catalog = engine._catalog()
        self.assertIn('res.partner', catalog)
        self.assertIn('product.template', catalog)
        self.assertNotIn('res.users', catalog)
        self.assertNotIn('password', catalog['res.partner']['fields'])
        self.env['res.partner'].create({'name': 'Synthetic active', 'active': True})
        self.env['res.partner'].create({'name': 'Synthetic archived', 'active': False})
        result = engine._count({'operation': 'count', 'model': 'res.partner', 'filters': []}, 'cuantos %s hay' % catalog['res.partner']['label'])
        expected = self.env['res.partner'].with_user(self.user).with_context(active_test=True).search_count([])
        self.assertEqual(result['count'], expected)
        self.assertEqual(result['count'], self.env['res.partner'].with_user(self.user).with_context(active_test=True).search_count([]))

    def test_forged_context_and_unsafe_plan_fail(self):
        engine = self.env['assistant.general.query'].with_user(self.user)
        with self.assertRaises(ValueError):
            engine._count({'operation': 'count', 'model': 'res.users', 'filters': []}, 'cuantos usuarios')
        with self.assertRaises(ValueError):
            engine._count({'operation': 'count', 'model': 'res.partner', 'filters': [], 'context': {'active_test': False}}, 'cuantos contactos')


    def test_record_rule_and_company_restrictions_apply(self):
        company = self.env['res.company'].create({'name': 'Synthetic Other Company'})
        visible = self.env['res.partner'].create({'name': 'Synthetic visible', 'company_id': self.env.company.id})
        shared = self.env['res.partner'].create({'name': 'Synthetic shared', 'company_id': False})
        hidden = self.env['res.partner'].create({'name': 'Synthetic hidden', 'company_id': company.id})
        self.env['ir.rule'].create({
            'name': 'Synthetic company restriction for general counts',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'domain_force': "['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]",
        })
        partners = self.env['res.partner'].with_user(self.user).with_context(allowed_company_ids=[self.env.company.id], active_test=True)
        self.assertIn(visible, partners.search([('id', '=', visible.id)]))
        self.assertIn(shared, partners.search([('id', '=', shared.id)]))
        self.assertFalse(partners.search([('id', '=', hidden.id)]))
        engine = self.env['assistant.general.query'].with_user(self.user).with_context(allowed_company_ids=[self.env.company.id])
        label = engine._catalog()['res.partner']['label']
        result = engine._count({'operation': 'count', 'model': 'res.partner', 'filters': []}, 'cuantos %s hay' % label)
        self.assertEqual(result['count'], partners.search_count([]))

    def test_omitted_filters_and_injected_model_choice_are_rejected(self):
        engine = self.env['assistant.general.query'].with_user(self.user)
        catalog = engine._catalog()
        label = catalog['res.partner']['label']
        plan = {'operation': 'count', 'model': 'res.partner', 'filters': []}
        with self.assertRaises(ValueError):
            engine._count(plan, 'cuantos %s vendidos hay' % label)
        other = {'operation': 'count', 'model': 'product.template', 'filters': []}
        with self.assertRaises(ValueError):
            engine._count(other, 'cuantos %s hay' % label)

    def test_zero_vs_denied_and_simple_literal_filter(self):
        engine = self.env['assistant.general.query'].with_user(self.user)
        plan = {'operation': 'count', 'model': 'product.template', 'filters': [{'field': 'name', 'op': 'equals', 'value': 'Mole synthetic absent'}]}
        question = '¿Cuántos productos con nombre "Mole synthetic absent" hay?'
        self.assertEqual(engine._count(plan, question)['count'], 0)
        self.env['product.template'].create({'name': 'Mole synthetic absent'})
        self.assertEqual(engine._count(plan, question)['count'], 1)
        outsider = new_test_user(self.env, login='general_portal', groups='base.group_portal', context={'no_reset_password': True})
        denied = self.env['assistant.general.query'].with_user(outsider)
        policy = denied._catalog(include_denied=True)
        self.assertTrue(policy['product.template']['denied'])
        from odoo.addons.assistant_local.mole_local import supported_plans
        self.assertEqual(supported_plans(question, policy), [plan])
        with self.assertRaises(AccessError):
            denied._count(plan, question)


    def test_unhashable_model_and_malformed_http_reply(self):
        import os
        from unittest.mock import patch
        engine = self.env['assistant.general.query'].with_user(self.user)
        for bad in ([], {}, None):
            with self.assertRaises(ValueError):
                engine._count({'operation': 'count', 'model': bad, 'filters': []}, 'cuantos contactos hay')
        provider = self.env['assistant.inference'].with_user(self.user)
        with patch.dict(os.environ, {'ASSISTANT_LOCAL_BACKEND': 'http', 'ASSISTANT_LOCAL_URL': 'http://127.0.0.1:11434', 'ASSISTANT_LOCAL_MODEL': 'synthetic'}):
            for reply in (None, [], {}, {'tool_calls': None}, {'tool_calls': [{}]}, {'tool_calls': [{'function': None}]}, {'tool_calls': [{'function': {'name': 'general_count', 'arguments': []}}]}):
                with self.subTest(reply=reply), patch('odoo.addons.assistant_local.models.inference.chat', return_value=reply):
                    self.assertIsNone(provider._general_plan('cuantos contactos', {}))

    def test_list_and_read_respect_access_and_records(self):
        engine = self.env['assistant.general.query'].with_user(self.user)
        partner = self.env['res.partner'].create({'name': 'Mole Test Partner Specific'})
        plan_list = {'operation': 'list', 'model': 'res.partner', 'filters': []}
        res_list = engine._execute(plan_list, '¿Cuáles son los contactos?')
        self.assertEqual(res_list['operation'], 'list')
        self.assertGreaterEqual(res_list['total_count'], 1)
        self.assertTrue(any(r.get('id') == partner.id for r in res_list['records']))

        plan_read = {'operation': 'read', 'model': 'res.partner', 'filters': [{'field': 'name', 'op': 'equals', 'value': 'Mole Test Partner Specific'}]}
        res_read = engine._execute(plan_read, 'Información del contacto "Mole Test Partner Specific"')
        self.assertEqual(res_read['operation'], 'read')
        self.assertIsNotNone(res_read['record'])
        self.assertEqual(res_read['record']['id'], partner.id)
