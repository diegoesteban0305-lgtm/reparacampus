"""Pruebas de ReparaCampus.

Cada prueba usa su propia base SQLite temporal y el cliente de pruebas de Flask.
Ejecutar:  pytest -v
"""
import sqlite3
from datetime import timedelta
from types import SimpleNamespace

import pytest

import app as app_module
from app import (ESTADOS, calcular_prioridad, create_app, desde_iso,
                 formatear_porcentaje)
from db import get_db, init_db
from seed import CUENTAS_SEMILLA, seed_db

PASSWORDS = {c["email"]: c["password"] for c in CUENTAS_SEMILLA}
SOLIC1, SOLIC2 = "solicitante1@usb.edu.co", "solicitante2@usb.edu.co"
COORD = "coordinador@usb.edu.co"
TEC1, TEC2 = "tecnico1@usb.edu.co", "tecnico2@usb.edu.co"

DATOS_OK = {
    "ubicacion": "LAB-01",
    "categoria": "ELECTRICIDAD",
    "descripcion": "Tomacorriente del laboratorio sin energía desde ayer.",
    "impacto": "BAJO",
    "riesgo": "false",
}
SOLUCION_OK = "Se reemplazó el tomacorriente y se verificó el voltaje."
MOTIVO_OK = "El equipo sigue sin funcionar."


# --------------------------------------------------------------------------
# Fixtures y ayudas
# --------------------------------------------------------------------------
@pytest.fixture
def app(tmp_path):
    aplicacion = create_app({
        "TESTING": True,
        "SECRET_KEY": "clave-de-pruebas",
        "DATABASE": str(tmp_path / "test.db"),
    })
    with aplicacion.app_context():
        init_db()
        seed_db(get_db(), metodo="pbkdf2:sha256:1000")  # hash liviano: acelera los logins
    return aplicacion


def consultar(app, sql, params=()):
    with app.app_context():
        return [dict(fila) for fila in get_db().execute(sql, params).fetchall()]


def usuario_id(app, email):
    return consultar(app, "SELECT id FROM usuarios WHERE email = ?", (email,))[0]["id"]


@pytest.fixture
def entrar(app):
    def _entrar(email):
        cliente = app.test_client()
        respuesta = cliente.post("/login", data={"email": email, "password": PASSWORDS[email]})
        assert respuesta.status_code == 302
        return cliente
    return _entrar


@pytest.fixture
def esc(app, entrar):
    """Escenario con un cliente autenticado por cada cuenta semilla."""
    e = SimpleNamespace(app=app)
    e.sol, e.sol2, e.coord, e.tec1, e.tec2 = (
        entrar(c) for c in (SOLIC1, SOLIC2, COORD, TEC1, TEC2))

    def crear(**cambios):
        respuesta = e.sol.post("/incidencias/nueva", data={**DATOS_OK, **cambios})
        assert respuesta.status_code == 302
        return consultar(app, "SELECT id FROM incidencias ORDER BY id DESC LIMIT 1")[0]["id"]

    def avanzar(hasta, **cambios):
        """Crea una incidencia y la lleva por el flujo normal hasta el estado pedido."""
        inc = crear(**cambios)
        objetivo = ESTADOS.index(hasta)
        if objetivo >= 1:
            assert e.coord.post(f"/incidencias/{inc}/asignar",
                                data={"tecnico_id": usuario_id(app, TEC1)}).status_code == 302
        if objetivo >= 2:
            assert e.tec1.post(f"/incidencias/{inc}/atender").status_code == 302
        if objetivo >= 3:
            assert e.tec1.post(f"/incidencias/{inc}/solucion",
                               data={"solucion": SOLUCION_OK}).status_code == 302
        if objetivo >= 4:
            assert e.sol.post(f"/incidencias/{inc}/confirmar").status_code == 302
        assert e.estado(inc) == hasta
        return inc

    e.crear = crear
    e.avanzar = avanzar
    e.estado = lambda inc: consultar(app, "SELECT estado FROM incidencias WHERE id = ?", (inc,))[0]["estado"]
    e.fila = lambda inc: consultar(app, "SELECT * FROM incidencias WHERE id = ?", (inc,))[0]
    e.historial = lambda inc: consultar(
        app, "SELECT * FROM historial WHERE incidencia_id = ? ORDER BY id", (inc,))
    e.total = lambda: consultar(app, "SELECT COUNT(*) AS n FROM incidencias")[0]["n"]
    return e


