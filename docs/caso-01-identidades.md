# Caso 1: Calidad del dato y resolución de identidades

## Descripción

La misma persona aparece varias veces en una base de clientes: cédula con un dígito errado,
nombre sin tilde, teléfono viejo. El proyecto detecta qué registros son el mismo cliente,
construye un registro de oro y deja a la vista los datos compartidos sospechosos (un mismo
teléfono en muchos clientes no relacionados), que pueden ser un problema de calidad o una
señal de riesgo.

## Objetivo

Consolidar registros en clientes únicos, explicar cada decisión y reducir la revisión manual
de casos dudosos con un agente.

## Técnicas

- Estandarización: nombres, teléfonos (+57), direcciones colombianas ("Cra", "Carrera", "KR";
  "# 10-20").
- Bloqueo para no comparar todos contra todos.
- Modelo probabilístico Fellegi-Sunter entrenado sin etiquetas (EM).
- Agrupación de pares en grafo (componentes conectados = clientes).
- Reglas de supervivencia para el registro de oro.
- Grafo de identidad compartida: clientes conectados por teléfono, correo, dirección o
  dispositivo.

## Agente

- Revisa la zona gris: lee la explicación de Splink, consulta historial y decide
  unir/separar/escalar con justificación.
- Propone el registro de oro y señala los casos que no encajan en las reglas.
- Opcional: agente que ajusta reglas de bloqueo y comparaciones, vuelve a correr y compara
  métricas.

## Librerías

- [Splink](https://github.com/moj-analytical-services/splink): motor de resolución; corre en
  DuckDB para prototipo y en Spark para escala.
- DuckDB.
- Faker (datos sintéticos colombianos).
- Cosmograph (visualización del universo de registros).
- Claude Agent SDK + MCP (agente).

## Datasets

- Datasets de demostración de Splink (incluyen la verdad conocida de qué registros son la
  misma persona).
- FEBRL (registros sintéticos de personas).
- Sintéticos colombianos generados con Faker, con errores inyectados a propósito.

## Evaluación

- Precisión y recall de emparejamiento contra la verdad conocida.
- Precisión de las decisiones del agente en la zona gris.
- Métricas de negocio simuladas: duplicados detectados, comunicaciones duplicadas evitadas,
  cambio en contactabilidad.

## Visualizaciones

- Gráfico de cascada por par y Cluster Studio (vienen con Splink).
- Universo de registros en Cosmograph: miles de puntos agrupándose en clientes, y estrellas de
  datos compartidos (un teléfono "3000000000" en cientos de registros).
- Antes y después animado.

## Hitos

1. **fake_1000 de punta a punta** (completado): carga del dataset de demostración de Splink,
   entrenamiento sin etiquetas, evaluación contra los grupos verdaderos (por par, por clúster,
   por umbral y recall perdido por el bloqueo) y tableros HTML de Splink. Resultados en el
   [README](https://github.com/stous1/identity-resolution#hito-1-fake_1000-de-punta-a-punta)
   y en [los tableros publicados](index.md).
2. Sintéticos colombianos con Faker y estandarización.
3. Registro de oro y grafo de identidad compartida.
4. Agente para la zona gris.

## Notas

- Es un prototipo de "cliente único". Con datos reales pasaría por gobierno de datos y
  seguridad; este repositorio solo usa datos públicos de demostración o sintéticos.
