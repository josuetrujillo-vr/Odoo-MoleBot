import importlib.util
import unittest
from pathlib import Path


module_path = Path(__file__).resolve().parents[1] / "assistant_local" / "tool_validation.py"
spec = importlib.util.spec_from_file_location("tool_validation", module_path)
tool_validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool_validation)


class ToolValidationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"invoice.count": {"date_from": str, "date_to": str}}

    def test_known_tool_and_valid_arguments(self):
        args = {"date_from": "2026-01-01", "date_to": "2026-01-31"}
        self.assertEqual(tool_validation.validate_call(self.catalog, "invoice.count", args), args)

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):
            tool_validation.validate_call(self.catalog, "account.move.write", {})

    def test_missing_or_extra_argument_rejected(self):
        for args in ({"date_from": "2026-01-01"},
                     {"date_from": "2026-01-01", "date_to": "2026-01-31", "user_id": 1}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                tool_validation.validate_call(self.catalog, "invoice.count", args)

    def test_wrong_type_or_non_object_rejected(self):
        for args in (None, [], {"date_from": 1, "date_to": "2026-01-31"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                tool_validation.validate_call(self.catalog, "invoice.count", args)

    def test_boolean_is_not_accepted_as_integer(self):
        with self.assertRaises(ValueError):
            tool_validation.validate_call({"stock.propose": {"quantity": int}},
                                          "stock.propose", {"quantity": True})

    def test_server_owned_value_constraints_are_enforced(self):
        catalog = {"stock.propose": {"quantity": (int, lambda value: 1 <= value <= 100)}}
        self.assertEqual(tool_validation.validate_call(catalog, "stock.propose", {"quantity": 3}),
                         {"quantity": 3})
        for quantity in (-1, 0, 101):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                tool_validation.validate_call(catalog, "stock.propose", {"quantity": quantity})


if __name__ == "__main__":
    unittest.main()
