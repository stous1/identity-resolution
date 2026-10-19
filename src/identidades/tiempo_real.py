"""Vinculación en tiempo real: "¿ya es cliente?" para registros que llegan uno a uno.

La base de clientes son **registros de oro** (un renglón por cliente), construidos con el
modelo v2 congelado y las reglas de supervivencia elegidas en el hito 3. Cada registro
nuevo se prepara con la estandarización v2 y se compara contra la base con
``find_matches_to_new_records`` de Splink, usando las reglas de bloqueo del modelo.

Decisión (umbrales fijados de antemano, sin ajustar con las consultas):

- ``cliente`` si la mejor coincidencia tiene probabilidad >= umbral congelado;
- ``revisar`` si está en la zona gris;
- ``nuevo`` en otro caso.

La zona gris depende de lo que se le dé al ``Vinculador``:

- **con bandas** (modelo v3, hito 6): desde la banda ``revisar`` de la calibración
  isotónica congelada en desarrollo (``calibracion.bandas``). Las bandas están en peso de
  coincidencia con la previa del desarrollo; aquí se trasladan a la previa 1/N (ver
  ``peso_con_otra_previa``), de modo que exigen la misma evidencia de los campos;
- **sin bandas** (modelo v2, hito 5): probabilidad >= 0,9. La auditoría (A3) mostró que
  esa probabilidad no está calibrada; se conserva solo para reproducir el hito 5.

La probabilidad a priori (lambda) se fija en 1/N clientes: una consulta corresponde a lo
sumo a un cliente de la base.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from splink import DuckDBAPI, Linker

from identidades import flujo, modelo, registro_oro, rutas
from identidades.modelo_co_v2 import ESQUEMA_V2, MAX_REGISTROS_POR_TELEFONO

ZONA_GRIS: float = 0.9
COLUMNAS_TF: tuple[str, ...] = (
    "nombre_completo",
    "primer_apellido",
    "email",
    "domicilio",
    "municipio",
)
COLUMNAS_CRUDAS: list[str] = [
    "unique_id",
    "tipo_documento",
    "numero_documento",
    "nombres",
    "apellidos",
    "fecha_nacimiento",
    "celular",
    "correo",
    "direccion",
    "ciudad",
    "departamento",
]


def reglas_supervivencia() -> dict[str, str]:
    """Reglas por campo elegidas en el desarrollo del hito 3."""
    metricas = json.loads(
        (rutas.DOCS_RESULTADOS_HITO3 / "metricas.json").read_text(encoding="utf-8")
    )
    return metricas["registro_oro"]["reglas_elegidas_en_desarrollo"]


def telefonos_de_relleno(registros: pd.DataFrame) -> set[str]:
    """Teléfonos en más registros de los que puede tener una persona."""
    from identidades import estandarizacion_v2 as v2

    frecuencia = registros["celular"].map(v2.extraer_telefonos).explode().value_counts()
    return set(frecuencia[frecuencia > MAX_REGISTROS_POR_TELEFONO].index)


def log_odds(probabilidad: float) -> float:
    """log2(p / (1 - p))."""
    return math.log2(probabilidad / (1 - probabilidad))


def peso_con_otra_previa(peso: float, previa_origen: float, previa_destino: float) -> float:
    """El mismo peso de coincidencia con otra probabilidad a priori.

    El peso de Splink es la previa en log-odds más la evidencia de los campos; al cambiar
    la previa la evidencia no cambia.
    """
    return peso - log_odds(previa_origen) + log_odds(previa_destino)


def columnas_tf(configuracion: dict) -> list[str]:
    """Columnas con ajuste por frecuencia en un modelo guardado."""
    return sorted(
        {
            n["tf_adjustment_column"]
            for c in configuracion["comparisons"]
            for n in c["comparison_levels"]
            if n.get("tf_adjustment_column")
        }
    )


def tabla_tipada(filas: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    """DataFrame para DuckDB con las columnas de listas del v4 tipadas como texto.

    Si en una consulta la lista de partes de la unidad es nula, DuckDB la leería como
    entero y la comparación de dirección del v4 fallaría.
    """
    import pyarrow as pa

    tabla = pd.DataFrame(filas)
    if "unidad_partes" in tabla:
        tabla["unidad_partes"] = pd.Series(
            [list(v) if isinstance(v, list | np.ndarray) else None for v in tabla["unidad_partes"]],
            index=tabla.index,
            dtype=pd.ArrowDtype(pa.list_(pa.string())),
        )
    return tabla


def construir_base(
    registros: pd.DataFrame, configuracion: dict, umbral: float, esquema: Any = None
) -> pd.DataFrame:
    """Registros de oro (formato crudo, un renglón por cliente) a partir de registros.

    Los clientes salen del modelo congelado; cada campo, de la regla de supervivencia del
    hito 3 (sin metadatos de canal, "fuente más confiable" y "validado" equivalen a "más
    reciente"; ver ``registro_oro``). ``cluster`` es la persona verdadera mayoritaria (solo
    para evaluar). El relleno no sobrevive.
    """
    linker = flujo.aplicar_configuracion(configuracion, registros, esquema or ESQUEMA_V2)
    clusters = modelo.agrupar(linker, modelo.predecir(linker), umbral).as_pandas_dataframe()
    con_meta = registros.assign(
        fecha_actualizacion=registros.get("fecha_actualizacion", "2020-01-01"),
        canal=registros.get("canal", "sucursal"),
        validado=registros.get("validado", False),
    )
    relleno = {"celular": telefonos_de_relleno(registros)}
    cand = registro_oro.candidatos(con_meta, clusters, relleno)
    oro = registro_oro.registro_de_oro(cand, reglas_supervivencia())
    ancho = oro.pivot(index="cluster_id", columns="campo", values="valor")

    asignacion = clusters[["unique_id", "cluster_id"]].merge(
        registros[["unique_id", "cluster", "ciudad", "departamento", "tipo_documento"]]
    )
    moda = asignacion.groupby("cluster_id").agg(
        cluster=("cluster", lambda s: s.mode().iloc[0]),
        ciudad=("ciudad", lambda s: s.mode().iloc[0] if s.notna().any() else None),
        departamento=("departamento", lambda s: s.mode().iloc[0] if s.notna().any() else None),
        tipo_documento=("tipo_documento", lambda s: s.mode().iloc[0] if s.notna().any() else None),
    )
    base = moda.join(ancho).reset_index()
    return pd.DataFrame(
        {
            "unique_id": range(len(base)),
            "tipo_documento": base["tipo_documento"],
            "numero_documento": base.get("documento"),
            "nombres": base.get("nombres"),
            "apellidos": base.get("apellidos"),
            "fecha_nacimiento": base.get("fecha_nacimiento"),
            "celular": base.get("celular"),
            "correo": base.get("correo"),
            "direccion": base.get("direccion"),
            "ciudad": base["ciudad"],
            "departamento": base["departamento"],
            "cluster": base["cluster"],
        }
    )


@dataclass
class Vinculador:
    """Compara registros nuevos contra una base de clientes con el modelo congelado."""

    base: pd.DataFrame
    configuracion: dict
    umbral: float
    zona_gris: float = ZONA_GRIS
    relleno: set[str] = field(default_factory=set)
    bandas: dict | None = None
    # Esquema del modelo (preparación de columnas); por defecto, el del v2 y el v3.
    esquema: Any = None

    def __post_init__(self) -> None:
        self.esquema = self.esquema or ESQUEMA_V2
        previa = 1 / max(len(self.base), 1)
        configuracion = {**self.configuracion, "probability_two_random_records_match": previa}
        # Las bandas se definieron con la previa del modelo congelado (la del desarrollo).
        self.peso_revisar: float | None = (
            None
            if self.bandas is None
            else peso_con_otra_previa(
                self.bandas["peso_desde_revisar"],
                self.configuracion["probability_two_random_records_match"],
                previa,
            )
        )
        preparada = tabla_tipada(self.esquema.preparar(self.base))
        self.linker = Linker(preparada, configuracion, db_api=DuckDBAPI())
        for columna in columnas_tf(configuracion):
            self.linker.table_management.compute_tf_table(columna)
        self.reglas_bloqueo = configuracion["blocking_rules_to_generate_predictions"]
        self.clientes = self.base.set_index("unique_id")
        self._compilar()
        self.etiquetas = {
            c.output_column_name: {
                n.comparison_vector_value: n.label_for_charts for n in c.comparison_levels
            }
            for c in self.linker._settings_obj.comparisons
        }

    def _preparar(self, registro: dict[str, Any]) -> list[dict[str, Any]]:
        fila = {c: registro.get(c) for c in COLUMNAS_CRUDAS}
        fila["unique_id"] = -1
        preparado = self.esquema.preparar(pd.DataFrame([fila]))
        telefonos = preparado.at[0, "telefonos"]
        if isinstance(telefonos, list):
            utiles = [t for t in telefonos if t not in self.relleno] or None
            preparado.at[0, "telefonos"] = utiles
            preparado.at[0, "telefono"] = next(
                (t for t in (utiles or []) if t.startswith("3")), None
            )
        registros = preparado.drop(columns=["cluster"], errors="ignore").to_dict("records")
        return [
            {
                k: list(v) if isinstance(v, list | np.ndarray) else (None if pd.isna(v) else v)
                for k, v in r.items()
            }
            for r in registros
        ]

    TABLA_CONSULTA = "__consulta_tiempo_real"

    def _compilar(self) -> None:
        """Genera una vez el SQL de Splink para comparar un registro contra la base.

        ``find_matches_to_new_records`` vuelve a construir y analizar el SQL en cada
        llamada (~250 ms). El SQL no depende del registro, así que se captura una vez con
        una tabla de consulta de nombre fijo y luego solo se reejecuta en DuckDB.
        """
        db_api = self.linker._db_api
        ejemplo = tabla_tipada(self._preparar({c: None for c in COLUMNAS_CRUDAS}))
        self.linker.table_management.register_table(ejemplo, self.TABLA_CONSULTA, overwrite=True)
        capturadas: list[str] = []
        original = db_api._execute_sql_against_backend

        def capturar(sql: str):
            capturadas.append(sql)
            return original(sql)

        db_api._execute_sql_against_backend = capturar
        try:
            salida = self.linker.inference.find_matches_to_new_records(
                self.TABLA_CONSULTA, blocking_rules=self.reglas_bloqueo, match_weight_threshold=-30
            )
        finally:
            db_api._execute_sql_against_backend = original
        self._sql = [
            sql.replace("CREATE TABLE ", "CREATE OR REPLACE TABLE ", 1)
            for sql in capturadas
            if sql.lstrip().upper().startswith("CREATE TABLE")
        ]
        self._salida = salida.physical_name
        self._con = db_api._con

    def comparar(self, registro: dict[str, Any], compilado: bool = True) -> pd.DataFrame:
        """Pares (consulta, cliente) puntuados, por el camino compilado o el de Splink."""
        preparado = self._preparar(registro)
        if not compilado:
            return self.linker.inference.find_matches_to_new_records(
                preparado, blocking_rules=self.reglas_bloqueo, match_weight_threshold=-30
            ).as_pandas_dataframe()
        self._con.register(self.TABLA_CONSULTA, tabla_tipada(preparado))
        for sql in self._sql:
            self._con.execute(sql)
        return self._con.sql(f"select * from {self._salida}").df()

    def decidir(self, probabilidad: float, peso: float) -> str:
        """``cliente``, ``revisar`` o ``nuevo`` para la mejor coincidencia."""
        if probabilidad >= self.umbral:
            return "cliente"
        en_zona_gris = (
            peso >= self.peso_revisar
            if self.peso_revisar is not None
            else probabilidad >= self.zona_gris
        )
        return "revisar" if en_zona_gris else "nuevo"

    def descripcion_zona_gris(self) -> dict[str, Any]:
        """Cómo se define la zona gris (para el servicio y los resultados)."""
        if self.peso_revisar is None:
            return {"criterio": "probabilidad sin calibrar", "desde_probabilidad": self.zona_gris}
        return {
            "criterio": "banda revisar de la calibración congelada en desarrollo",
            "peso_desde_revisar_desarrollo": self.bandas["peso_desde_revisar"],
            "peso_desde_revisar_tiempo_real": self.peso_revisar,
        }

    def explicar(self, fila: pd.Series) -> list[dict[str, Any]]:
        """Aporte de cada campo al peso de coincidencia, de mayor a menor efecto."""
        aportes = []
        for columna, niveles in self.etiquetas.items():
            gamma = int(fila[f"gamma_{columna}"])
            bf = float(fila[f"bf_{columna}"])
            tf = float(fila.get(f"bf_tf_adj_{columna}", 1.0) or 1.0)
            peso = math.log2(bf * tf) if bf * tf > 0 else float("-inf")
            aportes.append(
                {"campo": columna, "nivel": niveles.get(gamma, str(gamma)), "peso": round(peso, 2)}
            )
        return sorted(aportes, key=lambda a: -abs(a["peso"]))

    def consultar(self, registro: dict[str, Any]) -> dict[str, Any]:
        """Decisión, cliente encontrado y explicación para un registro."""
        inicio = time.perf_counter()
        resultado = self.comparar(registro)
        if resultado.empty:
            decision, mejor = "nuevo", None
        else:
            mejor = resultado.sort_values("match_weight", ascending=False).iloc[0]
            decision = self.decidir(float(mejor["match_probability"]), float(mejor["match_weight"]))
        respuesta: dict[str, Any] = {
            "decision": decision,
            "probabilidad": None if mejor is None else float(mejor["match_probability"]),
            "peso": None if mejor is None else float(mejor["match_weight"]),
            "candidatos_comparados": len(resultado),
        }
        if mejor is not None:
            cliente_id = int(
                mejor["unique_id_r"] if mejor["unique_id_l"] == -1 else mejor["unique_id_l"]
            )
            cliente = self.clientes.loc[cliente_id]
            respuesta["cliente"] = {
                "cliente_id": cliente_id,
                **{c: (None if pd.isna(cliente[c]) else cliente[c]) for c in COLUMNAS_CRUDAS[1:]},
            }
            respuesta["explicacion"] = self.explicar(mejor)
        respuesta["milisegundos"] = round((time.perf_counter() - inicio) * 1000, 2)
        return respuesta


def preparar_evaluacion(
    n_personas: int = 3000,
    semilla: int = 5050,
    frac_existentes: float = 0.7,
    max_consultas: int = 1000,
    registros: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Registros de la base y consultas con verdad: personas existentes y nuevas.

    De cada persona existente (con dos o más registros) se aparta un registro como
    consulta; el resto va a la base. De cada persona nueva se toma un registro.
    Devuelve ``(registros_base, consultas, personas)``; ``consultas`` tiene ``existe``.
    Si se dan ``registros`` (por ejemplo, de una prueba ciega), se usan en lugar de
    generarlos y ``personas`` es ``None``.
    """
    from identidades import sinteticos

    personas = None
    if registros is None:
        registros, personas = sinteticos.generar(n_personas, semilla)
    rng = np.random.default_rng(semilla)
    por_persona = registros.groupby("cluster")
    con_varios = [c for c, g in por_persona if len(g) >= 2]
    rng.shuffle(con_varios)
    existentes = set(con_varios[: round(frac_existentes * len(con_varios))])
    nuevas = [c for c in registros["cluster"].unique() if c not in existentes]

    consultas, base = [], []
    for c, g in por_persona:
        if c in existentes:
            consulta = g.sample(1, random_state=int(c))
            consultas.append(consulta.assign(existe=True))
            base.append(g.drop(consulta.index))
    for c in rng.permutation(nuevas)[:max_consultas]:
        consultas.append(
            por_persona.get_group(c).sample(1, random_state=int(c)).assign(existe=False)
        )
    consultas_df = pd.concat(consultas, ignore_index=True)
    existentes_df = consultas_df[consultas_df["existe"]].sample(
        min(max_consultas, int(consultas_df["existe"].sum())), random_state=semilla
    )
    nuevas_df = consultas_df[~consultas_df["existe"]]
    return (
        pd.concat(base, ignore_index=True),
        pd.concat([existentes_df, nuevas_df], ignore_index=True)
        .sample(frac=1, random_state=semilla)
        .reset_index(drop=True),
        personas,
    )


