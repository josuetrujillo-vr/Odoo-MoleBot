# Continuación de Mole: consultas de lectura

Estado: trabajo en progreso. La ronda actual permite al modelo elegir un plan estructurado entre modelos del catálogo; una validación independiente admite únicamente preguntas que puede verificar con seguridad. La interpretación sigue siendo limitada, en especial para criterios y ambigüedades no representables. No desplegar ni presentar como capacidad general terminada sin revisión y validación.

La ronda anterior pasó 25 pruebas Odoo y 34 pruebas Python, pero esos resultados no corresponden al último cambio de selección de planes. La ronda actual solo pasó 7 pruebas unitarias de consultas y 13 del intérprete; todavía no se ha probado en Odoo ni con el modelo real, y no ha recibido revisión independiente.

Pendiente: ejecutar las pruebas en una base sintética aislada local, con filtro exacto, correo y cron deshabilitados, incluidos ejemplos variados y adversariales con el modelo real; ejecutar la suite completa; revisar ACL, reglas, compañías, campos y denegaciones. Mantener la abstención cuando no se pueda verificar íntegramente la intención o el filtro. Revisar también rendimiento, límites y proveedor HTTP local.

Otras áreas pendientes de revisión independiente: seguridad del flujo RPC de inventario y semántica de moneda en consultas contables. No se afirma que estén corregidas o verificadas en este avance.
