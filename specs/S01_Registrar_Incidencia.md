> Proyecto ReparaCampus · Ingeniería de Software I · USB · Metodología SDD. Flujo: RF → Historia → SPEC → Código → Prueba (pytest).
> Estado: **v1.0 consolidada, pendiente de firma del equipo.** No generar código hasta aprobar esta SPEC.

# SPEC: S01 · Título: Registrar incidencia

Versión / autor / revisor / fecha: v1.0 (consolidada) / Equipo ReparaCampus (redacción: Claude; consolidación: Arquitecto de Software) / [revisor humano] / 2026-10-12
Requisito asociado: RF01
Dependencias: Ninguna (usa la función `calcular_prioridad` de S02 y `requiere_rol`).
Trazabilidad: RF01 → HU S01 → SPEC S01 → `validators.py`, `models/incidencias.py::crear_incidencia` → `tests/test_s01_*.py`
Historia: Como Solicitante, quiero registrar una incidencia de infraestructura indicando ubicación, categoría, descripción, impacto y riesgo, para que el problema quede formalmente reportado y entre al flujo de atención.

Alcance y exclusiones:
- Incluye: formulario y endpoint de creación, validaciones, código único, estado inicial, fila de historial, cálculo y persistencia de prioridad (función de S02).
- Excluye: edición o eliminación posterior del reporte, adjuntos, asignación (S02), listados (S05).

Entradas:

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `ubicacion` | texto | Sí | Exactamente uno de `LAB-01`, `AULA-201`, `BIB-01` |
| `categoria` | texto | Sí | Exactamente uno de `ELECTRICIDAD`, `HIDRAULICA`, `MOBILIARIO`, `TIC` |
| `descripcion` | texto | Sí | Tras `strip()`: 20 a 500 caracteres |
| `impacto` | texto | Sí | `BAJO` o `ALTO` |
| `riesgo_personas` | booleano | Sí | Solo `true` o `false` (cualquier otro valor se rechaza) |

Generados por el servidor: `codigo` único (formato propuesto `INC-000001`, derivado del id autoincremental), `autor_id` (sesión), `fecha_utc`, `estado='REGISTRADA'`, `prioridad`.

Precondiciones y permisos:
- Sesión activa con rol `SOLICITANTE`. Coordinador y Técnico no pueden registrar.
- No hay precondición de estado (la incidencia aún no existe).

Reglas y proceso:
1. Verificar sesión y rol.
2. Validar los 5 campos; si alguno falla, responder 400 con el listado de campos inválidos, sin abrir transacción de escritura.
3. Calcular `prioridad` con `calcular_prioridad(impacto, riesgo)` (definida en S02).
4. En una transacción: insertar incidencia, generar `codigo`, insertar historial (`CREAR`, NULL→REGISTRADA, autor = sesión).
5. Responder 201 con el código y redirigir al detalle.

Salidas y cambios persistidos:
- 1 fila en `incidencias` y 1 fila en `historial`. Ninguna otra tabla se modifica.
- Respuesta 201 con `codigo`, `estado`, `prioridad`, `fecha_utc`.

Errores y efectos que deben evitarse:
- Persistir parcialmente (incidencia sin historial o viceversa).
- Aceptar valores fuera de las listas, booleanos como texto libre ("si", "1") o descripciones que solo cumplan longitud por espacios.
- Tomar el autor o el estado desde el cuerpo de la petición.
- Interpretar la descripción como HTML o script (XSS).
- Duplicar códigos ante envíos repetidos.

AC-S01-01: Dado un Solicitante autenticado, Cuando envía ubicación `LAB-01`, categoría `TIC`, descripción válida de 40 caracteres, impacto `BAJO` y riesgo `false`, Entonces se responde 201, se crea la incidencia con estado `REGISTRADA`, código único, autor igual al de la sesión y fecha UTC, y queda 1 fila de historial `CREAR`.
AC-S01-02: Dado un Solicitante autenticado, Cuando envía descripciones de 19 y 501 caracteres (tras `strip()`) o una de 25 espacios más 10 letras, Entonces cada caso se responde 400 y no se persiste incidencia ni historial; y descripciones de exactamente 20 y 500 caracteres se aceptan.
AC-S01-03: Dado un Solicitante autenticado, Cuando envía una ubicación (`LAB-99`), categoría (`SEGURIDAD`), impacto (`MEDIO`) o riesgo (`talvez`) fuera de los valores permitidos, o omite cualquier campo, Entonces se responde 400 indicando el campo y no se persiste nada.
AC-S01-04: Dado un Coordinador o Técnico autenticado, o una petición sin sesión, Cuando intenta registrar una incidencia, Entonces se responde 403 (con sesión) o 401 (sin sesión) y no se persiste nada.
AC-S01-05: Dado un Solicitante que envía un cuerpo con `autor_id` ajeno, `estado='CERRADA'` y una descripción `<script>alert(1)</script>` de 20+ caracteres, Cuando se registra, Entonces el autor es el de la sesión, el estado es `REGISTRADA` y el detalle muestra el texto escapado sin ejecutarlo; además, si falla la inserción del historial, se revierte la incidencia (0 filas en ambas tablas).

