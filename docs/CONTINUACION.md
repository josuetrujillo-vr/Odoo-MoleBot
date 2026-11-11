# Continuación de Mole: consultas de lectura

Estado: MVP local consolidado; pruebas locales sin fallos. No está desplegado.

La ronda actual permite al modelo elegir un plan estructurado entre modelos del catálogo; una validación independiente admite únicamente preguntas que puede verificar con seguridad. La interpretación sigue siendo limitada, en especial para criterios y ambigüedades no representables.

La ronda anterior pasó 25 pruebas Odoo y 34 pruebas Python, pero esos resultados no corresponden al último cambio de selección de planes. La ronda actual solo pasó 7 pruebas unitarias de consultas y 13 del intérprete; después del avance final se ejecutaron las suites completas locales descritas en el informe final.

## Avance final (MVP del chat con consultas generales)

- Formateo centralizado en `assistant_local/general_query.py::format_result`, reutilizado por Discuss y el chat de conversaciones.
- El chat de Odoo responde consultas generales cuando el modelo no produjo herramienta ejecutable, mediante plan validado y ejecución server-side; fallback seguro sin datos inventados si no procede.
- Las cifras salen de Odoo bajo el usuario autenticado; ACLs, reglas, compañía y validación de forma de la pregunta se revalidan.

## Pendiente honesto

- Revisión independiente de seguridad, pruebas negativas amplias, rendimiento/límites, proveedor HTTP local y cualquier ampliación de criterios.
- No se desplegó ni se declaró capacidad general terminada sin revisión.

Informe final de la consolidación: [docs/superpowers/plans/2026-11-11-mole-mvp-final-report.md](superpowers/plans/2026-11-11-mole-mvp-final-report.md).
