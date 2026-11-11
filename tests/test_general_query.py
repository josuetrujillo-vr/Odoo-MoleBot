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

    def test_count_result_includes_facts_criteria_and_companies(self):
        result = {'operation': 'count', 'count': 7, 'label': 'Product', 'companies': ['ACME'],
                  'active': True, 'filters': []}
        text = query.format_result(result)
        self.assertIn('Registros activos visibles de Product: 7', text)
        self.assertIn('Criterios: sin filtros adicionales', text)
        self.assertIn('ACME', text)

    def test_count_result_with_literal_filter(self):
        result = {'operation': 'count', 'count': 0, 'label': 'Sale', 'companies': ['ACME'],
                  'active': False, 'filters': [{'field': 'name', 'op': 'equals', 'value': 'ACME'}]}
        self.assertIn('Criterios: nombre igual a "ACME"', query.format_result(result))

    def test_list_result_lists_records(self):
        result = {'operation': 'list', 'records': [{'id': 1, 'name': 'ACME'}], 'total_count': 1,
                  'label': 'Contact', 'companies': ['ACME'], 'active': True, 'filters': []}
        text = query.format_result(result)
        self.assertIn('Registros visibles de Contact (mostrando 1 de 1):', text)
        self.assertIn('• ACME', text)

    def test_empty_list_and_read_results_are_reported(self):
        empty_list = query.format_result({'operation': 'list', 'records': [], 'label': 'Contact',
                                         'companies': ['ACME'], 'active': True, 'filters': []})
        self.assertIn('No se encontraron', empty_list)
        empty_read = query.format_result({'operation': 'read', 'record': None, 'label': 'Contact',
                                         'companies': ['ACME'], 'active': True, 'filters': []})
        self.assertIn('No se encontró', empty_read)

    def test_invalid_format_results_are_rejected(self):
        self.assertIsNone(query.format_result({'operation': 'write'}))
        self.assertIsNone(query.format_result(None))

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
