# Tarea 1: informe de implementación

## Estado y archivos

Implementación preparada para revisión independiente, sin commit. Cambios de producto: `assistant_local_hr_holidays/models/assistant_capability.py`, `assistant_local/mole_local.py` y `assistant_local_mole/models/discuss_channel.py`. Pruebas: `assistant_local_hr_holidays/tests/test_hr_vacation_capability.py`, `assistant_local_mole/tests/test_mole_discuss.py`, `assistant_local_mole/tests/test_real_model.py`, `tests/test_mole_local.py` y ejecutor aislado `tests/run_mole_task1_odoo.py`.

## Decisiones

- La capacidad ajena exige `hr.group_hr_user`, búsqueda por nombre completo exacto mediante ORM y reglas del usuario en compañía activa, una sola coincidencia y acceso de lectura a campos del empleado. Tras autorizar al empleado visible comprueba con conteo privilegiado acotado a esa compañía y nombre que no exista otro homónimo oculto. Entradas y fallos se deniegan genéricamente. No acepta IDs ni campos adicionales.
- Discuss acepta un conjunto deliberadamente estrecho de frases con nombre literal, extraído directamente del mensaje actual. Ejecuta la capacidad en servidor; no ofrece la capacidad ajena al modelo. Para la capacidad propia también comprueba de nuevo que el mensaje sea una consulta segura del propio saldo. El modelo no elige el nombre ni proporciona cifras.
- `_compute_lft_balance` lee ausencias según reglas del usuario y podría producir un saldo incompleto. Después de autorizar el empleado y la compañía, se compara el número de ausencias LFT aprobadas y vigentes visibles con un conteo mediante `sudo` limitado a ese empleado, tipo y periodo. Si difiere se deniega sin divulgar detalles. La excepción privilegiada no calcula saldos ni devuelve ausencias; el cálculo de campos se efectúa como el usuario real, tras invalidar su caché. La fecha de ingreso, recurso y calendario son obligatorios; se compara además la visibilidad de asistencias y exclusiones del calendario asociadas al recurso, calendario, compañía y periodo. Si falta acceso o difieren los conteos se deniega.
- Las coincidencias se restringen a nombre completo exacto, no se intenta seleccionar una coincidencia parcial. Los conteos privilegiados son comprobaciones acotadas y no devuelven datos de otros registros; el saldo se obtiene sin elevar permisos.

## Validación

- RED inicial: el agente principal ejecutó `python tests/run_mole_task1_odoo.py --reuse-task1-red` en la base sintética local `assistant_test_70b48f7855b7`: 26 pruebas, un error esperado `Unknown capability`. Antes se corrigieron aserciones incompatibles con Odoo y se añadió `no_reset_password` para usuarios sintéticos.
- RED por datos invisibles: mismo comando, 31 pruebas, un fallo esperado porque la consulta no denegaba la ausencia aprobada ocultada por regla global.
- GREEN posterior: mismo comando y base, 31 pruebas, cero fallos y errores, según ejecución del agente principal. Incluye cálculo de una ausencia aprobada visible y denegación al ocultarla, permisos, compañía, homónimos visibles, argumento adicional, ausencia de escrituras en campos observados y falsificación del modelo en Discuss.
- Tras revisión independiente, RED con 36 pruebas y cuatro fallos esperados: homónimo oculto, ingreso ausente, asistencia de calendario oculta y exclusión de calendario oculta. GREEN posterior con el mismo comando y base: 36 pruebas, cero fallos y errores, según ejecución del agente principal. Una prueba adicional envía mensajes reales en Discuss con capacidad LFT sin mock, usuario RR. HH. y usuario normal, y comprueba campos observados sin escritura. Los patrones para «María de la Cruz» y «Cuál es el saldo» pasaron su prueba Python después de fallar inicialmente.
- `python -m unittest discover -s tests -p test_mole_local.py -v`: 11 pruebas aprobadas, incluida ejecución del clasificador real local para consulta propia; no demuestra la consulta ajena con un modelo o navegador reales.
- `python -m unittest discover -s tests -v`: 23 pruebas, 7 errores en `test_local_model` al inicializar SSL por `PermissionError` sobre `\\.\aswMonFltProxy\...` en el sandbox. Se solicitó repetir fuera de él; no se considera suite completa aprobada.
- Prueba de TCP a `127.0.0.1:5432` dentro del sandbox: WinError 10013. El agente principal ejecutó las pruebas Odoo fuera del sandbox en la base nombrada, con filtro anclado, filestore exclusivo, repositorio primero, HTTP y cron desactivados. SMTP se bloquea en proceso y los usuarios sintéticos evitan la invitación; no se observó envío de signup en los segmentos revisados de la segunda ejecución.

## Límites

No se ha verificado una sesión visual de Discuss ni datos reales; el parser admite solo las frases de su patrón. La prueba de no escritura inspecciona campos concretos, no una auditoría exhaustiva de toda la base. Las comprobaciones de calendario se basan en el código LFT y Odoo inspeccionado y requieren nueva revisión independiente para otras dependencias o particularidades de reglas. No se usaron VPS ni proveedores externos y no se hicieron commits.
