# Informe final: MVP local de Mole con consultas generales

Fecha: 2026-11-11.
Estado: MVP local funcional consolidado; pruebas locales sin fallos. No está desplegado.

## Alcance del avance final

- El chat responde consultas generales (conteos, listas, lectura por nombre entre comillas) cuando el modelo local propone un plan estructurado sobre un catálogo restringido por ACLs.
- El servidor valida el plan contra la forma reconocida de la pregunta y compila el resultado con el ORM; las cifras salen de Odoo.
- Si el modelo no propone, no expresa el criterio o falla, el chat publica el fallback seguro sin inventar datos.
- Formateo centralizado en `assistant_local/general_query.py::format_result`, reutilizado por Discuss y el chat de conversaciones.

## Evidencia local

- Python standalone: `python -m unittest discover -s tests -v` → **45 pruebas, OK**.
- Odoo core `assistant_local` (chat, inferencia, seguridad, general) en base aislada local `assistant_test_02da25e2fcf0`, filtro anclado, SMTP/cron deshabilitados → **42 pruebas, 0 fallos, 0 errores**.
- Odoo `assistant_local_hr_holidays` + `assistant_local_mole` con **backend local real** (llama-completion.exe + Qwen2.5 GGUF, solo local) en base aislada local `assistant_test_70b48f7855b7` → **44 pruebas, 0 fallos, 0 errores**, incluidas las adversariales de fallo cerrado.

## Límites honestos

- El MVP no certifica comprensión universal; los criterios no representados producen abstención.
- El navegador no se re-ejecutó en esta ronda (sin selenium/chromedriver en el entorno); la validación previa en Chrome headless local quedó registrada en `odoo-test-browser4.log`.
- No se evaluó rendimiento ni se desplegó; no hay afirmación de capacidad general terminada sin revisión.

## Commits de esta sesión

- `4c62ba4` Add restricted general read query plan selection.
- `0762243` Answer general read queries from the assistant chat through validated plans.
