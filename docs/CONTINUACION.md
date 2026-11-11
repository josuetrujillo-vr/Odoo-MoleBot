# Continuación de Mole: consultas de lectura

Estado: trabajo en progreso, en consolidación del MVP local.

La ronda actual permite al modelo elegir un plan estructurado entre modelos del catálogo; una validación independiente admite únicamente preguntas que puede verificar con seguridad. La interpretación sigue siendo limitada, en especial para criterios y ambigüedades no representables.

La ronda anterior pasó 25 pruebas Odoo y 34 pruebas Python, pero esos resultados no corresponden al último cambio de selección de planes. La ronda actual solo pasó 7 pruebas unitarias de consultas y 13 del intérprete; todavía no se ha probado en Odoo ni con el modelo real, y no ha recibido revisión independiente.

## Avance reciente (MVP del chat con consultas generales)

- Se añadió el formateo de resultados de consultas generales en `assistant_local/general_query.py` (`format_result`) y se reutilizó desde el chat de Odoo y desde el canal Mole de Discuss, eliminando duplicación.
- El chat de Odoo (`assistant.conversation.submit_chat_message` / `_apply_model_reply`) ahora, cuando el modelo no produjo una herramienta ejecutable, intenta responder la última pregunta del usuario con el plan validado (`assistant.general.query`) y publica el resultado; si no procede, emite el mensaje seguro de fallback actualizado.
- Las cifras de las respuestas generales salen de Odoo (`search_count` / `search_read`) bajo el usuario autenticado, con catálogo filtrado por ACL y validación de plan contra la forma reconocida de la pregunta.

## Pendiente

- Ejecutar la suite completa del addon `assistant_local` (chat, inferencia, seguridad, general) y registrar el resultado en el informe.
- Ejecutar pruebas con el modelo local real sobre consultas variadas y adversariales; ejecutar la suite completa; revisar ACL, reglas, compañías, campos y denegaciones. Mantener la abstención cuando no se pueda verificar íntegrammente la intención o el filtro. Revisar también rendimiento, límites y proveedor HTTP local.

Otras áreas pendientes de revisión independiente: seguridad del flujo RPC de inventario y semántica de moneda en consultas contables. No se afirma que estén corregidas o verificadas en este avance.
