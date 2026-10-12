# ReparaCampus · Especificaciones S01–S05 (borrador para revisión)

> Estado: **borrador v0.1**. Según la regla de oro del proyecto, el código de esta carpeta
> solo es válido cuando estas SPEC estén revisadas y aprobadas por el equipo.
> Cada AC tiene al menos una prueba en `test_app.py` (se indican entre paréntesis).

Convenciones comunes a todas las SPEC:
- Fechas en UTC (ISO 8601) tomadas del reloj del servidor.
- Códigos HTTP: 302 éxito (redirección al detalle), 400 dato inválido, 403 rol o propiedad incorrectos,
  404 incidencia inexistente, 409 transición no permitida o regla de tiempo incumplida.
- Una incidencia solo es visible para su autor, su técnico asignado y el coordinador.
- Estado e historial se guardan en la misma transacción; si falla uno, no se guarda ninguno.

---

## SPEC: S01 · Título: Registrar incidencia
Versión / autor / revisor / fecha: v0.1 / Diego García (con IA) / _pendiente_ / 2026-10-12
Requisito asociado: RF01
Historia: Como solicitante, quiero registrar una incidencia de infraestructura, para que el campus la atienda.
Alcance y exclusiones: Incluye validar y guardar la incidencia con su primer registro de historial. Excluye editar o borrar reportes, adjuntos y notificaciones.
Entradas:
- `ubicacion` (obligatoria): `LAB-01`, `AULA-201` o `BIB-01`.
- `categoria` (obligatoria): `ELECTRICIDAD`, `HIDRAULICA`, `MOBILIARIO` o `TIC`.
- `descripcion` (obligatoria): 20 a 500 caracteres tras retirar espacios externos.
- `impacto` (obligatoria): `BAJO` o `ALTO`.
- `riesgo` (obligatoria): `true` o `false`.
Precondiciones y permisos: Sesión iniciada con rol SOLICITANTE.
Reglas y proceso:
1. Verificar rol en el servidor.
2. Retirar espacios externos de la descripción y validar todos los campos.
3. Calcular la prioridad (ver S02) y generar código único, autor (de la sesión) y fecha UTC.
4. Guardar la incidencia en estado `REGISTRADA` y el historial `CREAR` en una transacción.
Salidas y cambios persistidos: Una fila en `incidencias` y una en `historial` (acción `CREAR`, estado inicial vacío, estado final `REGISTRADA`). Redirección al detalle.
Errores y efectos que deben evitarse: Cualquier valor inválido o faltante responde 400 y no guarda nada. Otros roles reciben 403. El texto nunca se interpreta como HTML.

AC-S01-01: Dado un solicitante con sesión ... Cuando envía datos válidos ... Entonces se crea la incidencia `REGISTRADA` con código único, su autor y fecha UTC, más un historial `CREAR`. (`test_registro_guarda_prioridad_y_primer_historial`, `test_registro_genera_codigo_unico_y_fecha_utc`)
AC-S01-02: Dado un solicitante ... Cuando la descripción mide 20, 500 o 20 más espacios externos ... Entonces se acepta. (`test_descripcion_en_los_limites_se_acepta`)
AC-S01-03: Dado un solicitante ... Cuando la descripción mide 19, 501 o solo espacios ... Entonces responde 400 y no se guarda nada. (`test_descripcion_fuera_de_limites_se_rechaza_sin_persistir`)
AC-S01-04: Dado un solicitante ... Cuando falta un campo o la ubicación, categoría, impacto o riesgo no es un valor permitido ... Entonces responde 400 y no se guarda nada. (`test_valores_invalidos_no_persisten`, `test_falta_de_campo_obligatorio_no_persiste`)
AC-S01-05: Dado un coordinador o un técnico ... Cuando intenta registrar ... Entonces responde 403; y si la descripción contiene HTML, se muestra escapado. (`test_solo_el_solicitante_registra`, `test_xss_se_escapa_en_el_detalle`)

Diseño y tareas vinculadas a cada AC: `schema.sql` (tablas y CHECK) · `app.py`: `validar_incidencia`, `registrar_incidencia`, ruta `/incidencias/nueva` · `templates/crear_incidencia.html`.
Pruebas y resultados esperados: pytest con cliente de Flask y SQLite temporal; los casos de borde 19/20/500/501 se parametrizan.
Decisión de revisión / versión aprobada: ☐ Aprobada ☐ Con cambios · Firmas: ____________

---

