# SDD ledger — plan: docs/superpowers/plans/2026-11-08-mole-continuacion.md

Spec: diseño aprobado 2026-11-07; la petición actual autoriza consulta ajena con permisos efectivos.

| Preflight | Interfaz y revisión |
|---|---|
| Tarea 1 | Consulta ajena y pruebas; comprobación de acceso en servidor, no por el modelo. |
| Tarea 2 | Consultas comerciales: no usar sumas de monedas sin conversión verificable. |
| Tarea 3 | Verificación de resultados y documentación, sin modificar bases existentes. |
| 1 ↔ 2 | Comparten despacho de Mole; implementar secuencialmente y preservar el contrato anterior. |
| 1 ↔ 3 | Pruebas y documentación consumen la capacidad implementada. |
| 2 ↔ 3 | Pruebas y documentación consumen consultas comerciales. |

Ruling: trabajar en la rama aislada existente, que no tiene ningún commit; `.git` no es escribible y no existe HEAD para crear un worktree. Mantener copias de referencia de archivos afectados y no alterar trabajo previo; sin commits. Costo: revisión por comparación de archivos en vez de rangos Git.
Ruling: autorización de consultas ajenas exige permisos efectivos de RR. HH. y reglas de Odoo, no pertenencia genérica al grupo administrador del asistente; evita ampliar acceso a datos personales. Costo: puede requerir configurar permisos de RR. HH. al usuario.
Ruling: el addon de stock existente expone propuestas modificables por RPC y admite ubicaciones no internas. No se habilitará desde Mole hasta corregir y verificar permisos, confirmación y concurrencia; prioridad a resultados de lectura confiables.
Task 1: revisión independiente encontró homónimos ocultos, fecha LFT ausente, acceso incompleto al calendario y falta de prueba integral de Discuss. Ronda de corrección 1 iniciada.
Task 1: fix round 1/5 (5 hallazgos atendidos, 0 abiertos; revisión independiente, 36 pruebas Odoo aprobadas). La verificación visual de Discuss y los límites del parser quedan documentados para la verificación final.
Ruling: se permite una comprobación privilegiada estrictamente limitada a detectar ambigüedad por nombre en la compañía activa y ausencias relevantes ocultas, solo después de comprobar autorización; no se enumeran registros ocultos ni se calcula o entrega el saldo con privilegios elevados.
Consulta general: revisión independiente no aprobada; el prototipo solo reconoce etiquetas exactas habitualmente en inglés, no propone planes generales ni filtros y no distingue permisos denegados; ronda de corrección 1 iniciada. La prueba real «¿Cuántos Product hay?» no representa las preguntas españolas solicitadas.
Consulta general: fix round 1/5 (enrutamiento, idioma y permisos mejorados; interpretación amplia y robustez HTTP pendientes). Fix round 2/5 (validación HTTP y modelos malformados corregidos; interpretación amplia continúa pendiente). 25 pruebas Odoo y 34 Python aprobadas antes de ronda 3.
