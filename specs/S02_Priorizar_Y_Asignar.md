> Proyecto ReparaCampus · Ingeniería de Software I · USB · Metodología SDD. Flujo: RF → Historia → SPEC → Código → Prueba (pytest).
> Estado: **v1.0 consolidada, pendiente de firma del equipo.** No generar código hasta aprobar esta SPEC.

# SPEC: S02 · Título: Priorizar y asignar incidencia

Versión / autor / revisor / fecha: v1.0 (consolidada) / Equipo ReparaCampus (redacción: Claude; consolidación: Arquitecto de Software) / [revisor humano] / 2026-10-12
Requisito asociado: RF02
Dependencias: S01 (incidencias en `REGISTRADA`).
Trazabilidad: RF02 → HU S02 → SPEC S02 → `services/prioridad.py`, `asignar_tecnico` → `tests/test_s02_*.py`
Historia: Como Coordinador, quiero que cada incidencia tenga una prioridad calculada automáticamente y asignarla a un técnico activo, para atender primero lo más urgente y asegurar un responsable.

Alcance y exclusiones:
- Incluye: función pura `calcular_prioridad`, endpoint de asignación, transición REGISTRADA→ASIGNADA, historial.
- Excluye: reasignación o desasignación de técnico, edición manual de prioridad, balanceo automático de carga.

Entradas:

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `incidencia_id` | entero (ruta) | Sí | Debe existir |
| `tecnico_id` | entero | Sí | Usuario con rol `TECNICO` y `activo=1` |
| `impacto`, `riesgo_personas` (para el cálculo) | ver S01 | Sí | Leídos de la incidencia, no del cliente |

Precondiciones y permisos:
- Rol `COORDINADOR`.
- Incidencia en estado `REGISTRADA` (sin técnico asignado).

Reglas y proceso:
1. Cálculo de prioridad (se ejecuta al registrar, ver S01):
   - riesgo = true → `CRITICA`
   - riesgo = false e impacto `ALTO` → `ALTA`
   - riesgo = false e impacto `BAJO` → `NORMAL`
2. Asignación: verificar sesión, rol, existencia, estado `REGISTRADA`, y que `tecnico_id` sea técnico activo.
3. En una transacción: guardar `tecnico_id`, cambiar estado a `ASIGNADA`, insertar historial (`ASIGNAR`, REGISTRADA→ASIGNADA, autor = coordinador, detalle = técnico).
4. Responder 200.

Salidas y cambios persistidos:
- `incidencias.tecnico_id` y `estado='ASIGNADA'`; 1 fila nueva en `historial`. La prioridad no cambia.

Errores y efectos que deben evitarse:
- Asignar a un usuario inexistente, inactivo o que no sea técnico.
- Reasignar una incidencia ya asignada o en cualquier estado distinto de `REGISTRADA`.
- Que la prioridad dependa de datos enviados por el cliente o sea editable.
- Cambios parciales (asignación sin historial).

AC-S02-01: Dadas las cuatro combinaciones de entrada, Cuando se llama `calcular_prioridad`, Entonces (riesgo true, impacto BAJO)→`CRITICA`, (true, ALTO)→`CRITICA`, (false, ALTO)→`ALTA`, (false, BAJO)→`NORMAL`, y la incidencia queda persistida con esa prioridad desde su registro.
AC-S02-02: Dado un Coordinador y una incidencia `REGISTRADA`, Cuando asigna un técnico activo, Entonces se responde 200, el estado pasa a `ASIGNADA`, `tecnico_id` queda guardado y se crea 1 fila de historial `ASIGNAR`.
AC-S02-03: Dado un Coordinador y una incidencia `REGISTRADA`, Cuando asigna un técnico inactivo, un `tecnico_id` inexistente o un usuario con rol Solicitante, Entonces se responde 400 y la incidencia permanece `REGISTRADA` sin `tecnico_id` ni historial nuevo.
AC-S02-04: Dado un Coordinador y una incidencia ya `ASIGNADA` (o en cualquier estado distinto de `REGISTRADA`), Cuando intenta asignar o reasignar un técnico, Entonces se responde 409 y no cambia técnico, estado ni historial.
AC-S02-05: Dado un Solicitante o Técnico autenticado (o sin sesión), Cuando invoca la asignación, Entonces se responde 403 (o 401) sin ningún cambio; y una incidencia inexistente responde 404.

Diseño y tareas vinculadas a cada AC:
- Módulos: `services/prioridad.py` (`calcular_prioridad`), `models/incidencias.py` (`asignar_tecnico`), `routes/coordinador.py` (`POST /incidencias/<id>/asignar`), `templates/incidencia_detalle.html` (selector de técnicos activos, visible solo al Coordinador, validado igualmente en servidor).
- AC-01: función pura + llamada desde S01. AC-02..05: modelo con transacción + `requiere_rol('COORDINADOR')`.

Pruebas y resultados esperados:
- `test_calcular_prioridad` parametrizada 4 casos (AC-01), `test_asignar_ok` (AC-02), `test_asignar_tecnico_invalido` parametrizada (AC-03), `test_reasignacion_rechazada` (AC-04), `test_asignar_sin_permiso_y_404` (AC-05).
- Resultado esperado: verde; tras cada rechazo, estado/técnico/historial idénticos al inicial.

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