def fijar_ahora(monkeypatch, momento):
    monkeypatch.setattr(app_module, "utcnow", lambda: momento)


# --------------------------------------------------------------------------
# Autenticación y acceso
# --------------------------------------------------------------------------
def test_login_correcto_redirige_al_tablero(app):
    cliente = app.test_client()
    respuesta = cliente.post("/login", data={"email": SOLIC1, "password": PASSWORDS[SOLIC1]})
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/dashboard")


def test_login_con_clave_incorrecta_devuelve_401(app):
    respuesta = app.test_client().post("/login", data={"email": SOLIC1, "password": "mala"})
    assert respuesta.status_code == 401


def test_las_contrasenas_se_guardan_con_hash(app):
    hashes = [f["password_hash"] for f in consultar(app, "SELECT password_hash FROM usuarios")]
    assert len(hashes) == 5
    assert all(h not in PASSWORDS.values() and ":" in h for h in hashes)


def test_ruta_protegida_sin_sesion_redirige_a_login(app):
    respuesta = app.test_client().get("/dashboard")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_el_rol_no_se_toma_del_cliente(esc):
    esc.crear()
    respuesta = esc.sol.get("/dashboard?rol=COORDINADOR")
    assert b"Porcentaje de cierre" not in respuesta.data
    assert esc.sol.post("/incidencias/1/asignar", data={"tecnico_id": "1", "rol": "COORDINADOR"}
                        ).status_code == 403


# --------------------------------------------------------------------------
# RF01 · Registrar incidencia
# --------------------------------------------------------------------------
@pytest.mark.parametrize("impacto, riesgo, esperada", [
    ("BAJO", True, "CRITICA"), ("ALTO", True, "CRITICA"),
    ("ALTO", False, "ALTA"), ("BAJO", False, "NORMAL"),
])
def test_calcular_prioridad(impacto, riesgo, esperada):
    assert calcular_prioridad(impacto, riesgo) == esperada


@pytest.mark.parametrize("impacto, riesgo, esperada", [
    ("ALTO", "true", "CRITICA"), ("ALTO", "false", "ALTA"), ("BAJO", "false", "NORMAL"),
])
def test_registro_guarda_prioridad_y_primer_historial(esc, impacto, riesgo, esperada):
    inc = esc.crear(impacto=impacto, riesgo=riesgo)
    fila = esc.fila(inc)
    assert fila["prioridad"] == esperada
    assert fila["estado"] == "REGISTRADA"
    assert fila["autor_id"] == usuario_id(esc.app, SOLIC1)
    assert fila["tecnico_id"] is None
    historial = esc.historial(inc)
    assert len(historial) == 1
    assert (historial[0]["accion"], historial[0]["estado_inicial"],
            historial[0]["estado_final"]) == ("CREAR", None, "REGISTRADA")


def test_registro_genera_codigo_unico_y_fecha_utc(esc):
    a, b = esc.crear(), esc.crear()
    fila_a, fila_b = esc.fila(a), esc.fila(b)
    assert fila_a["codigo"] != fila_b["codigo"]
    assert desde_iso(fila_a["creada_en"]).utcoffset() == timedelta(0)


@pytest.mark.parametrize("descripcion", [
    "a" * 20, "a" * 500, "   " + "a" * 20 + "   ",
])
def test_descripcion_en_los_limites_se_acepta(esc, descripcion):
    inc = esc.crear(descripcion=descripcion)
    assert esc.fila(inc)["descripcion"] == descripcion.strip()


