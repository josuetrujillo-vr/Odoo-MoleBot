import importlib.util
import tempfile
import unittest
from pathlib import Path

from tools.index_odoo_structure import build

_HELPER = Path(__file__).resolve().parents[1] / "assistant_local" / "odoo_index.py"
_spec = importlib.util.spec_from_file_location("assistant_odoo_index", _HELPER)
odoo_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(odoo_index)


class OdooIndexTests(unittest.TestCase):
    def test_build_and_search_minimal_addon(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            addons = root / "addons"
            addon = addons / "test_addon"
            (addon / "models").mkdir(parents=True)
            (addon / "__manifest__.py").write_text(
                "{'name': 'Test Addon', 'version': '18.0.1.0.0', 'depends': ['base']}",
                encoding="utf-8",
            )
            (addon / "models" / "thing.py").write_text(
                "from odoo import fields, models\n\n"
                "class StockThing(models.Model):\n"
                "    _name = 'x.stock.thing'\n"
                "    _description = 'Stock Thing'\n"
                "    product_id = fields.Many2one('product.product', required=True)\n"
                "    quantity = fields.Float()\n",
                encoding="utf-8",
            )
            out = root / "index"
            summary = build(root, out, addons_path=str(addons))
            self.assertEqual(summary["modules"], 1)
            self.assertEqual(summary["models"], 1)

            matches = odoo_index.search("stock thing", out / "models.jsonl")
            self.assertEqual(len(matches), 1)
            entry = matches[0]
            self.assertEqual(entry["model"], "x.stock.thing")
            self.assertEqual(entry["fields"]["product_id"]["comodel"], "product.product")
            self.assertIn("test_addon/models/thing.py", entry["file"])

            description = odoo_index.describe(entry)
            self.assertIn("x.stock.thing", description)
            self.assertIn("Many2one -> product.product", description)

    def test_missing_index_is_empty_and_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.jsonl"
            self.assertEqual(odoo_index.load(missing), [])
            self.assertEqual(odoo_index.search("stock", missing), [])
            self.assertEqual(odoo_index.search("", missing), [])

    def test_index_ignores_directories_without_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            addons = root / "addons"
            (addons / "not_an_addon" / "models").mkdir(parents=True)
            (addons / "not_an_addon" / "models" / "x.py").write_text(
                "class X:\n    pass\n", encoding="utf-8"
            )
            summary = build(root, root / "index", addons_path=str(addons))
            self.assertEqual(summary["modules"], 0)
            self.assertEqual(summary["classes"], 0)


if __name__ == "__main__":
    unittest.main()
