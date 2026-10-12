> Proyecto ReparaCampus · Ingeniería de Software I · USB · Metodología SDD. Flujo: RF → Historia → SPEC → Código → Prueba (pytest).
> Estado: **v1.0 consolidada, pendiente de firma del equipo.** No generar código hasta aprobar esta SPEC.

# SPEC: S03 · Título: Atender incidencia y registrar solución

Versión / autor / revisor / fecha: v1.0 (consolidada) / Equipo ReparaCampus (redacción: Claude; consolidación: Arquitecto de Software) / [revisor humano] / 2026-10-12
Requisito asociado: RF03
Dependencias: S02 (incidencias en `ASIGNADA`); recibe retornos desde S04.
Trazabilidad: RF03 → HU S03 → SPEC S03 → `iniciar_atencion`, `registrar_solucion` → `tests/test_s03_*.py`
Historia: Como Técnico asignado, quiero iniciar la atención de mi incidencia y registrar la solución aplicada, para que el solicitante pueda verificarla.

Alcance y exclusiones:
- Incluye: ASIGNADA→EN_ATENCION, EN_ATENCION→PENDIENTE_VALIDACION, almacenamiento de cada solución, historial.
- Excluye: edición o borrado de soluciones, cierre (S04), adjuntos, pausas o estados intermedios.

Entradas:

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `incidencia_id` | entero (ruta) | Sí | Debe existir |
| `solucion` | texto | Solo al registrar solución | Tras `strip()`: 20 a 800 caracteres |

Precondiciones y permisos:
- Rol `TECNICO` y `tecnico_id` de la incidencia = usuario en sesión.
- Iniciar atención: estado `ASIGNADA`. Registrar solución: estado `EN_ATENCION`.

Reglas y proceso:
1. Iniciar (`POST /incidencias/<id>/atender`): validar sesión, rol, asignación y estado; en una transacción pasar a `EN_ATENCION` e insertar historial `INICIAR_ATENCION`.
2. Registrar solución (`POST /incidencias/<id>/solucion`): validar sesión, rol, asignación, estado y longitud; en una transacción insertar fila en `soluciones` (append-only), pasar a `PENDIENTE_VALIDACION` e insertar historial `REGISTRAR_SOLUCION`.
3. Tras un rechazo o reapertura (S04) la incidencia vuelve a `EN_ATENCION` y el técnico registra una nueva solución sin sobrescribir las anteriores.

Salidas y cambios persistidos:
- Iniciar: `estado='EN_ATENCION'` + 1 historial.
- Solución: 1 fila en `soluciones`, `estado='PENDIENTE_VALIDACION'` + 1 historial.

Errores y efectos que deben evitarse:
- Que un técnico no asignado, el coordinador o el solicitante cambien el estado.
- Saltar estados (ASIGNADA→PENDIENTE_VALIDACION) o registrar solución fuera de `EN_ATENCION`.
- Sobrescribir soluciones previas; persistir solución sin cambio de estado o sin historial.
- Aceptar soluciones fuera de 20–800 caracteres.

AC-S03-01: Dado el Técnico asignado y una incidencia `ASIGNADA`, Cuando inicia la atención, Entonces se responde 200, el estado pasa a `EN_ATENCION` y se crea 1 historial `INICIAR_ATENCION` con ASIGNADA→EN_ATENCION.
AC-S03-02: Dado el Técnico asignado y una incidencia `EN_ATENCION`, Cuando registra una solución válida de 50 caracteres, Entonces se responde 200, se guarda la solución con autor y fecha UTC, el estado pasa a `PENDIENTE_VALIDACION` y se crea 1 historial `REGISTRAR_SOLUCION`.
AC-S03-03: Dado el Técnico asignado y una incidencia `EN_ATENCION`, Cuando envía una solución de 19 caracteres, de 801 caracteres o de solo espacios, Entonces se responde 400 y no cambian estado, soluciones ni historial; y soluciones de exactamente 20 y 800 caracteres se aceptan.
AC-S03-04: Dado un Técnico que no es el asignado, un Coordinador o un Solicitante, Cuando intenta iniciar atención o registrar solución, Entonces se responde 403 sin cambios; y si el usuario es el técnico correcto pero el estado no corresponde (iniciar en `EN_ATENCION`, solución en `ASIGNADA`) se responde 409 sin cambios.
AC-S03-05: Dada una incidencia que volvió a `EN_ATENCION` tras un rechazo (S04) con 1 solución previa, Cuando el mismo Técnico registra una nueva solución válida, Entonces existen 2 filas en `soluciones` (la previa intacta), el estado es `PENDIENTE_VALIDACION` y se añade 1 historial; si falla el insert del historial se revierte la solución y el estado.

Diseño y tareas vinculadas a cada AC:
- Módulos: `models/incidencias.py` (`iniciar_atencion`, `registrar_solucion`), `routes/tecnico.py` (`POST /incidencias/<id>/atender`, `POST /incidencias/<id>/solucion`), `validators.py` (`validar_solucion`), `templates/incidencia_detalle.html` (acciones visibles según rol y estado, siempre revalidadas en servidor).
- AC-01/02: modelo + rutas. AC-03: validador. AC-04: `requiere_rol('TECNICO')` + chequeo de asignación + máquina de estados. AC-05: tabla `soluciones` append-only + transacción.

Pruebas y resultados esperados:
- `test_iniciar_atencion_ok` (AC-01), `test_registrar_solucion_ok` (AC-02), `test_solucion_limites` 19/20/800/801/espacios (AC-03), `test_tecnico_ajeno_y_estado_invalido` parametrizada (AC-04), `test_segunda_solucion_conserva_primera` y `test_rollback_solucion` (AC-05).
- Resultado esperado: verde; conteos de `soluciones` e `historial` exactos.

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