@pytest.mark.parametrize("descripcion", ["a" * 19, "a" * 501, "   " + "a" * 19 + "   ", "     "])
def test_descripcion_fuera_de_limites_se_rechaza_sin_persistir(esc, descripcion):
    respuesta = esc.sol.post("/incidencias/nueva", data={**DATOS_OK, "descripcion": descripcion})
    assert respuesta.status_code == 400
    assert esc.total() == 0


@pytest.mark.parametrize("campo, valor", [
    ("ubicacion", "LAB-99"), ("categoria", "JARDINERIA"), ("impacto", "MEDIO"),
    ("riesgo", "quizas"), ("riesgo", ""), ("ubicacion", ""),
])
def test_valores_invalidos_no_persisten(esc, campo, valor):
    respuesta = esc.sol.post("/incidencias/nueva", data={**DATOS_OK, campo: valor})
    assert respuesta.status_code == 400
    assert esc.total() == 0


def test_falta_de_campo_obligatorio_no_persiste(esc):
    datos = {k: v for k, v in DATOS_OK.items() if k != "categoria"}
    assert esc.sol.post("/incidencias/nueva", data=datos).status_code == 400
    assert esc.total() == 0


@pytest.mark.parametrize("cliente", ["coord", "tec1"])
def test_solo_el_solicitante_registra(esc, cliente):
    respuesta = getattr(esc, cliente).post("/incidencias/nueva", data=DATOS_OK)
    assert respuesta.status_code == 403
    assert esc.total() == 0


def test_xss_se_escapa_en_el_detalle(esc):
    inc = esc.crear(descripcion="<script>alert('xss')</script> aviso al personal")
    cuerpo = esc.sol.get(f"/incidencias/{inc}").data
    assert b"<script>alert" not in cuerpo
    assert b"&lt;script&gt;alert" in cuerpo


# --------------------------------------------------------------------------
# RF02 · Asignar
# --------------------------------------------------------------------------
def test_coordinador_asigna_tecnico_activo(esc):
    inc = esc.crear()
    tecnico = usuario_id(esc.app, TEC1)
    assert esc.coord.post(f"/incidencias/{inc}/asignar",
                          data={"tecnico_id": tecnico}).status_code == 302
    fila = esc.fila(inc)
    assert (fila["estado"], fila["tecnico_id"]) == ("ASIGNADA", tecnico)
    assert [h["accion"] for h in esc.historial(inc)] == ["CREAR", "ASIGNAR"]


@pytest.mark.parametrize("cliente", ["sol", "tec1"])
def test_solo_el_coordinador_asigna(esc, cliente):
    inc = esc.crear()
    respuesta = getattr(esc, cliente).post(f"/incidencias/{inc}/asignar",
                                           data={"tecnico_id": usuario_id(esc.app, TEC1)})
    assert respuesta.status_code == 403
    assert esc.estado(inc) == "REGISTRADA"


def test_no_se_asigna_tecnico_inactivo_ni_usuario_que_no_es_tecnico(esc):
    inc = esc.crear()
    with esc.app.app_context():
        get_db().execute("UPDATE usuarios SET activo = 0 WHERE email = ?", (TEC2,))
        get_db().commit()
    for objetivo in (usuario_id(esc.app, TEC2), usuario_id(esc.app, SOLIC2), "", "abc"):
        respuesta = esc.coord.post(f"/incidencias/{inc}/asignar", data={"tecnico_id": objetivo})
        assert respuesta.status_code == 400
    assert esc.estado(inc) == "REGISTRADA"


