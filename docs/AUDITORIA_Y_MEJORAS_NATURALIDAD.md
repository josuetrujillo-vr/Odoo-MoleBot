# Auditoría Integral y Mejoras de Naturalidad - Odoo Assistant (Mole)

**Fecha**: Noviembre 2026  
**Rama**: `development`  
**Autor**: Antigravity Assistant  
**Entorno de Pruebas**: Local exclusivo (`odoo-testing-local`), bases desechables (`assistant_test_*`), sin conexión ni despliegue en VPS.

---

## 1. Resumen Ejecutivo

Se realizó una auditoría completa de seguridad, arquitectura, coherencia de datos y experiencia conversacional sobre todos los módulos del repositorio `odoo-assistant-local`:
1. `assistant_local`: Núcleo de inferencia, seguridad de conversaciones, registro de capacidades y motor de planes deterministas (`assistant.general.query`).
2. `assistant_local_business`: Capacidades contables y comerciales (facturas, gasto con proveedores, ventas de producto).
3. `assistant_local_hr_holidays`: Cálculo de vacaciones LFT mexicanas y balance propio o por nombre con permisos de RRHH.
4. `assistant_local_stock`: Consultas de cantidad y ubicación de inventario, y transferencias internas confirmadas.
5. `assistant_local_mole`: Integración del bot Mole en canales privados de Discuss (`discuss.channel`).

---

## 2. Hallazgos, Errores y Vulnerabilidades Resueltos

### A. Secuestro de preguntas con saludo integrado (Bug Crítico)
- **Problema detectado**: En `assistant_local_mole/models/discuss_channel.py`, cualquier mensaje que contuviera un saludo en cualquier posición (por ejemplo: *"Hola, ¿cuántos productos hay?"* o *"Buenos días, ¿cuáles son los pedidos de venta?"*) era interceptado inmediatamente por la verificación de bienvenida genérica, respondiendo con el texto de bienvenida y **descartando la pregunta del usuario**.
- **Solución implementada**:
  - Se implementó `classify_social(text)` en `assistant_local/mole_local.py`, distinguiendo entre mensajes que son *exclusivamente sociales* y aquellos que contienen una consulta legítima precedida por una cortesía.
  - Si el usuario dice únicamente *"Hola"* o *"Hola Mole"*, recibe la bienvenida y guía de uso. Si dice *"Hola, ¿cuántos productos hay?"*, la cortesía se procesa con fluidez y se responde de inmediato la consulta.

### B. Respuestas ausentes ante cortesías cotidianas (Agradecimientos, Despedidas y Acuses)
- **Problema detectado**: Si un usuario interactuaba educadamente diciendo *"Gracias"*, *"Muchas gracias"*, *"Hasta luego"*, *"Adiós"*, *"Excelente"* o *"Perfecto"*, el bot respondía con un error tosco:
  `⚠ No entendí la consulta. Puedes pedirme, por ejemplo...`
- **Solución implementada**:
  - Soporte completo para intenciones sociales:
    - **Gratitud** (*"Muchas gracias"*, *"Thank you"*): Responde cálidamente (*"¡Con mucho gusto! Quedo a tu disposición si necesitas consultar algo más."*).
    - **Despedida** (*"Hasta luego"*, *"Goodbye"*): Responde amablemente (*"¡Hasta luego! Que tengas un excelente día."*).
    - **Acuse/Afirmación** (*"Perfecto"*, *"Excelente"*, *"Great"*): Responde educadamente (*"¡Excelente! Dime si requieres consultar alguna otra información."*).

### C. Lenguaje burocrático, rígido y poco natural en las respuestas
- **Problema detectado**: `format_result` devolvía cadenas con estilo de auditoría de depuración técnica:
  `Registros activos visibles de Contacto: 5. Compañías activas en el contexto: My Company. Criterios: sin filtros adicionales; se aplican tus permisos y reglas...`
  Y las vacaciones se mostraban como un volcado de campos:
  `Saldo de vacaciones (LFT): Empleado: ... Antigüedad: ... Días disponibles: ...`
