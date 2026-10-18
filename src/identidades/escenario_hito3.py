"""Escenario del hito 3: historia en el tiempo, metadatos y datos compartidos con verdad.

Parte de las personas verdaderas de ``sinteticos`` (sin modificar ese generador, para no
alterar los hitos anteriores) y agrega:

- **Historia:** el celular, el correo y el domicilio de una persona pueden cambiar en una
  fecha. El valor **vigente** (el último) es la verdad del registro de oro.
- **Metadatos por registro:** ``fecha_actualizacion``, ``canal`` (sucursal, app, web,
  call_center, corresponsal) y ``validado`` (el contacto y el documento se verificaron en
  ese canal). Un registro guarda los valores vigentes en su fecha; los canales menos
  confiables y los datos no validados tienen más errores de captura.
- **Datos compartidos con verdad conocida:**
  - *relleno*: teléfonos, correos y direcciones genéricas (3000000000, notiene@...);
  - *hogar*: familiares que comparten dirección y a veces teléfono;
  - *sospechoso*: anillos de 3 a 6 personas no relacionadas que en registros recientes,
    por canales digitales y sin validar, comparten un mismo celular, correo o dirección;
    y suplantaciones: un registro de una persona con el documento de otra.

Todo es sintético.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from identidades import estandarizacion as v1
from identidades import estandarizacion_v2 as v2
from identidades import sinteticos

# Confiabilidad del canal: probabilidad de capturar un campo sin error (verdad del
# generador; el registro de oro no la conoce, debe inferir con qué fuente quedarse).
CONFIABILIDAD: dict[str, float] = {
    "sucursal": 0.97,
    "app": 0.93,
    "web": 0.85,
    "call_center": 0.80,
    "corresponsal": 0.75,
}
PROB_VALIDADO: dict[str, float] = {
    "sucursal": 0.80,
    "app": 0.60,
    "web": 0.30,
    "call_center": 0.20,
    "corresponsal": 0.10,
}
PESO_CANAL: dict[str, float] = {
    "sucursal": 0.30,
    "app": 0.25,
    "web": 0.20,
    "call_center": 0.15,
    "corresponsal": 0.10,
}
CANALES_DIGITALES: tuple[str, ...] = ("app", "web", "corresponsal")

INICIO: date = date(2012, 1, 1)
FIN: date = date(2025, 6, 30)


@dataclass(frozen=True)
class ParametrosEscenario:
    """Proporciones del escenario (por persona o por registro)."""

    cambia_celular: float = 0.35
    cambia_correo: float = 0.25
    se_muda: float = 0.25
    relleno: float = 0.04
    anillos_por_mil: float = 12.0
    tamano_anillo: tuple[int, int] = (3, 6)
    suplantaciones_por_mil: float = 6.0


def _fecha_aleatoria(rng: random.Random, desde: date = INICIO, hasta: date = FIN) -> date:
    return desde + timedelta(days=rng.randrange((hasta - desde).days + 1))


def _texto_direccion(d: dict) -> str:
    cuadrante = f" {d['cuadrante']}" if d.get("cuadrante") else ""
    via = sinteticos.VARIANTES_VIA[d["via"]][0]
    return f"{via} {d['numero_via']}{cuadrante} # {d['placa']}-{d['consecutivo']}"


class Escenario:
    """Genera registros con historia, metadatos y datos compartidos."""

    def __init__(
        self,
        n_personas: int = 2000,
        semilla: int = 3030,
        parametros: ParametrosEscenario | None = None,
    ) -> None:
        self.semilla = semilla
        self.rng = random.Random(semilla)
        self.p = parametros or ParametrosEscenario()
        _, self.personas = sinteticos.generar(n_personas, semilla)
        self.gen = sinteticos.Generador(semilla + 1)  # direcciones y celulares nuevos

    # ---------- Historia ----------

    def _familia(self) -> dict[int, int]:
        """Raíz de la familia de cada persona (ella misma si no tiene familiares)."""
        padre = dict(zip(self.personas["cluster"], self.personas["familiar_de"], strict=True))

        def raiz(c: int) -> int:
            while padre.get(c) is not None and not pd.isna(padre[c]):
                c = int(padre[c])
            return c

        return {c: raiz(c) for c in padre}

    def historia(self) -> dict[int, dict]:
        """Valores por persona: inicial, cambio (fecha y nuevo valor) y vigente."""
        familia = self._familia()
        con_familia = {r for c, r in familia.items() if c != r} | {
            c for c, r in familia.items() if c != r
        }
        hist = {}
        for fila in self.personas.itertuples(index=False):
            d = fila._asdict()
            direccion = {
                "via": d["direccion_via"],
                "numero_via": d["direccion_numero_via"],
                "cuadrante": None
                if pd.isna(d["direccion_cuadrante"])
                else d["direccion_cuadrante"],
                "placa": d["direccion_placa"],
                "consecutivo": d["direccion_consecutivo"],
            }
            h = {
                "celular": [(INICIO, d["celular"])],
                "correo": [(INICIO, d["correo"])],
                "direccion": [(INICIO, _texto_direccion(direccion))],
            }
            if self.rng.random() < self.p.cambia_celular:
                h["celular"].append((_fecha_aleatoria(self.rng), self.gen._celular()))
            if self.rng.random() < self.p.cambia_correo:
                nuevo = self.gen._correo(d["primer_nombre"], d["primer_apellido"])
                h["correo"].append((_fecha_aleatoria(self.rng), nuevo))
            # Los hogares no se mudan, para que la dirección compartida siga vigente.
            if d["cluster"] not in con_familia and self.rng.random() < self.p.se_muda:
                h["direccion"].append(
                    (_fecha_aleatoria(self.rng), _texto_direccion(self.gen._direccion()))
                )
            hist[d["cluster"]] = h
        return hist

    @staticmethod
    def vigente_en(historia: list[tuple[date, str]], fecha: date) -> str:
        valor = historia[0][1]
        for desde, v in historia:
            if desde <= fecha:
                valor = v
        return valor

    # ---------- Captura ----------

    def _error_texto(self, texto: str, canal: str, validado: bool) -> str:
        if validado or self.rng.random() < CONFIABILIDAD[canal]:
            return texto
        return self.gen._digitacion(texto)

    def _error_numero(self, numero: str, canal: str, validado: bool) -> str:
        if validado or self.rng.random() < CONFIABILIDAD[canal]:
            return numero
        i = self.rng.randrange(len(numero))
        return numero[:i] + self.rng.choice("0123456789") + numero[i + 1 :]

    def _faltante(self, canal: str) -> bool:
        return self.rng.random() < (1 - CONFIABILIDAD[canal]) / 2

    def registro(
        self, persona: dict, h: dict, fecha: date, canal: str, validado: bool, uid: int
    ) -> dict:
        nombres = " ".join(
            n for n in (persona["primer_nombre"], persona["segundo_nombre"]) if isinstance(n, str)
        )
        apellidos = " ".join(
            a
            for a in (persona["primer_apellido"], persona["segundo_apellido"])
            if isinstance(a, str)
        )
        celular = self.vigente_en(h["celular"], fecha)
        correo = self.vigente_en(h["correo"], fecha)
        direccion = self.vigente_en(h["direccion"], fecha)
        no_validado = not validado
        if no_validado and self.rng.random() < self.p.relleno:
            celular = self.rng.choice(sinteticos.TELEFONOS_RELLENO)
        if no_validado and self.rng.random() < self.p.relleno:
            correo = self.rng.choice(sinteticos.CORREOS_RELLENO)
        if no_validado and self.rng.random() < self.p.relleno:
            direccion = self.rng.choice(sinteticos.DIRECCIONES_RELLENO)
        return {
            "unique_id": uid,
            "tipo_documento": persona["tipo_documento"],
            "numero_documento": self._error_numero(persona["numero_documento"], canal, validado),
            "nombres": self.gen._mayusculas(self._error_texto(nombres, canal, False)),
            "apellidos": self.gen._mayusculas(self._error_texto(apellidos, canal, False)),
            "fecha_nacimiento": persona["fecha_nacimiento"],
            "celular": None
            if self._faltante(canal)
            else self._error_numero(celular, canal, validado),
            "correo": None if self._faltante(canal) else self._error_texto(correo, canal, validado),
            "direccion": None
            if self._faltante(canal)
            else self._error_texto(direccion, canal, False),
            "ciudad": persona["ciudad"],
            "departamento": persona["departamento"],
            "cluster": persona["cluster"],
            "fecha_actualizacion": fecha.isoformat(),
            "canal": canal,
            "validado": validado,
            "origen": "normal",
        }

    def _canal(self) -> str:
        return self.rng.choices(list(PESO_CANAL), weights=list(PESO_CANAL.values()))[0]

    # ---------- Escenario completo ----------

    def generar(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Devuelve ``(registros, verdad_personas, verdad_compartidos)``."""
        hist = self.historia()
        familia = self._familia()
        personas = {p["cluster"]: p for p in self.personas.to_dict("records")}
        pesos = sinteticos.Composicion().registros_por_persona
        registros: list[dict] = []
        for c, persona in personas.items():
            n = self.rng.choices(range(1, len(pesos) + 1), weights=pesos)[0]
            for _ in range(n):
                canal = self._canal()
                validado = self.rng.random() < PROB_VALIDADO[canal]
                fecha = _fecha_aleatoria(self.rng)
                registros.append(
                    self.registro(persona, hist[c], fecha, canal, validado, len(registros))
                )

        sospechosos: dict[tuple[str, str], set[int]] = {}
        self._anillos(personas, familia, hist, registros, sospechosos)
        self._suplantaciones(personas, hist, registros, sospechosos)

        verdad_personas = pd.DataFrame(
            [
                {
                    "cluster": c,
                    "documento": p["numero_documento"],
                    "nombres": " ".join(
                        n for n in (p["primer_nombre"], p["segundo_nombre"]) if isinstance(n, str)
                    ),
                    "apellidos": " ".join(
                        a
                        for a in (p["primer_apellido"], p["segundo_apellido"])
                        if isinstance(a, str)
                    ),
                    "fecha_nacimiento": p["fecha_nacimiento"],
                    "celular": hist[c]["celular"][-1][1],
                    "correo": hist[c]["correo"][-1][1],
                    "direccion": hist[c]["direccion"][-1][1],
                    "familia": familia[c],
                }
                for c, p in personas.items()
            ]
        )
        df = pd.DataFrame(registros)
        return df, verdad_personas, verdad_compartidos(df, familia, sospechosos)

    def _anillos(self, personas, familia, hist, registros, sospechosos) -> None:
        """Anillos: personas no relacionadas comparten un contacto en registros recientes."""
        solas = [
            c
            for c in personas
            if familia[c] == c and sum(1 for f in familia.values() if f == c) == 1
        ]
        self.rng.shuffle(solas)
        n_anillos = round(len(personas) * self.p.anillos_por_mil / 1000)
        for _ in range(n_anillos):
            k = self.rng.randint(*self.p.tamano_anillo)
            if len(solas) < k:
                break
            miembros = [solas.pop() for _ in range(k)]
            campo = self.rng.choice(["celular", "correo", "direccion"])
            if campo == "celular":
                valor = self.gen._celular()
            elif campo == "correo":
                dominio = self.rng.choice(sinteticos.DOMINIOS_CORREO)
                valor = f"pagos{self.rng.randint(100, 999)}@{dominio}"
            else:
                valor = _texto_direccion(self.gen._direccion())
            for c in miembros:
                fecha = _fecha_aleatoria(self.rng, date(2024, 1, 1), FIN)
                canal = self.rng.choice(CANALES_DIGITALES)
                r = self.registro(personas[c], hist[c], fecha, canal, False, len(registros))
                r[campo] = valor
                r["origen"] = f"anillo_{campo}"
                registros.append(r)
            sospechosos[(campo, valor)] = set(miembros)

    def _suplantaciones(self, personas, hist, registros, sospechosos) -> None:
        """Suplantación: un registro de una persona con el documento de otra."""
        ids = list(personas)
        n = round(len(personas) * self.p.suplantaciones_por_mil / 1000)
        for _ in range(n):
            victima, impostor = self.rng.sample(ids, 2)
            documento = personas[victima]["numero_documento"]
            fecha = _fecha_aleatoria(self.rng, date(2024, 1, 1), FIN)
            canal = self.rng.choice(CANALES_DIGITALES)
            r = self.registro(
                personas[impostor], hist[impostor], fecha, canal, False, len(registros)
            )
            r["numero_documento"] = documento
            r["origen"] = "suplantacion"
            registros.append(r)
            sospechosos[("documento", documento)] = {victima, impostor}


