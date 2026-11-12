"""Build a compact metadata index of an Odoo installation's source tree.

This is the bounded alternative to loading every addon into the local model.
It walks manifests and Python classes with ``ast`` (no imports, no execution)
and records module/model/field metadata plus a source location. The assistant
can then retrieve just the models relevant to a question.

Usage:
    python tools/index_odoo_structure.py
    python tools/index_odoo_structure.py --odoo C:\\Users\\me\\odoo --query "stock move"
"""

import argparse
import ast
import configparser
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_INDEX_HELPER = ROOT / "assistant_local" / "odoo_index.py"
_spec = importlib.util.spec_from_file_location("assistant_odoo_index", _INDEX_HELPER)
odoo_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(odoo_index)

RELDIR_SKIP = {"__pycache__", "tests", "test", "migrations", "static", "doc", "docs"}
MAX_FILE_BYTES = 2_000_000


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


def _manifest_data(path):
    try:
        return _literal(ast.parse(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return {}


def _addons_paths(odoo_root, override):
    if override:
        return [Path(item).expanduser() for item in override.split(",") if item.strip()]
    config = configparser.ConfigParser()
    if config.read(odoo_root / "odoo.conf") and config.has_option("options", "addons_path"):
        paths = config["options"]["addons_path"]
        return [Path(item).expanduser() for item in paths.split(",") if item.strip()]
    return [odoo_root / "odoo" / "addons", odoo_root / "extra-addons"]


def _class_models(class_node):
    name = None
    inherits = []
    description = None
    for statement in class_node.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id == "_name":
            value = _literal(statement.value)
            if isinstance(value, str):
                name = value
        elif target.id == "_inherit":
            value = _literal(statement.value)
            if isinstance(value, str):
                inherits = [value]
            elif isinstance(value, (list, tuple)):
                inherits = [item for item in value if isinstance(item, str)]
        elif target.id == "_description":
            value = _literal(statement.value)
            if isinstance(value, str):
                description = value
    models = [name] if name else inherits
    return [model for model in models if isinstance(model, str)], inherits, description


def _class_fields(class_node):
    fields = {}
    for statement in class_node.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        call = statement.value
        if not isinstance(target, ast.Name) or not isinstance(call, ast.Call):
            continue
        function = call.func
        if not (isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "fields"):
            continue
        info = {"type": function.attr}
        if function.attr in ("Many2one", "One2many", "Many2many") and call.args:
            comodel = _literal(call.args[0])
            if isinstance(comodel, str):
                info["comodel"] = comodel
        for keyword in call.keywords:
            value = _literal(keyword.value)
            if keyword.arg == "comodel_name" and isinstance(value, str):
                info["comodel"] = value
            elif keyword.arg == "required" and isinstance(value, bool):
                info["required"] = value
        fields[target.id] = info
    return fields


def _parse_python(path, addon_dir, module, models):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return
    relative = path.relative_to(addon_dir.parent).as_posix()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        model_names, inherits, description = _class_models(node)
        if not model_names:
            continue
        fields = _class_fields(node)
        if not fields and not description:
            continue
        for model in model_names:
            models.append({
                "module": module,
                "model": model,
                "class": node.name,
                "description": description,
                "inherits": inherits,
                "file": relative,
                "line": node.lineno,
                "fields": fields,
            })


def build(odoo_root, out_dir, addons_path=None):
    odoo_root = Path(odoo_root).expanduser().resolve()
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    modules = []
    models = []
    addon_dirs = []
    for base in _addons_paths(odoo_root, addons_path):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and (
                (child / "__manifest__.py").is_file()
                or (child / "__openerp__.py").is_file()
            ):
                addon_dirs.append(child)

    for addon_dir in addon_dirs:
        manifest_path = addon_dir / "__manifest__.py"
        if not manifest_path.is_file():
            manifest_path = addon_dir / "__openerp__.py"
        manifest = _manifest_data(manifest_path) if manifest_path.is_file() else {}
        module = addon_dir.name
        modules.append({
            "module": module,
            "label": manifest.get("name") if isinstance(manifest, dict) else None,
            "version": manifest.get("version") if isinstance(manifest, dict) else None,
            "depends": manifest.get("depends") if isinstance(manifest, dict) else None,
            "path": str(addon_dir),
        })
        for path in sorted(addon_dir.rglob("*.py")):
            if RELDIR_SKIP & set(path.relative_to(addon_dir).parts):
                continue
            _parse_python(path, addon_dir, module, models)

    with (out_dir / "modules.jsonl").open("w", encoding="utf-8") as handle:
        for entry in modules:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with (out_dir / "models.jsonl").open("w", encoding="utf-8") as handle:
        for entry in models:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "odoo_root": str(odoo_root),
        "modules": len(modules),
        "classes": len(models),
        "models": len({entry["model"] for entry in models}),
    }
    (out_dir / "index.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odoo", default=r"C:\Users\truji\odoo\odoo-testing-local")
    parser.add_argument("--out", default=str(ROOT / ".runtime" / "odoo-index"))
    parser.add_argument("--addons-path", default=None)
    parser.add_argument("--query", default=None)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args(argv)

    summary = build(args.odoo, args.out, args.addons_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.query:
        matches = odoo_index.search(
            args.query, Path(args.out) / "models.jsonl", limit=args.limit
        )
        print(json.dumps(matches, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
