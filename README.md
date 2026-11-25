# ETL PIB per cápita · Python + pandas + SQLite

Pipeline ETL que descarga dos CSV públicos del **Banco Mundial** (PIB y población por país y año), los valida y limpia, calcula el **PIB per cápita** y lo carga en un modelo dimensional en SQLite con **carga idempotente**, **registro de ejecuciones** e **informe de filas rechazadas**.

```
 gdp.csv ─┐                          ┌─> dim_pais        (países + agregados)
          ├─> extract ─> transform ──┼─> fact_indicador  (PIB, población, PIB per cápita)
 pop.csv ─┘     │            │       ├─> etl_ejecucion   (log de cada ejecución)
                │            │       └─> rechazos.csv    (filas descartadas + motivo)
             valida       tipa, valida,
            columnas      deduplica, une
```

## Qué problemas reales resuelve

Los ficheros de origen ([gdp.csv](https://github.com/datasets/gdp) y [population.csv](https://github.com/datasets/population)) tienen unas 14.000 y 17.400 filas y 262 códigos, y traen trampas típicas de datos reales:

| Problema en el origen | Cómo se trata |
|---|---|
| `population.csv` usa finales de línea CRLF (`\r\n`) | Se limpian cabeceras y valores al leer |
| Nombres con comas entre comillas (`"Bahamas, The"`) | Lectura con parser CSV real, no `split(',')` |
| 48 de los 262 códigos son **agregados** (World, European Union, renta alta…) mezclados con países | Se marcan con `es_agregado` y la vista `v_pib_per_capita_paises` los excluye |
| Años que tienen PIB pero no población, o al revés | *Outer join*: se conservan con la medida que falta a `NULL` |
| Filas duplicadas, años o valores no numéricos, valores ≤ 0, años fuera de rango, códigos mal formados | Se **rechazan con su motivo** en `rechazos.csv`, sin parar la carga |

## Diseño

- **Extract** (`etl/extract.py`): lee desde URL o fichero local, todo como texto, y valida las columnas esperadas.
- **Transform** (`etl/transform.py`): tipa, valida fila a fila, deduplica por `(código, año)`, separa agregados y calcula el PIB per cápita.
- **Load** (`etl/load.py`): `INSERT … ON CONFLICT DO UPDATE` en **una sola transacción**. Ejecutarlo dos veces deja el mismo resultado. Las restricciones `CHECK` y las claves foráneas viven también en la base de datos.
- **Trazabilidad**: cada ejecución queda en `etl_ejecucion` con inicio, fin, estado (`OK`/`ERROR`) y número de filas leídas, cargadas y rechazadas.

## Uso

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m etl.pipeline                      # descarga los CSV y genera datos.db y rechazos.csv
python -m etl.pipeline --db otra.db --pib gdp.csv --poblacion population.csv   # desde ficheros locales
```

Consultas de ejemplo (ranking, evolución interanual con `LAG`, huecos de datos, historial de ejecuciones) en [`sql/consultas.sql`](sql/consultas.sql):

```bash
sqlite3 datos.db < sql/consultas.sql
```

## Tests

```bash
pytest -q
```

Los tests usan extractos reales de los dos CSV más filas sucias a propósito. Comprueban:

- la lectura con CRLF y nombres entrecomillados;
- cada motivo de rechazo;
- el cálculo del PIB per cápita y la separación de agregados;
- que la carga es idempotente (dos ejecuciones, mismo resultado);
- que un fallo queda registrado como `ERROR` en `etl_ejecucion`.

## Stack

Python 3.10+ · pandas · SQLite (`sqlite3` de la librería estándar) · pytest
