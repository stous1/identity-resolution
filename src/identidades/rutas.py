"""Rutas del proyecto, centralizadas y relativas a la raíz del repositorio."""

from pathlib import Path

RAIZ: Path = Path(__file__).resolve().parents[2]

DATA: Path = RAIZ / "data"
DATA_RAW: Path = DATA / "raw"

REPORTS: Path = RAIZ / "reports"

DOCS: Path = RAIZ / "docs"
DOCS_RESULTADOS: Path = DOCS / "resultados"
