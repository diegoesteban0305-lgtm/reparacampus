"""Acceso a SQLite para ReparaCampus."""
import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db():
    """Devuelve la conexión de la petición actual (se crea una sola vez)."""
    if "db" not in g:
        conexion = sqlite3.connect(current_app.config["DATABASE"])
        conexion.row_factory = sqlite3.Row
        conexion.execute("PRAGMA foreign_keys = ON;")
        g.db = conexion
    return g.db


def close_db(_error=None):
    conexion = g.pop("db", None)
    if conexion is not None:
        conexion.close()


def init_db():
    """Crea las tablas y triggers definidos en schema.sql (idempotente)."""
    conexion = get_db()
    conexion.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conexion.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