## SPEC: S02 · Título: Priorizar y asignar
Versión / autor / revisor / fecha: v0.1 / Diego García (con IA) / _pendiente_ / 2026-10-12
Requisito asociado: RF02
Historia: Como coordinador, quiero asignar un técnico a cada incidencia registrada, para que alguien la atienda según su prioridad.
Alcance y exclusiones: Incluye el cálculo automático de prioridad y la asignación inicial. Excluye reasignar técnicos, asignarse a sí mismo y editar la prioridad.
Entradas: `tecnico_id` (obligatorio): id de un usuario con rol TECNICO y activo. Para la prioridad: `impacto` y `riesgo` de la incidencia.
Precondiciones y permisos: Rol COORDINADOR; incidencia en `REGISTRADA`.
Reglas y proceso:
1. Prioridad: riesgo `true` → `CRITICA`; riesgo `false` e impacto `ALTO` → `ALTA`; riesgo `false` e impacto `BAJO` → `NORMAL`.
2. Verificar rol y estado `REGISTRADA`.
3. Verificar que el técnico existe, es TECNICO y está activo.
4. Pasar a `ASIGNADA` guardando el técnico y el historial `ASIGNAR`.
Salidas y cambios persistidos: `estado = ASIGNADA`, `tecnico_id` fijado, historial con el nombre del técnico asignado.
Errores y efectos que deben evitarse: Técnico inválido o inactivo → 400. Otro rol → 403. Estado distinto de `REGISTRADA` (incluida una reasignación) → 409.

AC-S02-01: Dados impacto y riesgo ... Cuando se calcula la prioridad ... Entonces riesgo `true` es CRITICA, riesgo `false` con ALTO es ALTA y con BAJO es NORMAL. (`test_calcular_prioridad`, `test_registro_guarda_prioridad_y_primer_historial`)
AC-S02-02: Dada una incidencia `REGISTRADA` ... Cuando el coordinador asigna un técnico activo ... Entonces pasa a `ASIGNADA` con ese técnico y un historial `ASIGNAR`. (`test_coordinador_asigna_tecnico_activo`)
AC-S02-03: Dada una incidencia `REGISTRADA` ... Cuando un solicitante o un técnico intenta asignar ... Entonces responde 403 y el estado no cambia. (`test_solo_el_coordinador_asigna`)
AC-S02-04: Dada una incidencia `REGISTRADA` ... Cuando se envía un técnico inactivo, inexistente, vacío o un usuario que no es técnico ... Entonces responde 400 y sigue `REGISTRADA`. (`test_no_se_asigna_tecnico_inactivo_ni_usuario_que_no_es_tecnico`)
AC-S02-05: Dada una incidencia ya `ASIGNADA` ... Cuando el coordinador intenta asignar otro técnico ... Entonces responde 409 y conserva el técnico original. (`test_no_hay_reasignacion_de_tecnico`)

Diseño y tareas vinculadas a cada AC: `app.py`: `calcular_prioridad`, `aplicar_transicion`, ruta `/incidencias/<id>/asignar` · `templates/detalle_incidencia.html` (formulario de asignación).
Pruebas y resultados esperados: unitaria parametrizada para la prioridad; integración para la asignación.
Decisión de revisión / versión aprobada: ☐ Aprobada ☐ Con cambios · Firmas: ____________

---

## SPEC: S03 · Título: Atender incidencia
Versión / autor / revisor / fecha: v0.1 / Diego García (con IA) / _pendiente_ / 2026-10-12
Requisito asociado: RF03
Historia: Como técnico, quiero iniciar la atención y registrar la solución, para que el solicitante pueda validarla.
Alcance y exclusiones: Incluye pasar a `EN_ATENCION` y registrar la solución. Excluye reasignar y editar soluciones ya registradas.
Entradas: `solucion` (obligatoria): 20 a 800 caracteres tras retirar espacios externos.
Precondiciones y permisos: Rol TECNICO y ser el técnico asignado. Atender exige `ASIGNADA`; registrar la solución exige `EN_ATENCION`.
Reglas y proceso:
1. Verificar rol, asignación y estado.
2. Atender: `ASIGNADA` → `EN_ATENCION` con historial `ATENDER`.
3. Registrar solución: validar longitud; `EN_ATENCION` → `PENDIENTE_VALIDACION` con historial `RESOLVER` que guarda el texto.
Salidas y cambios persistidos: Nuevo estado y entrada de historial en una sola transacción.
Errores y efectos que deben evitarse: Técnico no asignado → 403. Estado incorrecto → 409. Solución fuera de rango → 400 sin cambios. Si falla el historial, el estado no cambia.

