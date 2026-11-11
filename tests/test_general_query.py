import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'assistant_local' / 'general_query.py'
spec = importlib.util.spec_from_file_location('general_query', path)
query = importlib.util.module_from_spec(spec)
spec.loader.exec_module(query)

class GeneralPlanTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {'sale.order': {'state': {'type': 'selection', 'values': ['draft', 'sale']}, 'name': {'type': 'char'}}, 'product.template': {'name': {'type': 'char'}}}

    def test_count_for_two_models(self):
        for model in self.catalog:
            plan = {'operation': 'count', 'model': model, 'filters': []}
            self.assertEqual(query.validate_plan(plan, self.catalog, '¿Cuántos registros hay?'), [])

    def test_literal_must_occur_as_complete_text_in_question(self):
        plan = {'operation': 'count', 'model': 'sale.order', 'filters': [{'field': 'name', 'op': 'equals', 'value': 'ACME'}]}
        self.assertEqual(query.validate_plan(plan, self.catalog, '¿Cuántos llamados ACME?'), [('name', '=', 'ACME')])
        for text in ('¿Cuántos llamados XACME?', '¿Cuántos pedidos?'):
            with self.assertRaises(ValueError): query.validate_plan(plan, self.catalog, text)

    def test_rejects_private_injection_extra_keys_and_unsupported_values(self):
        bad = [
            {'operation': 'write', 'model': 'sale.order', 'filters': []},
            {'operation': 'count', 'model': 'res.users', 'filters': []},
            {'operation': 'count', 'model': 'sale.order', 'filters': [], 'context': {'active_test': False}},
            {'operation': 'count', 'model': 'sale.order', 'filters': [{'field': '__class__', 'op': 'equals', 'value': 'x'}]},
            {'operation': 'count', 'model': 'sale.order', 'filters': [{'field': 'name', 'op': 'ilike', 'value': 'x'}]},
            {'operation': 'count', 'model': 'sale.order', 'filters': [{'field': 'state', 'op': 'equals', 'value': 'inventado'}]},
        ]
        for plan in bad:
            with self.subTest(plan=plan), self.assertRaises(ValueError): query.validate_plan(plan, self.catalog, 'x inventado')


    def test_untrusted_plan_and_literal_shapes(self):
        invalid = [
            {'operation': 'count', 'model': [], 'filters': []},
            {'operation': 'count', 'model': 'sale.order', 'filters': [{'field': 'name', 'op': 'equals', 'value': {'literal': 'x'}}]},
            {'operation': 'count', 'model': 'sale.order', 'filters': [{'field': 'name', 'op': 'equals', 'value': 'x', 'context': {'active_test': False}}]},
        ]
        for plan in invalid:
            with self.subTest(plan=plan), self.assertRaises(ValueError): query.validate_plan(plan, self.catalog, 'x')

    def test_list_and_read_operations_allowed(self):
        plan_list = {'operation': 'list', 'model': 'sale.order', 'filters': [], 'limit': 10}
        self.assertEqual(query.validate_plan(plan_list, self.catalog, '¿Cuáles pedidos?'), [])
        plan_read = {'operation': 'read', 'model': 'sale.order', 'filters': [{'field': 'name', 'op': 'equals', 'value': 'ACME'}]}
        self.assertEqual(query.validate_plan(plan_read, self.catalog, 'Detalles de ACME'), [('name', '=', 'ACME')])

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            query.validate_plan({'operation': 'list', 'model': 'sale.order', 'filters': [], 'limit': -5}, self.catalog, 'pedidos')
        with self.assertRaises(ValueError):
            query.validate_plan({'operation': 'list', 'model': 'sale.order', 'filters': [], 'limit': 'diez'}, self.catalog, 'pedidos')



if __name__ == '__main__': unittest.main()
