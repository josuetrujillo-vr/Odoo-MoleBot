# Mole: asistente local para Odoo 18

Mole es un prototipo de asistente local integrado en Conversaciones (Discuss) de Odoo 18. Su alcance actual es consultar el saldo propio de vacaciones LFT del usuario autenticado. Está en desarrollo: no se ha validado para producción y no debe instalarse en una base con datos reales sin una revisión independiente de seguridad y funcionamiento.

## Arquitectura y alcance

- `assistant_local` aporta conversaciones, mensajes, registro de capacidades, controles de acceso, auditoría y adaptadores experimentales de inferencia local.
- `assistant_local_hr_holidays` obtiene el empleado vinculado al usuario y compañía activos y consulta su saldo LFT. Requiere el módulo externo `l10n_mx_hr_holidays_lft`, que no se incluye aquí.
- `assistant_local_mole` integra un chat privado de Discuss. Solo expone al modelo la consulta del saldo propio; las cifras provienen de Odoo. La clasificación del texto combina reglas restrictivas con un modelo local y puede rechazar preguntas válidas o interpretar mal frases ambiguas.
- `assistant_local_business` contiene capacidades experimentales de lectura de facturas, gasto por proveedor y ventas por producto. Sus cálculos y criterios, especialmente monedas, fechas y notas de crédito, necesitan revisión antes de cualquier uso operativo; no están disponibles desde el chat Mole actual.
- `assistant_local_stock` contiene una propuesta y confirmación experimental de transferencias internas mediante operaciones de Odoo. No está disponible desde el chat Mole actual y no se considera listo para uso operativo. La reserva para eventos prevista equivale a una transferencia a su ubicación, no a una reserva independiente.

No se implementa la solicitud de vacaciones mediante el asistente. Las consultas de vacaciones y negocio son de lectura. El código evita ejecutar Python, SQL o métodos arbitrarios generados por el modelo, pero las pruebas existentes no demuestran ausencia de vulnerabilidades.

## Requisitos

Odoo 18 y sus dependencias, PostgreSQL local, Python compatible con la instalación de Odoo y los addons requeridos en el `addons_path`. Para vacaciones es necesario instalar por separado `l10n_mx_hr_holidays_lft` y verificar su compatibilidad. El backend de clasificación `llama_cpp_cli` actual requiere Windows, `pywin32`, un `llama-completion.exe` compatible y un modelo GGUF local compatible; ninguno se distribuye aquí. Se ha experimentado con Qwen2.5 1.5B Instruct GGUF. Revise licencias y procedencia de cada dependencia.

## Instalación de evaluación

1. Prepare una instalación local aislada de Odoo 18 y PostgreSQL con datos sintéticos y sin conexión a producción. Desactive explícitamente el envío externo de correo y otros efectos externos.
2. Añada la raíz de este repositorio al `addons_path`, antes de cualquier otra copia de estos addons; incluya también los addons de Odoo y la dependencia LFT. Actualice la lista de aplicaciones e instale `assistant_local_mole` y sus dependencias en la base aislada. Los addons de negocio e inventario son opcionales y experimentales.
3. Vincule un usuario interno sintético con un único empleado de la compañía activa y configure los datos LFT necesarios. Acceda a Discuss como ese usuario.
4. Para el backend CLI, defina en el entorno del proceso Odoo `ASSISTANT_LOCAL_BACKEND=llama_cpp_cli`, `MOLE_LLAMA_EXE` con la ruta absoluta al ejecutable local y `MOLE_MODEL_PATH` con la ruta absoluta al modelo `.gguf`. Sin modelo configurado se informa que la inferencia no está disponible. No incluya credenciales, modelos, bases ni archivos de configuración privados en Git.

Existe además un transporte experimental HTTP para un servicio local, configurado con `ASSISTANT_LOCAL_URL` y `ASSISTANT_LOCAL_MODEL`; está restringido a loopback y no implica conectividad entre contenedores. No se necesita una clave de API para el backend local. La configuración de red, permisos de archivos, acceso a Discuss y aislamiento del modelo siguen siendo responsabilidad del operador.

## Pruebas

Las pruebas independientes se ejecutan desde la raíz:

```powershell
python -m unittest discover -s tests -v
```

Algunas pruebas dependen de un modelo o ejecutable local y pueden omitirse si no están configurados. Las pruebas Odoo requieren una instalación y dependencias completas: cree una base local nueva y exclusiva para pruebas, use un filestore separado y datos sintéticos, limite HTTP a `127.0.0.1`, desactive correo externo y verifique que el `addons_path` resuelva esta copia. Pase tanto `-d <base-aislada>` como `--db-filter=^<base-aislada>$` con el nombre exacto, incluso para pruebas HTTP; nunca use una base existente. Ejecute los tests de los módulos con `--test-enable`, `--test-tags` y `--stop-after-init` según su instalación. No comparta una base entre ejecuciones simultáneas.

Hubo pruebas locales previas con datos sintéticos, incluido un caso de inferencia real de saldo propio, pero los resultados anteriores no certifican el estado actual. La aparición y el flujo visual completos en Discuss, las pruebas negativas amplias, la robustez del modelo, privacidad, concurrencia, permisos y compatibilidad requieren nueva verificación. No se ha evaluado el rendimiento ni desplegado esta versión en un servidor de producción.

El contrato de diseño inicial está en [docs/core-contract.md](docs/core-contract.md); es un objetivo de diseño, no una garantía de implementación.
