# Resolución de identidades con Splink

Caso de uso 1 de un portafolio de ciencia de datos y agentes aplicado a banca: detectar qué
registros de una base de clientes corresponden a la misma persona, explicar cada decisión y
medir su precisión contra la verdad conocida.

- [Descripción del caso](caso-01-identidades.md)
- Código: [github.com/stous1/identity-resolution](https://github.com/stous1/identity-resolution)

## Hito 1: fake_1000

1.000 registros de 251 personas (dataset de demostración de Splink). Modelo Fellegi-Sunter
entrenado sin etiquetas, con bloqueo exacto y aproximado (fonético, por prefijos y por año de
nacimiento). Umbral de operación: 0,84, el que minimiza el costo de errores por clúster con un
falso positivo 10 veces más costoso que un falso negativo.

| Nivel | Precisión | Recall | F1 |
|---|---|---|---|
| Por par | 1,000 | 0,731 | 0,844 |
| Por clúster | 1,000 | 0,904 | 0,950 |

El bloqueo compara 7.110 pares (de ~500.000) y cubre el 92,4 % de los pares verdaderos; 205 de
las 251 personas (81,7 %) quedan reconstruidas exactamente. Detalle en
[metricas.json](resultados/metricas.json) y
[comparacion_bloqueos.csv](resultados/comparacion_bloqueos.csv).

## Tableros

- [Cascada por par](resultados/cascada.html): cómo cada campo suma o resta evidencia
  (aciertos, falsos positivos y falsos negativos).
- [Cluster Studio](resultados/cluster_studio.html): grafo de cada clúster, empezando por los
  que tienen errores.
- [Comparison viewer](resultados/comparison_viewer.html): ejemplos por patrón de comparación.
- [Parámetros m/u](resultados/parametros_mu.html) y
  [pesos de coincidencia](resultados/pesos.html) del modelo entrenado.
- Curvas por umbral: [por par](resultados/curva_umbral.html),
  [por clúster](resultados/curva_umbral_clusters.html) y [costo](resultados/costo_umbral.html).

![Costo según el umbral](resultados/costo_umbral.png)

## Regla de datos

Este proyecto nunca usa datos reales de clientes: solo datasets públicos de demostración
(Splink, FEBRL) o sintéticos generados con Faker.
