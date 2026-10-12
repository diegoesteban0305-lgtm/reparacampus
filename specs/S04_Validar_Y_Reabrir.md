> Proyecto ReparaCampus · Ingeniería de Software I · USB · Metodología SDD. Flujo: RF → Historia → SPEC → Código → Prueba (pytest).
> Estado: **v1.0 consolidada, pendiente de firma del equipo.** No generar código hasta aprobar esta SPEC.

# SPEC: S04 · Título: Validar, rechazar y reabrir incidencia

Versión / autor / revisor / fecha: v1.0 (consolidada) / Equipo ReparaCampus (redacción: Claude; consolidación: Arquitecto de Software) / [revisor humano] / 2026-10-12
Requisito asociado: RF04
Dependencias: S03 (incidencias en `PENDIENTE_VALIDACION`); devuelve a S03 mediante `EN_ATENCION`.
Trazabilidad: RF04 → HU S04 → SPEC S04 → `confirmar`, `rechazar`, `reabrir` → `tests/test_s04_*.py`
Historia: Como Solicitante dueño del reporte, quiero confirmar, rechazar o reabrir la solución de mi incidencia, para asegurar que el problema quedó realmente resuelto.

Alcance y exclusiones:
- Incluye: confirmar (→CERRADA), rechazar (→EN_ATENCION), reabrir dentro de 48 h (→EN_ATENCION), registro de motivos y cierres, historial.
- Excluye: cierre automático por tiempo, reasignación de técnico, reapertura pasadas 48 h, edición de motivos.

Entradas:

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `incidencia_id` | entero (ruta) | Sí | Debe existir |
| `motivo` | texto | Solo en rechazar y reabrir | Tras `strip()`: 10 a 300 caracteres |

Precondiciones y permisos:
- Rol `SOLICITANTE` y `autor_id` de la incidencia = usuario en sesión.
- Confirmar y rechazar: estado `PENDIENTE_VALIDACION`. Reabrir: estado `CERRADA` y `ahora_utc() - fecha_ultimo_cierre <= 48 h`.

Reglas y proceso:
1. Confirmar: en una transacción pasar a `CERRADA`, insertar fila en `cierres` con `fecha_utc` del servidor e historial `CONFIRMAR`.
2. Rechazar: validar motivo; en una transacción pasar a `EN_ATENCION`, guardar motivo (`RECHAZO`) e historial `RECHAZAR`. El `tecnico_id` no cambia y la solución previa se conserva.
3. Reabrir: obtener el **último** cierre de la incidencia; si `diferencia <= 48 h` (exactamente 48 h:00 s se permite) y el motivo es válido, en una transacción pasar a `EN_ATENCION`, guardar motivo (`REAPERTURA`) e historial `REABRIR`; el técnico no cambia. Si la diferencia es mayor, responder 409 sin cambios.
4. El tiempo se calcula solo con el reloj del servidor en UTC; nunca con datos del cliente.
5. Un nuevo cierre tras una reapertura crea otra fila en `cierres`, y esa fecha es la base de la siguiente ventana de 48 h.

Salidas y cambios persistidos:
- Confirmar: estado + `cierres` + historial. Rechazar/Reabrir: estado + `motivos` + historial. Nada se borra ni se edita.

Errores y efectos que deben evitarse:
- Que quien no es el solicitante dueño (otro solicitante, técnico, coordinador) valide, rechace o reabra.
- Reabrir fuera de ventana, o calcular la ventana con la hora del cliente o desde el primer cierre.
- Perder la solución previa, el motivo o el técnico asignado.
- Confirmar o rechazar fuera de `PENDIENTE_VALIDACION`, o reabrir fuera de `CERRADA`.
- Cambios parciales (estado sin historial).

AC-S04-01: Dado el Solicitante dueño y una incidencia `PENDIENTE_VALIDACION`, Cuando confirma la solución, Entonces se responde 200, el estado es `CERRADA`, se registra `fecha_utc` en `cierres` y se crea 1 historial `CONFIRMAR`.
AC-S04-02: Dado el Solicitante dueño y una incidencia `PENDIENTE_VALIDACION` con una solución, Cuando rechaza con un motivo de 30 caracteres, Entonces el estado vuelve a `EN_ATENCION`, el `tecnico_id` no cambia, la solución previa y el motivo quedan guardados y se crea 1 historial `RECHAZAR`; y motivos de 9 o 301 caracteres responden 400 sin cambios.
AC-S04-03: Dado el Solicitante dueño y una incidencia `CERRADA` hace exactamente 48 h (y otro caso hace 47 h 59 min), Cuando reabre con un motivo válido, Entonces se responde 200, el estado es `EN_ATENCION`, el técnico es el mismo, el motivo `REAPERTURA` queda guardado y se crea 1 historial `REABRIR`.
AC-S04-04: Dado el Solicitante dueño y una incidencia `CERRADA` hace 48 h y 1 segundo (reloj del servidor en UTC), Cuando intenta reabrir, Entonces se responde 409 y no cambian estado, motivos ni historial; y si la incidencia fue reabierta y cerrada de nuevo, la ventana se mide desde el último cierre.
AC-S04-05: Dado un usuario que no es el solicitante dueño (otro Solicitante, Técnico o Coordinador), o el dueño con el estado incorrecto (confirmar en `CERRADA`, reabrir en `PENDIENTE_VALIDACION`), Cuando intenta confirmar, rechazar o reabrir, Entonces se responde 403 (no dueño) o 409 (estado incorrecto) sin ningún cambio.

Diseño y tareas vinculadas a cada AC:
- Módulos: `models/incidencias.py` (`confirmar`, `rechazar`, `reabrir`), `routes/solicitante.py` (`POST /incidencias/<id>/confirmar|rechazar|reabrir`), `validators.py` (`validar_motivo`), `clock.py` (`ahora_utc`), tablas `cierres` y `motivos`, `templates/incidencia_detalle.html` (botones según estado, revalidados en servidor).
- AC-01..03: modelo + rutas + transacciones. AC-04: consulta del último cierre + comparación `<= timedelta(hours=48)`. AC-05: chequeo de dueño + máquina de estados.

Pruebas y resultados esperados:
- `test_confirmar_ok` (AC-01), `test_rechazar_conserva_tecnico_y_solucion` y `test_motivo_limites` (AC-02), `test_reabrir_en_limite_48h` con `ahora_utc` monkeypatched (AC-03), `test_reabrir_fuera_ventana` y `test_ventana_desde_ultimo_cierre` (AC-04), `test_no_dueno_y_estado_incorrecto` parametrizada (AC-05).
- Resultado esperado: verde; tras cada rechazo de operación, tablas idénticas al estado previo.

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
