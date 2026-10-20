/*
 * Cálculos del laboratorio (docs/laboratorio.html), sin acceso al DOM. Funciona en el
 * navegador (window.Laboratorio) y en Node (module.exports), para que
 * tests/test_laboratorio.py compare con src/identidades/laboratorio.py.
 */
(function (raiz, fabrica) {
  if (typeof module === "object" && module.exports) {
    module.exports = fabrica();
  } else {
    raiz.Laboratorio = fabrica();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /** Etiqueta de componente de cada registro (unión-búsqueda; la raíz menor gana). */
  function componentes(n, aristas) {
    var padre = new Int32Array(n);
    for (var i = 0; i < n; i++) padre[i] = i;
    function raiz(x) {
      while (padre[x] !== x) { padre[x] = padre[padre[x]]; x = padre[x]; }
      return x;
    }
    for (var k = 0; k < aristas.length; k++) {
      var a = raiz(aristas[k][0]), b = raiz(aristas[k][1]);
      if (a !== b) { if (a < b) padre[b] = a; else padre[a] = b; }
    }
    var salida = new Int32Array(n);
    for (var j = 0; j < n; j++) salida[j] = raiz(j);
    return salida;
  }

  function paresDe(conteo) { return conteo * (conteo - 1) / 2; }

  /** Métricas por clúster (pares inducidos), como laboratorio.metricas en Python. */
  function metricas(cluster, persona, costo) {
    var n = cluster.length, porCluster = {}, porPersona = {}, porAmbos = {};
    var personasDe = {}, clustersDe = {};
    for (var i = 0; i < n; i++) {
      var c = cluster[i], p = persona[i], k = c + "|" + p;
      porCluster[c] = (porCluster[c] || 0) + 1;
      porPersona[p] = (porPersona[p] || 0) + 1;
      porAmbos[k] = (porAmbos[k] || 0) + 1;
      (personasDe[c] = personasDe[c] || {})[p] = true;
      (clustersDe[p] = clustersDe[p] || {})[c] = true;
    }
    var predichos = 0, verdaderos = 0, tp = 0, mezclados = 0;
    for (var a in porCluster) predichos += paresDe(porCluster[a]);
    for (var b in porPersona) verdaderos += paresDe(porPersona[b]);
    for (var d in porAmbos) tp += paresDe(porAmbos[d]);
    var unaPersona = {};
    for (var e in personasDe) {
      var cuantas = Object.keys(personasDe[e]).length;
      unaPersona[e] = cuantas === 1;
      if (cuantas > 1) mezclados++;
    }
    var exacta = {}, nPersonas = 0, exactas = 0;
    for (var f in clustersDe) {
      var cl = Object.keys(clustersDe[f]);
      exacta[f] = cl.length === 1 && unaPersona[cl[0]];
      nPersonas++;
      if (exacta[f]) exactas++;
    }
    var fp = predichos - tp, fn = verdaderos - tp;
    return {
      tp: tp, fp: fp, fn: fn,
      precision: predichos ? tp / predichos : 1,
      recall: verdaderos ? tp / verdaderos : 1,
      f1: predichos + verdaderos ? 2 * tp / (predichos + verdaderos) : 1,
      exactas: exactas, personas: nPersonas, pct_exactas: exactas / nPersonas,
      mezclados: mezclados,
      costo: costo ? costo.fp * fp + costo.fn * fn : null,
      exacta: exacta
    };
  }

  /** Índices de las aristas que son puente (Tarjan iterativo). */
  function puentes(n, aristas) {
    var vecinos = new Array(n);
    for (var i = 0; i < n; i++) vecinos[i] = [];
    aristas.forEach(function (ar, k) {
      vecinos[ar[0]].push([ar[1], k]);
      vecinos[ar[1]].push([ar[0], k]);
    });
    var orden = new Int32Array(n).fill(-1), bajo = new Int32Array(n), contador = 0;
    var esPuente = new Uint8Array(aristas.length);
    for (var inicio = 0; inicio < n; inicio++) {
      if (orden[inicio] !== -1 || vecinos[inicio].length === 0) continue;
      orden[inicio] = bajo[inicio] = contador++;
      var pila = [[inicio, -1, 0]];
      while (pila.length) {
        var tope = pila[pila.length - 1], v = tope[0], aristaPadre = tope[1], j = tope[2];
        if (j < vecinos[v].length) {
          tope[2] = j + 1;
          var w = vecinos[v][j][0], k = vecinos[v][j][1];
          if (k === aristaPadre) continue;
          if (orden[w] === -1) {
            orden[w] = bajo[w] = contador++;
            pila.push([w, k, 0]);
          } else {
            bajo[v] = Math.min(bajo[v], orden[w]);
          }
        } else {
          pila.pop();
          if (pila.length) {
            var u = pila[pila.length - 1][0];
            bajo[u] = Math.min(bajo[u], bajo[v]);
            if (bajo[v] > orden[u]) esPuente[aristaPadre] = 1;
          }
        }
      }
    }
    return esPuente;
  }

  /** Todo lo que muestra el control de umbral, para un peso mínimo (bits). */
  function analizarUmbral(datos, peso) {
    var n = datos.registros, persona = datos.persona, aristas = [], pesos = [];
    datos.pares.forEach(function (p) {
      if (p[2] >= peso) { aristas.push([p[0], p[1]]); pesos.push(p[2]); }
    });
    var cluster = componentes(n, aristas);
    var m = metricas(cluster, persona, datos.costo);
    var directos = 0;
    aristas.forEach(function (a) { if (persona[a[0]] !== persona[a[1]]) directos++; });
    var esPuente = puentes(n, aristas), nPuentes = 0, debiles = 0, sostenidos = {};
    for (var k = 0; k < aristas.length; k++) {
      if (!esPuente[k]) continue;
      nPuentes++;
      if (pesos[k] < datos.peso_puente_debil) debiles++;
      if (persona[aristas[k][0]] !== persona[aristas[k][1]]) sostenidos[cluster[aristas[k][0]]] = true;
    }
    delete m.exacta;
    m.aristas = aristas.length;
    m.falsos_directos = directos;
    m.falsos_por_transitividad = m.fp - directos;
    m.puentes = nPuentes;
    m.puentes_debiles = debiles;
    m.mezclas_sostenidas_por_puente = Object.keys(sostenidos).length;
    return m;
  }

  /** Costo y recall para una lista de pesos (la curva del control de umbral). */
  function curva(datos, pesos) {
    return pesos.map(function (p) {
      var r = analizarUmbral(datos, p);
      return { peso: p, costo: r.costo, precision: r.precision, recall: r.recall, fp: r.fp, fn: r.fn };
    });
  }

  /** La auditoría en vivo: clústeres del v1 al umbral congelado, con o sin los vetos. */
  function auditoria(datos, sinVetos) {
    var aristas = [];
    datos.pares.forEach(function (p) {
      var w = sinVetos ? p[2] - p[3] : p[2];
      if (w >= datos.peso_umbral) aristas.push([p[0], p[1]]);
    });
    var cluster = componentes(datos.registros, aristas);
    var m = metricas(cluster, datos.persona, null);
    var equidad = {};
    Object.keys(datos.atributos).forEach(function (a) {
      var marcadas = {};
      datos.marcas[a].forEach(function (p) { marcadas[p] = true; });
      var con = [0, 0], sin = [0, 0];
      Object.keys(m.exacta).forEach(function (p) {
        var g = marcadas[p] ? con : sin;
        g[0] += m.exacta[p] ? 1 : 0;
        g[1] += 1;
      });
      equidad[a] = { exactas_con: con[0] / con[1], exactas_sin: sin[0] / sin[1],
        personas_con: con[1], personas_sin: sin[1] };
    });
    delete m.exacta;
    m.equidad = equidad;
    return m;
  }

  /** Probabilidad <-> peso (log2 de las odds). */
  function pesoDe(p) { return Math.log2(p / (1 - p)); }
  function probabilidadDe(w) { return 1 / (1 + Math.pow(2, -w)); }

  /** Número con coma decimal. */
  function coma(x, d) {
    var s = Math.abs(x).toFixed(d).replace(".", ",");
    return (x < 0 && Number(Math.abs(x).toFixed(d)) !== 0 ? "−" : "") + s;
  }
  function miles(n) { return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, "."); }

  return {
    componentes: componentes, metricas: metricas, puentes: puentes,
    analizarUmbral: analizarUmbral, curva: curva, auditoria: auditoria,
    pesoDe: pesoDe, probabilidadDe: probabilidadDe, coma: coma, miles: miles
  };
});
