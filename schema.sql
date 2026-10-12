-- ReparaCampus · esquema relacional
-- Las restricciones CHECK replican los valores permitidos del dominio;
-- la validación de la aplicación es la primera barrera y esta es la última.

CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre        TEXT    NOT NULL CHECK (length(trim(nombre)) > 0),
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    rol           TEXT    NOT NULL CHECK (rol IN ('SOLICITANTE', 'COORDINADOR', 'TECNICO')),
    activo        INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE TABLE IF NOT EXISTS incidencias (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT    NOT NULL UNIQUE,
    ubicacion   TEXT    NOT NULL CHECK (ubicacion IN ('LAB-01', 'AULA-201', 'BIB-01')),
    categoria   TEXT    NOT NULL CHECK (categoria IN ('ELECTRICIDAD', 'HIDRAULICA', 'MOBILIARIO', 'TIC')),
    descripcion TEXT    NOT NULL CHECK (length(descripcion) BETWEEN 20 AND 500),
    impacto     TEXT    NOT NULL CHECK (impacto IN ('BAJO', 'ALTO')),
    riesgo      INTEGER NOT NULL CHECK (riesgo IN (0, 1)),
    prioridad   TEXT    NOT NULL CHECK (prioridad IN ('CRITICA', 'ALTA', 'NORMAL')),
    estado      TEXT    NOT NULL DEFAULT 'REGISTRADA'
                CHECK (estado IN ('REGISTRADA', 'ASIGNADA', 'EN_ATENCION',
                                  'PENDIENTE_VALIDACION', 'CERRADA')),
    autor_id    INTEGER NOT NULL REFERENCES usuarios (id),
    tecnico_id  INTEGER REFERENCES usuarios (id),
    creada_en   TEXT    NOT NULL,            -- ISO 8601, UTC
    cerrada_en  TEXT                         -- ISO 8601, UTC; último cierre
);

CREATE INDEX IF NOT EXISTS idx_incidencias_autor   ON incidencias (autor_id);
CREATE INDEX IF NOT EXISTS idx_incidencias_tecnico ON incidencias (tecnico_id);
CREATE INDEX IF NOT EXISTS idx_incidencias_estado  ON incidencias (estado);

CREATE TABLE IF NOT EXISTS historial (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    incidencia_id  INTEGER NOT NULL REFERENCES incidencias (id),
    autor_id       INTEGER NOT NULL REFERENCES usuarios (id),
    fecha          TEXT    NOT NULL,         -- ISO 8601, UTC
    estado_inicial TEXT    CHECK (estado_inicial IS NULL OR estado_inicial IN
                           ('REGISTRADA', 'ASIGNADA', 'EN_ATENCION',
                            'PENDIENTE_VALIDACION', 'CERRADA')),
    estado_final   TEXT    NOT NULL CHECK (estado_final IN
                           ('REGISTRADA', 'ASIGNADA', 'EN_ATENCION',
                            'PENDIENTE_VALIDACION', 'CERRADA')),
    accion         TEXT    NOT NULL CHECK (accion IN
                           ('CREAR', 'ASIGNAR', 'ATENDER', 'RESOLVER',
                            'CONFIRMAR', 'RECHAZAR', 'REABRIR')),
    detalle        TEXT                      -- solución, motivo o técnico asignado
);

CREATE INDEX IF NOT EXISTS idx_historial_incidencia ON historial (incidencia_id);

-- El historial es inmutable: no se edita ni se borra.
CREATE TRIGGER IF NOT EXISTS historial_no_update
BEFORE UPDATE ON historial
BEGIN
    SELECT RAISE(ABORT, 'El historial es inmutable: no se puede editar');
END;

CREATE TRIGGER IF NOT EXISTS historial_no_delete
BEFORE DELETE ON historial
BEGIN
    SELECT RAISE(ABORT, 'El historial es inmutable: no se puede borrar');
END;
