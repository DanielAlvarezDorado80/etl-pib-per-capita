"""Extracción: descarga (o lee en local) los CSV públicos de PIB y población."""
from __future__ import annotations

import io
import logging
import urllib.request
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# Datos abiertos del Banco Mundial publicados por el proyecto datasets (Open Knowledge Foundation)
URL_PIB = "https://raw.githubusercontent.com/datasets/gdp/main/data/gdp.csv"
URL_POBLACION = "https://raw.githubusercontent.com/datasets/population/main/data/population.csv"

COLUMNAS_ORIGEN = ["Country Name", "Country Code", "Year", "Value"]


def leer_csv(origen: str | Path, timeout: int = 30) -> pd.DataFrame:
    """Lee un CSV desde una URL o una ruta local y valida que trae las columnas esperadas.

    Todo se lee como texto: los tipos se convierten y validan después, en la transformación,
    para poder rechazar filas sucias en lugar de que falle la lectura completa.
    """
    origen = str(origen)
    if origen.startswith(("http://", "https://")):
        log.info("Descargando %s", origen)
        with urllib.request.urlopen(origen, timeout=timeout) as resp:
            contenido = resp.read().decode("utf-8-sig")
        df = pd.read_csv(io.StringIO(contenido), dtype=str, keep_default_na=False)
    else:
        log.info("Leyendo fichero local %s", origen)
        df = pd.read_csv(origen, dtype=str, keep_default_na=False, encoding="utf-8-sig")

    # El CSV de población trae finales de línea CRLF: limpiamos espacios en cabeceras y valores
    df.columns = [c.strip() for c in df.columns]
    faltan = set(COLUMNAS_ORIGEN) - set(df.columns)
    if faltan:
        raise ValueError(f"Faltan columnas en {origen}: {sorted(faltan)}")
    df = df[COLUMNAS_ORIGEN].apply(lambda s: s.str.strip())
    log.info("Leídas %d filas de %s", len(df), origen)
    return df