def resultados_por_consulta(vinculador: Vinculador, consultas: pd.DataFrame) -> pd.DataFrame:
    """Decisión de cada consulta con ``tp``, ``fp`` y ``fn``.

    Un acierto exige decir ``cliente`` **y** encontrar al cliente correcto (el de la
    misma persona verdadera). ``revisar`` y ``nuevo`` cuentan como "no es cliente".
    """
    persona_de_cliente = vinculador.base.set_index("unique_id")["cluster"]
    for fila in consultas.head(3).to_dict("records"):  # calentamiento
        vinculador.consultar(fila)
    filas = []
    for fila in consultas.to_dict("records"):
        r = vinculador.consultar(fila)
        cliente = r.get("cliente", {}).get("cliente_id")
        correcto = cliente is not None and persona_de_cliente.get(cliente) == fila["cluster"]
        filas.append(
            {
                "existe": fila["existe"],
                "decision": r["decision"],
                "correcto": bool(correcto),
                "probabilidad": r["probabilidad"],
                "peso": r["peso"],
                "milisegundos": r["milisegundos"],
            }
        )
    t = pd.DataFrame(filas)
    t["tp"] = (t["decision"] == "cliente") & t["existe"] & t["correcto"]
    t["fp"] = (t["decision"] == "cliente") & ~(t["existe"] & t["correcto"])
    t["fn"] = t["existe"] & ~t["tp"]
    return t


