"""
Capa de acceso a datos.

Usa libsql-client, que habla el mismo protocolo tanto con:
  - Turso remoto:  libsql://tu-db-org.turso.io   (+ TURSO_AUTH_TOKEN)
  - Un archivo local: file:local.db              (para desarrollo, sin Turso)

Así el mismo código sirve para desarrollar en tu máquina y para producción
en Cloud Run, solo cambiando variables de entorno.
"""
from __future__ import annotations

import libsql_client
from flask import current_app, g


def get_client() -> libsql_client.ClientSync:
    """Devuelve un cliente libsql reutilizable dentro del contexto de la request."""
    if "db_client" not in g:
        url = current_app.config["TURSO_DATABASE_URL"]
        token = current_app.config["TURSO_AUTH_TOKEN"]

        if url:
            g.db_client = libsql_client.create_client_sync(url=url, auth_token=token)
        else:
            # Fallback local: archivo sqlite normal, útil para desarrollar sin Turso.
            local_path = current_app.config["LOCAL_DB_PATH"]
            g.db_client = libsql_client.create_client_sync(url=f"file:{local_path}")
    return g.db_client


def close_client(_exception=None):
    client = g.pop("db_client", None)
    if client is not None:
        client.close()


def init_app(app):
    app.teardown_appcontext(close_client)


def query(sql: str, params: list | tuple | None = None) -> list[dict]:
    """Ejecuta un SELECT y devuelve una lista de dicts."""
    rs = get_client().execute(sql, list(params) if params else None)
    return [dict(zip(rs.columns, row)) for row in rs.rows]


def query_one(sql: str, params: list | tuple | None = None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: list | tuple | None = None):
    """Ejecuta un INSERT/UPDATE/DELETE."""
    return get_client().execute(sql, list(params) if params else None)


SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    document_id TEXT,
    address TEXT,
    phone TEXT,

    emergency_contact_1_name TEXT,
    emergency_contact_1_phone TEXT,
    emergency_contact_1_relationship TEXT,
    emergency_contact_2_name TEXT,
    emergency_contact_2_phone TEXT,
    emergency_contact_2_relationship TEXT,
    emergency_contact_3_name TEXT,
    emergency_contact_3_phone TEXT,
    emergency_contact_3_relationship TEXT,

    -- Resumen médico de emergencia: NO es una historia clínica completa,
    -- es la información mínima que alguien sin formación médica necesita
    -- para reconocer la situación y ayudar (ej. "Alzheimer", "Epilepsia").
    blood_type TEXT,
    conditions TEXT,
    allergies TEXT,
    medications TEXT,
    medical_device TEXT,
    care_instructions TEXT,
    insurance TEXT,

    photo_url TEXT,
    photo_public_id TEXT,

    password_hash TEXT NOT NULL,
    password_is_temp INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_slug ON users(slug);
"""


def init_schema():
    """Crea las tablas si no existen. Idempotente."""
    client = get_client()
    for statement in [s.strip() for s in SCHEMA.split(";") if s.strip()]:
        client.execute(statement)