def test_no_hay_reasignacion_de_tecnico(esc):
    inc = esc.avanzar("ASIGNADA")
    respuesta = esc.coord.post(f"/incidencias/{inc}/asignar",
                               data={"tecnico_id": usuario_id(esc.app, TEC2)})
    assert respuesta.status_code == 409
    assert esc.fila(inc)["tecnico_id"] == usuario_id(esc.app, TEC1)


# --------------------------------------------------------------------------
# RF03 · Atender
# --------------------------------------------------------------------------
def test_tecnico_no_asignado_no_puede_atender(esc):
    inc = esc.avanzar("ASIGNADA")
    assert esc.tec2.post(f"/incidencias/{inc}/atender").status_code == 403
    assert esc.estado(inc) == "ASIGNADA"


def test_flujo_completo_hasta_cerrada_con_historial(esc):
    inc = esc.avanzar("CERRADA")
    historial = esc.historial(inc)
    assert [h["accion"] for h in historial] == [
        "CREAR", "ASIGNAR", "ATENDER", "RESOLVER", "CONFIRMAR"]
    assert [h["estado_final"] for h in historial] == [
        "REGISTRADA", "ASIGNADA", "EN_ATENCION", "PENDIENTE_VALIDACION", "CERRADA"]
    assert historial[3]["detalle"] == SOLUCION_OK
    assert esc.fila(inc)["cerrada_en"] is not None


@pytest.mark.parametrize("solucion, codigo", [("a" * 19, 400), ("a" * 801, 400), ("a" * 20, 302), ("a" * 800, 302)])
def test_limites_de_la_solucion(esc, solucion, codigo):
    inc = esc.avanzar("EN_ATENCION")
    respuesta = esc.tec1.post(f"/incidencias/{inc}/solucion", data={"solucion": solucion})
    assert respuesta.status_code == codigo
    assert esc.estado(inc) == ("PENDIENTE_VALIDACION" if codigo == 302 else "EN_ATENCION")


def test_no_se_puede_resolver_sin_atender(esc):
    inc = esc.avanzar("ASIGNADA")
    respuesta = esc.tec1.post(f"/incidencias/{inc}/solucion", data={"solucion": SOLUCION_OK})
    assert respuesta.status_code == 409
    assert esc.estado(inc) == "ASIGNADA"


# --------------------------------------------------------------------------
# RF04 · Validar y reabrir
# --------------------------------------------------------------------------
@pytest.mark.parametrize("cliente, codigo", [("sol2", 403), ("tec1", 403), ("coord", 403)])
def test_solo_el_solicitante_dueno_confirma(esc, cliente, codigo):
    inc = esc.avanzar("PENDIENTE_VALIDACION")
    assert getattr(esc, cliente).post(f"/incidencias/{inc}/confirmar").status_code == codigo
    assert esc.estado(inc) == "PENDIENTE_VALIDACION"


def test_rechazo_vuelve_a_en_atencion_y_conserva_solucion_y_motivo(esc):
    inc = esc.avanzar("PENDIENTE_VALIDACION")
    assert esc.sol.post(f"/incidencias/{inc}/rechazar", data={"motivo": MOTIVO_OK}).status_code == 302
    fila = esc.fila(inc)
    assert (fila["estado"], fila["tecnico_id"]) == ("EN_ATENCION", usuario_id(esc.app, TEC1))
    historial = esc.historial(inc)
    assert historial[3]["detalle"] == SOLUCION_OK
    assert (historial[-1]["accion"], historial[-1]["detalle"]) == ("RECHAZAR", MOTIVO_OK)


@pytest.mark.parametrize("motivo", ["a" * 9, "a" * 301, "   "])
def test_motivo_de_rechazo_fuera_de_limites(esc, motivo):
    inc = esc.avanzar("PENDIENTE_VALIDACION")
    assert esc.sol.post(f"/incidencias/{inc}/rechazar", data={"motivo": motivo}).status_code == 400
    assert esc.estado(inc) == "PENDIENTE_VALIDACION"


