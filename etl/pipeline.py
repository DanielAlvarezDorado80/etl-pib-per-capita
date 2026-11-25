"""Orquestación del pipeline. Uso:

    python -m etl.pipeline                       # descarga los CSV y carga datos.db
    python -m etl.pipeline --db salida.db --pib pib.csv --poblacion poblacion.csv
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import extract, load, transform

log = logging.getLogger("etl")


def ejecutar(db: str, origen_pib: str, origen_poblacion: str, ruta_rechazos: str | None = None) -> dict:
    con = load.conectar(db)
    id_ejec = load.iniciar_ejecucion(con)
    try:
        pib = extract.leer_csv(origen_pib)
        pob = extract.leer_csv(origen_poblacion)
        paises, indicadores, rechazadas = transform.transformar(pib, pob)
        cargadas = load.cargar(con, paises, indicadores)

        if ruta_rechazos and not rechazadas.empty:
            rechazadas.to_csv(ruta_rechazos, index=False)
            log.warning("%d filas rechazadas -> %s", len(rechazadas), ruta_rechazos)

        resumen = {
            "filas_leidas": len(pib) + len(pob),
            "filas_cargadas": cargadas,
            "filas_rechazadas": len(rechazadas),
            "paises": int((paises["es_agregado"] == 0).sum()),
            "agregados": int(paises["es_agregado"].sum()),
        }
        load.cerrar_ejecucion(con, id_ejec, "OK", resumen["filas_leidas"], cargadas, len(rechazadas))
        log.info("Ejecución %d OK: %s", id_ejec, resumen)
        return resumen
    except Exception as exc:
        load.cerrar_ejecucion(con, id_ejec, "ERROR", detalle=str(exc)[:500])
        log.exception("Ejecución %d fallida", id_ejec)
        raise
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ETL PIB y población (Banco Mundial) -> SQLite")
    parser.add_argument("--db", default="datos.db", help="ruta de la base de datos SQLite")
    parser.add_argument("--pib", default=extract.URL_PIB, help="URL o ruta del CSV de PIB")
    parser.add_argument("--poblacion", default=extract.URL_POBLACION, help="URL o ruta del CSV de población")
    parser.add_argument("--rechazos", default="rechazos.csv", help="CSV con las filas descartadas")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ejecutar(args.db, args.pib, args.poblacion, args.rechazos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
