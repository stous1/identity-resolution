// Motor de la demo: estandarización v2 y comparaciones del modelo v2 congelado, en JavaScript.
//
// Reimplementa src/identidades/estandarizacion.py, estandarizacion_v2.py y la preparación de
// modelo_co_v2.py, y evalúa los niveles de cada comparación con la misma lógica que el SQL
// que Splink corre en DuckDB. Los parámetros (m, u, lambda) vienen de modelo_demo.json,
// exportado por src/identidades/demo.py. tests/test_demo.py comprueba que da los mismos
// niveles y el mismo peso que Splink sobre una muestra de pares.
//
// No aplica el ajuste por frecuencia de términos (depende de la base completa).

// ---------------------------------------------------------------- distancias (como DuckDB)

export function levenshtein(a, b) {
  const s = [...a], t = [...b];
  let previa = Array.from({ length: t.length + 1 }, (_, j) => j);
  for (let i = 1; i <= s.length; i++) {
    const actual = [i];
    for (let j = 1; j <= t.length; j++) {
      actual[j] = Math.min(previa[j] + 1, actual[j - 1] + 1, previa[j - 1] + (s[i - 1] === t[j - 1] ? 0 : 1));
    }
    previa = actual;
  }
  return previa[t.length];
}

// Damerau-Levenshtein completo (transposiciones no restringidas), como DuckDB.
export function damerauLevenshtein(a, b) {
  const s = [...a], t = [...b];
  const n = s.length, m = t.length, max = n + m;
  const ultima = new Map();
  const d = Array.from({ length: n + 2 }, () => new Array(m + 2).fill(0));
  d[0][0] = max;
  for (let i = 0; i <= n; i++) { d[i + 1][0] = max; d[i + 1][1] = i; }
  for (let j = 0; j <= m; j++) { d[0][j + 1] = max; d[1][j + 1] = j; }
  for (let i = 1; i <= n; i++) {
    let db = 0;
    for (let j = 1; j <= m; j++) {
      const i1 = ultima.get(t[j - 1]) ?? 0;
      const j1 = db;
      let costo = 1;
      if (s[i - 1] === t[j - 1]) { costo = 0; db = j; }
      d[i + 1][j + 1] = Math.min(
        d[i][j] + costo, d[i + 1][j] + 1, d[i][j + 1] + 1,
        d[i1][j1] + (i - i1 - 1) + 1 + (j - j1 - 1),
      );
    }
    ultima.set(s[i - 1], i);
  }
  return d[n + 1][m + 1];
}

export function jaroWinkler(a, b) {
  const s = [...a], t = [...b];
  if (!s.length && !t.length) return 1;
  if (!s.length || !t.length) return 0;
  const ventana = Math.max(0, Math.floor(Math.max(s.length, t.length) / 2) - 1);
  const usadoS = new Array(s.length).fill(false), usadoT = new Array(t.length).fill(false);
  let coincidencias = 0;
  for (let i = 0; i < s.length; i++) {
    const desde = Math.max(0, i - ventana), hasta = Math.min(t.length - 1, i + ventana);
    for (let j = desde; j <= hasta; j++) {
      if (!usadoT[j] && s[i] === t[j]) { usadoS[i] = usadoT[j] = true; coincidencias++; break; }
    }
  }
  if (!coincidencias) return 0;
  let k = 0, medias = 0;
  for (let i = 0; i < s.length; i++) {
    if (!usadoS[i]) continue;
    while (!usadoT[k]) k++;
    if (s[i] !== t[k]) medias++;
    k++;
  }
  const c = coincidencias;
  const jaro = (c / s.length + c / t.length + (c - medias / 2) / c) / 3;
  if (jaro <= 0.7) return jaro;
  let prefijo = 0;
  while (prefijo < Math.min(4, s.length, t.length) && s[prefijo] === t[prefijo]) prefijo++;
  return jaro + prefijo * 0.1 * (1 - jaro);
}

// ---------------------------------------------------------------- estandarización v1

const PATRON_CORREO = /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/;
const PATRON_DIRECCION = new RegExp(
  "^(?<via>[A-Z]+)\\s+(?<numero>\\d+\\s?[A-Z]?(?:\\s?BIS)?)(?:\\s+(?<cuad1>SUR|ESTE|NORTE|OESTE))?" +
  "\\s*#?\\s*(?<placa>\\d+\\s?[A-Z]?)\\s*-?\\s*(?<consecutivo>\\d+)(?:\\s+(?<cuad2>SUR|ESTE|NORTE|OESTE))?$",
);