def precision_por_prevalencia(
    t: pd.DataFrame,
    prevalencias: tuple[float, ...] = (0.01, 0.10, 0.50),
    n_bootstrap: int = 1000,
    semilla: int = 0,
) -> dict[str, Any]:
    """Precisión esperada si una fracción ``prevalencia`` de las consultas son clientes.

    La evaluación mezcla consultas de clientes existentes y de personas nuevas en una
    proporción fija. Con las tasas de cada grupo (aciertos y clientes equivocados entre
    las existentes, falsas alarmas entre las nuevas) se recalcula la precisión para otra
    mezcla: π·a / (π·(a + e) + (1 − π)·f). El recall no depende de la mezcla. El
    intervalo remuestrea por separado existentes y nuevas.
    """
    existentes, nuevas = t[t["existe"]], t[~t["existe"]]

    def tasas(e: pd.DataFrame, n: pd.DataFrame) -> tuple[float, float, float]:
        return e["tp"].mean(), e["fp"].mean(), n["fp"].mean()

    def precision(a: float, e: float, f: float, pi: float) -> float:
        positivos = pi * (a + e) + (1 - pi) * f
        return pi * a / positivos if positivos else 0.0

    rng = np.random.default_rng(semilla)
    replicas = [
        tasas(
            existentes.iloc[rng.integers(0, len(existentes), len(existentes))],
            nuevas.iloc[rng.integers(0, len(nuevas), len(nuevas))],
        )
        for _ in range(n_bootstrap)
    ]
    a, e, f = tasas(existentes, nuevas)
    resultado: dict[str, Any] = {
        "tasas": {
            "aciertos_entre_existentes": a,
            "cliente_equivocado_entre_existentes": e,
            "falsa_alarma_entre_nuevas": f,
            "falsas_alarmas": int(nuevas["fp"].sum()),
            "nuevas": len(nuevas),
        },
        "precision": {},
    }
    for pi in prevalencias:
        valores = [precision(*r, pi) for r in replicas]
        resultado["precision"][str(pi)] = {
            "valor": precision(a, e, f, pi),
            "ic_inf": float(np.quantile(valores, 0.025)),
            "ic_sup": float(np.quantile(valores, 0.975)),
        }
    return resultado


