# Resolución de identidades con Splink

Caso de uso 1 de un portafolio de ciencia de datos y agentes aplicado a banca: detectar qué
registros de una base de clientes corresponden a la misma persona, explicar cada decisión y
medir su precisión contra la verdad conocida.

- [Descripción del caso](caso-01-identidades.md)
- Código: [github.com/stous1/identity-resolution](https://github.com/stous1/identity-resolution)

## Hito 1: fake_1000

1.000 registros de 251 personas (dataset de demostración de Splink). Modelo Fellegi-Sunter
entrenado sin etiquetas; umbral de `match_probability` = 0,9.

| Nivel | Precisión | Recall | F1 |
|---|---|---|---|
| Por par | 1,000 | 0,638 | 0,779 |
| Por clúster | 1,000 | 0,826 | 0,905 |

El bloqueo compara 3.989 pares y cubre el 81,2 % de los pares verdaderos.
Detalle en [metricas.json](resultados/metricas.json).

## Tableros

- [Cascada por par](resultados/cascada.html): cómo cada campo suma o resta evidencia
  (aciertos, falsos positivos y falsos negativos).
- [Cluster Studio](resultados/cluster_studio.html): grafo de cada clúster, empezando por los
  que tienen errores.
- [Comparison viewer](resultados/comparison_viewer.html): ejemplos por patrón de comparación.
- [Parámetros m/u](resultados/parametros_mu.html) y
  [pesos de coincidencia](resultados/pesos.html) del modelo entrenado.
- [Curva por umbral](resultados/curva_umbral.html): precisión, recall y F1 por par.

![Curva por umbral](resultados/curva_umbral.png)

## Regla de datos

Este proyecto nunca usa datos reales de clientes: solo datasets públicos de demostración
(Splink, FEBRL) o sintéticos generados con Faker.
