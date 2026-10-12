"""ReparaCampus · servidor Flask y lógica de negocio.

Estructura de permisos (todo se verifica en el servidor):
  1. login_required / roles_required: rol exigido por cada endpoint. El rol se lee
     de la base de datos en cada petición, nunca del cliente.
  2. puede_ver(): una incidencia solo es visible para su autor, su técnico
     asignado o el coordinador. Se comprueba antes de ejecutar cualquier acción.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

import db as database
from db import get_db
from seed import CUENTAS_SEMILLA

# --------------------------------------------------------------------------
# Dominio
# --------------------------------------------------------------------------
UBICACIONES = ("LAB-01", "AULA-201", "BIB-01")
CATEGORIAS = ("ELECTRICIDAD", "HIDRAULICA", "MOBILIARIO", "TIC")
IMPACTOS = ("BAJO", "ALTO")
ESTADOS = ("REGISTRADA", "ASIGNADA", "EN_ATENCION", "PENDIENTE_VALIDACION", "CERRADA")
PRIORIDADES = ("CRITICA", "ALTA", "NORMAL")

DESCRIPCION_MIN, DESCRIPCION_MAX = 20, 500
SOLUCION_MIN, SOLUCION_MAX = 20, 800
MOTIVO_MIN, MOTIVO_MAX = 10, 300
VENTANA_REAPERTURA_HORAS = 48

# Únicas transiciones permitidas: (estado actual, estado nuevo) -> acción en historial.
TRANSICIONES = {
    ("REGISTRADA", "ASIGNADA"): "ASIGNAR",
    ("ASIGNADA", "EN_ATENCION"): "ATENDER",
    ("EN_ATENCION", "PENDIENTE_VALIDACION"): "RESOLVER",
    ("PENDIENTE_VALIDACION", "CERRADA"): "CONFIRMAR",
    ("PENDIENTE_VALIDACION", "EN_ATENCION"): "RECHAZAR",
    ("CERRADA", "EN_ATENCION"): "REABRIR",
}

ESTADO_CLASES = {
    "REGISTRADA": "text-bg-secondary",
    "ASIGNADA": "text-bg-info",
    "EN_ATENCION": "text-bg-warning",
    "PENDIENTE_VALIDACION": "text-bg-primary",
    "CERRADA": "text-bg-success",
}
PRIORIDAD_CLASES = {
    "CRITICA": "text-bg-danger",
    "ALTA": "rc-badge-alta",
    "NORMAL": "text-bg-secondary",
}


class ErrorNegocio(Exception):
    """Regla de negocio incumplida; lleva el código HTTP que corresponde."""

    def __init__(self, status, mensaje):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje


# --------------------------------------------------------------------------
# Utilidades puras (fáciles de probar)
# --------------------------------------------------------------------------
def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def a_iso(momento):
    return momento.isoformat()


def desde_iso(texto):
    return datetime.fromisoformat(texto)


def calcular_prioridad(impacto, riesgo):
    """Riesgo para personas => CRITICA; si no, ALTA con impacto ALTO; si no, NORMAL."""
    if riesgo:
        return "CRITICA"
    return "ALTA" if impacto == "ALTO" else "NORMAL"


def formatear_porcentaje(cerradas, total):
    """(cerradas / total) * 100 con exactamente un decimal; 0.0% si no hay registros."""
    if total == 0:
        return "0.0%"
    valor = (Decimal(cerradas) * 100 / Decimal(total)).quantize(Decimal("0.1"), ROUND_HALF_UP)
    return f"{valor}%"


def normalizar_texto(valor):
    """Retira espacios externos y unifica saltos de línea (los navegadores envían \\r\\n)."""
    return (valor or "").replace("\r\n", "\n").strip()


def error_longitud(texto, minimo, maximo, etiqueta):
    if not minimo <= len(texto) <= maximo:
        return f"{etiqueta} debe tener entre {minimo} y {maximo} caracteres."
    return None


def validar_incidencia(form):
    """Valida el formulario de RF01. Devuelve (datos, errores); sin errores => datos válidos."""
    errores = []
    ubicacion = (form.get("ubicacion") or "").strip()
    categoria = (form.get("categoria") or "").strip()
    impacto = (form.get("impacto") or "").strip()
    riesgo_txt = (form.get("riesgo") or "").strip().lower()
    descripcion = normalizar_texto(form.get("descripcion"))

    if ubicacion not in UBICACIONES:
        errores.append("Selecciona una ubicación válida.")
    if categoria not in CATEGORIAS:
        errores.append("Selecciona una categoría válida.")
    if impacto not in IMPACTOS:
        errores.append("Selecciona un impacto válido (BAJO o ALTO).")
    if riesgo_txt not in ("true", "false"):
        errores.append("Indica si existe riesgo para las personas.")
    mensaje = error_longitud(descripcion, DESCRIPCION_MIN, DESCRIPCION_MAX, "La descripción")
    if mensaje:
        errores.append(mensaje)

    datos = {
        "ubicacion": ubicacion, "categoria": categoria, "descripcion": descripcion,
        "impacto": impacto, "riesgo": riesgo_txt == "true",
    }
    return datos, errores


def dentro_ventana_reapertura(inc):
    """True si la incidencia está CERRADA y han pasado <= 48 h (UTC, reloj del servidor)."""
    if inc["estado"] != "CERRADA" or not inc["cerrada_en"]:
        return False
    transcurrido = utcnow() - desde_iso(inc["cerrada_en"])
    return transcurrido <= timedelta(hours=VENTANA_REAPERTURA_HORAS)


def limite_reapertura(inc):
    if not inc["cerrada_en"]:
        return None
    return a_iso(desde_iso(inc["cerrada_en"]) + timedelta(hours=VENTANA_REAPERTURA_HORAS))


# --------------------------------------------------------------------------
# Acceso a datos y operaciones atómicas
# --------------------------------------------------------------------------
CONSULTA_INCIDENCIA = """
    SELECT i.*, a.nombre AS autor_nombre, t.nombre AS tecnico_nombre
    FROM incidencias i
    JOIN usuarios a ON a.id = i.autor_id
    LEFT JOIN usuarios t ON t.id = i.tecnico_id
