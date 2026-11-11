# Mole: continuación local

**Objetivo:** permitir consultas autorizadas de saldos ajenos y avanzar las capacidades del diseño aprobado, con seguridad verificable en Odoo local.

**Diseño base:** `C:/Users/truji/odoo/docs/superpowers/specs/2026-11-07-asistente-local-odoo-design.md`; el usuario amplía explícitamente el saldo a personas autorizadas para consultar a otros empleados. Conservar Discuss, los límites de compañía y los permisos efectivos de Odoo; no dar autorización al modelo ni inventar cifras.

## Restricciones globales

- Todas las pruebas y ejecuciones son locales, usando únicamente bases `assistant_test_[a-f0-9]{12}` y datos sintéticos; sin correo externo, producción ni VPS.
- No ejecutar SQL, código, dominios ni métodos arbitrarios generados por el modelo. No modificar datos de vacaciones o contables. No habilitar confirmación de stock a través del modelo sin sus protecciones integrales.
- Comprobar autorización en servidor para cada registro y campo, compañía activa y ambigüedad de nombres; ante duda denegar o pedir precisión. Evitar ampliar permisos con sudo.
- Las cifras y criterios salen de Odoo, no del texto libre generado por el modelo.
- Preservar trabajo preexistente sin commit. El repositorio no tiene commits y `.git` es de solo lectura: no crear commits ni worktree desde un HEAD inexistente; revisar contra copias previas de los archivos afectados.

## Tarea 1: vacaciones de otro empleado

Implementar y probar consulta por nombre desde Discuss para usuarios que realmente tengan permisos de RR. HH. sobre el empleado, respetando compañía activa, ACL, reglas y permisos de campos; resolver nombres sin ambigüedad ni filtrar información a usuarios no autorizados. Mantener saldo propio y bloqueo de llamadas no autorizadas. El clasificador no concede permisos y no se confía en texto o IDs inventados. Probar usuario autorizado, usuario normal, registros restringidos, otra compañía, nombres duplicados, intentos de falsificación, saldo numérico de Odoo y consultas propias.

## Tarea 2: consultas comerciales

Revisar e implementar solamente las consultas cuyo resultado y permisos puedan demostrarse: facturas de cliente, gasto por proveedor y ventas por producto; corregir defectos de moneda, fechas, devoluciones y acceso antes de conectar a Mole. Pedir datos faltantes y mostrar criterios explícitos; sin escrituras. No ampliar módulos por pregunta.

## Tarea 3: verificación y documentación

Ejecutar pruebas relevantes en el código y la instalación Odoo de tester local con bases sintéticas aisladas; distinguir pruebas con proveedor falso, modelo real y navegador. Documentar comandos, resultados y límites, incluyendo pendientes de inventario y comparación de modelos. Actualizar documentación obsoleta.

## Tarea 4: consultas generales según módulos y permisos

El usuario aclara que contactos es solo un ejemplo: quiere que Mole descubra y consulte temas diversos según los módulos instalados y los permisos efectivos, sin un módulo ni una función por cada pregunta. Diseñar y probar un mecanismo extensible de solo lectura que descubra metadatos autorizados y valide en servidor cualquier consulta estructurada, sin aceptar SQL, métodos ni dominios arbitrarios del modelo. Respetar ACL, reglas, campos restringidos y compañías; pedir precisión cuando falte semántica de fechas, monedas, unidades o filtros. No interpretar falta de permisos como cero ni usar sudo para entregar datos. El conteo de contactos es un caso de prueba, no el objetivo completo; «mis contactos» puede ser ambiguo. Probar usuarios, reglas, compañías, archivados, cero, inyección, modelo local y flujo Discuss con datos sintéticos. No reclamar que el modelo fue reentrenado.
