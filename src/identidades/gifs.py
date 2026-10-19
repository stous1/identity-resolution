"""GIF reproducibles para el README y Pages, capturados con Playwright.

- ``grabar_universo``: recorrido por el universo de Cosmograph del hito 3 (acercar, mover,
  alejar), con la página servida en local solo mientras dura la grabación.
- ``grabar_agrupacion``: antes y después. Registros sueltos de la prueba ciega 3 que el
  modelo v3 congelado agrupa en clientes; se dibujan en una página local y se capturan
  cuadro por cuadro (la animación depende de un parámetro, no del reloj, así que el GIF
  sale igual en cada corrida).

Los GIF se reducen de tamaño y de paleta para que pesen poco.
"""

from __future__ import annotations

import contextlib
import functools
import html
import http.server
import io
import json
import math
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

ARGS_WEBGL: list[str] = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]


def guardar_gif(
    cuadros: list[Image.Image],
    ruta: Path,
    duraciones: list[int] | int = 120,
    ancho: int | None = None,
    colores: int = 96,
) -> Path:
    """Guarda ``cuadros`` como GIF en bucle, con paleta adaptativa común y tamaño reducido."""
    if not cuadros:
        raise ValueError("No hay cuadros para el GIF")
    if ancho is not None:
        cuadros = [
            c.resize((ancho, round(c.height * ancho / c.width)), Image.LANCZOS) for c in cuadros
        ]
    # Una sola paleta para todos los cuadros: evita parpadeos y reduce el peso.
    # La muestra incluye siempre el primer y el último cuadro (los que más se miran).
    indices = sorted({0, len(cuadros) - 1, *range(0, len(cuadros), max(1, len(cuadros) // 5))})
    muestra = Image.new("RGB", (cuadros[0].width, cuadros[0].height * len(indices)))
    for i, k in enumerate(indices):
        muestra.paste(cuadros[k].convert("RGB"), (0, i * cuadros[0].height))
    paleta = muestra.quantize(colors=colores, method=Image.Quantize.MEDIANCUT)
    indexados = [
        c.convert("RGB").quantize(palette=paleta, dither=Image.Dither.NONE) for c in cuadros
    ]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    indexados[0].save(
        ruta,
        save_all=True,
        append_images=indexados[1:],
        duration=duraciones,
        loop=0,
        optimize=True,
        disposal=1,
    )
    return ruta


@contextlib.contextmanager
def servir(raiz: Path, puerto: int) -> Iterator[str]:
    """Sirve ``raiz`` en 127.0.0.1 solo dentro del bloque; devuelve la URL base."""

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

    servidor = http.server.ThreadingHTTPServer(
        ("127.0.0.1", puerto), functools.partial(Silencioso, directory=str(raiz))
    )
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor.shutdown()


def _cuadro(pagina: Any) -> Image.Image:
    return Image.open(io.BytesIO(pagina.screenshot())).convert("RGB")


def grabar_universo(
    raiz: Path,
    ruta_gif: Path,
    pagina: str = "hito3_universo.html",
    ancho: int = 960,
    alto: int = 600,
    espera_ms: int = 25000,
    puerto: int = 8766,
    ancho_gif: int = 440,
) -> Path:
    """Recorrido por el universo de Cosmograph: vista general, acercar, mover y alejar."""
    from playwright.sync_api import sync_playwright

    with servir(raiz, puerto) as base, sync_playwright() as p:
        navegador = p.chromium.launch(args=ARGS_WEBGL)
        web = navegador.new_page(viewport={"width": ancho, "height": alto})
        web.goto(f"{base}/{pagina}")
        web.wait_for_timeout(espera_ms)
        # El panel de la leyenda tapa parte del grafo; en el GIF se oculta.
        web.add_style_tag(content="body > div:not(#grafo):not(canvas) {display:none !important}")
        centro = (ancho * 0.55, alto * 0.5)
        cuadros, duraciones = [_cuadro(web)], [1400]
        web.mouse.move(*centro)
        for _ in range(5):  # acercar
            web.mouse.wheel(0, -110)
            web.wait_for_timeout(260)
            cuadros.append(_cuadro(web))
            duraciones.append(140)
        duraciones[-1] = 1200
        for _ in range(3):  # mover
            web.mouse.move(*centro)
            web.mouse.down()
            web.mouse.move(centro[0] - 45, centro[1] - 15, steps=4)
            web.mouse.up()
            web.wait_for_timeout(220)
            cuadros.append(_cuadro(web))
            duraciones.append(140)
        duraciones[-1] = 1200
        for _ in range(5):  # alejar
            web.mouse.move(*centro)
            web.mouse.wheel(0, 110)
            web.wait_for_timeout(260)
            cuadros.append(_cuadro(web))
            duraciones.append(140)
        duraciones[-1] = 1400
        navegador.close()
    return guardar_gif(cuadros, ruta_gif, duraciones, ancho=ancho_gif, colores=32)


# ---------------------------------------------------------------------------
# Antes y después
# ---------------------------------------------------------------------------

COLORES_CLIENTE: list[str] = ["#2563eb", "#16a34a", "#d97706", "#9333ea", "#dc2626"]


def ejemplo_agrupacion(n_clientes: int = 5, semilla: int = 3) -> pd.DataFrame:
    """Registros de la ciega 3 agrupados por el v3 congelado, para el GIF.

    Elige ``n_clientes`` clientes predichos de 2 a 4 registros. Devuelve ``unique_id``,
    ``cliente`` y los campos crudos que se muestran.
    """
    from identidades import flujo, flujo_hito6, modelo
    from identidades.modelo_co_v3 import ESQUEMA_V3

    configuracion, umbral, _, _ = flujo_hito6.cargar_congelado_v3()
    registros, _, _ = flujo_hito6.registros_ciega_3()
    linker = flujo.aplicar_configuracion(configuracion, registros, ESQUEMA_V3)
    clusters = modelo.agrupar(linker, modelo.predecir(linker), umbral).as_pandas_dataframe()
    tabla = clusters[["unique_id", "cluster_id"]].merge(registros, on="unique_id")
    tamanos = tabla.groupby("cluster_id")["unique_id"].transform("size")
    puros = tabla.groupby("cluster_id")["cluster"].transform("nunique") == 1
    candidatos = tabla[(tamanos.between(2, 4)) & puros]
    elegidos = (
        candidatos["cluster_id"].drop_duplicates().sample(n_clientes, random_state=semilla).tolist()
    )
    salida = candidatos[candidatos["cluster_id"].isin(elegidos)].copy()
    salida["cliente"] = salida["cluster_id"].map({c: i for i, c in enumerate(elegidos)})
    columnas = ["unique_id", "cliente", "numero_documento", "nombres", "apellidos", "celular"]
    return salida[columnas].sort_values(["cliente", "unique_id"]).reset_index(drop=True)


def _posiciones(registros: pd.DataFrame, ancho: int, alto: int, semilla: int = 7) -> list[dict]:
    """Posición inicial (dispersa) y final (agrupada por cliente) de cada tarjeta."""
    import random

    rng = random.Random(semilla)
    n = len(registros)
    columnas = 4
    filas = math.ceil(n / columnas)
    celdas = [(c, f) for f in range(filas) for c in range(columnas)]
    rng.shuffle(celdas)
    clientes = sorted(registros["cliente"].unique())
    ancho_grupo = ancho / len(clientes)
    salida = []
    contador: dict[int, int] = {}
    for i, fila in enumerate(registros.itertuples()):
        c, f = celdas[i]
        x0 = 20 + c * (ancho - 40) / columnas + rng.uniform(-6, 6)
        y0 = 70 + f * (alto - 110) / filas + rng.uniform(-6, 6)
        k = contador.get(fila.cliente, 0)
        contador[fila.cliente] = k + 1
        x1 = 8 + clientes.index(fila.cliente) * ancho_grupo
        y1 = 92 + k * 74
        salida.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return salida


def _html_agrupacion(registros: pd.DataFrame, ancho: int, alto: int) -> str:
    posiciones = _posiciones(registros, ancho, alto)
    ancho_tarjeta = ancho / registros["cliente"].nunique() - 16
    tarjetas = []
    for fila, pos in zip(registros.itertuples(), posiciones, strict=True):
        texto = [
            f"{fila.nombres or ''} {fila.apellidos or ''}".strip() or "(sin nombre)",
            f"Doc. {fila.numero_documento or '—'}",
            f"Cel. {fila.celular or '—'}",
        ]
        lineas = "".join(f"<div>{html.escape(str(t))}</div>" for t in texto)
        tarjetas.append(
            f'<div class="t" data-p=\'{json.dumps(pos)}\' data-c="{fila.cliente}">{lineas}</div>'
        )
    colores = json.dumps(COLORES_CLIENTE)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body {{ margin:0; width:{ancho}px; height:{alto}px; background:#0d1117; color:#e6edf3;
  font: 12px/1.35 system-ui, "Segoe UI", sans-serif; overflow:hidden; position:relative; }}
.t {{ position:absolute; box-sizing:border-box; width:{ancho_tarjeta:.0f}px;
  padding:6px 8px; border-radius:7px;
  background:#161b22; border:2px solid #3b4450; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }}
.t div {{ overflow:hidden; text-overflow:ellipsis; }}
.t div:first-child {{ font-weight:600; }}
#titulo {{ position:absolute; left:16px; top:14px; font-size:20px; font-weight:650; }}
#sub {{ position:absolute; left:16px; top:42px; font-size:13px; color:#9aa6b2; }}
</style></head><body><div id="titulo"></div><div id="sub"></div>{"".join(tarjetas)}
<script>
const COLORES = {colores};
const n = document.querySelectorAll(".t").length;
const clientes = new Set([...document.querySelectorAll(".t")].map(t => t.dataset.c)).size;
window.dibujar = (t) => {{
  const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  for (const el of document.querySelectorAll(".t")) {{
    const p = JSON.parse(el.dataset.p);
    el.style.left = (p.x0 + (p.x1 - p.x0) * e) + "px";
    el.style.top = (p.y0 + (p.y1 - p.y0) * e) + "px";
    el.style.borderColor = t >= 0.999 ? COLORES[+el.dataset.c % COLORES.length] : "#3b4450";
  }}
  const fin = t >= 0.999;
  document.getElementById("titulo").textContent = fin
    ? `Después: ${{clientes}} clientes` : `Antes: ${{n}} registros sueltos`;
  document.getElementById("sub").textContent = fin
    ? "Agrupados por el modelo v3 congelado (prueba ciega 3, datos sintéticos)"
    : "Cédula con un dígito errado, nombre sin tilde, otro celular...";
}};
window.dibujar(0);
</script></body></html>"""


def grabar_agrupacion(
    ruta_gif: Path,
    registros: pd.DataFrame | None = None,
    ancho: int = 760,
    alto: int = 420,
    pasos: int = 18,
) -> Path:
    """Antes y después: tarjetas de registros que se agrupan en clientes."""
    from playwright.sync_api import sync_playwright

    registros = ejemplo_agrupacion() if registros is None else registros
    contenido = _html_agrupacion(registros, ancho, alto)
    cuadros, duraciones = [], []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        web = navegador.new_page(viewport={"width": ancho, "height": alto})
        web.set_content(contenido)
        for i in range(pasos + 1):
            web.evaluate(f"window.dibujar({i / pasos})")
            cuadros.append(_cuadro(web))
            duraciones.append(2200 if i == 0 else 2800 if i == pasos else 70)
        navegador.close()
    return guardar_gif(cuadros, ruta_gif, duraciones, colores=64)
