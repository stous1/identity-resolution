/* Interfaz del laboratorio: lee los JSON publicados y dibuja con el motor (motor.js). */
(function () {
  "use strict";
  var L = window.Laboratorio;
  var BASE = "resultados/laboratorio/";
  var $ = function (s) { return document.querySelector(s); };
  var c3 = function (x) { return L.coma(x, 3); };
  var pct = function (x) { return L.coma(x * 100, 1) + " %"; };
  var esc = function (t) {
    return String(t).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  };

  // ---------- Pestañas ----------
  var curvaLista = false;
  document.querySelectorAll('[role="tab"]').forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll('[role="tab"]').forEach(function (t) {
        var activa = t === tab;
        t.setAttribute("aria-selected", String(activa));
        document.getElementById(t.getAttribute("aria-controls")).hidden = !activa;
      });
      history.replaceState(null, "", tab.id === "tab-umbral" ? "#umbral" : "#auditoria");
      if (tab.id === "tab-umbral") iniciarUmbral();
    });
  });

  function cifra(etiqueta, valor, antes, mejor) {
    var clase = mejor === undefined ? "" : mejor ? "sube" : "baja";
    return '<div class="cifra"><div class="etiqueta">' + etiqueta + '</div><div class="valor ' + clase +
      '">' + valor + "</div>" + (antes ? '<div class="antes">' + antes + "</div>" : "") + "</div>";
  }

  function barra(etiqueta, valor, clase) {
    return '<div class="barra"><span>' + etiqueta + '</span><div class="pista"><div class="relleno ' +
      (clase || "") + '" style="width:' + (valor * 100).toFixed(1) + '%"></div></div><span>' +
      pct(valor) + "</span></div>";
  }

  // ---------- La auditoría en vivo ----------
  var auditoria = null;
  function dibujarAuditoria() {
    var sin = $("#sin-vetos").checked;
    var r = L.auditoria(auditoria, sin), otro = L.auditoria(auditoria, !sin);
    var base = sin ? otro : null;
    var html = '<div class="cifras">' +
      cifra("Recall por clúster", c3(r.recall), base ? "con vetos: " + c3(base.recall) : "", sin ? true : undefined) +
      cifra("Precisión", c3(r.precision), base ? "con vetos: " + c3(base.precision) : "") +
      cifra("Personas reconstruidas exactas", pct(r.pct_exactas), base ? "con vetos: " + pct(base.pct_exactas) : "", sin ? true : undefined) +
      cifra("Clientes que mezclan personas", L.miles(r.mezclados), base ? "con vetos: " + L.miles(base.mezclados) : "") +
      "</div>";
    html += '<div class="tarjeta"><h2>Personas reconstruidas exactas, por grupo</h2><div class="barras">';
    Object.keys(auditoria.atributos).forEach(function (a) {
      var e = r.equidad[a], nombre = auditoria.atributos[a];
      html += barra("Con " + nombre, e.exactas_con, "grupo") + barra("Sin " + nombre, e.exactas_sin);
    });
    html += "</div></div>";
    html += '<div class="tarjeta"><h2>La brecha de equidad, antes y después</h2><div class="tabla"><table>' +
      "<thead><tr><th>Grupo</th><th>Con vetos</th><th>Sin vetos</th></tr></thead><tbody>";
    Object.keys(auditoria.atributos).forEach(function (a) {
      var fila = "<tr><td>" + esc(auditoria.atributos[a]) + "</td>";
      ["con_vetos", "sin_vetos"].forEach(function (k) {
        var d = auditoria.referencia[k].equidad[a].diferencia;
        fila += "<td>" + L.coma(-d.valor * 100, 1) + " puntos [" + L.coma(-d.ic_sup * 100, 1) + ", " +
          L.coma(-d.ic_inf * 100, 1) + "]<br><strong>" + (d.significativa ? "significativa" : "no significativa") +
          "</strong></td>";
      });
      html += fila + "</tr>";
    });
    html += "</tbody></table></div><p class='nota'>Diferencia en personas exactas entre quienes tienen la " +
      "condición y quienes no, con intervalo del 95 % por bootstrap de personas (calculado en Python).</p></div>";
    html += '<p class="nota">' + (sin
      ? "Sin los vetos, el recall sube a " + c3(r.recall) + " y la brecha del apellido de casada deja de ser significativa: " +
        "casi toda era efecto de los vetos, no de los nombres. La de los apodos se reduce pero sigue: esa sí es real. " +
        "Por eso el hito 6 cambió el generador (mudanzas) y puso un piso a los pesos negativos (ningún campo resta más de 10 bits)."
      : "Con los vetos, una persona que se mudó o escribió su dirección de otra forma queda partida en varios clientes, " +
        "aunque nombre, documento y fecha coincidan. Las mujeres con apellido de casada se mudan con su nueva familia, " +
        "y por eso parecían discriminadas.") +
      " Umbral congelado del v1: 0,999999 (" + L.coma(auditoria.peso_umbral, 1) + " bits). La auditoría publicó 0,636 y 0,943 con los datos de antes de fijar la fecha.</p>";
    $("#auditoria").innerHTML = html;
  }

  fetch(BASE + "auditoria.json").then(function (r) { return r.json(); }).then(function (d) {
    auditoria = d;
    $("#sin-vetos").addEventListener("change", dibujarAuditoria);
    dibujarAuditoria();
  }).catch(function (e) { $("#auditoria").innerHTML = "<p>No se pudo cargar: " + esc(e) + "</p>"; });

  // ---------- El umbral en tus manos ----------
  var umbral = null, curva = null;
  function iniciarUmbral() {
    if (umbral) return;
    fetch(BASE + "umbral.json").then(function (r) { return r.json(); }).then(function (d) {
      umbral = d;
      var marcas = Object.keys(d.marcas).map(function (k) {
        return '<button type="button" data-peso="' + d.marcas[k] + '">' + esc(k) + "</button>";
      }).join("");
      $("#marcas").innerHTML = marcas;
      document.querySelectorAll("#marcas button").forEach(function (b) {
        b.addEventListener("click", function () { moverA(Number(b.dataset.peso)); });
      });
      $("#umbral").addEventListener("input", function () { dibujarUmbral(Number(this.value)); });
      moverA(d.marcas["v3 congelado (0,999999)"]);
      setTimeout(dibujarCurva, 30);
    }).catch(function (e) { $("#umbral-resultado").innerHTML = "<p>No se pudo cargar: " + esc(e) + "</p>"; });
  }

  function moverA(peso) {
    $("#umbral").value = String(Math.round(peso * 2) / 2);
    dibujarUmbral(peso);
  }

  var pesoActual = 20;
  function dibujarUmbral(peso) {
    pesoActual = peso;
    var r = L.analizarUmbral(umbral, peso), p = L.probabilidadDe(peso);
    $("#umbral-valor").textContent = L.coma(peso, 1) + " bits (probabilidad " +
      (p > 0.99999 ? L.coma(p, 7) : p > 0.999 ? L.coma(p, 5) : L.coma(p, 3)) + ")";
    var html = '<div class="cifras">' +
      cifra("Precisión por clúster", c3(r.precision)) +
      cifra("Recall por clúster", c3(r.recall)) +
      cifra("Costo (10·FP + FN)", L.miles(r.costo)) +
      cifra("Clientes que mezclan personas", L.miles(r.mezclados)) +
      "</div>";
    html += '<div class="tarjeta"><div class="tabla"><table><tbody>' +
      "<tr><td>Pares unidos por error (FP)</td><td><strong>" + L.miles(r.fp) + "</strong></td></tr>" +
      "<tr><td>… porque el modelo los unió directamente</td><td>" + L.miles(r.falsos_directos) + "</td></tr>" +
      "<tr><td>… solo por transitividad (A-B y B-C, pero A no se parece a C)</td><td><strong>" +
      L.miles(r.falsos_por_transitividad) + "</strong></td></tr>" +
      "<tr><td>Pares de la misma persona sin unir (FN)</td><td>" + L.miles(r.fn) + "</td></tr>" +
      "<tr><td>Puentes (enlaces que, al quitarlos, parten un cliente)</td><td>" + L.miles(r.puentes) + "</td></tr>" +
      "<tr><td>… débiles (menos de " + umbral.peso_puente_debil + " bits)</td><td>" + L.miles(r.puentes_debiles) + "</td></tr>" +
      "<tr><td>Clientes mezclados que cuelgan de un puente</td><td><strong>" + L.miles(r.mezclas_sostenidas_por_puente) +
      "</strong> de " + L.miles(r.mezclados) + "</td></tr>" +
      "</tbody></table></div><p class='nota'>Con un umbral bajo, la mayoría de los errores no vienen de un par malo " +
      "sino de cadenas: por eso los clientes mezclados que cuelgan de un puente débil son los que vale la pena revisar " +
      "(la cola de revisión del hito 3).</p></div>";
    $("#umbral-resultado").innerHTML = html;
    if (curva) dibujarCurva();
  }

  function dibujarCurva() {
    if (!curva) {
      var pesos = [];
      for (var w = 0; w <= 40; w += 1) pesos.push(w);
      Object.keys(umbral.marcas).forEach(function (k) { pesos.push(umbral.marcas[k]); });
      pesos.sort(function (a, b) { return a - b; });
      curva = L.curva(umbral, pesos);
    }
    var W = 640, H = 230, m = { i: 46, d: 12, a: 12, b: 34 };
    var maxCosto = Math.max.apply(null, curva.map(function (c) { return c.costo; }));
    var x = function (w) { return m.i + (w / 40) * (W - m.i - m.d); };
    var y = function (c) { return m.a + (1 - c / maxCosto) * (H - m.a - m.b); };
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Costo según el umbral">';
    for (var t = 0; t <= 40; t += 10) {
      s += '<line x1="' + x(t) + '" x2="' + x(t) + '" y1="' + m.a + '" y2="' + (H - m.b) + '" stroke="var(--borde)"/>' +
        '<text x="' + x(t) + '" y="' + (H - m.b + 16) + '" font-size="12" text-anchor="middle" fill="var(--suave)">' + t + "</text>";
    }
    s += '<text x="' + (W / 2) + '" y="' + (H - 4) + '" font-size="12" text-anchor="middle" fill="var(--suave)">umbral (bits)</text>';
    s += '<text x="6" y="' + (m.a + 10) + '" font-size="12" fill="var(--suave)">' + L.miles(maxCosto) + "</text>";
    s += '<polyline fill="none" stroke="var(--acento)" stroke-width="2.5" points="' +
      curva.map(function (c) { return x(c.peso).toFixed(1) + "," + y(c.costo).toFixed(1); }).join(" ") + '"/>';
    var mejor = curva.reduce(function (a, b) { return b.costo < a.costo ? b : a; });
    s += '<circle cx="' + x(mejor.peso) + '" cy="' + y(mejor.costo) + '" r="4" fill="var(--bien)"/>';
    var congelado = umbral.marcas["v3 congelado (0,999999)"];
    s += '<line x1="' + x(congelado) + '" x2="' + x(congelado) + '" y1="' + m.a + '" y2="' + (H - m.b) +
      '" stroke="var(--aviso)" stroke-dasharray="4 3"/>';
    s += '<line x1="' + x(pesoActual) + '" x2="' + x(pesoActual) + '" y1="' + m.a + '" y2="' + (H - m.b) +
      '" stroke="var(--texto)" stroke-width="1.5"/>';
    s += "</svg>";
    s += '<p class="nota">Línea punteada: umbral congelado del v3. Punto verde: el umbral de menor costo en esta prueba (' +
      L.coma(mejor.peso, 1) + " bits, costo " + L.miles(mejor.costo) + "), que solo se conoce después de mirar la verdad. Línea negra: tu umbral.</p>";
    $("#curva").innerHTML = s;
  }

  if (location.hash === "#umbral") document.getElementById("tab-umbral").click();
})();
