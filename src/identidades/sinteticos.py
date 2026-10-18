"""Generador de clientes sintéticos colombianos con duplicados y errores inyectados.

Cada persona tiene datos "verdaderos" (documento, nombres, apellidos, fecha de nacimiento,
celular, correo, dirección, ciudad y departamento) y aparece en uno o varios registros.
Cada registro se captura con errores a tasas configurables, como pasaría en distintos
canales y momentos: dígitos transpuestos o faltantes en el documento, errores de
digitación, tildes presentes o ausentes, nombres en otro orden, segundo apellido omitido,
abreviaturas distintas de dirección, y teléfono o correo cambiados con el tiempo.

También se inyectan datos de relleno compartidos por personas distintas (teléfonos como
3000000000, correos genéricos, direcciones vagas), que el hito 3 usará como señal.

La columna ``cluster`` es la verdad: el identificador de la persona. Todo es sintético:
ningún dato corresponde a una persona real.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd
from faker import Faker
from faker.providers.address.es_CO import Provider as DireccionesCO

# Ciudades grandes, para que la mitad de las personas viva en ellas (código DANE).
CIUDADES_GRANDES: list[str] = ["11001", "05001", "76001", "08001", "13001", "68001"]

DOMINIOS_CORREO: list[str] = ["gmail.com", "hotmail.com", "yahoo.com", "outlook.com"]

TELEFONOS_RELLENO: list[str] = ["3000000000", "3111111111", "3001234567"]
CORREOS_RELLENO: list[str] = ["notiene@gmail.com", "sincorreo@hotmail.com", "na@na.com"]
DIRECCIONES_RELLENO: list[str] = ["CENTRO", "SIN DIRECCION", "CONOCIDA", "BARRIO CENTRO"]

# Formas de escribir el tipo de vía y el número, de la canónica a las variantes.
VARIANTES_VIA: dict[str, list[str]] = {
    "CL": ["Calle", "Cl", "CL", "Cll", "Cl."],
    "KR": ["Carrera", "Cra", "KR", "Kra", "Cr", "Cra."],
    "DG": ["Diagonal", "Dg", "Diag"],
    "TV": ["Transversal", "Tv", "Trans"],
    "AV": ["Avenida", "Av", "Av."],
}
VARIANTES_NUMERO: list[str] = ["#", "No.", "N°", "No", "#"]


@dataclass(frozen=True)
class TasasError:
    """Probabilidad de cada error al capturar un registro (los duplicados la sufren)."""

    documento_transpuesto: float = 0.08
    documento_digito_faltante: float = 0.05
    documento_digito_errado: float = 0.06
    documento_vacio: float = 0.05
    documento_con_puntos: float = 0.25
    digitacion_nombre: float = 0.10
    digitacion_apellido: float = 0.10
    fecha_errada: float = 0.06
    tilde_cambiada: float = 0.30
    nombres_invertidos: float = 0.20
    segundo_apellido_omitido: float = 0.25
    direccion_otra_escritura: float = 0.70
    telefono_cambiado: float = 0.12
    correo_cambiado: float = 0.10
    telefono_otro_formato: float = 0.40
    mayusculas_distintas: float = 0.50
    campo_vacio: float = 0.05
    relleno_telefono: float = 0.04
    relleno_correo: float = 0.04
    relleno_direccion: float = 0.03


@dataclass(frozen=True)
class Composicion:
    """Proporciones de la población sintética."""

    nombre_compuesto: float = 0.40
    dos_apellidos: float = 0.85
    cedula_extranjeria: float = 0.08
    # Fracción de personas que son familiares de otra (hermanos o padre/hijo): comparten
    # apellidos, dirección y ciudad, y a veces el teléfono. Son la fuente típica de
    # falsos positivos.
    familiares: float = 0.25
    familiar_comparte_telefono: float = 0.30
    en_ciudad_grande: float = 0.55
    # Probabilidad de que una persona tenga 1, 2, 3, ... registros.
    registros_por_persona: tuple[float, ...] = (0.35, 0.25, 0.18, 0.12, 0.06, 0.04)


def tiene_tilde(texto: str) -> bool:
    """True si el texto tiene alguna vocal con tilde o diéresis, o una eñe."""
    return any(c in "ÁÉÍÓÚÜÑáéíóúüñ" for c in texto)


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _fecha_valida(texto: str) -> bool:
    try:
        date.fromisoformat(texto)
    except ValueError:
        return False
    return True


def _ascii(texto: str) -> str:
    return _sin_tildes(texto).lower().replace(" ", "")


class Generador:
    """Genera personas y registros con una semilla fija (reproducible)."""

    def __init__(
        self,
        semilla: int = 42,
        tasas: TasasError | None = None,
        composicion: Composicion | None = None,
    ) -> None:
        self.rng = random.Random(semilla)
        self.fake = Faker("es_CO")
        self.fake.seed_instance(semilla)
        self.tasas = tasas or TasasError()
        self.composicion = composicion or Composicion()
        self._municipios = dict(DireccionesCO.municipalities)
        self._departamentos = DireccionesCO.departments

    # ---------- Personas ----------

    def _primer_token(self, nombre: str) -> str:
        return nombre.split()[0]

    def _nombres(self, femenino: bool) -> tuple[str, str | None]:
        generar = self.fake.first_name_female if femenino else self.fake.first_name_male
        primero = self._primer_token(generar())
        if self.rng.random() >= self.composicion.nombre_compuesto:
            return primero, None
        segundo = self._primer_token(generar())
        while segundo == primero:
            segundo = self._primer_token(generar())
        return primero, segundo

    def _apellidos(self) -> tuple[str, str | None]:
        primero = self.fake.last_name()
        if self.rng.random() >= self.composicion.dos_apellidos:
            return primero, None
        segundo = self.fake.last_name()
        while segundo == primero:
            segundo = self.fake.last_name()
        return primero, segundo

    def _documento(self) -> tuple[str, str]:
        if self.rng.random() < self.composicion.cedula_extranjeria:
            return "CE", str(self.rng.randint(100_000, 9_999_999))
        if self.rng.random() < 0.6:
            return "CC", str(self.rng.randint(1_000_000_000, 1_150_000_000))
        return "CC", str(self.rng.randint(10_000_000, 99_999_999))

    def _celular(self) -> str:
        prefijo = self.rng.choice(["300", "301", "304", "310", "311", "312", "315", "320", "350"])
        return prefijo + "".join(str(self.rng.randint(0, 9)) for _ in range(7))

    def _correo(self, nombre: str, apellido: str) -> str:
        usuario = self.rng.choice(
            [
                f"{_ascii(nombre)}.{_ascii(apellido)}",
                f"{_ascii(nombre)[0]}{_ascii(apellido)}",
                f"{_ascii(nombre)}{_ascii(apellido)}",
            ]
        )
        return f"{usuario}{self.rng.randint(1, 99)}@{self.rng.choice(DOMINIOS_CORREO)}"

    def _direccion(self) -> dict[str, str | None]:
        via = self.rng.choices(list(VARIANTES_VIA), weights=[45, 40, 5, 5, 5])[0]
        letra = self.rng.choice(["", "", "", "A", "B", "C"])
        bis = " BIS" if self.rng.random() < 0.05 else ""
        cuadrante = self.rng.choice([None] * 8 + ["SUR", "ESTE"])
        placa_letra = self.rng.choice(["", "", "", "A", "B"])
        return {
            "via": via,
            "numero_via": f"{self.rng.randint(1, 150)}{letra}{bis}",
            "cuadrante": cuadrante,
            "placa": f"{self.rng.randint(1, 120)}{placa_letra}",
            "consecutivo": str(self.rng.randint(1, 99)),
        }

    def _ciudad(self) -> tuple[str, str]:
        if self.rng.random() < self.composicion.en_ciudad_grande:
            codigo = self.rng.choice(CIUDADES_GRANDES)
        else:
            codigo = self.rng.choice(list(self._municipios))
        return self._municipios[codigo], self._departamentos[codigo[:2]]

    def familiar(self, persona_id: int, base: dict) -> dict:
        """Un familiar de ``base``: hermano (mismos dos apellidos) o hijo (primer apellido).

        Comparte dirección y ciudad, y a veces el teléfono; tiene otros nombres,
        documento, fecha de nacimiento y correo.
        """
        p = self.persona(persona_id)
        hermano = self.rng.random() < 0.5
        p["primer_apellido"] = base["primer_apellido"]
        p["segundo_apellido"] = base["segundo_apellido"] if hermano else p["segundo_apellido"]
        p["direccion"] = dict(base["direccion"])
        p["ciudad"], p["departamento"] = base["ciudad"], base["departamento"]
        if self._ocurre(self.composicion.familiar_comparte_telefono):
            p["celular"] = base["celular"]
        p["correo"] = self._correo(p["primer_nombre"], p["primer_apellido"])
        nombres = " ".join(n for n in (p["primer_nombre"], p["segundo_nombre"]) if n)
        apellidos = " ".join(a for a in (p["primer_apellido"], p["segundo_apellido"]) if a)
        p["dos_apellidos"] = p["segundo_apellido"] is not None
        p["con_tilde"] = tiene_tilde(nombres + apellidos)
        p["familiar_de"] = base["cluster"]
        return p

    def persona(self, persona_id: int) -> dict:
        """Datos verdaderos de una persona."""
        femenino = self.rng.random() < 0.5
        primer_nombre, segundo_nombre = self._nombres(femenino)
        primer_apellido, segundo_apellido = self._apellidos()
        tipo, numero = self._documento()
        ciudad, departamento = self._ciudad()
        nombres = " ".join(n for n in (primer_nombre, segundo_nombre) if n)
        apellidos = " ".join(a for a in (primer_apellido, segundo_apellido) if a)
        return {
            "cluster": persona_id,
            "tipo_documento": tipo,
            "numero_documento": numero,
            "primer_nombre": primer_nombre,
            "segundo_nombre": segundo_nombre,
            "primer_apellido": primer_apellido,
            "segundo_apellido": segundo_apellido,
            "fecha_nacimiento": self.fake.date_of_birth(minimum_age=18, maximum_age=85).isoformat(),
            "celular": self._celular(),
            "correo": self._correo(primer_nombre, primer_apellido),
            "direccion": self._direccion(),
            "ciudad": ciudad,
            "departamento": departamento,
            # Atributos para el análisis de equidad.
            "nombre_compuesto": segundo_nombre is not None,
            "dos_apellidos": segundo_apellido is not None,
            "con_tilde": tiene_tilde(nombres + apellidos),
            "familiar_de": None,
        }

    # ---------- Errores ----------

    def _ocurre(self, tasa: float) -> bool:
        return self.rng.random() < tasa

    def _digitacion(self, texto: str) -> str:
        """Un error de digitación: borrar, duplicar, intercambiar o cambiar una letra."""
        if len(texto) < 3:
            return texto
        i = self.rng.randrange(1, len(texto) - 1)
        operacion = self.rng.choice(["borrar", "duplicar", "intercambiar", "cambiar"])
        if operacion == "borrar":
            return texto[:i] + texto[i + 1 :]
        if operacion == "duplicar":
            return texto[:i] + texto[i] + texto[i:]
        if operacion == "intercambiar":
            return texto[: i - 1] + texto[i] + texto[i - 1] + texto[i + 1 :]
        letra = self.rng.choice("abcdefghijlmnoprstuv")
        return texto[:i] + (letra.upper() if texto[i].isupper() else letra) + texto[i + 1 :]

    def _cambiar_tildes(self, texto: str) -> str:
        """Quita las tildes si las hay; si no, a veces pone una en una vocal."""
        if tiene_tilde(texto):
            return _sin_tildes(texto)
        vocales = [i for i, c in enumerate(texto) if c in "aeiou"]
        if not vocales or self.rng.random() < 0.5:
            return texto
        i = self.rng.choice(vocales)
        return texto[:i] + "áéíóú"["aeiou".index(texto[i])] + texto[i + 1 :]

    def _mayusculas(self, texto: str) -> str:
        if not self._ocurre(self.tasas.mayusculas_distintas):
            return texto
        return self.rng.choice([texto.upper(), texto.lower(), texto.title()])

    def _documento_capturado(self, numero: str) -> str:
        digitos = list(numero)
        if self._ocurre(self.tasas.documento_transpuesto) and len(digitos) > 2:
            i = self.rng.randrange(len(digitos) - 1)
            digitos[i], digitos[i + 1] = digitos[i + 1], digitos[i]
        if self._ocurre(self.tasas.documento_digito_faltante) and len(digitos) > 6:
            del digitos[self.rng.randrange(len(digitos))]
        if self._ocurre(self.tasas.documento_digito_errado):
            i = self.rng.randrange(len(digitos))
            digitos[i] = self.rng.choice([d for d in "0123456789" if d != digitos[i]])
        texto = "".join(digitos)
        if self._ocurre(self.tasas.documento_con_puntos):
            grupos = []
            while texto:
                grupos.insert(0, texto[-3:])
                texto = texto[:-3]
            texto = self.rng.choice([".", " ", ","]).join(grupos)
        return texto

    def _fecha_capturada(self, fecha: str) -> str:
        """Fecha ISO con, a veces, día y mes intercambiados o un dígito errado."""
        if not self._ocurre(self.tasas.fecha_errada):
            return fecha
        anio, mes, dia = fecha.split("-")
        if int(dia) <= 12 and dia != mes and self.rng.random() < 0.5:
            return f"{anio}-{dia}-{mes}"
        digitos = list(anio + mes + dia)
        for _ in range(10):
            i = self.rng.randrange(len(digitos))
            candidato = digitos.copy()
            candidato[i] = self.rng.choice("0123456789")
            texto = "".join(candidato)
            nueva = f"{texto[:4]}-{texto[4:6]}-{texto[6:]}"
            if nueva != fecha and _fecha_valida(nueva):
                return nueva
        return fecha

    def _nombres_capturados(self, p: dict) -> str:
        nombres = [p["primer_nombre"]] + ([p["segundo_nombre"]] if p["segundo_nombre"] else [])
        if len(nombres) == 2 and self._ocurre(self.tasas.nombres_invertidos):
            nombres.reverse()
        texto = " ".join(nombres)
        if self._ocurre(self.tasas.tilde_cambiada):
            texto = self._cambiar_tildes(texto)
        if self._ocurre(self.tasas.digitacion_nombre):
            texto = self._digitacion(texto)
        return self._mayusculas(texto)

    def _apellidos_capturados(self, p: dict) -> str:
        apellidos = [p["primer_apellido"]]
        if p["segundo_apellido"] and not self._ocurre(self.tasas.segundo_apellido_omitido):
            apellidos.append(p["segundo_apellido"])
        texto = " ".join(apellidos)
        if self._ocurre(self.tasas.tilde_cambiada):
            texto = self._cambiar_tildes(texto)
        if self._ocurre(self.tasas.digitacion_apellido):
            texto = self._digitacion(texto)
        return self._mayusculas(texto)

    def _celular_capturado(self, celular: str) -> str | None:
        if self._ocurre(self.tasas.relleno_telefono):
            return self.rng.choice(TELEFONOS_RELLENO)
        if self._ocurre(self.tasas.telefono_cambiado):
            celular = self._celular()
        if self._ocurre(self.tasas.campo_vacio):
            return None
        if self._ocurre(self.tasas.telefono_otro_formato):
            return self.rng.choice(
                [
                    f"+57 {celular[:3]} {celular[3:6]} {celular[6:]}",
                    f"{celular[:3]}-{celular[3:6]}-{celular[6:]}",
                    f"({celular[:3]}) {celular[3:]}",
                    f"57{celular}",
                ]
            )
        return celular

    def _correo_capturado(self, p: dict) -> str | None:
        if self._ocurre(self.tasas.relleno_correo):
            return self.rng.choice(CORREOS_RELLENO)
        correo = p["correo"]
        if self._ocurre(self.tasas.correo_cambiado):
            correo = self._correo(p["primer_nombre"], p["primer_apellido"])
        if self._ocurre(self.tasas.campo_vacio):
            return None
        return correo.upper() if self._ocurre(self.tasas.mayusculas_distintas / 3) else correo

    def _direccion_capturada(self, d: dict) -> str | None:
        if self._ocurre(self.tasas.relleno_direccion):
            return self.rng.choice(DIRECCIONES_RELLENO)
        if self._ocurre(self.tasas.campo_vacio):
            return None
        otra = self._ocurre(self.tasas.direccion_otra_escritura)
        via = self.rng.choice(VARIANTES_VIA[d["via"]]) if otra else VARIANTES_VIA[d["via"]][0]
        numero = self.rng.choice(VARIANTES_NUMERO) if otra else "#"
        guion = self.rng.choice(["-", " - ", " "]) if otra else "-"
        cuadrante = f" {d['cuadrante'].title()}" if d["cuadrante"] else ""
        texto = f"{via} {d['numero_via']}{cuadrante} {numero} {d['placa']}{guion}{d['consecutivo']}"
        return self._mayusculas(texto)

    def registro(self, p: dict, unique_id: int) -> dict:
        """Un registro de la persona ``p`` tal como se capturó, con errores."""
        return {
            "unique_id": unique_id,
            "tipo_documento": p["tipo_documento"],
            "numero_documento": None
            if self._ocurre(self.tasas.documento_vacio)
            else self._documento_capturado(p["numero_documento"]),
            "nombres": self._nombres_capturados(p),
            "apellidos": self._apellidos_capturados(p),
            "fecha_nacimiento": self._fecha_capturada(p["fecha_nacimiento"]),
            "celular": self._celular_capturado(p["celular"]),
            "correo": self._correo_capturado(p),
            "direccion": self._direccion_capturada(p["direccion"]),
            "ciudad": self._mayusculas(p["ciudad"]),
            "departamento": p["departamento"],
            "cluster": p["cluster"],
        }


def generar(
    n_personas: int = 2000,
    semilla: int = 42,
    tasas: TasasError | None = None,
    composicion: Composicion | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera ``n_personas`` y sus registros.

    Devuelve ``(registros, personas)``. ``registros`` tiene los datos capturados y la
    verdad en ``cluster``; ``personas`` tiene los datos verdaderos y los atributos de
    equidad (``nombre_compuesto``, ``dos_apellidos``, ``con_tilde``).
    """
    generador = Generador(semilla, tasas, composicion)
    pesos = generador.composicion.registros_por_persona
    personas, registros = [], []
    for persona_id in range(n_personas):
        if personas and generador.rng.random() < generador.composicion.familiares:
            p = generador.familiar(persona_id, generador.rng.choice(personas))
        else:
            p = generador.persona(persona_id)
        personas.append(p)
        cantidad = generador.rng.choices(range(1, len(pesos) + 1), weights=pesos)[0]
        for _ in range(cantidad):
            registros.append(generador.registro(p, len(registros)))

    tabla_personas = pd.DataFrame(personas)
    direcciones = pd.DataFrame(tabla_personas.pop("direccion").tolist()).add_prefix("direccion_")
    return pd.DataFrame(registros), pd.concat([tabla_personas, direcciones], axis=1)


