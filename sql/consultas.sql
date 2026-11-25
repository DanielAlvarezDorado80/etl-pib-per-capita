-- Consultas de ejemplo sobre datos.db (SQLite)

-- 1) Ranking de PIB per cápita del último año disponible (solo países, sin agregados)
WITH ultimo AS (SELECT MAX(anio) AS anio FROM v_pib_per_capita_paises)
SELECT RANK() OVER (ORDER BY pib_per_capita DESC) AS puesto,
       nombre, ROUND(pib_per_capita, 0) AS pib_per_capita_usd
FROM v_pib_per_capita_paises
WHERE anio = (SELECT anio FROM ultimo)
ORDER BY puesto
LIMIT 20;

-- 2) Evolución de España con variación interanual del PIB per cápita
SELECT anio,
       ROUND(pib_per_capita, 0) AS pib_pc,
       ROUND(100.0 * (pib_per_capita / LAG(pib_per_capita) OVER (ORDER BY anio) - 1), 1) AS var_pct
FROM fact_indicador
WHERE codigo = 'ESP' AND pib_per_capita IS NOT NULL
ORDER BY anio;

-- 3) Calidad: años con población pero sin PIB (y al revés) por país
SELECT p.nombre,
       SUM(f.pib_usd IS NULL)   AS anios_sin_pib,
       SUM(f.poblacion IS NULL) AS anios_sin_poblacion
FROM fact_indicador f JOIN dim_pais p USING (codigo)
WHERE p.es_agregado = 0
GROUP BY p.nombre
HAVING anios_sin_pib + anios_sin_poblacion > 0
ORDER BY anios_sin_pib DESC
LIMIT 20;

-- 4) Historial de ejecuciones del pipeline
SELECT id, inicio, fin, estado, filas_leidas, filas_cargadas, filas_rechazadas
FROM etl_ejecucion ORDER BY id DESC;