- **Solución implementada**:
  - Rediseño de `format_result` en `assistant_local/general_query.py` para generar respuestas fluidas, concisas y humanas manteniendo exactitud factual:
    - *Conteo (ES)*: *"Actualmente hay **5** registros activos de **Contacto** en My Company."*
    - *Conteo con filtro (ES)*: *"Actualmente hay **1** registro de **Sale** con nombre igual a "ACME" en My Company."*
    - *Listado (ES)*: *"Aquí tienes los registros de **Contacto** (mostrando 5 de 12) en My Company: ..."*
    - *Detalle (ES)*: *"Detalle de Contacto (Azure Interior) en My Company: ..."*
    - *Equivalentes en inglés* con detección automática de idioma (`detect_language`).
  - Creación de `format_vacation_balance(result, language)`: Redacción en párrafos naturales para el saldo propio (*"Cuentas con **12** días de vacaciones disponibles (de un derecho total de **14** días para el periodo)..."*) o de terceros para personal autorizado de RRHH.

### D. Discrepancia entre Discuss y el Chat OWL (`assistant.conversation`)
- **Problema detectado**: En `assistant_local/models/conversation.py`, si no había runtime de modelo local activo en la máquina, la llamada fallaba y no recurría a los planes deterministas seguros (`supported_plans`), mientras que `discuss.channel` sí lo hacía. Además, al ejecutar herramientas de vacaciones devolvía un volcado JSON crudo.
- **Solución implementada**:
  - Se unificó `_try_answer_general` en `conversation.py` para utilizar `supported_plans` ante ausencia o declinación del modelo.
  - Se formateó la respuesta de vacaciones con `format_vacation_balance`.

### E. Rigidez en el parser de consultas generales (`supported_plans`)
- **Problema detectado**: El parser regex rechazaba consultas habituales que incluían fórmulas de cortesía (*"me puedes decir cuántos..."*, *"podrías mostrarme..."*, *"por favor..."*, *"sabes cuántos..."*, *"cuántos productos tenemos en la empresa"*, *"how many products do we have in total"*).
- **Solución implementada**:
  - Normalización con extracción previa de prefijos de cortesía (`clean_courtesy`).
  - Ampliación de prefijos y sufijos en inglés y español permitiendo combinaciones naturales (ej. `do we have in total`, `en la empresa`, `en el sistema`).

### F. Seguridad y Aislamiento de Entorno
- Scripts temporales y archivos locales con credenciales o configuraciones locales (`tools/check_*.py`, `.test-data*`, `.runtime`, `.env*`) quedaron estrictamente ignorados en `.gitignore` para evitar filtraciones accidentales al repositorio.
- Todas las pruebas de Odoo se realizaron en bases de datos efímeras creadas y destruidas en tiempo de ejecución (`assistant_test_[a-f0-9]{12}`), con SMTP mockeado y `--db-filter` anclado.

---

## 3. Matriz de Pruebas y Verificación

| Suite | Archivo / Runner | Pruebas | Fallos | Errores | Estado |
|---|---|---|---|---|---|
| **Standalone Python** | `python -m unittest discover -s tests -v` | 63 | 0 | 0 | **PASS** |
| **Integración Odoo Discuss / Stock** | `tests/run_mole_stock_odoo.py` | 37 | 0 | 0 | **PASS** |
| **Integración Odoo Suite Completa** | `tests/run_full_odoo_suite.py` | 105 | 0 | 0 | **PASS** |
| **Total Combinado** | **168 pruebas automáticas ejecutadas** | **168** | **0** | **0** | **100% PASS** |

### Módulos validados en la suite de integración de Odoo:
- `assistant_local`: 56 pruebas (Chat API, Conversation Security, General Query, Inference, Message Security, Audit Security, Capability Dispatch).
- `assistant_local_business`: 7 pruebas (Facturas de cliente, notas de crédito, gasto por proveedor, ventas de producto, validación de fechas y monedas).
- `assistant_local_hr_holidays`: 23 pruebas (Cálculo de vacaciones LFT, aislamiento entre empleados, validaciones anti-fuga con sudo).
- `assistant_local_stock`: 7 pruebas (Transferencias internas, propuestas con token efímero de 5 min, validaciones de permisos de inventario).
- `assistant_local_mole`: 36 pruebas (Canal Discuss privado, bot partner, respuestas naturales, rechazo de datos inventados, transferencias en dos pasos).

---

## 4. Estado de Git y Próximos Pasos para el Usuario

- Todo el trabajo y los commits se encuentran en la rama local:
  ```bash
  git branch
  # * development
  ```
- **Sin push realizado**: De acuerdo con las instrucciones, no se ha hecho ningún `git push` al servidor remoto.
- Cuando desees subir los cambios a tu repositorio remoto, simplemente ejecuta:
  ```bash
  git push origin development
  ```