# ---------- Normalización común para comparar valores ----------


def normalizar(tipo: str, valor: object) -> str | None:
    """Clave normalizada de un valor de contacto o documento (para agrupar y comparar)."""
    if tipo == "celular":
        telefonos = v2.extraer_telefonos(valor)
        return telefonos[0] if telefonos else None
    if tipo == "correo":
        return v1.normalizar_correo(valor)
    if tipo == "direccion":
        return v1.normalizar_direccion(valor)["direccion"]
    if tipo == "documento":
        return v2.limpiar_documento(valor)
    raise ValueError(tipo)


TIPOS_COMPARTIDOS: dict[str, str] = {
    "celular": "celular",
    "correo": "correo",
    "direccion": "direccion",
    "documento": "numero_documento",
}


def verdad_compartidos(
    registros: pd.DataFrame,
    familia: dict[int, int],
    sospechosos: dict[tuple[str, str], set[int]],
) -> pd.DataFrame:
    """Etiqueta verdadera de cada valor compartido por dos o más personas distintas.

    relleno (valor genérico conocido) > sospechoso (anillo o suplantación inyectados) >
    hogar (todas las personas de la misma familia) > coincidencia (otro caso).
    """
    rellenos = {
        "celular": {normalizar("celular", t) for t in sinteticos.TELEFONOS_RELLENO},
        "correo": {normalizar("correo", c) for c in sinteticos.CORREOS_RELLENO},
        "direccion": {normalizar("direccion", d) for d in sinteticos.DIRECCIONES_RELLENO},
        "documento": set(),
    }
    sospechosos_norm = {(t, normalizar(t, v)): ps for (t, v), ps in sospechosos.items()}
    filas = []
    for tipo, columna in TIPOS_COMPARTIDOS.items():
        claves = registros[columna].map(lambda v, t=tipo: normalizar(t, v))
        grupos = registros.assign(clave=claves).dropna(subset=["clave"]).groupby("clave")
        for clave, g in grupos:
            personas = set(g["cluster"])
            if len(personas) < 2:
                continue
            if clave in rellenos[tipo]:
                etiqueta = "relleno"
            elif (tipo, clave) in sospechosos_norm:
                etiqueta = "sospechoso"
            elif len({familia[p] for p in personas}) == 1:
                etiqueta = "hogar"
            else:
                etiqueta = "coincidencia"
            filas.append(
                {
                    "tipo": tipo,
                    "valor": clave,
                    "etiqueta": etiqueta,
                    "personas": len(personas),
                    "registros": len(g),
                }
            )
    return pd.DataFrame(filas)


def generar_escenario(
    n_personas: int = 2000, semilla: int = 3030, parametros: ParametrosEscenario | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Atajo: ``Escenario(n_personas, semilla, parametros).generar()``."""
    return Escenario(n_personas, semilla, parametros).generar()
