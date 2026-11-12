"""Validate a small, server-catalogued subset of declarative read plans."""
import re


def format_result(result, language='es'):
    """Render a validated general query result into the chat reply text."""
    if not isinstance(result, dict):
        return None
    operation = result.get('operation')
    if operation not in ('count', 'list', 'read'):
        return None
    english = language == 'en'
    companies = ', '.join(result.get('companies') or [])
    if operation == 'count':
        if english:
            criteria = ('name equals "%s"' % result['filters'][0]['value']
                        if result.get('filters') else 'no additional filters')
            archived = 'active ' if result.get('active') else ''
            return ("Visible %srecords of %s: %s. Active companies in context: %s. "
                    "Criteria: %s; your permissions and rules apply. "
                    "Model rules determine company scope.") % (
                archived, result.get('label'), result.get('count'), companies, criteria)
        criteria = ('nombre igual a "%s"' % result['filters'][0]['value']
                    if result.get('filters') else 'sin filtros adicionales')
        archived = 'activos ' if result.get('active') else ''
        return ("Registros %svisibles de %s: %s. Compañías activas en el contexto: %s. "
                "Criterios: %s; se aplican tus permisos y reglas. "
                "Las reglas del modelo determinan el alcance por compañía.") % (
            archived, result.get('label'), result.get('count'), companies, criteria)
    if operation == 'list':
        records = result.get('records') or []
        if not records:
            if english:
                return "No visible records of %s matched those criteria." % (result.get('label'),)
            return "No se encontraron registros visibles de %s con esos criterios." % (result.get('label'),)
        if english:
            lines = ["Visible records of %s (showing %s of %s):" % (
                result.get('label'), len(records), result.get('total_count'))]
        else:
            lines = ["Registros visibles de %s (mostrando %s de %s):" % (
                result.get('label'), len(records), result.get('total_count'))]
        for record in records:
            name = record.get('display_name') or record.get('name') or ("ID %s" % record.get('id'))
            lines.append("• %s" % name)
        footer = ("\nActive companies: %s. Your permissions and rules apply." % companies
                  if english else
                  "\nCompañías activas: %s. Se aplican tus permisos y reglas." % companies)
        lines.append(footer)
        return "\n".join(lines)
    record = result.get('record') or {}
    if not record:
        if english:
            return "No %s record matched those criteria." % (result.get('label'),)
        return "No se encontró ningún registro de %s con esos criterios." % (result.get('label'),)
    title = record.get('display_name') or record.get('name') or ("ID %s" % record.get('id'))
    lines = [("Information for %s (%s):" if english else "Información de %s (%s):")
             % (result.get('label'), title)]
    fields_info = result.get('fields_info') or {}
    for field, value in record.items():
        if field in ('id', 'display_name') or value is False or value is None or value == '':
            continue
        lines.append("• %s: %s" % (fields_info.get(field, field), value))
    footer = ("\nActive companies: %s. Your permissions and rules apply." % companies
              if english else
              "\nCompañías activas: %s. Se aplican tus permisos y reglas." % companies)
    lines.append(footer)
    return "\n".join(lines)


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
