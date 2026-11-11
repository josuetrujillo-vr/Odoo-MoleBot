# Mole: asistente local para Odoo 18

Mole es un prototipo de asistente local integrado en Conversaciones (Discuss) de Odoo 18. Su alcance actual incluye consultar el saldo propio de vacaciones LFT y, para usuarios de Recursos Humanos autorizados, el saldo de una persona nombrada en la compañía activa. Está en desarrollo: no se ha validado para producción y no debe instalarse en una base con datos reales sin una revisión independiente de seguridad y funcionamiento.

## Arquitectura y alcance

- `assistant_local` aporta conversaciones, mensajes, registro de capacidades, controles de acceso, auditoría y adaptadores experimentales de inferencia local.
- `assistant_local_hr_holidays` obtiene el empleado vinculado al usuario y compañía activos y consulta su saldo LFT. Requiere el módulo externo `l10n_mx_hr_holidays_lft`, que no se incluye aquí.
- `assistant_local_mole` integra un chat privado de Discuss. La consulta propia usa reglas restrictivas y un modelo local; la consulta ajena sigue un patrón determinista y no permite al modelo elegir al empleado. Las cifras provienen de Odoo. La interpretación puede rechazar preguntas válidas o tratar de forma incorrecta frases ambiguas.
- `assistant_local_business` contiene capacidades experimentales de lectura de facturas, gasto por proveedor y ventas por producto. Sus cálculos y criterios, especialmente monedas, fechas y notas de crédito, necesitan revisión antes de cualquier uso operativo; no están disponibles desde el chat Mole actual.
- `assistant_local_stock` contiene una propuesta y confirmación experimental de transferencias internas mediante operaciones de Odoo. No está disponible desde el chat Mole actual y no se considera listo para uso operativo. La reserva para eventos prevista equivale a una transferencia a su ubicación, no a una reserva independiente.

La consulta ajena exige pertenecer al grupo de usuario de Recursos Humanos de Odoo y contar con acceso efectivo de lectura al empleado y a los registros necesarios para calcular el saldo. Solo busca una coincidencia exacta de nombre en la compañía activa; homónimos, permisos insuficientes o datos necesarios ausentes producen una negativa genérica. El parser acepta únicamente frases limitadas como «Saldo de vacaciones de María López» o «¿Cuántos días de vacaciones tiene María López?», con nombre literal y mayúsculas iniciales; no resuelve apodos, referencias indirectas ni lenguaje libre. El cálculo depende del módulo LFT, del calendario y de la visibilidad de ausencias, jornadas y excepciones; si detecta registros relevantes ocultos, rechaza la consulta. Estos controles necesitan validación con la configuración y calendarios reales antes de su uso operativo.

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

Hubo pruebas locales con datos sintéticos, incluido un caso de inferencia real de saldo propio y 36 pruebas Odoo aisladas de las capacidades y la integración de vacaciones. Estas pruebas no certifican todos los escenarios ni el uso en producción. La aparición y el flujo visual completos en Discuss, las pruebas negativas amplias, la robustez del modelo, privacidad, concurrencia, permisos y compatibilidad requieren nueva verificación. No se ha evaluado el rendimiento ni desplegado esta versión en un servidor de producción.

El contrato de diseño inicial está en [docs/core-contract.md](docs/core-contract.md); es un objetivo de diseño, no una garantía de implementación.

### Consultas generales de Mole (prototipo)

Mole puede contar registros visibles de algunos modelos comerciales instalados, sujetos a tus permisos, reglas y compañías. Por ejemplo: «¿Cuántos productos hay?» o «¿Cuántos productos con nombre "Mole" hay?». El único filtro disponible es igualdad por nombre entre comillas. Las cantidades monetarias, otros criterios y modelos ambiguos requieren aclaración; la cobertura y la interpretación son limitadas.
