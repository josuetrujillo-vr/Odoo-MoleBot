"""Server-owned, deliberately limited policy for generic read queries."""
from odoo import api, models
from odoo.exceptions import AccessError

from ..general_query import validate_plan
from ..mole_local import supported_plans

# These are business records, not a per-question dispatch table. Extend after
# assessing the model's privacy and record rules.
ALLOWED_MODELS = frozenset({
    'res.partner',
    'product.template',
    'product.product',
    'sale.order',
    'purchase.order',
    'stock.picking',
    'stock.quant',
    'project.task',
    'project.project',
    'crm.lead',
    'account.move',
    'hr.employee',
    'hr.leave',
    'hr.department',
    'calendar.event',
    'maintenance.request',
})
MODEL_ALIASES = {
    'res.partner': ['contacto', 'contactos', 'cliente', 'clientes', 'proveedor', 'proveedores', 'partner', 'partners'],
    'product.template': ['producto', 'productos', 'artículo', 'artículos', 'articulo', 'articulos'],
    'product.product': ['variante', 'variantes', 'variante de producto', 'variantes de producto'],
    'sale.order': ['pedido de venta', 'pedidos de venta', 'orden de venta', 'ordenes de venta', 'venta', 'ventas', 'cotización', 'cotizaciones', 'cotizacion'],
    'purchase.order': ['pedido de compra', 'pedidos de compra', 'orden de compra', 'ordenes de compra', 'compra', 'compras'],
    'stock.picking': ['transferencia', 'transferencias', 'albarán', 'albaranes', 'albaran', 'envío', 'envíos', 'envio', 'envios', 'entrega', 'entregas'],
    'stock.quant': ['inventario', 'existencia', 'existencias', 'stock', 'quants'],
    'project.task': ['tarea', 'tareas', 'actividad', 'actividades'],
    'project.project': ['proyecto', 'proyectos'],
    'crm.lead': ['oportunidad', 'oportunidades', 'iniciativa', 'iniciativas', 'lead', 'leads', 'prospecto', 'prospectos'],
    'account.move': ['factura', 'facturas', 'asiento', 'asientos', 'factura de cliente', 'facturas de cliente', 'factura de proveedor', 'facturas de proveedor'],
    'hr.employee': ['empleado', 'empleados', 'colaborador', 'colaboradores', 'trabajador', 'trabajadores'],
    'hr.leave': ['ausencia', 'ausencias', 'permiso', 'permisos', 'vacaciones solicitadas'],
    'hr.department': ['departamento', 'departamentos', 'área', 'áreas', 'area', 'areas'],
    'calendar.event': ['evento', 'eventos', 'reunión', 'reuniones', 'reunion', 'cita', 'citas'],
    'maintenance.request': ['mantenimiento', 'solicitud de mantenimiento', 'petición de mantenimiento'],
}
SENSITIVE = ('password', 'secret', 'token', 'bank', 'email', 'phone', 'mobile', 'vat', 'credit', 'salary', 'private', 'barcode', 'ssn', 'identification')