def describir_tasas(tasas: TasasError | None = None) -> dict[str, float]:
    """Las tasas de error como diccionario (para documentar una corrida)."""
    return asdict(tasas or TasasError())


# ---------- Historia de vida (hito 6) ----------

# Desplazamiento de la semilla para que la historia no altere el sorteo de ``generar``.
DESPLAZAMIENTO_HISTORIA: int = 606_060


@dataclass(frozen=True)
class Historia:
    """Cambios de vida entre los registros de una persona.

    ``generar`` no cambia nunca la ciudad ni la dirección de una persona, y no produce
    apellido de casada. Un modelo entrenado así aprende que "municipio distinto" casi no
    ocurre en la misma persona y lo convierte en un veto (auditoría, hallazgo A1). Las
    tasas se aplican a personas con dos o más registros; los registros de una persona se
    toman en orden de ``unique_id`` como orden en el tiempo.
    """

    # Personas que se mudan: los registros desde un punto llevan la dirección nueva.
    mudanza: float = 0.20
    # Entre las mudanzas, las que además cambian de ciudad (y a veces de departamento).
    mudanza_otra_ciudad: float = 0.5
    # Mujeres que usan apellido de casada desde un punto ("Pérez de Gómez").
    casada: float = 0.30
    # Entre las casadas, las que cambian de apellido de casada (divorcio y nuevo matrimonio).
    nuevo_matrimonio: float = 0.20


