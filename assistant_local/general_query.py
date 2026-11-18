"""Validate a small, server-catalogued subset of declarative read plans."""
import re


def format_result(result, language='es'):
    """Render a validated general query result into a natural, conversational response."""
    if not isinstance(result, dict):
        return None
    operation = result.get('operation')
    if operation not in ('count', 'list', 'read'):
        return None
    english = language == 'en'
    companies = ', '.join(result.get('companies') or [])
    company_context = f" en {companies}" if companies else ""
    company_context_en = f" in {companies}" if companies else ""

    if operation == 'count':
        count = result.get('count', 0)
        label = result.get('label') or ('records' if english else 'registros')
        filters = result.get('filters') or []
        archived = 'active ' if result.get('active') else ''
        archived_es = 'activos ' if result.get('active') else ''

        if english:
            criteria = (f' with name equal to "{filters[0]["value"]}"'
                        if filters else '')
            if count == 0:
                return f"No {archived}{label} records{criteria} were found{company_context_en}."
            elif count == 1:
                return f"There is currently **1** {archived}{label} record{criteria}{company_context_en}."
            else:
                return f"There are currently **{count}** {archived}{label} records{criteria}{company_context_en}."
        else:
            criteria = (f' con nombre igual a "{filters[0]["value"]}"'
                        if filters else '')
            if count == 0:
                return f"No se encontraron registros {archived_es}de **{label}**{criteria}{company_context}."
            elif count == 1:
                return f"Actualmente hay **1** registro {archived_es}de **{label}**{criteria}{company_context}."
            else:
                return f"Actualmente hay **{count}** registros {archived_es}de **{label}**{criteria}{company_context}."

    if operation == 'list':
        records = result.get('records') or []
        label = result.get('label') or ('records' if english else 'registros')
        total = result.get('total_count', len(records))
        if not records:
            if english:
                return f"No {label} records were found{company_context_en}."
            return f"No se encontraron registros de **{label}**{company_context}."
        if english:
            lines = [f"Here are the {label} records (showing {len(records)} of {total}){company_context_en}:"]
        else:
            lines = [f"Aquí tienes los registros de **{label}** (mostrando {len(records)} de {total}){company_context}:"]
        for record in records:
            name = record.get('display_name') or record.get('name') or f"ID {record.get('id')}"
            lines.append(f"• {name}")
        return "\n".join(lines)

    if operation == 'read':
        record = result.get('record') or {}
        label = result.get('label') or ('record' if english else 'registro')
        if not record:
            if english:
                return f"No {label} record matched the specified criteria."
            return f"No se encontró ningún registro de **{label}** con esos criterios."
        title = record.get('display_name') or record.get('name') or f"ID {record.get('id')}"
        lines = [f"Information for {label} ({title}){company_context_en}:" if english
                 else f"Detalle de {label} ({title}){company_context}:"]
        fields_info = result.get('fields_info') or {}
        for field, value in record.items():
            if field in ('id', 'display_name') or value is False or value is None or value == '':
                continue
            lines.append(f"• {fields_info.get(field, field)}: {value}")
        return "\n".join(lines)


def format_vacation_balance(result, language='es'):
    """Render vacation balance results into a natural, conversational response."""
    if not isinstance(result, dict):
        return ("Vacation balance is not available at this moment." if language == 'en'
                else "El saldo de vacaciones no está disponible en este momento.")

    employee = result.get("employee")
    service_years = result.get("service_years")
    entitlement_days = result.get("entitlement_days")
    approved_days = result.get("approved_days") or 0
    available_days = result.get("available_days")
    next_anniversary = result.get("next_anniversary")

    if language == 'en':
        who = f"**{employee}** has" if employee else "You have"
        lines = []
        if available_days is not None:
            if entitlement_days is not None:
                lines.append(f"{who} **{available_days}** vacation days available (out of **{entitlement_days}** entitled days).")
            else:
                lines.append(f"{who} **{available_days}** vacation days available.")
        details = []
        if service_years is not None:
            details.append(f"Seniority: {service_years} year(s)")
        if approved_days:
            details.append(f"Approved / taken days: {approved_days}")
        if next_anniversary:
            details.append(f"Next work anniversary: {next_anniversary}")
        if details:
            lines.append("• " + "\n• ".join(details))
        return "\n\n".join(lines) if lines else "Vacation balance is not available."

    who = f"**{employee}** cuenta con" if employee else "Cuentas con"
    lines = []
    if available_days is not None:
        if entitlement_days is not None:
            lines.append(f"{who} **{available_days}** días de vacaciones disponibles (de un derecho total de **{entitlement_days}** días para el periodo).")
        else:
            lines.append(f"{who} **{available_days}** días de vacaciones disponibles.")
    details = []
    if service_years is not None:
        details.append(f"Antigüedad: {service_years} año(s)")
    if approved_days:
        details.append(f"Días aprobados/tomados: {approved_days}")
    if next_anniversary:
        details.append(f"Próximo aniversario laboral: {next_anniversary}")
    if details:
        lines.append("• " + "\n• ".join(details))
    return "\n\n".join(lines) if lines else "El saldo de vacaciones no está disponible en este momento."


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
