"""Load and search a compact index of an Odoo source tree.

The index is produced by ``tools/index_odoo_structure.py``. It intentionally
contains metadata only (module, model, field names/types, file and line), not
entire source files, so it can be used as retrieval context without dumping
hundreds of addons into a small local model.
"""

import json
import os
import re
from pathlib import Path


DEFAULT_INDEX = (
    Path(__file__).resolve().parents[1] / ".runtime" / "odoo-index" / "models.jsonl"
)
_MAX_LINE_BYTES = 2_000_000


def index_path(path=None):
    return Path(path or os.environ.get("ASSISTANT_ODOO_INDEX") or DEFAULT_INDEX)


def _tokens(text):
    return [token for token in re.split(r"[^a-z0-9_]+", str(text).casefold()) if token]


def load(path=None, limit=200_000):
    """Return index entries, or an empty list when the index is absent."""
    target = index_path(path)
    if not target.is_file():
        return []
    entries = []
    with target.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle):
            if line_no >= limit or len(line) > _MAX_LINE_BYTES:
                break
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                entries.append(entry)
    return entries


def search(query, path=None, limit=12, entries=None):
    """Rank models by name, description, module and field-name matches."""
    tokens = _tokens(query)
    if not tokens:
        return []
    if entries is None:
        entries = load(path)
    ranked = []
    for entry in entries:
        model = str(entry.get("model") or "").casefold()
        module = str(entry.get("module") or "").casefold()
        description = str(entry.get("description") or "").casefold()
        field_names = " ".join((entry.get("fields") or {}).keys()).casefold()
        score = 0
        for token in tokens:
            if token == model:
                score += 20
            elif token in model:
                score += 6
            if token in field_names:
                score += 3
            if token in description:
                score += 2
            if token in module:
                score += 1
        if score:
            ranked.append((score, model, entry))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [entry for _score, _model, entry in ranked[:max(1, limit)]]


def describe(entry, max_fields=30):
    """Render one index entry as a compact, model-readable description."""
    if not isinstance(entry, dict):
        return ""
    fields = entry.get("fields") or {}
    lines = ["%s (%s) from module %s" % (
        entry.get("model"), entry.get("description") or "no description",
        entry.get("module") or "unknown",
    )]
    if entry.get("file"):
        lines.append("Source: %s:%s" % (entry.get("file"), entry.get("line") or "?"))
    for name in sorted(fields)[:max_fields]:
        info = fields[name] or {}
        field_type = info.get("type") or "Field"
        comodel = info.get("comodel")
        lines.append("- %s: %s%s" % (
            name, field_type, " -> %s" % comodel if comodel else "",
        ))
    if len(fields) > max_fields:
        lines.append("- ... %s more fields" % (len(fields) - max_fields))
    return "\n".join(lines)
