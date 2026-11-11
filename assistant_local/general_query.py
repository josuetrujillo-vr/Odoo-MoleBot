"""Validate a small, server-catalogued subset of declarative read plans."""
import re


def validate_plan(plan, catalog, question):
    if not isinstance(plan, dict) or set(plan) not in (
        {'operation', 'model', 'filters'},
        {'operation', 'model', 'filters', 'limit'},
    ):
        raise ValueError('Invalid plan')
    model = plan['model']
    if plan['operation'] not in ('count', 'list', 'read') or not isinstance(model, str) or model not in catalog:
        raise ValueError('Unsupported operation or model')
    filters = plan['filters']
    if not isinstance(filters, list) or len(filters) > 3 or not isinstance(question, str) or len(question) > 4000:
        raise ValueError('Invalid filters or question')
    if 'limit' in plan and (not isinstance(plan['limit'], int) or plan['limit'] < 1 or plan['limit'] > 100):
        raise ValueError('Invalid limit')
    domain = []
    for item in filters:
        if not isinstance(item, dict) or set(item) != {'field', 'op', 'value'}:
            raise ValueError('Invalid filter')
        field, op, value = item['field'], item['op'], item['value']
        if not isinstance(field, str) or field.startswith('_') or field not in catalog[model] or op != 'equals':
            raise ValueError('Unsupported filter')
        definition = catalog[model][field]
        if definition.get('type') not in ('char', 'selection') or not isinstance(value, str) or not value.strip() or len(value) > 100:
            raise ValueError('Invalid value')
        if definition['type'] == 'selection' and value not in definition.get('values', []):
            raise ValueError('Unknown selection')
        if not re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', question, re.IGNORECASE):
            raise ValueError('Value not supported by question')
        domain.append((field, '=', value))
    return domain