"""


def obtener_incidencia(db, inc_id):
    inc = db.execute(CONSULTA_INCIDENCIA + " WHERE i.id = ?", (inc_id,)).fetchone()
    if inc is None:
        abort(404)
    return inc


def puede_ver(usuario, inc):
    rol = usuario["rol"]
    if rol == "COORDINADOR":
        return True
    if rol == "SOLICITANTE":
        return inc["autor_id"] == usuario["id"]
    if rol == "TECNICO":
        return inc["tecnico_id"] == usuario["id"]
    return False


def listar_incidencias(db, usuario, estado="", prioridad="", texto=""):
    condiciones, parametros = [], []
    if usuario["rol"] == "SOLICITANTE":
        condiciones.append("i.autor_id = ?")
        parametros.append(usuario["id"])
    elif usuario["rol"] == "TECNICO":
        condiciones.append("i.tecnico_id = ?")
        parametros.append(usuario["id"])
    if estado in ESTADOS:
        condiciones.append("i.estado = ?")
        parametros.append(estado)
    if prioridad in PRIORIDADES:
        condiciones.append("i.prioridad = ?")
        parametros.append(prioridad)
    if texto:
        escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condiciones.append("(i.codigo LIKE ? ESCAPE '\\' OR i.descripcion LIKE ? ESCAPE '\\')")
        parametros.extend([f"%{escapado}%"] * 2)
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    return db.execute(
        CONSULTA_INCIDENCIA + donde + " ORDER BY i.creada_en DESC, i.id DESC", parametros
    ).fetchall()


def calcular_metricas(db):
    por_estado = {e: 0 for e in ESTADOS}
    for fila in db.execute("SELECT estado, COUNT(*) AS n FROM incidencias GROUP BY estado"):
        por_estado[fila["estado"]] = fila["n"]
    por_prioridad = {p: 0 for p in PRIORIDADES}
    for fila in db.execute("SELECT prioridad, COUNT(*) AS n FROM incidencias GROUP BY prioridad"):
        por_prioridad[fila["prioridad"]] = fila["n"]
    total = sum(por_estado.values())
    criticas_abiertas = db.execute(
        "SELECT COUNT(*) AS n FROM incidencias WHERE prioridad = 'CRITICA' AND estado != 'CERRADA'"
    ).fetchone()["n"]
    return {
        "total": total,
        "por_estado": por_estado,
        "por_prioridad": por_prioridad,
        "criticas_abiertas": criticas_abiertas,
        "porcentaje_cierre": formatear_porcentaje(por_estado["CERRADA"], total),
    }


def registrar_incidencia(db, autor_id, datos):
    """RF01: crea la incidencia y su primer registro de historial en una sola transacción."""
    ahora = a_iso(utcnow())
    codigo = "INC-" + uuid.uuid4().hex[:8].upper()
    try:
        cursor = db.execute(
            "INSERT INTO incidencias (codigo, ubicacion, categoria, descripcion, impacto, riesgo, "
            "prioridad, estado, autor_id, creada_en) VALUES (?, ?, ?, ?, ?, ?, ?, 'REGISTRADA', ?, ?)",
            (codigo, datos["ubicacion"], datos["categoria"], datos["descripcion"],
             datos["impacto"], int(datos["riesgo"]),
             calcular_prioridad(datos["impacto"], datos["riesgo"]), autor_id, ahora),
        )
        inc_id = cursor.lastrowid
        db.execute(
            "INSERT INTO historial (incidencia_id, autor_id, fecha, estado_inicial, estado_final, "
            "accion, detalle) VALUES (?, ?, ?, NULL, 'REGISTRADA', 'CREAR', NULL)",
            (inc_id, autor_id, ahora),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return inc_id


def aplicar_transicion(db, inc, estado_nuevo, autor_id, detalle=None,
                       tecnico_id=None, marcar_cierre=False):
    """Cambia el estado y escribe el historial en la misma transacción.

    Solo acepta transiciones de TRANSICIONES. El UPDATE exige que el estado siga
    siendo el leído, para que dos peticiones simultáneas no se pisen.
    """
    accion = TRANSICIONES.get((inc["estado"], estado_nuevo))
    if accion is None:
        raise ErrorNegocio(409, f"Transición no permitida: {inc['estado']} → {estado_nuevo}.")
    ahora = a_iso(utcnow())
    try:
        cursor = db.execute(
            "UPDATE incidencias SET estado = ?, tecnico_id = COALESCE(?, tecnico_id), "
            "cerrada_en = COALESCE(?, cerrada_en) WHERE id = ? AND estado = ?",
            (estado_nuevo, tecnico_id, ahora if marcar_cierre else None, inc["id"], inc["estado"]),
        )
        if cursor.rowcount != 1:
            raise ErrorNegocio(409, "La incidencia cambió de estado. Recarga la página e inténtalo de nuevo.")
        db.execute(
            "INSERT INTO historial (incidencia_id, autor_id, fecha, estado_inicial, estado_final, "
            "accion, detalle) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (inc["id"], autor_id, ahora, inc["estado"], estado_nuevo, accion, detalle),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


# --------------------------------------------------------------------------
# Decoradores de acceso
# --------------------------------------------------------------------------
def login_required(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return vista(*args, **kwargs)
    return envoltura


def roles_required(*roles):
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(*args, **kwargs):
            if g.user["rol"] not in roles:
                abort(403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador


# --------------------------------------------------------------------------
# Aplicación
# --------------------------------------------------------------------------
def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-solo-desarrollo-cambiar-en-produccion"),
        DATABASE=os.path.join(app.root_path, "reparacampus.db"),
        MOSTRAR_CREDENCIALES_DEMO=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    database.init_app(app)

    @app.before_request
    def cargar_usuario():
        g.user = None
        usuario_id = session.get("user_id")
        if usuario_id is not None:
            g.user = get_db().execute(
                "SELECT id, nombre, email, rol FROM usuarios WHERE id = ? AND activo = 1",
                (usuario_id,),
            ).fetchone()
            if g.user is None:
                session.clear()

    @app.context_processor
    def contexto_plantillas():
        return {"ESTADO_CLASES": ESTADO_CLASES, "PRIORIDAD_CLASES": PRIORIDAD_CLASES,
                "usuario": g.get("user")}

    @app.template_filter("fecha_utc")
    def fecha_utc(valor):
        return f"{valor[:16].replace('T', ' ')} UTC" if valor else "—"

    @app.template_filter("legible")
    def legible(valor):
        return (valor or "").replace("_", " ")

    @app.errorhandler(403)
    def prohibido(_error):
        return render_template("error.html", codigo=403, titulo="Acceso denegado",
                               mensaje="No tienes permiso para realizar esta acción."), 403

    @app.errorhandler(404)
    def no_encontrado(_error):
        return render_template("error.html", codigo=404, titulo="No encontrado",
                               mensaje="La página o la incidencia no existe."), 404

    # ---------------------------------------------------------------- sesión
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user is not None:
            return redirect(url_for("dashboard"))
        cuentas = CUENTAS_SEMILLA if app.config["MOSTRAR_CREDENCIALES_DEMO"] else []
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            fila = get_db().execute(
                "SELECT id, password_hash FROM usuarios WHERE email = ? AND activo = 1", (email,)
            ).fetchone()
            if fila is None or not check_password_hash(fila["password_hash"], password):
                flash("Correo o contraseña incorrectos.", "danger")
                return render_template("login.html", cuentas=cuentas), 401
            session.clear()
            session["user_id"] = fila["id"]
            return redirect(url_for("dashboard"))
        return render_template("login.html", cuentas=cuentas)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ---------------------------------------------------------------- tablero
    @app.get("/")
    @login_required
    def inicio():
        return redirect(url_for("dashboard"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        db = get_db()
        filtros = {
            "estado": request.args.get("estado", "").strip(),
            "prioridad": request.args.get("prioridad", "").strip(),
            "q": request.args.get("q", "").strip(),
        }
        incidencias = listar_incidencias(db, g.user, filtros["estado"],
                                         filtros["prioridad"], filtros["q"])
        metricas = calcular_metricas(db) if g.user["rol"] == "COORDINADOR" else None
        return render_template("dashboard.html", incidencias=incidencias, metricas=metricas,
                               filtros=filtros, estados=ESTADOS, prioridades=PRIORIDADES)

    # ------------------------------------------------------------ RF01 crear
    @app.route("/incidencias/nueva", methods=["GET", "POST"])
    @roles_required("SOLICITANTE")
    def nueva_incidencia():
        contexto = {"ubicaciones": UBICACIONES, "categorias": CATEGORIAS, "impactos": IMPACTOS,
                    "descripcion_min": DESCRIPCION_MIN, "descripcion_max": DESCRIPCION_MAX}
        if request.method == "GET":
            return render_template("crear_incidencia.html", form={}, errores=[], **contexto)
        datos, errores = validar_incidencia(request.form)
        if errores:
            return render_template("crear_incidencia.html", form=request.form,
                                   errores=errores, **contexto), 400
        inc_id = registrar_incidencia(get_db(), g.user["id"], datos)
        flash("Incidencia registrada correctamente.", "success")
        return redirect(url_for("detalle", inc_id=inc_id))

    # ------------------------------------------------------------- detalle
    def render_detalle(inc_id):
        db = get_db()
        inc = obtener_incidencia(db, inc_id)
        rol = g.user["rol"]
        es_dueno = rol == "SOLICITANTE" and inc["autor_id"] == g.user["id"]
        es_tecnico = rol == "TECNICO" and inc["tecnico_id"] == g.user["id"]
        historial = db.execute(
            "SELECT h.*, u.nombre AS autor_nombre FROM historial h "
            "JOIN usuarios u ON u.id = h.autor_id WHERE h.incidencia_id = ? ORDER BY h.id",
            (inc_id,),
        ).fetchall()
        ultima_solucion = next((h for h in reversed(historial) if h["accion"] == "RESOLVER"), None)
        puede_asignar = rol == "COORDINADOR" and inc["estado"] == "REGISTRADA"
        tecnicos = db.execute(
            "SELECT id, nombre FROM usuarios WHERE rol = 'TECNICO' AND activo = 1 ORDER BY nombre"
        ).fetchall() if puede_asignar else []
        return render_template(
            "detalle_incidencia.html", inc=inc, historial=historial,
            ultima_solucion=ultima_solucion, tecnicos=tecnicos,
            puede_asignar=puede_asignar,
            puede_atender=es_tecnico and inc["estado"] == "ASIGNADA",
            puede_resolver=es_tecnico and inc["estado"] == "EN_ATENCION",
            puede_validar=es_dueno and inc["estado"] == "PENDIENTE_VALIDACION",
            puede_reabrir=es_dueno and dentro_ventana_reapertura(inc),
            ventana_vencida=es_dueno and inc["estado"] == "CERRADA"
            and not dentro_ventana_reapertura(inc),
            limite_reapertura=limite_reapertura(inc),
            horas_ventana=VENTANA_REAPERTURA_HORAS,
            solucion_min=SOLUCION_MIN, solucion_max=SOLUCION_MAX,
            motivo_min=MOTIVO_MIN, motivo_max=MOTIVO_MAX,
        )

    @app.get("/incidencias/<int:inc_id>")
    @login_required
    def detalle(inc_id):
        inc = obtener_incidencia(get_db(), inc_id)
        if not puede_ver(g.user, inc):
            abort(403)
        return render_detalle(inc_id)

    def ejecutar_accion(inc_id, accion):
        """Carga la incidencia, exige visibilidad y ejecuta la acción de negocio."""
        db = get_db()
        inc = obtener_incidencia(db, inc_id)
        if not puede_ver(g.user, inc):
            abort(403)
        try:
            mensaje = accion(db, inc)
        except ErrorNegocio as error:
            flash(error.mensaje, "danger")
            return render_detalle(inc_id), error.status
        flash(mensaje, "success")
        return redirect(url_for("detalle", inc_id=inc_id))

    def exigir_estado(inc, esperado, texto):
        if inc["estado"] != esperado:
            raise ErrorNegocio(409, f"{texto} (estado actual: {inc['estado']}).")

    def leer_texto(campo, minimo, maximo, etiqueta):
        texto = normalizar_texto(request.form.get(campo))
        mensaje = error_longitud(texto, minimo, maximo, etiqueta)
        if mensaje:
            raise ErrorNegocio(400, mensaje)
        return texto

    # ----------------------------------------------------------- RF02 asignar
    @app.post("/incidencias/<int:inc_id>/asignar")
    @roles_required("COORDINADOR")
    def asignar(inc_id):
        def accion(db, inc):
            exigir_estado(inc, "REGISTRADA", "Solo se puede asignar una incidencia REGISTRADA")
            tecnico = db.execute(
                "SELECT id, nombre FROM usuarios WHERE id = ? AND rol = 'TECNICO' AND activo = 1",
                (request.form.get("tecnico_id", ""),),
            ).fetchone()
            if tecnico is None:
                raise ErrorNegocio(400, "Selecciona un técnico activo.")
            aplicar_transicion(db, inc, "ASIGNADA", g.user["id"],
                               detalle=f"Técnico asignado: {tecnico['nombre']}",
                               tecnico_id=tecnico["id"])
            return f"Incidencia asignada a {tecnico['nombre']}."
        return ejecutar_accion(inc_id, accion)

    # ----------------------------------------------------------- RF03 atender
    @app.post("/incidencias/<int:inc_id>/atender")
    @roles_required("TECNICO")
    def atender(inc_id):
        def accion(db, inc):
            exigir_estado(inc, "ASIGNADA", "Solo se puede atender una incidencia ASIGNADA")
            aplicar_transicion(db, inc, "EN_ATENCION", g.user["id"])
            return "Incidencia en atención."
        return ejecutar_accion(inc_id, accion)

    @app.post("/incidencias/<int:inc_id>/solucion")
    @roles_required("TECNICO")
    def registrar_solucion(inc_id):
        def accion(db, inc):
            exigir_estado(inc, "EN_ATENCION", "Solo se puede registrar la solución de una incidencia EN_ATENCION")
            solucion = leer_texto("solucion", SOLUCION_MIN, SOLUCION_MAX, "La solución")
            aplicar_transicion(db, inc, "PENDIENTE_VALIDACION", g.user["id"], detalle=solucion)
            return "Solución registrada. Queda pendiente de validación."
        return ejecutar_accion(inc_id, accion)

    # ---------------------------------------------------------- RF04 validar
    @app.post("/incidencias/<int:inc_id>/confirmar")
    @roles_required("SOLICITANTE")
    def confirmar(inc_id):
        def accion(db, inc):
            exigir_estado(inc, "PENDIENTE_VALIDACION", "Solo se puede confirmar una solución PENDIENTE_VALIDACION")
            aplicar_transicion(db, inc, "CERRADA", g.user["id"], marcar_cierre=True)
            return "Solución confirmada. La incidencia quedó cerrada."
        return ejecutar_accion(inc_id, accion)

    @app.post("/incidencias/<int:inc_id>/rechazar")
    @roles_required("SOLICITANTE")
    def rechazar(inc_id):
        def accion(db, inc):
            exigir_estado(inc, "PENDIENTE_VALIDACION", "Solo se puede rechazar una solución PENDIENTE_VALIDACION")
            motivo = leer_texto("motivo", MOTIVO_MIN, MOTIVO_MAX, "El motivo")
            aplicar_transicion(db, inc, "EN_ATENCION", g.user["id"], detalle=motivo)
            return "Solución rechazada. La incidencia volvió a atención."
        return ejecutar_accion(inc_id, accion)

    @app.post("/incidencias/<int:inc_id>/reabrir")
    @roles_required("SOLICITANTE")
    def reabrir(inc_id):
        def accion(db, inc):
            exigir_estado(inc, "CERRADA", "Solo se puede reabrir una incidencia CERRADA")
            if not dentro_ventana_reapertura(inc):
                raise ErrorNegocio(
                    409, f"Pasaron más de {VENTANA_REAPERTURA_HORAS} horas desde el cierre: "
                         "ya no se puede reabrir.")
            motivo = leer_texto("motivo", MOTIVO_MIN, MOTIVO_MAX, "El motivo")
            aplicar_transicion(db, inc, "EN_ATENCION", g.user["id"], detalle=motivo)
            return "Incidencia reabierta. Volvió a atención con el mismo técnico."
        return ejecutar_accion(inc_id, accion)

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
