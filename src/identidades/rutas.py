"""Rutas del proyecto, centralizadas y relativas a la raíz del repositorio."""

from pathlib import Path

RAIZ: Path = Path(__file__).resolve().parents[2]

DATA: Path = RAIZ / "data"
DATA_RAW: Path = DATA / "raw"

REPORTS: Path = RAIZ / "reports"
REPORTS_HITO2: Path = REPORTS / "hito2"
REPORTS_VALIDACION: Path = REPORTS / "validacion"
REPORTS_HITO2B: Path = REPORTS / "hito2b"
REPORTS_HITO3: Path = REPORTS / "hito3"
REPORTS_HITO5: Path = REPORTS / "hito5"

DOCS: Path = RAIZ / "docs"
DOCS_RESULTADOS: Path = DOCS / "resultados"
DOCS_RESULTADOS_HITO2: Path = DOCS_RESULTADOS / "hito2"
DOCS_RESULTADOS_VALIDACION: Path = DOCS_RESULTADOS / "validacion"
DOCS_RESULTADOS_HITO2B: Path = DOCS_RESULTADOS / "hito2b"
DOCS_RESULTADOS_HITO3: Path = DOCS_RESULTADOS / "hito3"
DOCS_RESULTADOS_HITO5: Path = DOCS_RESULTADOS / "hito5"
REPORTS_HITO6: Path = REPORTS / "hito6"
DOCS_RESULTADOS_HITO6: Path = DOCS_RESULTADOS / "hito6"
REPORTS_V11: Path = REPORTS / "v11"
DOCS_RESULTADOS_V11: Path = DOCS_RESULTADOS / "v11"