class AssistantGeneralQuery(models.AbstractModel):
    _name = 'assistant.general.query'
    _description = 'Restricted General Read Queries'

    @api.model
    def _safe_env_model(self, name):
        # Replace the caller context, keeping only validated companies and locale.
        companies = self.env.companies.ids
        return self.env[name].with_context({}, allowed_company_ids=companies, active_test=True,
                                           lang=self.env.user.lang or 'en_US')

    @api.model
    def _catalog(self, include_denied=False):
        catalog = {}
        for name in sorted(ALLOWED_MODELS):
            if name not in self.env.registry:
                continue
            model = self._safe_env_model(name)
            try:
                model.check_access('read')
            except AccessError:
                if include_denied:
                    catalog[name] = {'label': model._description or name, 'aliases': MODEL_ALIASES.get(name, []), 'fields': {'name': {'type': 'char'}}, 'denied': True}
                continue
            visible = model.fields_get(attributes=['string', 'type', 'selection'])
            fields = {}
            for field_name, info in visible.items():
                field = model._fields[field_name]
                if (field_name.startswith('_') or any(s in field_name.lower() for s in SENSITIVE)
                        or field.compute or not field.store or info.get('type') not in ('char', 'selection')):
                    continue
                definition = {'type': info['type'], 'label': info.get('string', field_name)}
                if info['type'] == 'selection':
                    definition['values'] = [value for value, _label in info.get('selection', []) if isinstance(value, str)]
                fields[field_name] = definition
            # Registry descriptions are metadata; reading ir.model requires extra ACLs.
            catalog[name] = {'label': model._description or name, 'aliases': MODEL_ALIASES.get(name, []), 'fields': fields}
        return catalog

    @api.model
    def _count(self, plan, question):
        requested = plan.get('model') if isinstance(plan, dict) else None
        if not isinstance(requested, str):
            raise ValueError('Invalid model')
        policy = self._catalog(include_denied=True)
        if requested in policy and policy[requested].get('denied'):
            raise AccessError('Read access denied')
        catalog = self._catalog()
        field_catalog = {name: item['fields'] for name, item in catalog.items()}
        domain = validate_plan(plan, field_catalog, question)
        candidates = supported_plans(question, catalog)
        if len(candidates) != 1 or candidates[0] != plan:
            raise ValueError("Question is ambiguous or does not match the plan")
        model = self._safe_env_model(plan['model'])
        model.check_access('read')
        count = model.search_count(domain)
        return {'operation': 'count', 'count': count, 'label': catalog[plan['model']]['label'],
                'companies': self.env.companies.mapped('name'), 'active': 'active' in model._fields, 'filters': plan['filters']}

    @api.model
    def _list(self, plan, question):
        requested = plan.get('model') if isinstance(plan, dict) else None
        if not isinstance(requested, str):
            raise ValueError('Invalid model')
        policy = self._catalog(include_denied=True)
        if requested in policy and policy[requested].get('denied'):
            raise AccessError('Read access denied')
        catalog = self._catalog()
        field_catalog = {name: item['fields'] for name, item in catalog.items()}
        domain = validate_plan(plan, field_catalog, question)
        candidates = supported_plans(question, catalog)
        if len(candidates) != 1 or candidates[0] != plan:
            raise ValueError("Question is ambiguous or does not match the plan")
        model = self._safe_env_model(plan['model'])
        model.check_access('read')
        limit = min(plan.get('limit') or 5, 20)
        read_fields = ['display_name'] if 'display_name' in model._fields else ['name']
        records = model.search_read(domain, fields=read_fields, limit=limit)
        total_count = model.search_count(domain)
        return {
            'operation': 'list',
            'records': records,
            'count': len(records),
            'total_count': total_count,
            'label': catalog[plan['model']]['label'],
            'companies': self.env.companies.mapped('name'),
            'active': 'active' in model._fields,
            'filters': plan['filters'],
        }

    @api.model
    def _read(self, plan, question):
        requested = plan.get('model') if isinstance(plan, dict) else None
        if not isinstance(requested, str):
            raise ValueError('Invalid model')
        policy = self._catalog(include_denied=True)
        if requested in policy and policy[requested].get('denied'):
            raise AccessError('Read access denied')
        catalog = self._catalog()
        field_catalog = {name: item['fields'] for name, item in catalog.items()}
        domain = validate_plan(plan, field_catalog, question)
        candidates = supported_plans(question, catalog)
        if len(candidates) != 1 or candidates[0] != plan:
            raise ValueError("Question is ambiguous or does not match the plan")
        model = self._safe_env_model(plan['model'])
        model.check_access('read')
        safe_fields = [f for f in catalog[requested]['fields'].keys() if f in model._fields][:6]
        if 'display_name' in model._fields and 'display_name' not in safe_fields:
            safe_fields.insert(0, 'display_name')
        records = model.search_read(domain, fields=safe_fields, limit=1)
        record = records[0] if records else None
        return {
            'operation': 'read',
            'record': record,
            'fields_info': {f: catalog[requested]['fields'].get(f, {}).get('label', f) for f in safe_fields},
            'label': catalog[plan['model']]['label'],
            'companies': self.env.companies.mapped('name'),
            'active': 'active' in model._fields,
            'filters': plan['filters'],
        }

    @api.model
    def _execute(self, plan, question):
        op = plan.get('operation') if isinstance(plan, dict) else None
        if op == 'count':
            return self._count(plan, question)
        elif op == 'list':
            return self._list(plan, question)
        elif op == 'read':
            return self._read(plan, question)
        raise ValueError('Unsupported operation')