const vacio = (v) => v === null || v === undefined || String(v) === "";

export function normalizarTexto(v) {
  if (vacio(v)) return null;
  const texto = String(v).replace(/\s+/gu, " ").trim().toUpperCase();
  return texto || null;
}

export function quitarTildes(v) {
  if (vacio(v)) return null;
  return v.normalize("NFD").replace(/\p{Mn}/gu, "");
}

export function normalizarNombre(v) {
  const texto = normalizarTexto(v);
  if (texto === null) return null;
  return normalizarTexto(texto.replace(/[^A-ZÁÉÍÓÚÜÑ ]/gu, " "));
}

const conCodigoPython = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

function crearEstandarizador(dic) {
  const particulas = new Set(dic.particulas);

  function agruparParticulas(tokens) {
    const grupos = [];
    let pendiente = [];
    for (const token of tokens) {
      if (particulas.has(quitarTildes(token))) pendiente.push(token);
      else { grupos.push([...pendiente, token].join(" ")); pendiente = []; }
    }
    if (pendiente.length) {
      if (grupos.length) grupos[grupos.length - 1] = [grupos[grupos.length - 1], ...pendiente].join(" ");
      else grupos.push(pendiente.join(" "));
    }
    return grupos;
  }

  function separarCompuesto(v) {
    const texto = normalizarNombre(v);
    if (texto === null) return [null, null];
    const grupos = agruparParticulas(texto.split(" "));
    return [grupos[0], grupos.slice(1).join(" ") || null];
  }

  const ordenarTokens = (v) => (vacio(v) ? null : v.split(" ").sort(conCodigoPython).join(" "));

  function normalizarCelularV1(v) {
    if (vacio(v)) return null;
    let d = String(v).replace(/\D/g, "");
    if (d.length === 12 && d.startsWith("57")) d = d.slice(2);
    return /^3\d{9}$/.test(d) ? d : null;
  }

  function normalizarCorreo(v) {
    if (vacio(v)) return null;
    const correo = String(v).replace(/\s+/gu, "").toLowerCase();
    return PATRON_CORREO.test(correo) ? correo : null;
  }

  function normalizarDireccion(v) {
    const nulo = { via: null, numero_via: null, cuadrante: null, placa: null, consecutivo: null };
    const texto = quitarTildes(normalizarTexto(v));
    if (texto === null) return { ...nulo, direccion: null };
    let limpio = texto.replace(/[.,°º]/g, " ");
    limpio = limpio.replace(/(?<=\s)(?:N|NO|NRO|NUMERO)(?=\s)/g, "#");
    limpio = limpio.replace(/\s+/gu, " ").trim();
    const m = PATRON_DIRECCION.exec(limpio);
    const via = m ? dic.alias_via[m.groups.via] ?? null : null;
    if (!m || via === null) return { ...nulo, direccion: limpio };
    const numero = m.groups.numero.replace(/\s+/g, "").replace("BIS", " BIS");
    const placa = m.groups.placa.replace(/\s+/g, "");
    const consecutivo = m.groups.consecutivo;
    const cuadrante = m.groups.cuad1 || m.groups.cuad2 || null;
    let canonica = `${via} ${numero}` + (cuadrante ? ` ${cuadrante}` : "");
    canonica += ` # ${placa}-${consecutivo}`;
    return { via, numero_via: numero, cuadrante, placa, consecutivo, direccion: canonica };
  }

  // ------------------------------------------------------------ estandarización v2

  const OCR = { O: "0", o: "0", l: "1", I: "1", i: "1", S: "5", s: "5", B: "8", Z: "2", z: "2" };
  const traducirOcr = (texto) => texto.replace(/[OolIiSsBZz]/g, (c) => OCR[c]);

  function repararCodificacion(v) {
    if (typeof v !== "string" || !/[ÃÂ]/.test(v)) return v;
    const bytes = [];
    for (const c of v) {
      const codigo = c.codePointAt(0);
      if (codigo > 255) return v;
      bytes.push(codigo);
    }
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(new Uint8Array(bytes));
    } catch {
      return v;
    }
  }

  function ocrEnTramosNumericos(texto) {
    return texto.replace(/[0-9OolIiSsBZz]{4,}/g, (tramo) => {
      const digitos = [...tramo].filter((c) => /\d/.test(c)).length;
      return digitos >= Math.max(3, tramo.length / 2) ? traducirOcr(tramo) : tramo;
    });
  }

  function limpiarDocumento(v) {
    if (vacio(v)) return null;
    const texto = String(v).replace(/(?<=\d)[.,\s](?=\d)/gu, "");
    const tramos = ocrEnTramosNumericos(texto).match(/\d+/g);
    if (!tramos) return null;
    let mayor = tramos[0];
    for (const t of tramos) if (t.length > mayor.length) mayor = t;
    return mayor.replace(/^0+/, "") || null;
  }

  function extraerTelefonos(v) {
    if (vacio(v)) return [];
    let texto = String(v).split(/\b(?:ext|extension|ext\.)\b/i)[0];
    texto = ocrEnTramosNumericos(texto);
    const numeros = [];
    for (const parte of texto.split(/[/;,|]|\by\b/)) {
      let d = parte.replace(/\D/g, "");
      if (d.length === 12 && d.startsWith("57")) d = d.slice(2);
      if (/^(?:3\d{9}|60\d{8}|\d{7})$/.test(d) && !numeros.includes(d)) numeros.push(d);
    }
    return numeros;
  }

  function fechaIso(anio, mes, dia) {
    if (anio < 1 || anio > 9999 || mes < 1 || mes > 12 || dia < 1) return null;
    const fecha = new Date(Date.UTC(2000, mes - 1, dia));
    fecha.setUTCFullYear(anio);
    if (fecha.getUTCMonth() !== mes - 1 || fecha.getUTCDate() !== dia) return null;
    const dos = (n) => String(n).padStart(2, "0");
    return `${String(anio).padStart(4, "0")}-${dos(mes)}-${dos(dia)}`;
  }

  function normalizarFecha(v) {
    if (vacio(v)) return null;
    let texto = String(v).replace(/[_'";]/g, "");
    texto = texto.replace(/[^0-9A-Za-zÁÉÍÓÚáéíóúÑñ]+/g, " ").trim();
    let partes = texto.split(" ").filter((p) => p !== "").map((p) =>
      /^[0-9OolIiSsBZz]+$/.test(p) && (/\d/.test(p) || p.length <= 2) ? traducirOcr(p) : p,
    );
    partes = partes.map((p) => quitarTildes(p.toUpperCase()));
    const esNumero = (x) => /^\d+$/.test(x);
    let anio = null, mes = null, dia = null;
    if (partes.length === 1 && /^\d{8}$/.test(partes[0])) {
      anio = +partes[0].slice(0, 4); mes = +partes[0].slice(4, 6); dia = +partes[0].slice(6);
    } else {
      partes = partes.filter((p) => p !== "DE");
      if (partes.length === 3) {
        let [a, b, c] = partes;
        if (b in dic.meses) b = String(dic.meses[b]);
        if ([a, b, c].every(esNumero)) {
          if (a.length === 4) { anio = +a; mes = +b; dia = +c; }
          else {
            dia = +a; mes = +b; anio = +c;
            if (c.length === 2) anio += anio > new Date().getFullYear() % 100 ? 1900 : 2000;
          }
        }
      }
    }
    return anio === null ? null : fechaIso(anio, mes, dia);
  }

  function nombreFormal(nombres) {
    if (vacio(nombres)) return null;
    const junto = nombres.replaceAll(" ", "");
    if (Object.hasOwn(dic.compuestos, junto)) return dic.compuestos[junto];
    return nombres.split(" ").map((t) => dic.compuestos[t] ?? dic.apodos[t] ?? t).join(" ");
  }

  const APELLIDOS_CON_DE = dic.apellidos_con_de;
  function separarApellidoCasada(apellidos) {
    if (vacio(apellidos)) return [null, null];
    if (APELLIDOS_CON_DE.some((c) => apellidos.includes(c))) return [apellidos, null];
    const m = /^(.+?)\s+(?:(?:VIUDA|VDA)\s+)?DE\s+([A-Z]+)$/.exec(apellidos);
    if (!m || particulas.has(m[2])) return [apellidos, null];
    return [m[1], m[2]];
  }

  const textoNombre = (v) => quitarTildes(normalizarNombre(repararCodificacion(v)));

  // Columnas del modelo v2 (como modelo_co_v2.preparar) para un registro crudo.
  return function preparar(crudo) {
    const r = Object.fromEntries(Object.entries(crudo).map(([k, v]) => [k, repararCodificacion(v)]));
    const [apellidosBase, apellidoCasada] = separarApellidoCasada(textoNombre(r.apellidos));
    const nombresFormales = nombreFormal(textoNombre(r.nombres));

    const nombresSin = quitarTildes(normalizarNombre(nombresFormales));
    const apellidosSin = quitarTildes(normalizarNombre(apellidosBase));
    const [primerNombre] = separarCompuesto(nombresSin);
    const [primerApellido, segundoApellido] = separarCompuesto(apellidosSin);

    let palabras = [];
    for (const campo of [nombresSin, primerApellido, segundoApellido]) {
      if (typeof campo === "string") palabras.push(...campo.split(" ").map(nombreFormal));
    }
    palabras = palabras.flatMap((t) => t.split(" ")).filter((p) => !particulas.has(p));
    const tokens = [...new Set(palabras)].sort(conCodigoPython);

    const telefonos = extraerTelefonos(crudo.celular);
    const dir = normalizarDireccion(r.direccion);
    const clave = dir.via !== null && dir.numero_via !== null && dir.placa !== null
      ? `${dir.via} ${dir.numero_via} # ${dir.placa}` : null;
    void normalizarCelularV1;
    return {
      documento: limpiarDocumento(crudo.numero_documento),
      nombre_completo: nombresSin,
      nombres_ordenados: ordenarTokens(nombresSin),
      primer_nombre: primerNombre,
      primer_apellido: primerApellido,
      segundo_apellido: segundoApellido,
      apellido_casada: apellidoCasada,
      tokens_nombre: tokens.length ? tokens : null,
      fecha_nacimiento: normalizarFecha(crudo.fecha_nacimiento),
      telefonos: telefonos.length ? telefonos : null,
      email: normalizarCorreo(r.correo),
      domicilio: dir.direccion,
      domicilio_clave: clave,
      municipio: quitarTildes(normalizarTexto(r.ciudad)),
    };
  };
}

// ---------------------------------------------------------------- niveles de comparación

// Cada condición devuelve true, false o null (null = el SQL daría NULL: no se cumple).
const nulo = (...v) => v.some((x) => x === null || x === undefined);
const igual = (a, b) => (nulo(a, b) ? null : a === b);
const contiene = (lista, x) => (nulo(lista, x) ? null : lista.includes(x));
const cruce = (a, b) => (nulo(a, b) ? null : a.filter((x) => b.includes(x)).length);
const o = (a, b) => (a === true || b === true ? true : a === null || b === null ? null : false);
const y = (a, b) => (a === false || b === false ? false : a === null || b === null ? null : true);
const jw = (a, b, umbral) => (nulo(a, b) ? null : jaroWinkler(a, b) >= umbral);
const usuario = (correo) => (correo === null ? null : correo.match(/^[^@]+/)?.[0] || null);
const epoch = (iso) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 1000;
const largo = (s) => [...s].length;

const NIVELES = {
  documento: (l, r) => {
    const [a, b] = [l.documento, r.documento];
    if (nulo(a, b)) return 0;
    if (a === b) return 1;
    const mismo = largo(a) === largo(b);
    if (mismo && levenshtein(a, b) === 1) return 2;
    if (mismo && damerauLevenshtein(a, b) === 1) return 3;
    if (Math.abs(largo(a) - largo(b)) === 1 && levenshtein(a, b) === 1) return 4;
    if (damerauLevenshtein(a, b) === 2) return 5;
    return 6;
  },
  nombres: (l, r) => {
    if (nulo(l.nombre_completo, r.nombre_completo)) return 0;
    if (l.nombre_completo === r.nombre_completo) return 1;
    if (igual(l.nombres_ordenados, r.nombres_ordenados)) return 2;
    if (igual(l.primer_nombre, r.primer_nombre)) return 3;
    if (igual(l.primer_nombre, r.primer_apellido)) return 4;
    const comun = cruce(l.tokens_nombre, r.tokens_nombre);
    const nivel5 = y(comun === null ? null : comun >= 2,
      o(contiene(r.tokens_nombre, l.primer_nombre), contiene(l.tokens_nombre, r.primer_nombre)));
    if (nivel5 === true) return 5;
    if (jw(l.nombre_completo, r.nombre_completo, 0.92)) return 6;
    if (jw(l.nombre_completo, r.nombre_completo, 0.8)) return 7;
    return 8;
  },
  primer_apellido: (l, r) => {
    const [a, b] = [l.primer_apellido, r.primer_apellido];
    if (nulo(a, b)) return 0;
    if (a === b) return 1;
    if (jw(a, b, 0.92)) return 2;
    if (jw(a, b, 0.8)) return 3;
    if (o(contiene(r.tokens_nombre, a), contiene(l.tokens_nombre, b)) === true) return 4;
    return 5;
  },
  segundo_apellido: (l, r) => {
    const [a, b] = [l.segundo_apellido, r.segundo_apellido];
    if (nulo(a, b)) return 0;
    if (a === b) return 1;
    if (jw(a, b, 0.9)) return 2;
    return 3;
  },
  apellido_casada: (l, r) => {
    const [a, b] = [l.apellido_casada, r.apellido_casada];
    if (nulo(a, b)) return 0;
    return a === b ? 1 : 2;
  },
  fecha_nacimiento: (l, r) => {
    const [a, b] = [l.fecha_nacimiento, r.fecha_nacimiento];
    if (nulo(a, b)) return 0;
    if (a === b) return 1;
    if (damerauLevenshtein(a, b) <= 1) return 2;
    const diferencia = Math.abs(epoch(a) - epoch(b));
    if (diferencia <= 2629800) return 3;
    if (diferencia <= 31557600) return 4;
    if (diferencia <= 315576000) return 5;
    return 6;
  },
  telefonos: (l, r) => {
    const [a, b] = [l.telefonos, r.telefonos];
    if (nulo(a, b)) return 0;
    if (cruce(a, b) >= 1) return 1;
    const sinCelular = (t) => t.filter((x) => x.startsWith("3")).length === 0;
    if (sinCelular(a) || sinCelular(b)) return 2;
    return 3;
  },
  email: (l, r) => {
    const [a, b] = [l.email, r.email];
    if (nulo(a, b)) return 0;
    if (a === b) return 1;
    if (igual(usuario(a), usuario(b))) return 2;
    if (jw(a, b, 0.88)) return 3;
    if (jw(usuario(a), usuario(b), 0.88)) return 4;
    return 5;
  },
  domicilio: (l, r) => {
    const [a, b] = [l.domicilio, r.domicilio];
    if (nulo(a, b)) return 0;
    if (a === b) return 1;
    if (igual(l.domicilio_clave, r.domicilio_clave)) return 2;
    if (jw(a, b, 0.9)) return 3;
    return 4;
  },
  municipio: (l, r) => {
    const [a, b] = [l.municipio, r.municipio];
    if (nulo(a, b)) return 0;
    return a === b ? 1 : 2;
  },
};

// ---------------------------------------------------------------- motor

export function crearMotor(modelo) {
  const preparar = crearEstandarizador(modelo.diccionarios);
  const previo = Math.log2(modelo.lambda / (1 - modelo.lambda));

  function comparar(crudo1, crudo2) {
    const l = preparar(crudo1), r = preparar(crudo2);
    const detalle = modelo.comparaciones.map((c) => {
      const indice = NIVELES[c.columna](l, r);
      const nivel = c.niveles[indice];
      const gamma = nivel.nulo ? -1 : c.niveles.length - 1 - indice;
      const bf = nivel.nulo ? 1 : nivel.m / nivel.u;
      return { columna: c.columna, descripcion: c.descripcion, indice, gamma, etiqueta: nivel.etiqueta, bf, peso: Math.log2(bf) };
    });
    const peso = previo + detalle.reduce((s, d) => s + d.peso, 0);
    const probabilidad = 1 / (1 + 2 ** -peso);
    return { preparados: [l, r], previo, detalle, peso, probabilidad };
  }

  return { preparar, comparar, previo };
}