def test_transiciones_no_permitidas_devuelven_409(esc):
    registrada = esc.crear()
    assert esc.sol.post(f"/incidencias/{registrada}/confirmar").status_code == 409
    asignada = esc.avanzar("ASIGNADA")
    assert esc.sol.post(f"/incidencias/{asignada}/confirmar").status_code == 409
    assert esc.sol.post(f"/incidencias/{asignada}/reabrir", data={"motivo": MOTIVO_OK}).status_code == 409
    assert esc.estado(registrada) == "REGISTRADA" and esc.estado(asignada) == "ASIGNADA"


def test_reapertura_exactamente_a_las_48_horas_se_acepta(esc, monkeypatch):
    inc = esc.avanzar("CERRADA")
    cierre = desde_iso(esc.fila(inc)["cerrada_en"])
    fijar_ahora(monkeypatch, cierre + timedelta(hours=48))
    respuesta = esc.sol.post(f"/incidencias/{inc}/reabrir", data={"motivo": MOTIVO_OK})
    assert respuesta.status_code == 302
    fila = esc.fila(inc)
    assert (fila["estado"], fila["tecnico_id"]) == ("EN_ATENCION", usuario_id(esc.app, TEC1))
    assert esc.historial(inc)[-1]["accion"] == "REABRIR"


def test_reapertura_pasadas_48_horas_se_rechaza(esc, monkeypatch):
    inc = esc.avanzar("CERRADA")
    cierre = desde_iso(esc.fila(inc)["cerrada_en"])
    fijar_ahora(monkeypatch, cierre + timedelta(hours=48, seconds=1))
    antes = len(esc.historial(inc))
    respuesta = esc.sol.post(f"/incidencias/{inc}/reabrir", data={"motivo": MOTIVO_OK})
    assert respuesta.status_code == 409
    assert esc.estado(inc) == "CERRADA"
    assert len(esc.historial(inc)) == antes


def test_el_detalle_oculta_el_boton_de_reabrir_tras_48_horas(esc, monkeypatch):
    inc = esc.avanzar("CERRADA")
    assert b"Reabrir incidencia" in esc.sol.get(f"/incidencias/{inc}").data
    cierre = desde_iso(esc.fila(inc)["cerrada_en"])
    fijar_ahora(monkeypatch, cierre + timedelta(hours=49))
    cuerpo = esc.sol.get(f"/incidencias/{inc}").data
    assert b"Reabrir incidencia" not in cuerpo
    assert "ya no se puede reabrir".encode() in cuerpo


def test_reapertura_exige_motivo_y_dueno(esc):
    inc = esc.avanzar("CERRADA")
    assert esc.sol.post(f"/incidencias/{inc}/reabrir", data={"motivo": "corto"}).status_code == 400
    assert esc.sol2.post(f"/incidencias/{inc}/reabrir", data={"motivo": MOTIVO_OK}).status_code == 403
    assert esc.estado(inc) == "CERRADA"


def test_el_ultimo_cierre_reinicia_la_ventana(esc, monkeypatch):
    inc = esc.avanzar("CERRADA")
    primer_cierre = desde_iso(esc.fila(inc)["cerrada_en"])
    assert esc.sol.post(f"/incidencias/{inc}/reabrir", data={"motivo": MOTIVO_OK}).status_code == 302
    esc.tec1.post(f"/incidencias/{inc}/solucion", data={"solucion": SOLUCION_OK})
    fijar_ahora(monkeypatch, primer_cierre + timedelta(hours=100))
    assert esc.sol.post(f"/incidencias/{inc}/confirmar").status_code == 302
    fijar_ahora(monkeypatch, primer_cierre + timedelta(hours=100 + 48))
    assert esc.sol.post(f"/incidencias/{inc}/reabrir", data={"motivo": MOTIVO_OK}).status_code == 302


