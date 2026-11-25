"""Carga: modelo en SQLite con upsert idempotente y registro de ejecuciones."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pandas as pd

DDL = """
CREATE TABLE IF NOT EXISTS dim_pais (
    codigo       TEXT PRIMARY KEY CHECK (length(codigo) = 3),
    nombre       TEXT NOT NULL,
    es_agregado  INTEGER NOT NULL DEFAULT 0 CHECK (es_agregado IN (0, 1))
);

CREATE TABLE IF NOT EXISTS fact_indicador (
    codigo          TEXT    NOT NULL REFERENCES dim_pais (codigo),
    anio            INTEGER NOT NULL,
    pib_usd         REAL    CHECK (pib_usd IS NULL OR pib_usd > 0),
    poblacion       INTEGER CHECK (poblacion IS NULL OR poblacion > 0),
    pib_per_capita  REAL,
    PRIMARY KEY (codigo, anio)
);

CREATE TABLE IF NOT EXISTS etl_ejecucion (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio            TEXT NOT NULL,
    fin               TEXT,
    filas_leidas      INTEGER,
    filas_cargadas    INTEGER,
    filas_rechazadas  INTEGER,
    estado            TEXT NOT NULL CHECK (estado IN ('EN_CURSO', 'OK', 'ERROR')),
    detalle           TEXT
);

CREATE VIEW IF NOT EXISTS v_pib_per_capita_paises AS
SELECT p.nombre, f.*
FROM fact_indicador f
JOIN dim_pais p USING (codigo)
WHERE p.es_agregado = 0 AND f.pib_per_capita IS NOT NULL;
"""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar(ruta: str) -> sqlite3.Connection:
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(DDL)
    return con


def iniciar_ejecucion(con: sqlite3.Connection) -> int:
    cur = con.execute("INSERT INTO etl_ejecucion (inicio, estado) VALUES (?, 'EN_CURSO')", (_ahora(),))
    con.commit()
    return cur.lastrowid


def cerrar_ejecucion(con, id_ejec, estado, leidas=None, cargadas=None, rechazadas=None, detalle=None):
    con.execute(
        """UPDATE etl_ejecucion
              SET fin = ?, estado = ?, filas_leidas = ?, filas_cargadas = ?,
                  filas_rechazadas = ?, detalle = ?
            WHERE id = ?""",
        (_ahora(), estado, leidas, cargadas, rechazadas, detalle, id_ejec),
    )
    con.commit()


def _nulos(valor):
    """pandas usa NaN/<NA>; SQLite necesita None."""
    return None if pd.isna(valor) else valor


def cargar(con: sqlite3.Connection, paises: pd.DataFrame, indicadores: pd.DataFrame) -> int:
    """Upsert en una única transacción: si algo falla, no queda nada a medias."""
    with con:
        con.executemany(
            """INSERT INTO dim_pais (codigo, nombre, es_agregado) VALUES (?, ?, ?)
               ON CONFLICT (codigo) DO UPDATE SET nombre = excluded.nombre,
                                                 es_agregado = excluded.es_agregado""",
            paises[["codigo", "nombre", "es_agregado"]].itertuples(index=False, name=None),
        )
        filas = [
            (r.codigo, int(r.anio), _nulos(r.pib_usd), None if pd.isna(r.poblacion) else int(r.poblacion), _nulos(r.pib_per_capita))
            for r in indicadores.itertuples(index=False)
        ]
        con.executemany(
            """INSERT INTO fact_indicador (codigo, anio, pib_usd, poblacion, pib_per_capita)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (codigo, anio) DO UPDATE SET pib_usd = excluded.pib_usd,
                                                       poblacion = excluded.poblacion,
                                                       pib_per_capita = excluded.pib_per_capita""",
            filas,
        )
    return len(filas)