AC-S03-01: Dada una incidencia `ASIGNADA` ... Cuando el técnico asignado la atiende ... Entonces pasa a `EN_ATENCION` con historial `ATENDER`. (`test_flujo_completo_hasta_cerrada_con_historial`)
AC-S03-02: Dada una incidencia `ASIGNADA` ... Cuando otro técnico intenta atenderla ... Entonces responde 403 y sigue `ASIGNADA`. (`test_tecnico_no_asignado_no_puede_atender`)
AC-S03-03: Dada una incidencia `EN_ATENCION` ... Cuando el técnico registra una solución de 20 a 800 caracteres ... Entonces pasa a `PENDIENTE_VALIDACION` y el historial guarda la solución. (`test_flujo_completo_hasta_cerrada_con_historial`, `test_limites_de_la_solucion`)
AC-S03-04: Dada una incidencia `EN_ATENCION` ... Cuando la solución mide 19 u 801 caracteres ... Entonces responde 400 y sigue `EN_ATENCION`. (`test_limites_de_la_solucion`)
AC-S03-05: Dada una incidencia `ASIGNADA` ... Cuando el técnico intenta registrar la solución sin haberla atendido, o falla el guardado del historial ... Entonces responde 409 (o el error de base de datos) y el estado no cambia. (`test_no_se_puede_resolver_sin_atender`, `test_estado_e_historial_se_guardan_juntos`)

Diseño y tareas vinculadas a cada AC: `app.py`: rutas `/atender` y `/solucion`, `aplicar_transicion` (UPDATE condicionado al estado + INSERT en una transacción) · `templates/detalle_incidencia.html`.
Pruebas y resultados esperados: integración con pytest; el AC-S03-05 fuerza un fallo con un trigger temporal.
Decisión de revisión / versión aprobada: ☐ Aprobada ☐ Con cambios · Firmas: ____________

---

## SPEC: S04 · Título: Validar y reabrir incidencia
Versión / autor / revisor / fecha: v0.1 / Diego García (con IA) / _pendiente_ / 2026-10-12
Requisito asociado: RF04
Historia: Como solicitante, quiero confirmar, rechazar o reabrir la solución de mi incidencia, para asegurar que el problema quedó resuelto.
Alcance y exclusiones: Incluye confirmar, rechazar y reabrir. Excluye el cierre automático y cambiar de técnico al reabrir.
Entradas: `motivo` (obligatorio en rechazar y reabrir): 10 a 300 caracteres tras retirar espacios externos.
Precondiciones y permisos: Rol SOLICITANTE y ser el autor de la incidencia. Confirmar y rechazar exigen `PENDIENTE_VALIDACION`; reabrir exige `CERRADA`.
Reglas y proceso:
1. Confirmar: `PENDIENTE_VALIDACION` → `CERRADA`; se guarda la fecha del cierre.
2. Rechazar: validar motivo; → `EN_ATENCION` con el mismo técnico; el historial conserva la solución previa y el motivo.
3. Reabrir: si (ahora UTC − último cierre) ≤ 48 horas, validar motivo y pasar a `EN_ATENCION` con el mismo técnico; si no, rechazar. Cada cierre actualiza el «último cierre».
Salidas y cambios persistidos: Nuevo estado, `cerrada_en` al confirmar y entrada de historial (`CONFIRMAR`, `RECHAZAR` o `REABRIR`).
Errores y efectos que deben evitarse: Otro solicitante o rol → 403. Estado incorrecto o pasadas más de 48 horas → 409. Motivo inválido → 400. Nunca se usa la hora del cliente.

AC-S04-01: Dada una incidencia `PENDIENTE_VALIDACION` ... Cuando su solicitante la confirma ... Entonces pasa a `CERRADA` y se guarda la fecha de cierre. (`test_flujo_completo_hasta_cerrada_con_historial`)
AC-S04-02: Dada una incidencia `PENDIENTE_VALIDACION` ... Cuando otro solicitante, un técnico o el coordinador intenta confirmarla ... Entonces responde 403 y no cambia. (`test_solo_el_solicitante_dueno_confirma`)
AC-S04-03: Dada una incidencia `PENDIENTE_VALIDACION` ... Cuando su solicitante la rechaza con un motivo de 10 a 300 caracteres ... Entonces vuelve a `EN_ATENCION` con el mismo técnico y el historial conserva solución y motivo. (`test_rechazo_vuelve_a_en_atencion_y_conserva_solucion_y_motivo`, `test_motivo_de_rechazo_fuera_de_limites`)
AC-S04-04: Dada una incidencia `CERRADA` ... Cuando su solicitante la reabre con motivo válido y han pasado 48 horas exactas o menos ... Entonces vuelve a `EN_ATENCION` con el mismo técnico y un historial `REABRIR`. (`test_reapertura_exactamente_a_las_48_horas_se_acepta`, `test_el_ultimo_cierre_reinicia_la_ventana`)
AC-S04-05: Dada una incidencia `CERRADA` ... Cuando han pasado más de 48 horas (por ejemplo 48 h y 1 s) ... Entonces responde 409, sigue `CERRADA` y no se agrega historial. (`test_reapertura_pasadas_48_horas_se_rechaza`, `test_el_detalle_oculta_el_boton_de_reabrir_tras_48_horas`)