# --------------------------------------------------------------------------
# RF05 · Consultas, historial inmutable y tablero
# --------------------------------------------------------------------------
def test_el_solicitante_solo_ve_sus_incidencias(esc):
    inc = esc.crear()
    assert esc.sol2.get(f"/incidencias/{inc}").status_code == 403
    assert esc.sol.get(f"/incidencias/{inc}").status_code == 200
    assert esc.sol2.get("/dashboard").data.count(b"INC-") == 0
    assert esc.sol.get("/dashboard").data.count(b"INC-") >= 1


def test_el_tecnico_solo_ve_sus_asignadas(esc):
    asignada = esc.avanzar("ASIGNADA")
    sin_asignar = esc.crear()
    assert esc.tec1.get(f"/incidencias/{asignada}").status_code == 200
    assert esc.tec1.get(f"/incidencias/{sin_asignar}").status_code == 403
    assert esc.tec2.get(f"/incidencias/{asignada}").status_code == 403


def test_el_coordinador_ve_todas_y_filtra_por_estado_y_prioridad(esc):
    esc.crear(riesgo="true")
    esc.avanzar("ASIGNADA", impacto="ALTO")
    todas = esc.coord.get("/dashboard").data
    assert todas.count(b"Ver detalle") == 2
    assert esc.coord.get("/dashboard?estado=ASIGNADA").data.count(b"Ver detalle") == 1
    assert esc.coord.get("/dashboard?prioridad=CRITICA").data.count(b"Ver detalle") == 1
    assert esc.coord.get("/dashboard?estado=ASIGNADA&prioridad=CRITICA").data.count(b"Ver detalle") == 0


@pytest.mark.parametrize("cerradas, total, esperado", [
    (0, 0, "0.0%"), (1, 4, "25.0%"), (1, 3, "33.3%"), (2, 3, "66.7%"),
    (1, 16, "6.3%"), (4, 4, "100.0%"),
])
def test_formato_del_porcentaje_de_cierre(cerradas, total, esperado):
    assert formatear_porcentaje(cerradas, total) == esperado


def test_tablero_del_coordinador_sin_registros(esc):
    cuerpo = esc.coord.get("/dashboard").data
    assert b"0.0%" in cuerpo


def test_tablero_del_coordinador_con_metricas(esc):
    esc.avanzar("CERRADA", riesgo="true")           # CRITICA cerrada
    esc.crear(riesgo="true")                         # CRITICA sin cerrar
    esc.crear(impacto="ALTO")                        # ALTA
    esc.crear()                                      # NORMAL
    with esc.app.app_context():
        metricas = app_module.calcular_metricas(get_db())
    assert metricas["total"] == 4
    assert metricas["porcentaje_cierre"] == "25.0%"
    assert metricas["criticas_abiertas"] == 1
    assert metricas["por_estado"]["CERRADA"] == 1 and metricas["por_estado"]["REGISTRADA"] == 3
    assert metricas["por_prioridad"] == {"CRITICA": 2, "ALTA": 1, "NORMAL": 1}
    assert b"25.0%" in esc.coord.get("/dashboard").data


def test_el_historial_es_inmutable(esc):
    inc = esc.crear()
    with esc.app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE historial SET detalle = 'alterado' WHERE incidencia_id = ?", (inc,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM historial WHERE incidencia_id = ?", (inc,))
    assert len(esc.historial(inc)) == 1


def test_estado_e_historial_se_guardan_juntos(esc):
    """Si falla el INSERT del historial, el estado no debe quedar modificado."""
    inc = esc.avanzar("ASIGNADA")
    with esc.app.app_context():
        db = get_db()
        db.execute("CREATE TRIGGER falla_historial BEFORE INSERT ON historial "
                   "WHEN NEW.accion = 'ATENDER' BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END")
        db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        esc.tec1.post(f"/incidencias/{inc}/atender")
    assert esc.estado(inc) == "ASIGNADA"
    assert [h["accion"] for h in esc.historial(inc)] == ["CREAR", "ASIGNAR"]