def _es_nombre_femenino(nombre: str) -> bool:
    from faker.providers.person.es_CO import Provider as Personas

    femeninos = {_sin_tildes(n).upper() for n in Personas.first_names_female}
    return _sin_tildes(nombre).upper() in femeninos


def _forma_casada(rng: random.Random, apellidos: str, esposo: str) -> str:
    """ "Pérez Gómez" -> "Pérez Gómez de Ruiz" o "Pérez de Ruiz" (sin el segundo apellido)."""
    partes = apellidos.split()
    base = partes[0] if len(partes) > 1 and rng.random() < 0.4 else apellidos
    return f"{base} {rng.choice(['de', 'DE', 'De'])} {esposo}"


def agregar_historia(
    registros: pd.DataFrame,
    personas: pd.DataFrame,
    semilla: int = 42,
    historia: Historia | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Agrega mudanzas y apellidos de casada a la salida de ``generar``.

    No modifica ``generar``: los mismos registros y personas, salvo los campos que cambian
    por la historia. Usa un sorteo propio (``semilla`` + ``DESPLAZAMIENTO_HISTORIA``).
    Devuelve ``(registros, personas)``; ``personas`` gana las columnas ``mudanza``,
    ``mudanza_otra_ciudad``, ``apellido_casada``, ``nuevo_matrimonio`` y ``mujer``.
    """
    historia = historia or Historia()
    gen = Generador(semilla + DESPLAZAMIENTO_HISTORIA)
    rng = gen.rng
    registros = registros.copy()
    personas = personas.copy()
    marcas = {
        c: pd.Series(False, index=personas.index)
        for c in ("mudanza", "mudanza_otra_ciudad", "apellido_casada", "nuevo_matrimonio")
    }
    personas["mujer"] = personas["primer_nombre"].map(_es_nombre_femenino)
    filas_por_persona = registros.sort_values("unique_id").groupby("cluster").groups

    for i, p in personas.iterrows():
        filas = list(filas_por_persona.get(p["cluster"], []))
        if len(filas) < 2:
            continue
        if rng.random() < historia.mudanza:
            desde = rng.randrange(1, len(filas))
            nueva = gen._direccion()
            marcas["mudanza"][i] = True
            ciudad = departamento = None
            if rng.random() < historia.mudanza_otra_ciudad:
                ciudad, departamento = gen._ciudad()
                marcas["mudanza_otra_ciudad"][i] = ciudad != p["ciudad"]
            for f in filas[desde:]:
                registros.at[f, "direccion"] = gen._direccion_capturada(nueva)
                if ciudad is not None:
                    registros.at[f, "ciudad"] = gen._mayusculas(ciudad)
                    registros.at[f, "departamento"] = departamento
        if personas.at[i, "mujer"] and rng.random() < historia.casada:
            desde = rng.randrange(0, len(filas))
            esposos = [gen.fake.last_name()]
            cambio = None
            if len(filas) - desde >= 2 and rng.random() < historia.nuevo_matrimonio:
                cambio = rng.randrange(desde + 1, len(filas))
                esposos.append(gen.fake.last_name())
                marcas["nuevo_matrimonio"][i] = esposos[0] != esposos[1]
            for k, f in enumerate(filas[desde:], start=desde):
                apellidos = registros.at[f, "apellidos"]
                if not isinstance(apellidos, str) or not apellidos.strip():
                    continue
                esposo = esposos[1] if cambio is not None and k >= cambio else esposos[0]
                registros.at[f, "apellidos"] = _forma_casada(rng, apellidos, esposo)
                marcas["apellido_casada"][i] = True

    return registros, personas.assign(**marcas)
