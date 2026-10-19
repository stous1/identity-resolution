"""Escenario residencial de la v1.1: hogares, predios y familias colombianas.

El escenario del hito 3 (``escenario_hito3``) solo tiene familiares que comparten apellido
y dirección, y personas solas. Este escenario genera la población desde los **predios** y
los **hogares**, para que aparezca la realidad residencial colombiana:

- **Predios:** casa (un hogar), casa de varios pisos ("le echaron la plancha": padres en
  un piso y el hijo con su propio hogar en otro, a veces con un arrendatario), edificio
  (apartamentos) y conjunto (torres, bloques, interiores, apartamentos o casas).
- **Hogares:** persona sola, pareja casada o en unión libre (sin apellidos en común),
  familia con hijos adultos que llevan el primer apellido del padre y el primero de la
  madre, madre o padre con hijos, hermanos, y compañeros de apartamento o estudiantes que
  comparten arriendo.
- **Apellido de casada:** parte de las mujeres casadas firma algunos registros como
  "Rincón de Salazar".
- **Complemento de dirección:** cada registro escribe la unidad a su manera ("Apto 502",
  "Ap 502", "T 2 Ap 501", "Piso 2", "2do piso") o la omite; el nombre del conjunto o del
  edificio aparece a veces, antes o después de la dirección.
- **Historia:** los convivientes y parte de las parejas llegaron al predio en una fecha
  (antes vivían en otro lado); el hijo del segundo piso vivió antes con sus padres; un
  apartamento que se desocupa puede recibir a otro inquilino después (ocupación sucesiva).
- **Teléfono fijo del hogar y correo familiar** compartidos, además de los datos de
  relleno, los anillos y las suplantaciones del hito 3.

Reutiliza la captura del hito 3 (canales, validación, errores) y los generadores de nombres,
documentos y direcciones de ``sinteticos``, sin modificarlos: los datos de las versiones
anteriores no cambian. Corre con la fecha fija ``sinteticos_fecha.HOY_V11``, así que es
determinista. Todo es sintético.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from identidades import sinteticos
from identidades.escenario_hito3 import (
    FIN,
    INICIO,
    PROB_VALIDADO,
    TIPOS_COMPARTIDOS,
    Escenario,
    ParametrosEscenario,
    _fecha_aleatoria,
    normalizar,
)
from identidades.sinteticos_fecha import HOY_V11, fecha_fija

TIPOS_PREDIO: tuple[str, ...] = ("casa", "casa_pisos", "edificio", "conjunto")

NOMBRES_CONJUNTO: list[str] = [
    "Los Almendros", "Altos del Bosque", "Portal de la Sabana", "Mirador del Río",
    "Villa del Prado", "Torres de San Juan", "Parque Central", "Los Cerezos",
    "Reservas del Campo", "Balcones de Alcalá", "Hacienda Santa Bárbara", "El Recreo",
    "Prados del Norte", "Colina Real", "Senderos de Castilla", "La Arboleda",
]  # fmt: skip
NOMBRES_EDIFICIO: list[str] = [
    "Torre del Parque", "San Marino", "Bellavista", "El Nogal", "Mónaco", "Plaza 93",
    "Santa Mónica", "La Esmeralda", "Portofino", "Ática", "Los Rosales", "Granada",
]  # fmt: skip

# Formas de escribir cada componente de la unidad (la primera es la canónica).
FORMAS_UNIDAD: dict[str, list[str]] = {
    "torre": ["Torre", "T", "Tr", "To", "Torre"],
    "bloque": ["Bloque", "Bl", "Blq", "Bloque"],
    "interior": ["Interior", "Int", "In", "Int."],
    "apto": ["Apto", "Apartamento", "Ap", "Apt", "Apto.", "AP", "Apt."],
    "casa": ["Casa", "Cs", "Casa"],
}
FORMAS_PISO: list[str] = ["Piso {n}", "P {n}", "{n} Piso", "{o} Piso", "{o} piso", "Piso {n}"]
ORDINALES: dict[int, list[str]] = {
    1: ["Primer", "1er"],
    2: ["Segundo", "2do", "2o"],
    3: ["Tercer", "3er"],
    4: ["Cuarto", "4to"],
}
FORMAS_CONJUNTO: list[str] = [
    "Conjunto Residencial {n}", "Conj. Res. {n}", "Conjunto {n}", "Cjto {n}",
    "Urbanización {n}", "Unidad Residencial {n}", "Conj {n}",
]  # fmt: skip
FORMAS_EDIFICIO: list[str] = ["Edificio {n}", "Ed. {n}", "Edif {n}", "Edificio {n}"]


def _tipo_predio_defecto() -> dict[str, float]:
    return {"casa": 0.55, "casa_pisos": 0.17, "edificio": 0.14, "conjunto": 0.14}


def _tipo_hogar_defecto() -> dict[str, float]:
    return {
        "solo": 0.30,
        "pareja": 0.22,
        "familia": 0.23,
        "monoparental": 0.08,
        "hermanos": 0.05,
        "convivientes": 0.12,
    }


@dataclass(frozen=True)
class ParametrosResidencial:
    """Proporciones del escenario residencial (por predio, hogar, persona o registro)."""

    tipo_predio: dict[str, float] = field(default_factory=_tipo_predio_defecto)
    tipo_hogar: dict[str, float] = field(default_factory=_tipo_hogar_defecto)
    hogares_edificio: tuple[int, int] = (2, 6)
    hogares_conjunto: tuple[int, int] = (3, 10)
    # Edificios y conjuntos, casi siempre en ciudades grandes.
    multifamiliar_ciudad_grande: float = 0.85
    # Casa de varios pisos: el piso 2 es del hijo con su pareja, o de un arrendatario.
    piso2_hijo: float = 0.75
    piso3_arrendatario: float = 0.30
    # El hogar de arriba escribe el piso; si no, usa la misma dirección de la casa.
    escribe_piso: float = 0.6
    pareja_casada: float = 0.55  # el resto, unión libre
    usa_apellido_casada: float = 0.55  # de las casadas, por registro
    pareja_llega_despues: float = 0.5  # la pareja empezó a vivir junta en una fecha
    omite_unidad: float = 0.15  # por registro, en edificios y conjuntos
    nombre_predio: float = 0.35  # por registro, el nombre del conjunto o edificio
    fijo_hogar: float = 0.25  # por hogar de 2 o más personas
    usa_fijo: float = 0.30  # por registro, si el hogar tiene fijo
    correo_familiar: float = 0.06  # por pareja: comparten un correo
    se_muda_solo: float = 0.25  # personas solas y convivientes que se van del predio
    ocupacion_sucesiva: float = 0.5  # la unidad que deja una persona sola recibe a otra
    escenario: ParametrosEscenario = field(default_factory=ParametrosEscenario)


@dataclass
class Predio:
    """Un predio: dirección base, tipo, ciudad y nombre (si es conjunto o edificio)."""

    id: int
    tipo: str
    base: dict
    ciudad: str
    departamento: str
    nombre: str | None = None
    estilo: str | None = None  # en conjuntos: torre, bloque, interior o casa
    unidades: set = field(default_factory=set)


def texto_base(d: dict, rng: random.Random | None = None) -> str:
    """Dirección base ("Calle 45 # 12-30"), con abreviaturas al azar si hay ``rng``."""
    formas = sinteticos.VARIANTES_VIA[d["via"]]
    via = rng.choice(formas) if rng else formas[0]
    numero = rng.choice(sinteticos.VARIANTES_NUMERO) if rng else "#"
    guion = rng.choice(["-", "-", " - "]) if rng else "-"
    cuadrante = f" {d['cuadrante'].title()}" if d.get("cuadrante") else ""
    return f"{via} {d['numero_via']}{cuadrante} {numero} {d['placa']}{guion}{d['consecutivo']}"


def texto_unidad(unidad: tuple, rng: random.Random | None = None) -> str:
    """Complemento de la unidad. ``unidad`` es una tupla de pares (componente, valor)."""
    partes = []
    for componente, valor in unidad:
        if componente == "piso":
            if rng is None:
                partes.append(f"Piso {valor}")
                continue
            forma = rng.choice(FORMAS_PISO)
            ordinal = rng.choice(ORDINALES.get(int(valor), [str(valor)]))
            partes.append(forma.format(n=valor, o=ordinal))
        else:
            formas = FORMAS_UNIDAD[componente]
            etiqueta = rng.choice(formas) if rng else formas[0]
            pegado = rng is not None and componente == "torre" and rng.random() < 0.1
            partes.append(f"{etiqueta}{valor}" if pegado else f"{etiqueta} {valor}")
    return " ".join(partes)


def texto_direccion(
    predio: Predio,
    unidad: tuple,
    rng: random.Random | None = None,
    p: ParametrosResidencial | None = None,
) -> str:
    """Dirección completa como la escribiría un registro (canónica si no hay ``rng``)."""
    base = texto_base(predio.base, rng)
    if rng is None:
        return f"{base} {texto_unidad(unidad)}".strip()
    p = p or ParametrosResidencial()
    omitir = predio.tipo in ("edificio", "conjunto") and rng.random() < p.omite_unidad
    complemento = "" if omitir else texto_unidad(unidad, rng)
    nombre = ""
    if predio.nombre and rng.random() < p.nombre_predio:
        formas = FORMAS_CONJUNTO if predio.tipo == "conjunto" else FORMAS_EDIFICIO
        nombre = rng.choice(formas).format(n=predio.nombre)
    if nombre and rng.random() < 0.4:
        return f"{nombre} {base} {complemento}".strip()
    return " ".join(t for t in (base, nombre, complemento) if t)


class EscenarioResidencial(Escenario):
    """Genera registros desde predios y hogares, con la captura del escenario del hito 3."""

    def __init__(
        self,
        n_personas: int = 2000,
        semilla: int = 4040,
        parametros: ParametrosResidencial | None = None,
    ) -> None:
        # No llama a Escenario.__init__: la población sale de los hogares, no de sinteticos.
        self.semilla = semilla
        self.n_personas = n_personas
        self.rng = random.Random(semilla)
        self.r = parametros or ParametrosResidencial()
        self.p = self.r.escenario
        self.gen = sinteticos.Generador(semilla + 1)
        self.personas_lista: list[dict] = []
        self.predios: list[Predio] = []
        self.hogares: dict[int, dict] = {}
        self.familias = 0

    # ---------- Personas y hogares ----------

    def _persona(
        self,
        mujer: bool,
        edad: tuple[int, int],
        apellidos: tuple[str, str | None] | None = None,
    ) -> dict:
        g = self.gen
        primer_nombre, segundo_nombre = g._nombres(mujer)
        primer_apellido, segundo_apellido = apellidos or g._apellidos()
        tipo, numero = g._documento()
        nacimiento = g.fake.date_of_birth(minimum_age=edad[0], maximum_age=edad[1])
        return {
            "cluster": len(self.personas_lista),
            "tipo_documento": tipo,
            "numero_documento": numero,
            "primer_nombre": primer_nombre,
            "segundo_nombre": segundo_nombre,
            "primer_apellido": primer_apellido,
            "segundo_apellido": segundo_apellido,
            "fecha_nacimiento": nacimiento.isoformat(),
            "celular": g._celular(),
            "correo": g._correo(primer_nombre, primer_apellido),
            "mujer": mujer,
            "apellido_casada": None,
        }

    def _agregar(self, persona: dict, hogar: int, familia: int, rol: str) -> dict:
        predio = self.predios[self.hogares[hogar]["predio"]]
        persona.update(
            cluster=len(self.personas_lista),
            hogar=hogar,
            familia=familia,
            rol=rol,
            ciudad=predio.ciudad,
            departamento=predio.departamento,
        )
        self.personas_lista.append(persona)
        self.hogares[hogar]["miembros"].append(persona["cluster"])
        return persona

    def _nueva_familia(self) -> int:
        self.familias += 1
        return self.familias - 1

    def _hogar(self, tipo: str, predio: Predio, unidad: tuple, desde: date = INICIO) -> int:
        i = len(self.hogares)
        self.hogares[i] = {
            "tipo": tipo,
            "predio": predio.id,
            "unidad": unidad,
            "desde": desde,
            "miembros": [],
            "fijo": None,
            "correo": None,
        }
        predio.unidades.add(unidad)
        return i

    @staticmethod
    def _apellidos_hijo(padre: dict, madre: dict) -> tuple[str, str]:
        """Convención colombiana: primer apellido del padre y primer apellido de la madre."""
        return padre["primer_apellido"], madre["primer_apellido"]

    def _pareja(
        self, hogar: int, edad: tuple[int, int], familia: int | None = None
    ) -> tuple[dict, dict]:
        """Hombre y mujer sin apellidos en común; ella a veces usa el apellido de casada."""
        familia = self._nueva_familia() if familia is None else familia
        el = self._agregar(self._persona(False, edad), hogar, familia, "pareja")
        ella = self._persona(True, edad)
        while {ella["primer_apellido"], ella["segundo_apellido"]} & {
            el["primer_apellido"],
            el["segundo_apellido"],
        } - {None}:
            ella = self._persona(True, edad)
        self._agregar(ella, hogar, familia, "pareja")
        if self.rng.random() < self.r.pareja_casada:
            ella["apellido_casada"] = el["primer_apellido"]
        if self.rng.random() < self.r.correo_familiar:
            usuario = sinteticos._ascii(f"familia{el['primer_apellido']}")
            dominio = self.rng.choice(sinteticos.DOMINIOS_CORREO)
            self.hogares[hogar]["correo"] = f"{usuario}{self.rng.randint(1, 99)}@{dominio}"
        return el, ella

    def _llenar_hogar(self, tipo: str, hogar: int) -> None:
        rng = self.rng
        if tipo == "solo":
            persona = self._persona(rng.random() < 0.5, (18, 85))
            self._agregar(persona, hogar, self._nueva_familia(), "solo")
        elif tipo == "pareja":
            self._pareja(hogar, (22, 80))
        elif tipo == "familia":
            familia = self._nueva_familia()
            padre, madre = self._pareja(hogar, (42, 78), familia)
            for _ in range(rng.choice([1, 1, 2, 2, 3])):
                apellidos = self._apellidos_hijo(padre, madre)
                self._agregar(self._persona(rng.random() < 0.5, (18, 30), apellidos), hogar,
                              familia, "hijo")  # fmt: skip
        elif tipo == "monoparental":
            familia = self._nueva_familia()
            jefe = self._agregar(
                self._persona(rng.random() < 0.75, (40, 75)), hogar, familia, "jefe"
            )
            otro = self.gen._apellidos()[0]  # el otro padre no vive ahí
            for _ in range(rng.choice([1, 1, 2])):
                if jefe["mujer"]:
                    apellidos = (otro, jefe["primer_apellido"])
                else:
                    apellidos = (jefe["primer_apellido"], otro)
                self._agregar(self._persona(rng.random() < 0.5, (18, 30), apellidos), hogar,
                              familia, "hijo")  # fmt: skip
        elif tipo == "hermanos":
            familia = self._nueva_familia()
            apellidos = self.gen._apellidos()
            for _ in range(rng.choice([2, 2, 3])):
                self._agregar(self._persona(rng.random() < 0.5, (18, 60), apellidos), hogar,
                              familia, "hermano")  # fmt: skip
        elif tipo == "convivientes":
            for _ in range(rng.choice([2, 2, 3, 3, 4])):
                self._agregar(self._persona(rng.random() < 0.5, (18, 35)), hogar,
                              self._nueva_familia(), "conviviente")  # fmt: skip
        else:
            raise ValueError(tipo)

    # ---------- Predios ----------

    def _predio(self, tipo: str) -> Predio:
        ciudad, departamento = self.gen._ciudad()
        if (
            tipo in ("edificio", "conjunto")
            and self.rng.random() < self.r.multifamiliar_ciudad_grande
        ):
            codigo = self.rng.choice(sinteticos.CIUDADES_GRANDES)
            ciudad = self.gen._municipios[codigo]
            departamento = self.gen._departamentos[codigo[:2]]
        nombre = None
        if tipo == "conjunto":
            nombre = self.rng.choice(NOMBRES_CONJUNTO)
        elif tipo == "edificio" and self.rng.random() < 0.6:
            nombre = self.rng.choice(NOMBRES_EDIFICIO)
        predio = Predio(len(self.predios), tipo, self.gen._direccion(), ciudad, departamento,
                        nombre)  # fmt: skip
        self.predios.append(predio)
        return predio

    def _tipo_hogar(self) -> str:
        tipos = list(self.r.tipo_hogar)
        return self.rng.choices(tipos, weights=list(self.r.tipo_hogar.values()))[0]

    def _desde(self, tipo: str) -> date:
        """Fecha en que el hogar llegó al predio: los convivientes y parte de las parejas."""
        if tipo == "convivientes" or (
            tipo == "pareja" and self.rng.random() < self.r.pareja_llega_despues
        ):
            return _fecha_aleatoria(self.rng, date(2014, 1, 1), date(2024, 6, 30))
        return INICIO

    def _apto(self, max_piso: int = 20) -> tuple[str, str]:
        return ("apto", f"{self.rng.randint(1, max_piso)}{self.rng.randint(1, 4):02d}")

    def _forma_unidad(self, predio: Predio) -> Callable[[], tuple]:
        rng = self.rng
        if predio.tipo == "edificio":
            return lambda: (self._apto(),)
        if predio.estilo is None:
            predio.estilo = rng.choice(["torre", "bloque", "interior", "casa"])
        estilo = predio.estilo
        if estilo == "casa":
            return lambda: (("casa", str(rng.randint(1, 120))),)
        return lambda: ((estilo, str(rng.randint(1, 8))), self._apto(12))

    def _unidad_libre(self, predio: Predio, forma: Callable[[], tuple]) -> tuple:
        for _ in range(100):
            unidad = forma()
            if unidad not in predio.unidades:
                return unidad
        raise RuntimeError("sin unidades libres")

    def _poblar_predio(self, predio: Predio) -> None:
        rng = self.rng
        if predio.tipo == "casa":
            tipo = self._tipo_hogar()
            self._llenar_hogar(tipo, self._hogar(tipo, predio, (), self._desde(tipo)))
        elif predio.tipo == "casa_pisos":
            self._casa_pisos(predio)
        else:
            rango = (
                self.r.hogares_edificio if predio.tipo == "edificio" else self.r.hogares_conjunto
            )
            forma = self._forma_unidad(predio)
            for _ in range(rng.randint(*rango)):
                tipo = self._tipo_hogar()
                unidad = self._unidad_libre(predio, forma)
                self._llenar_hogar(tipo, self._hogar(tipo, predio, unidad, self._desde(tipo)))

    def _casa_pisos(self, predio: Predio) -> None:
        """Padres en el primer piso; el hijo con su pareja (o un arrendatario) arriba."""
        rng = self.rng
        familia = self._nueva_familia()
        abajo = self._hogar("familia", predio, ())
        padre, madre = self._pareja(abajo, (50, 80), familia)
        if rng.random() < 0.4:  # un hermano sigue viviendo con los padres
            apellidos = self._apellidos_hijo(padre, madre)
            self._agregar(self._persona(rng.random() < 0.5, (18, 35), apellidos), abajo, familia,
                          "hijo")  # fmt: skip
        piso2 = (("piso", "2"),) if rng.random() < self.r.escribe_piso else ()
        desde = _fecha_aleatoria(rng, date(2014, 1, 1), date(2023, 12, 31))
        if rng.random() < self.r.piso2_hijo:
            arriba = self._hogar("pareja_hijo", predio, piso2, desde)
            self.hogares[arriba]["antes"] = abajo  # el hijo vivió abajo antes de subir
            apellidos = self._apellidos_hijo(padre, madre)
            hijo = self._agregar(self._persona(rng.random() < 0.5, (24, 45), apellidos), arriba,
                                 familia, "hijo_piso2")  # fmt: skip
            # La pareja del hijo es familia política: misma familia, otro hogar.
            pareja = self._agregar(self._persona(not hijo["mujer"], (24, 45)), arriba, familia,
                                   "pareja_hijo")  # fmt: skip
            if pareja["mujer"] and rng.random() < self.r.pareja_casada:
                pareja["apellido_casada"] = hijo["primer_apellido"]
        else:
            arriba = self._hogar("arrendatario", predio, piso2, desde)
            self._llenar_hogar(rng.choice(["solo", "pareja", "convivientes"]), arriba)
        if rng.random() < self.r.piso3_arrendatario:
            tercero = self._hogar("arrendatario", predio, (("piso", "3"),), desde)
            self._llenar_hogar(rng.choice(["solo", "pareja", "convivientes"]), tercero)

    def construir_poblacion(self) -> None:
        tipos = list(self.r.tipo_predio)
        pesos = list(self.r.tipo_predio.values())
        while len(self.personas_lista) < self.n_personas:
            self._poblar_predio(self._predio(self.rng.choices(tipos, weights=pesos)[0]))
        for hogar in self.hogares.values():
            if len(hogar["miembros"]) >= 2 and self.rng.random() < self.r.fijo_hogar:
                hogar["fijo"] = "601" + "".join(str(self.rng.randint(0, 9)) for _ in range(7))

    # ---------- Historia ----------

    def _otra_direccion(self) -> tuple[Predio, tuple]:
        """Una casa o apartamento en otro lado, donde nadie más del escenario vive."""
        tipo = self.rng.choice(["casa", "edificio"])
        predio = self._predio(tipo)
        unidad = () if tipo == "casa" else (self._apto(),)
        predio.unidades.add(unidad)
        return predio, unidad

    def historia_residencial(self) -> dict[int, dict]:
        """Valores por persona en el tiempo: celular, correo y domicilio (predio, unidad)."""
        rng = self.rng
        hist: dict[int, dict] = {}
        sucesivos: list[tuple[int, date]] = []
        for p in list(self.personas_lista):
            hogar = self.hogares[p["hogar"]]
            predio = self.predios[hogar["predio"]]
            h: dict[str, list] = {
                "celular": [(INICIO, p["celular"])],
                "correo": [(INICIO, p["correo"])],
                "direccion": [],
            }
            if rng.random() < self.p.cambia_celular:
                h["celular"].append((_fecha_aleatoria(rng), self.gen._celular()))
            if rng.random() < self.p.cambia_correo:
                nuevo = self.gen._correo(p["primer_nombre"], p["primer_apellido"])
                h["correo"].append((_fecha_aleatoria(rng), nuevo))
            if hogar["desde"] > INICIO:
                if p["rol"] == "hijo_piso2":
                    previo = (predio, ())  # vivía con los padres, en la misma casa
                else:
                    previo = self._otra_direccion()
                h["direccion"].append((INICIO, previo))
            h["direccion"].append((hogar["desde"], (predio, hogar["unidad"])))
            if (
                p["rol"] in ("solo", "conviviente")
                and hogar["tipo"] not in ("arrendatario", "sucesivo")
                and hogar["desde"] < date(2022, 1, 1)
                and rng.random() < self.r.se_muda_solo
            ):
                desde = max(hogar["desde"], date(2015, 1, 1))
                fecha = _fecha_aleatoria(rng, desde, date(2023, 6, 30))
                h["direccion"].append((fecha, self._otra_direccion()))
                if p["rol"] == "solo" and rng.random() < self.r.ocupacion_sucesiva:
                    sucesivos.append((p["hogar"], fecha))
            hist[p["cluster"]] = h
        for hogar_anterior, fecha in sucesivos:
            self._ocupante_sucesivo(hogar_anterior, fecha, hist)
        return hist

    def _ocupante_sucesivo(self, hogar_anterior: int, fecha: date, hist: dict) -> None:
        """Un inquilino nuevo llega a la unidad que se desocupó (después de ``fecha``)."""
        anterior = self.hogares[hogar_anterior]
        predio = self.predios[anterior["predio"]]
        llegada = fecha + timedelta(days=self.rng.randint(30, 400))
        hogar = self._hogar("sucesivo", predio, anterior["unidad"], llegada)
        p = self._agregar(
            self._persona(self.rng.random() < 0.5, (20, 60)), hogar, self._nueva_familia(), "solo"
        )
        hist[p["cluster"]] = {
            "celular": [(INICIO, p["celular"])],
            "correo": [(INICIO, p["correo"])],
            "direccion": [
                (INICIO, self._otra_direccion()),
                (llegada, (predio, anterior["unidad"])),
            ],
        }

    # ---------- Captura ----------

    def registro_residencial(
        self, persona: dict, h: dict, fecha: date, canal: str, validado: bool, uid: int
    ) -> dict:
        """Un registro con la captura del hito 3 (canal, validación, errores, relleno), la
        dirección escrita a su manera, el apellido de casada y los datos del hogar."""
        rng = self.rng
        hogar = self.hogares[persona["hogar"]]
        nombres = " ".join(
            n for n in (persona["primer_nombre"], persona["segundo_nombre"]) if isinstance(n, str)
        )
        apellidos = " ".join(
            a
            for a in (persona["primer_apellido"], persona["segundo_apellido"])
            if isinstance(a, str)
        )
        if persona["apellido_casada"] and rng.random() < self.r.usa_apellido_casada:
            base = persona["primer_apellido"]
            if persona["segundo_apellido"] and rng.random() < 0.5:
                base += f" {persona['segundo_apellido']}"
            apellidos = f"{base} {rng.choice(['de', 'DE', 'De'])} {persona['apellido_casada']}"
        celular = self.vigente_en(h["celular"], fecha)
        correo = self.vigente_en(h["correo"], fecha)
        predio, unidad = self.vigente_en(h["direccion"], fecha)
        if hogar["fijo"] and rng.random() < self.r.usa_fijo:
            celular = hogar["fijo"]
        if hogar["correo"] and rng.random() < 0.6:
            correo = hogar["correo"]
        direccion = texto_direccion(predio, unidad, rng, self.r)
        if not validado and rng.random() < self.p.relleno:
            celular = rng.choice(sinteticos.TELEFONOS_RELLENO)
        if not validado and rng.random() < self.p.relleno:
            correo = rng.choice(sinteticos.CORREOS_RELLENO)
        if not validado and rng.random() < self.p.relleno:
            direccion = rng.choice(sinteticos.DIRECCIONES_RELLENO)
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
            else self.gen._mayusculas(self._error_texto(direccion, canal, False)),
            "ciudad": predio.ciudad,
            "departamento": predio.departamento,
            "cluster": persona["cluster"],
            "fecha_actualizacion": fecha.isoformat(),
            "canal": canal,
            "validado": validado,
            "origen": "normal",
        }

    # ---------- Escenario completo ----------

    def generar(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Devuelve ``(registros, verdad_personas, verdad_compartidos)``.

        ``verdad_compartidos`` agrupa con la normalización del hito 3; para otra
        normalización, ``verdad_compartidos_residencial`` con ``self.verdad_personas`` y
        ``self.sospechosos``.
        """
        with fecha_fija(*HOY_V11):
            return self._generar()

    def _generar(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        self.construir_poblacion()
        hist = self.historia_residencial()
        pesos = sinteticos.Composicion().registros_por_persona
        registros: list[dict] = []
        personas = {p["cluster"]: p for p in self.personas_lista}
        for c, persona in personas.items():
            hogar = self.hogares[persona["hogar"]]
            desde = hogar["desde"] if hogar["tipo"] == "sucesivo" else INICIO
            n = self.rng.choices(range(1, len(pesos) + 1), weights=pesos)[0]
            for _ in range(n):
                canal = self._canal()
                validado = self.rng.random() < PROB_VALIDADO[canal]
                fecha = _fecha_aleatoria(self.rng, desde, FIN)
                registros.append(
                    self.registro_residencial(
                        persona, hist[c], fecha, canal, validado, len(registros)
                    )  # fmt: skip
                )
        # Los anillos y las suplantaciones usan la captura del hito 3 (``Escenario.registro``)
        # con la dirección vigente en texto canónico. Los anillos se forman solo con personas
        # que viven solas.
        textos = {
            c: {**h, "direccion": [(d, texto_direccion(pr, u)) for d, (pr, u) in h["direccion"]]}
            for c, h in hist.items()
        }
        familia = {c: (c if p["rol"] == "solo" else -1 - p["hogar"]) for c, p in personas.items()}
        self.sospechosos: dict[tuple[str, str], set[int]] = {}
        self._anillos(personas, familia, textos, registros, self.sospechosos)
        self._suplantaciones(personas, textos, registros, self.sospechosos)

        self.verdad_personas = self._tabla_personas(hist)
        df = pd.DataFrame(registros)
        verdad = verdad_compartidos_residencial(
            df, self.verdad_personas, self.sospechosos, normalizar
        )
        return df, self.verdad_personas, verdad

    def _tabla_personas(self, hist: dict) -> pd.DataFrame:
        filas = []
        for p in self.personas_lista:
            hogar = self.hogares[p["hogar"]]
            predio = self.predios[hogar["predio"]]
            nombres = " ".join(n for n in (p["primer_nombre"], p["segundo_nombre"]) if n)
            apellidos = " ".join(a for a in (p["primer_apellido"], p["segundo_apellido"]) if a)
            ultimo = hist[p["cluster"]]["direccion"][-1][1][0]
            filas.append(
                {
                    "cluster": p["cluster"],
                    "documento": p["numero_documento"],
                    "nombres": nombres,
                    "apellidos": apellidos,
                    "fecha_nacimiento": p["fecha_nacimiento"],
                    "celular": hist[p["cluster"]]["celular"][-1][1],
                    "correo": hist[p["cluster"]]["correo"][-1][1],
                    "direccion": texto_direccion(predio, hogar["unidad"]),
                    "mujer": p["mujer"],
                    "apellido_casada": p["apellido_casada"],
                    "rol": p["rol"],
                    "hogar": p["hogar"],
                    "tipo_hogar": hogar["tipo"],
                    "familia": p["familia"],
                    "predio": predio.id,
                    "tipo_predio": predio.tipo,
                    "unidad": texto_unidad(hogar["unidad"]) or None,
                    "se_mudo": ultimo.id != predio.id,
                }
            )
        return pd.DataFrame(filas)


# ---------- Verdad de los datos compartidos ----------

ETIQUETAS_VERDAD: tuple[str, ...] = (
    "relleno",
    "sospechoso",
    "hogar",
    "pareja",
    "convivencia",
    "multifamiliar",
    "coincidencia",
)


def etiquetar_personas(personas: set[int], verdad: pd.DataFrame) -> str:
    """Etiqueta verdadera de un grupo de personas que comparten un dato (sin relleno ni
    sospecha inyectada). ``verdad`` es la tabla de personas indexada por ``cluster``.

    - ``hogar``: todas de la misma familia (incluye la familia repartida en dos pisos);
    - ``pareja``: una pareja sola (sin hijos ni otros familiares en el grupo);
    - ``convivencia``: un solo hogar sin parentesco entre todos (compañeros de apartamento)
      u ocupantes sucesivos de la misma unidad;
    - ``multifamiliar``: varios hogares sin parentesco en el mismo predio;
    - ``coincidencia``: otro caso (por ejemplo, un error de digitación que choca).
    """
    filas = verdad.loc[sorted(personas)]
    if filas["familia"].nunique() == 1:
        roles = set(filas["rol"])
        return "pareja" if roles == {"pareja"} and len(filas) == 2 else "hogar"
    if filas["predio"].nunique() > 1:
        return "coincidencia"
    if filas["hogar"].nunique() == 1:
        return "convivencia"
    sucesivos = "sucesivo" in set(filas["tipo_hogar"])
    if sucesivos and filas["unidad"].fillna("").nunique() == 1:
        return "convivencia"  # ocupantes sucesivos de la misma unidad
    return "multifamiliar"


def verdad_compartidos_residencial(
    registros: pd.DataFrame,
    verdad_personas: pd.DataFrame,
    sospechosos: dict[tuple[str, str], set[int]],
    normalizador: Callable[[str, object], str | None],
    columnas: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Etiqueta verdadera de cada valor que comparten dos o más personas distintas.

    ``normalizador(tipo, valor)`` da la clave del valor (la del grafo que se evalúa: la
    dirección completa del hito 3 o el predio de la v1.1). relleno > sospechoso >
    etiqueta por las personas (``etiquetar_personas``).
    """
    columnas = columnas or TIPOS_COMPARTIDOS
    rellenos = {
        "celular": {normalizador("celular", t) for t in sinteticos.TELEFONOS_RELLENO},
        "correo": {normalizador("correo", c) for c in sinteticos.CORREOS_RELLENO},
        "direccion": {normalizador("direccion", d) for d in sinteticos.DIRECCIONES_RELLENO},
        "documento": set(),
    }
    inyectados = {(t, normalizador(t, v)) for (t, v) in sospechosos}
    verdad = verdad_personas.set_index("cluster")
    filas = []
    for tipo, columna in columnas.items():
        claves = registros[columna].map(lambda v, t=tipo: normalizador(t, v))
        grupos = registros.assign(clave=claves).dropna(subset=["clave"]).groupby("clave")
        for clave, g in grupos:
            personas = set(g["cluster"])
            if len(personas) < 2:
                continue
            if clave in rellenos[tipo]:
                etiqueta = "relleno"
            elif (tipo, clave) in inyectados:
                etiqueta = "sospechoso"
            else:
                etiqueta = etiquetar_personas(personas, verdad)
            filas.append(
                {
                    "tipo": tipo,
                    "valor": clave,
                    "etiqueta": etiqueta,
                    "personas": len(personas),
                    "registros": len(g),
                }
            )
    return pd.DataFrame(filas, columns=["tipo", "valor", "etiqueta", "personas", "registros"])


def generar_escenario_residencial(
    n_personas: int = 2000, semilla: int = 4040, parametros: ParametrosResidencial | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Atajo: ``EscenarioResidencial(n_personas, semilla, parametros).generar()``."""
    return EscenarioResidencial(n_personas, semilla, parametros).generar()
