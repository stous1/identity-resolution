"""GIF reproducibles: ensamblado, posiciones y página del antes y después (sin navegador)."""

from pathlib import Path

import pandas as pd
from PIL import Image

from identidades import gifs


def _registros() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_id": range(6),
            "cliente": [0, 0, 1, 1, 1, 2],
            "numero_documento": ["1", "1", "2", None, "2", "3"],
            "nombres": ["Ana", "ANA", "Luis", "Luis", "Lucho", "Eva"],
            "apellidos": ["Gómez", "GOMEZ", "Ríos", "Rios", "Ríos", "Paz"],
            "celular": ["300", "300", None, "301", "301", "302"],
        }
    )


def test_guardar_gif_en_bucle_con_todos_los_cuadros(tmp_path: Path) -> None:
    cuadros = [Image.new("RGB", (80, 40), (i * 40, 20, 200 - i * 40)) for i in range(5)]

    ruta = gifs.guardar_gif(
        cuadros, tmp_path / "x.gif", duraciones=[300, 50, 50, 50, 900], ancho=40
    )

    gif = Image.open(ruta)
    assert gif.n_frames == 5 and gif.size == (40, 20)
    assert gif.info.get("loop") == 0


def test_posiciones_finales_agrupan_por_cliente() -> None:
    registros = _registros()

    posiciones = gifs._posiciones(registros, ancho=600, alto=400)

    por_cliente: dict[int, set[float]] = {}
    for cliente, p in zip(registros["cliente"], posiciones, strict=True):
        por_cliente.setdefault(cliente, set()).add(p["x1"])
    assert all(len(xs) == 1 for xs in por_cliente.values())  # una columna por cliente
    assert len({next(iter(xs)) for xs in por_cliente.values()}) == 3
    assert posiciones == gifs._posiciones(registros, ancho=600, alto=400)  # reproducible


def test_html_agrupacion_escapa_y_tiene_una_tarjeta_por_registro() -> None:
    registros = _registros()
    registros.loc[0, "nombres"] = "<b>Ana</b>"

    contenido = gifs._html_agrupacion(registros, 600, 400)

    assert contenido.count('class="t"') == len(registros)
    assert "<b>Ana</b>" not in contenido and "&lt;b&gt;Ana&lt;/b&gt;" in contenido
