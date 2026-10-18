"""Rutas del proyecto, centralizadas y relativas a la raíz del repositorio."""

from pathlib import Path

RAIZ: Path = Path(__file__).resolve().parents[2]

DATA: Path = RAIZ / "data"
DATA_RAW: Path = DATA / "raw"

REPORTS: Path = RAIZ / "reports"
REPORTS_HITO2: Path = REPORTS / "hito2"
REPORTS_VALIDACION: Path = REPORTS / "validacion"

DOCS: Path = RAIZ / "docs"
DOCS_RESULTADOS: Path = DOCS / "resultados"
DOCS_RESULTADOS_HITO2: Path = DOCS_RESULTADOS / "hito2"
DOCS_RESULTADOS_VALIDACION: Path = DOCS_RESULTADOS / "validacion"