def evaluar(
    vinculador: Vinculador, consultas: pd.DataFrame, n_bootstrap: int = 1000, semilla: int = 0
) -> dict[str, Any]:
    """Precisión y recall de "ya es cliente", decisiones y latencia por consulta."""
    t = resultados_por_consulta(vinculador, consultas)

    def metricas(muestra: pd.DataFrame) -> tuple[float, float]:
        tp, fp, fn = muestra["tp"].sum(), muestra["fp"].sum(), muestra["fn"].sum()
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        return precision, recall

    rng = np.random.default_rng(semilla)
    replicas = np.array(
        [metricas(t.iloc[rng.integers(0, len(t), len(t))]) for _ in range(n_bootstrap)]
    )
    precision, recall = metricas(t)
    return {
        "consultas": len(t),
        "existentes": int(t["existe"].sum()),
        "nuevas": int((~t["existe"]).sum()),
        "precision": {
            "valor": precision,
            "ic_inf": float(np.quantile(replicas[:, 0], 0.025)),
            "ic_sup": float(np.quantile(replicas[:, 0], 0.975)),
        },
        "recall": {
            "valor": recall,
            "ic_inf": float(np.quantile(replicas[:, 1], 0.025)),
            "ic_sup": float(np.quantile(replicas[:, 1], 0.975)),
        },
        "decisiones": {
            "existentes": t[t["existe"]]["decision"].value_counts().to_dict(),
            "nuevas": t[~t["existe"]]["decision"].value_counts().to_dict(),
        },
        "cliente_equivocado": int(
            ((t["decision"] == "cliente") & t["existe"] & ~t["correcto"]).sum()
        ),
        "latencia_ms": {
            "mediana": float(t["milisegundos"].median()),
            "p95": float(t["milisegundos"].quantile(0.95)),
            "maxima": float(t["milisegundos"].max()),
        },
    }


def guardar(resultado: dict, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )
