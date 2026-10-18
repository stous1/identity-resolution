"""Las pruebas de auditoría importan los módulos de ``audit/`` (``_comun``, ``a1_fugas``...)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
