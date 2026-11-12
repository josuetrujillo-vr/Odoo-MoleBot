import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'assistant_local' / 'stock_nl.py'
spec = importlib.util.spec_from_file_location('stock_nl', path)
stock_nl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stock_nl)


class StockParsingTests(unittest.TestCase):
    def test_english_quantity_questions(self):
        cases = {
            'How much of Mole Widget is there?': 'Mole Widget',
            'How many units of Mole Widget do we have?': 'Mole Widget',
            'How much Mole Widget do we have in stock?': 'Mole Widget',
            'What is the stock of Mole Widget?': 'Mole Widget',
            'What is the current quantity of Mole Widget?': 'Mole Widget',
            'How much is left of Mole Widget?': 'Mole Widget',
            'Do we have Mole Widget in stock?': 'Mole Widget',
        }
        for question, product in cases.items():
            with self.subTest(question=question):
                intent = stock_nl.parse_stock_intent(question)
                self.assertIsNotNone(intent, question)
                self.assertEqual(intent['intent'], 'quantity')
                self.assertEqual(intent['language'], 'en')
                self.assertEqual(intent['product'], product)

    def test_english_location_questions(self):
        cases = {
            'Where is Mole Widget located?': 'Mole Widget',
            'Where can I find Mole Widget?': 'Mole Widget',
            'In which location is Mole Widget?': 'Mole Widget',
            'What is the location of Mole Widget?': 'Mole Widget',
            'Where is the stock of Mole Widget?': 'Mole Widget',
        }
        for question, product in cases.items():
            with self.subTest(question=question):
                intent = stock_nl.parse_stock_intent(question)
                self.assertIsNotNone(intent, question)
                self.assertEqual(intent['intent'], 'location')
                self.assertEqual(intent['language'], 'en')
                self.assertEqual(intent['product'], product)

    def test_english_transfer_questions(self):
        cases = (
            ('Transfer 5 units of Mole Widget from Location A to Location B',
             'Mole Widget', 'Location A', 'Location B', 5.0),
            ('Move Mole Widget from "Main Stock" to "Input"',
             'Mole Widget', 'Main Stock', 'Input', None),
            ('Transfer "Mole Widget" from "Location A" to "Location B"',
             'Mole Widget', 'Location A', 'Location B', None),
            ('Please transfer 2 boxes of Mole Widget from WH/Stock to WH/Input',
             'Mole Widget', 'WH/Stock', 'WH/Input', 2.0),
        )
        for question, product, origin, destination, quantity in cases:
            with self.subTest(question=question):
                intent = stock_nl.parse_stock_intent(question)
                self.assertIsNotNone(intent, question)
                self.assertEqual(intent['intent'], 'transfer')
                self.assertEqual(intent['language'], 'en')
                self.assertEqual(intent['product'], product)
                self.assertEqual(intent['origin'], origin)
                self.assertEqual(intent['destination'], destination)
                self.assertEqual(intent['quantity'], quantity)

    def test_spanish_questions_still_work(self):
        quantity = stock_nl.parse_stock_intent('¿Cuánto hay de producto "Café Molido"?')
        self.assertIsNotNone(quantity)
        self.assertEqual(quantity['intent'], 'quantity')
        self.assertEqual(quantity['language'], 'es')
        self.assertEqual(quantity['product'], 'Café Molido')

        location = stock_nl.parse_stock_intent('¿Dónde está el producto Café Molido?')
        self.assertIsNotNone(location)
        self.assertEqual(location['intent'], 'location')
        self.assertEqual(location['product'], 'Café Molido')

        transfer = stock_nl.parse_stock_intent(
            'Transfiere 3 unidades de Café Molido de la ubicación "Almacén A" a la ubicación "Almacén B"'
        )
        self.assertIsNotNone(transfer)
        self.assertEqual(transfer['intent'], 'transfer')
        self.assertEqual(transfer['language'], 'es')
        self.assertEqual(transfer['product'], 'Café Molido')
        self.assertEqual(transfer['origin'], 'Almacén A')
        self.assertEqual(transfer['destination'], 'Almacén B')
        self.assertEqual(transfer['quantity'], 3.0)

    def test_generic_counts_are_not_claimed_as_stock_questions(self):
        for question in (
            'How many products are there?',
            'How many contacts do we have?',
            'How many sale orders exist?',
            '¿Cuántos productos hay?',
            '¿Cuántos contactos existen?',
        ):
            with self.subTest(question=question):
                self.assertIsNone(stock_nl.parse_stock_intent(question))

    def test_time_off_questions_are_not_claimed_as_stock(self):
        for question in (
            'How many vacation days do I have left?',
            'What is my time off balance?',
            'How many holidays are available?',
            '¿Cuántos días de vacaciones me quedan?',
            '¿Cuántas vacaciones tengo disponibles?',
        ):
            with self.subTest(question=question):
                self.assertIsNone(stock_nl.parse_stock_intent(question))

    def test_quoted_and_explicit_stock_flags(self):
        quoted = stock_nl.parse_stock_intent('How much of "Mole Widget" is there?')
        self.assertTrue(quoted['product_quoted'])
        self.assertFalse(quoted['explicit_stock'])

        explicit = stock_nl.parse_stock_intent('How much of Mole Widget is in stock?')
        self.assertFalse(explicit['product_quoted'])
        self.assertTrue(explicit['explicit_stock'])

        plain = stock_nl.parse_stock_intent('How much of Mole Widget is there?')
        self.assertFalse(plain['product_quoted'])
        self.assertFalse(plain['explicit_stock'])

    def test_confirmation_and_cancellation(self):
        for text in ('confirm', 'Yes', 'ok', 'proceed', 'hazlo', 'sí', 'adelante', 'confirm please'):
            with self.subTest(text=text):
                self.assertEqual(stock_nl.parse_transfer_reply(text), 'confirm')
        for text in ('cancel', 'no', 'discard', 'cancelar', 'no gracias'):
            with self.subTest(text=text):
                self.assertEqual(stock_nl.parse_transfer_reply(text), 'cancel')
        for text in ('confirm the transfer of Mole Widget', 'yes but from A', 'hola'):
            with self.subTest(text=text):
                self.assertIsNone(stock_nl.parse_transfer_reply(text))

    def test_language_detection(self):
        self.assertEqual(stock_nl.detect_language('How many products are there?'), 'en')
        self.assertEqual(stock_nl.detect_language('Where is Mole Widget?'), 'en')
        self.assertEqual(stock_nl.detect_language('¿Cuántos productos hay?'), 'es')
        self.assertEqual(stock_nl.detect_language('Transfiere el producto X'), 'es')


if __name__ == '__main__':
    unittest.main()