Diseño y tareas vinculadas a cada AC: `app.py`: `dentro_ventana_reapertura`, rutas `/confirmar`, `/rechazar`, `/reabrir` · `templates/detalle_incidencia.html`.
Pruebas y resultados esperados: el reloj se fija con `monkeypatch` sobre `app.utcnow`; se prueban los bordes de 48 h y 48 h + 1 s.
Decisión de revisión / versión aprobada: ☐ Aprobada ☐ Con cambios · Firmas: ____________
Nota de revisión: el código HTTP elegido para «ventana vencida» es 409; si el equipo prefiere 403 o 422, solo cambia una línea en `reabrir`.

---

## SPEC: S05 · Título: Consultar, historizar y tablero
Versión / autor / revisor / fecha: v0.1 / Diego García (con IA) / _pendiente_ / 2026-10-12
Requisito asociado: RF05
Historia: Como coordinador, quiero consultar incidencias, ver su historial y un tablero de métricas, para supervisar el estado del campus.
Alcance y exclusiones: Incluye listados con filtros y búsqueda, historial inmutable y tablero del coordinador. Excluye exportar datos y gráficos.
Entradas: Filtros opcionales `estado`, `prioridad` y `q` (código o texto de la descripción) por la URL.
Precondiciones y permisos: Sesión iniciada. Solicitante: solo las propias. Técnico: solo las asignadas. Coordinador: todas y el tablero.
Reglas y proceso:
1. Listar según el rol, aplicando filtros (valores desconocidos se ignoran).
2. Cada creación y transición guarda en el historial autor, fecha, estados inicial y final, acción y detalle (solución o motivo).
3. Tablero: conteo por estado y por prioridad, críticas no cerradas y porcentaje de cierre `(CERRADAS / total) × 100` con un decimal; `0.0%` sin registros.
Salidas y cambios persistidos: Solo lectura; el historial no se edita ni se borra (triggers `RAISE(ABORT)`).
Errores y efectos que deben evitarse: Ver una incidencia ajena → 403; el rol nunca viene del cliente; el tablero no se muestra a otros roles.

AC-S05-01: Dado un solicitante ... Cuando consulta una incidencia ajena o el listado ... Entonces recibe 403 en la ajena y solo ve las suyas en el listado. (`test_el_solicitante_solo_ve_sus_incidencias`)
AC-S05-02: Dado un técnico ... Cuando consulta incidencias ... Entonces solo ve las que tiene asignadas. (`test_el_tecnico_solo_ve_sus_asignadas`)
AC-S05-03: Dado un coordinador ... Cuando filtra por estado y prioridad ... Entonces ve todas las incidencias que coinciden. (`test_el_coordinador_ve_todas_y_filtra_por_estado_y_prioridad`)
AC-S05-04: Dado el historial de una incidencia ... Cuando se intenta editar o borrar una entrada ... Entonces la base lo rechaza y el historial conserva solución, motivos, cierres y reaperturas. (`test_el_historial_es_inmutable`, `test_flujo_completo_hasta_cerrada_con_historial`)
AC-S05-05: Dado el tablero del coordinador ... Cuando hay 4 incidencias y 1 cerrada ... Entonces muestra `25.0%`, las críticas no cerradas y los conteos; y con 0 registros muestra `0.0%`. (`test_tablero_del_coordinador_con_metricas`, `test_tablero_del_coordinador_sin_registros`, `test_formato_del_porcentaje_de_cierre`)

Diseño y tareas vinculadas a cada AC: `app.py`: `listar_incidencias`, `puede_ver`, `calcular_metricas`, `formatear_porcentaje`, ruta `/dashboard` · `schema.sql` (triggers) · `templates/dashboard.html`, `detalle_incidencia.html`.
Pruebas y resultados esperados: integración por rol; unitarias parametrizadas para el formato del porcentaje.
Decisión de revisión / versión aprobada: ☐ Aprobada ☐ Con cambios · Firmas: ____________
