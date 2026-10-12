> Proyecto ReparaCampus · Ingeniería de Software I · USB · Metodología SDD. Flujo: RF → Historia → SPEC → Código → Prueba (pytest).
> Estado: **v1.0 consolidada, pendiente de firma del equipo.** No generar código hasta aprobar esta SPEC.

# SPEC: S05 · Título: Consultar, historial inmutable y tablero del Coordinador

Versión / autor / revisor / fecha: v1.0 (consolidada) / Equipo ReparaCampus (redacción: Claude; consolidación: Arquitecto de Software) / [revisor humano] / 2026-10-12
Requisito asociado: RF05
Dependencias: S01–S04 (consume sus datos; no modifica nada).
Trazabilidad: RF05 → HU S05 → SPEC S05 → `models/consultas.py`, `models/tablero.py` → `tests/test_s05_*.py`
Historia: Como usuario del sistema, quiero consultar y filtrar las incidencias que mi rol me permite ver, revisar su historial completo y, como Coordinador, ver métricas globales, para dar seguimiento y tomar decisiones con trazabilidad.

Alcance y exclusiones:
- Incluye: listado y detalle por rol, filtros por estado y prioridad, historial de solo lectura, tablero del Coordinador.
- Excluye: exportación, gráficos, edición o borrado de historial, paginación avanzada, notificaciones.

Entradas:

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `estado` (query) | texto | No | Uno de los 5 estados; otro valor → 400 |
| `prioridad` (query) | texto | No | `CRITICA`, `ALTA` o `NORMAL`; otro valor → 400 |
| `incidencia_id` (ruta, detalle) | entero | Sí | Debe existir y ser visible para el rol |

Precondiciones y permisos:
- Cualquier rol autenticado puede consultar, con alcance distinto: Solicitante, solo las propias (`autor_id`); Técnico, solo las asignadas (`tecnico_id`); Coordinador, todas.
- Tablero: solo `COORDINADOR`.

Reglas y proceso:
1. El filtro por rol se aplica **en la consulta SQL del servidor**, antes de aplicar filtros del usuario; los filtros de estado y prioridad se combinan con AND.
2. Detalle: si la incidencia no es visible para el rol, responder 403. Incluye datos, todas las soluciones, motivos de rechazo/reapertura, cierres e historial ordenado por fecha ascendente.
3. Inmutabilidad: no existen rutas de edición/borrado de historial, y la BD lo refuerza con triggers `BEFORE UPDATE` y `BEFORE DELETE` en `historial` que abortan la operación.
4. Tablero: calcular en servidor (a) conteo por cada uno de los 5 estados (con 0 si no hay), (b) conteo por cada una de las 3 prioridades, (c) número de incidencias `CRITICA` con estado distinto de `CERRADA`, (d) porcentaje de cierre `CERRADAS / total * 100` con exactamente 1 decimal y sufijo `%` (ejemplo `25.0%`), calculado con `decimal.Decimal` y redondeo `ROUND_HALF_UP` (no con `round()` de float); con 0 incidencias, `0.0%`.

Salidas y cambios persistidos:
- Solo lectura: no se modifica ninguna tabla. Listado, detalle con historial y tablero (HTML y/o JSON).

Errores y efectos que deben evitarse:
- Mostrar incidencias ajenas a un Solicitante o Técnico (incluso adivinando el id en la URL).
- Filtros con valores inválidos que se ignoren en silencio o rompan la consulta (inyección SQL: usar parámetros).
- Permitir modificar o eliminar historial por cualquier vía.
- División por cero en el porcentaje; formato distinto de 1 decimal.
- Acceso de no-Coordinador al tablero.

AC-S05-01: Dados el Solicitante A con 2 incidencias, el Solicitante B con 1, y 3 incidencias en total asignadas así: 2 al Técnico T1 (una de ellas de A) y 1 al Técnico T2, Cuando A, B, T1 y el Coordinador consultan el listado, Entonces A ve solo sus 2, B solo la suya, T1 solo sus 2 asignadas y el Coordinador ve las 3 del sistema; y A que pide el detalle de una incidencia de B recibe 403.
AC-S05-02: Dado el Coordinador con incidencias en varios estados y prioridades, Cuando filtra `estado=EN_ATENCION`, `prioridad=CRITICA` y ambos a la vez, Entonces recibe solo las que cumplen cada condición (AND); y un valor `estado=ABIERTA` responde 400.
AC-S05-03: Dada una incidencia que fue asignada, atendida, rechazada, vuelta a atender, cerrada y reabierta, Cuando un usuario autorizado ve el detalle, Entonces el historial muestra todas las entradas en orden cronológico con autor, fecha UTC, estado inicial/final y acción, junto con todas las soluciones, motivos y cierres; y un `UPDATE` o `DELETE` directo sobre `historial` falla por trigger sin modificar filas.
AC-S05-04: Dado el Coordinador con 8 incidencias (3 `CRITICA`, de ellas 1 `CERRADA`), Cuando abre el tablero, Entonces ve el conteo correcto por cada estado y por cada prioridad (incluyendo ceros) y "críticas no cerradas = 2".
AC-S05-05: Dado el tablero, Cuando hay 8 incidencias con 2 `CERRADA`, Entonces el porcentaje es `25.0%`; con 1 de 3 es `33.3%`; con 1 de 16 es `6.3%` (6.25 redondeado half-up); con 0 incidencias es `0.0%` sin error; y un Solicitante o Técnico que accede al tablero recibe 403.

Diseño y tareas vinculadas a cada AC:
- Módulos: `models/consultas.py` (`listar_incidencias(usuario, estado, prioridad)`, `obtener_detalle(usuario, id)`), `models/tablero.py` (`calcular_tablero`), `routes/consultas.py` (`GET /incidencias`, `GET /incidencias/<id>`, `GET /tablero`), `schema.sql` (triggers de inmutabilidad), `templates/incidencias_lista.html`, `incidencia_detalle.html`, `tablero.html`.
- AC-01: filtro de rol en SQL parametrizado. AC-02: validación de filtros. AC-03: join de historial/soluciones/motivos/cierres + triggers. AC-04/05: agregaciones SQL + `f"{pct:.1f}%"`.

Pruebas y resultados esperados:
- `test_visibilidad_por_rol` y `test_detalle_ajeno_403` (AC-01), `test_filtros_estado_prioridad_y_invalido` (AC-02), `test_historial_completo_orden` y `test_historial_inmutable_triggers` (AC-03), `test_tablero_conteos_y_criticas` (AC-04), `test_porcentaje_formato_redondeo_y_cero_registros` parametrizada y `test_tablero_solo_coordinador` (AC-05).
- Resultado esperado: verde; las consultas no alteran ninguna tabla.

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
