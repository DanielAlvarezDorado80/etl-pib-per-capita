"""Transformación: tipado, validación, limpieza y cálculo del PIB per cápita."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Códigos de agregados regionales y por nivel de renta del Banco Mundial (no son países).
# Se separan para no mezclar "Spain" con "European Union" o "World" en los rankings.
CODIGOS_AGREGADOS = frozenset(
    "AFE AFW ARB CEB CSS EAP EAR EAS ECA ECS EMU EUU FCS HIC HPC IBD IBT IDA IDB IDX INX "
    "LAC LCN LDC LIC LMC LMY LTE MEA MIC MNA NAC OED OSS PRE PSS PST SAS SSA SSF SST TEA "
    "TEC TLA TMN TSA TSS UMC WLD".split()
)

ANIO_MIN = 1960


@dataclass
class Resultado:
    validas: pd.DataFrame
    rechazadas: pd.DataFrame


def _normalizar(df: pd.DataFrame, nombre_valor: str) -> Resultado:
    """Convierte tipos y separa filas válidas de rechazadas, anotando el motivo."""
    out = pd.DataFrame(
        {
            "codigo": df["Country Code"].str.upper(),
            "nombre": df["Country Name"],
            "anio": pd.to_numeric(df["Year"], errors="coerce"),
            nombre_valor: pd.to_numeric(df["Value"], errors="coerce"),
        }
    )
    anio_max = pd.Timestamp.today().year

    motivo = pd.Series("", index=out.index)
    motivo[~out["codigo"].str.fullmatch(r"[A-Z0-9]{3}", na=False)] = "codigo_invalido"
    motivo[(motivo == "") & out["anio"].isna()] = "anio_no_numerico"
    motivo[(motivo == "") & ~out["anio"].between(ANIO_MIN, anio_max)] = "anio_fuera_de_rango"
    motivo[(motivo == "") & out[nombre_valor].isna()] = "valor_no_numerico"
    motivo[(motivo == "") & (out[nombre_valor] <= 0)] = "valor_no_positivo"

    duplicada = out.duplicated(subset=["codigo", "anio"], keep="first")
    motivo[(motivo == "") & duplicada] = "duplicada"

    rechazadas = df.loc[motivo != ""].assign(motivo=motivo[motivo != ""], fuente=nombre_valor)
    validas = out.loc[motivo == ""].copy()
    validas["anio"] = validas["anio"].astype(int)
    return Resultado(validas, rechazadas)


def transformar(pib: pd.DataFrame, poblacion: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Devuelve (paises, indicadores, rechazadas).

    - paises: dimensión con código, nombre y si es agregado regional.
    - indicadores: una fila por país y año con PIB, población y PIB per cápita.
    - rechazadas: filas de origen descartadas con su motivo (para el informe de calidad).
    """
    r_pib = _normalizar(pib, "pib_usd")
    r_pob = _normalizar(poblacion, "poblacion")

    # Dimensión de países: unión de ambas fuentes; si el nombre difiere, prevalece el de PIB
    paises = (
        pd.concat([r_pib.validas[["codigo", "nombre"]], r_pob.validas[["codigo", "nombre"]]])
        .drop_duplicates(subset="codigo", keep="first")
        .sort_values("codigo")
        .reset_index(drop=True)
    )
    paises["es_agregado"] = paises["codigo"].isin(CODIGOS_AGREGADOS).astype(int)

    # Hechos: outer join para no perder años que solo tienen una de las dos medidas
    indicadores = r_pib.validas[["codigo", "anio", "pib_usd"]].merge(
        r_pob.validas[["codigo", "anio", "poblacion"]], on=["codigo", "anio"], how="outer"
    )
    indicadores["poblacion"] = indicadores["poblacion"].astype("Int64")
    indicadores["pib_per_capita"] = (indicadores["pib_usd"] / indicadores["poblacion"]).round(2)
    indicadores = indicadores.sort_values(["codigo", "anio"]).reset_index(drop=True)

    rechazadas = pd.concat([r_pib.rechazadas, r_pob.rechazadas], ignore_index=True)
    return paises, indicadores, rechazadas