Diseño y tareas vinculadas a cada AC:
- Módulos: `db.py` + `schema.sql` (tablas `usuarios`, `incidencias`, `historial`), `validators.py` (`validar_incidencia`), `models/incidencias.py` (`crear_incidencia`), `routes/incidencias.py` (`GET/POST /incidencias/nueva`), `templates/incidencia_nueva.html`, `auth.py` (decorador `requiere_rol`).
- AC-01: ruta + modelo + historial. AC-02/03: `validators.py`. AC-04: `requiere_rol('SOLICITANTE')`. AC-05: transacción única + escape Jinja2 + ignorar campos extra.

Pruebas y resultados esperados (pytest, Flask test client, SQLite temporal independiente por prueba):
- `test_registro_exitoso` (AC-01), `test_descripcion_limites` parametrizada 19/20/500/501/espacios (AC-02), `test_campos_invalidos` parametrizada (AC-03), `test_rol_no_permitido_y_sin_sesion` (AC-04), `test_autor_estado_ignorados_y_xss_escapado` y `test_rollback_si_falla_historial` con monkeypatch (AC-05).
- Resultado esperado: todas en verde; conteo de filas en BD coincide con lo indicado en cada AC.

Decisión de revisión / versión aprobada: [ ] Aprobada [ ] Con cambios — Firmas: ______ / ______ — Fecha: ______

---

## Convenciones y decisiones de diseño aplicables

- Estados: `REGISTRADA`, `ASIGNADA`, `EN_ATENCION`, `PENDIENTE_VALIDACION`, `CERRADA`.
- Transiciones permitidas (únicas): REGISTRADA→ASIGNADA (S02); ASIGNADA→EN_ATENCION, EN_ATENCION→PENDIENTE_VALIDACION (S03); PENDIENTE_VALIDACION→CERRADA, PENDIENTE_VALIDACION→EN_ATENCION (rechazo), CERRADA→EN_ATENCION (reapertura ≤ 48 h) (S04).
- Identidad y rol salen **solo** de `session` del servidor. Se ignora cualquier `autor`, `rol` o `estado` enviado en el cuerpo de la petición.
- Orden de validación en cada endpoint: sesión (401) → rol (403) → existencia (404) → propiedad/asignación (403) → estado (409) → datos de entrada (400).
- Códigos HTTP: 201 creación, 200 éxito, 400 dato inválido, 401 sin sesión, 403 sin permiso, 404 no existe, 409 estado/regla temporal no permite la operación.
- Fechas en UTC (ISO 8601, `datetime.now(timezone.utc)`), obtenidas mediante una función `ahora_utc()` inyectable para poder probar el límite de 48 h.
- Textos: se aplica `strip()` antes de medir longitud; se almacenan como texto plano y Jinja2 los escapa al renderizar (sin `|safe`).
- Atomicidad: cambio de estado + fila de historial en **una sola transacción** SQLite; si falla una, se revierte todo.
- Historial (`historial`): `id, incidencia_id, autor_id, fecha_utc, estado_inicial, estado_final, accion, detalle`. Acciones: `CREAR`, `ASIGNAR`, `INICIAR_ATENCION`, `REGISTRAR_SOLUCION`, `CONFIRMAR`, `RECHAZAR`, `REABRIR`. Para la creación, `estado_inicial` es NULL.
- Tablas de soporte: `soluciones(id, incidencia_id, tecnico_id, texto, fecha_utc)`, `cierres(id, incidencia_id, fecha_utc)`, `motivos(id, incidencia_id, tipo[RECHAZO|REAPERTURA], texto, autor_id, fecha_utc)`. Son append-only.

- Decisiones fijadas en la consolidación: la prioridad se calcula y persiste al registrar; código `INC-000001` derivado del id autoincremental; reglas de estado/tiempo rechazadas con 409 y datos inválidos con 400; detalle de incidencia ajena responde 403; exactamente 48 h permite reabrir.
