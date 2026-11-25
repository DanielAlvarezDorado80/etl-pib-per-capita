"""Tests con extractos reales de los CSV de origen más filas sucias a propósito."""
import sqlite3

import pytest

from etl import pipeline, transform
from etl.extract import leer_csv

# Extracto real de gdp.csv (incluye un nombre entrecomillado con coma) + filas sucias
PIB_CSV = """Country Name,Country Code,Year,Value
Spain,ESP,2022,1417800466262.6514
Spain,ESP,2023,1580694712515.714
Portugal,PRT,2023,287080013574.4972
European Union,EUU,2023,18349388450765.61
"Bahamas, The",BHS,1960,169803921.56862745
Spain,ESP,2023,1580694712515.714
Francia,FRA,dos mil,123
Narnia,NA,2023,1000
Atlantis,ATL,1850,5000
Utopia,UTO,2023,-7
Vacio,VAC,2023,
"""

# Extracto real de population.csv: trae finales de línea CRLF
POB_CSV = (
    "Country Name,Country Code,Year,Value\r\n"
    "Spain,ESP,2022,47786102\r\n"
    "Spain,ESP,2023,48352528\r\n"
    "Portugal,PRT,2023,10578174\r\n"
    "European Union,EUU,2023,448897545\r\n"
    "Portugal,PRT,2021,10361831\r\n"
)


@pytest.fixture
def ficheros(tmp_path):
    pib = tmp_path / "pib.csv"
    pob = tmp_path / "pob.csv"
    pib.write_text(PIB_CSV, encoding="utf-8")
    pob.write_bytes(POB_CSV.encode("utf-8"))
    return str(pib), str(pob)


def test_lectura_limpia_crlf_y_comillas(ficheros):
    df = leer_csv(ficheros[1])
    assert list(df.columns) == ["Country Name", "Country Code", "Year", "Value"]
    assert df["Value"].iloc[0] == "47786102"  # sin \r al final
    assert "Bahamas, The" in set(leer_csv(ficheros[0])["Country Name"])


def test_rechazos_con_motivo(ficheros):
    _, _, rechazadas = transform.transformar(leer_csv(ficheros[0]), leer_csv(ficheros[1]))
    motivos = dict(zip(rechazadas["Country Code"], rechazadas["motivo"]))
    assert motivos == {
        "ESP": "duplicada",
        "FRA": "anio_no_numerico",
        "NA": "codigo_invalido",
        "ATL": "anio_fuera_de_rango",
        "UTO": "valor_no_positivo",
        "VAC": "valor_no_numerico",
    }


def test_pib_per_capita_y_agregados(ficheros):
    paises, ind, _ = transform.transformar(leer_csv(ficheros[0]), leer_csv(ficheros[1]))
    esp_2023 = ind[(ind.codigo == "ESP") & (ind.anio == 2023)].iloc[0]
    assert esp_2023.pib_per_capita == round(1580694712515.714 / 48352528, 2)  # 32691.05 USD
    assert paises.set_index("codigo").loc["EUU", "es_agregado"] == 1
    assert paises.set_index("codigo").loc["ESP", "es_agregado"] == 0
    # Portugal 2021 solo tiene población: se conserva con PIB nulo (outer join)
    prt_2021 = ind[(ind.codigo == "PRT") & (ind.anio == 2021)].iloc[0]
    assert prt_2021.poblacion == 10361831 and prt_2021.pib_usd != prt_2021.pib_usd  # NaN


def test_carga_idempotente_y_registro(ficheros, tmp_path):
    db = str(tmp_path / "datos.db")
    r1 = pipeline.ejecutar(db, *ficheros)
    r2 = pipeline.ejecutar(db, *ficheros)  # segunda vez: no debe duplicar
    assert r1 == r2

    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM fact_indicador").fetchone()[0] == r1["filas_cargadas"]
    assert con.execute("SELECT COUNT(*) FROM etl_ejecucion WHERE estado = 'OK'").fetchone()[0] == 2
    # La vista excluye agregados como la Unión Europea
    codigos = {c for (c,) in con.execute("SELECT codigo FROM v_pib_per_capita_paises")}
    assert codigos == {"ESP", "PRT"}


def test_error_queda_registrado(tmp_path):
    malo = tmp_path / "malo.csv"
    malo.write_text("a,b\n1,2\n", encoding="utf-8")
    db = str(tmp_path / "datos.db")
    with pytest.raises(ValueError):
        pipeline.ejecutar(db, str(malo), str(malo))
    estado, detalle = sqlite3.connect(db).execute("SELECT estado, detalle FROM etl_ejecucion").fetchone()
    assert estado == "ERROR" and "Faltan columnas" in detalle
