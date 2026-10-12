"""Datos semilla de ReparaCampus: 2 solicitantes, 1 coordinador, 2 técnicos.

Uso:  python seed.py
Las contraseñas son ficticias y solo sirven para demostración.
"""
from werkzeug.security import generate_password_hash

from db import get_db, init_db

CUENTAS_SEMILLA = [
    {"nombre": "Laura Pérez", "email": "solicitante1@usb.edu.co",
     "password": "Solicitante1!", "rol": "SOLICITANTE"},
    {"nombre": "Andrés Mejía", "email": "solicitante2@usb.edu.co",
     "password": "Solicitante2!", "rol": "SOLICITANTE"},
    {"nombre": "Marta Rojas", "email": "coordinador@usb.edu.co",
     "password": "Coordinador1!", "rol": "COORDINADOR"},
    {"nombre": "Carlos Vega", "email": "tecnico1@usb.edu.co",
     "password": "Tecnico1!", "rol": "TECNICO"},
    {"nombre": "Sofía Duarte", "email": "tecnico2@usb.edu.co",
     "password": "Tecnico2!", "rol": "TECNICO"},
]


def seed_db(db, metodo="scrypt"):
    """Inserta las cuentas que aún no existen (idempotente).

    `metodo` es el algoritmo de hash de Werkzeug; las pruebas usan uno liviano para ir rápido.
    """
    for cuenta in CUENTAS_SEMILLA:
        db.execute(
            "INSERT OR IGNORE INTO usuarios (nombre, email, password_hash, rol, activo) "
            "VALUES (?, ?, ?, ?, 1)",
            (cuenta["nombre"], cuenta["email"],
             generate_password_hash(cuenta["password"], method=metodo), cuenta["rol"]),
        )
    db.commit()


def main():
    from app import create_app

    app = create_app()
    with app.app_context():
        init_db()
        seed_db(get_db())
    print(f"Base de datos lista en {app.config['DATABASE']} con {len(CUENTAS_SEMILLA)} cuentas.")


if __name__ == "__main__":
    main()
