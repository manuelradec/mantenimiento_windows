"""
Pytest configuration — DB isolation per test.

Sin esto, los tests heredan dos problemas:
1. `Config.LOG_DIR` apunta a `C:\\ProgramData\\CleanCPU\\` (ruta de
   producción). Los tests no-elevados no pueden escribir ahí y obtienen
   `OperationalError: attempt to write a readonly database`.
2. `core.persistence._local.conn` cachea la conexión SQLite a nivel de
   thread. Una vez creada apuntando a un path X, subsiguientes tests
   reusan la misma conexión aunque `Config.LOG_DIR` haya cambiado, lo
   que contamina el estado o falla cuando el path X ya no existe.

La fixture `_isolate_db` (autouse) corrige ambos: redirige LOG_DIR y
REPORT_DIR a un `tmp_path` por test y resetea la conexión thread-local
antes y después.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Aísla DB y directorios de logs/reports en `tmp_path` por test."""
    import config
    from core import persistence

    log_dir = tmp_path / "logs"
    report_dir = tmp_path / "reports"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config.Config, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(config.Config, "REPORT_DIR", str(report_dir))

    # Reset thread-local connection antes del test (puede sobrevivir de uno previo).
    if getattr(persistence._local, "conn", None) is not None:
        try:
            persistence._local.conn.close()
        except Exception:
            pass
        persistence._local.conn = None

    yield

    # Teardown: cerrar la conexión creada durante el test.
    if getattr(persistence._local, "conn", None) is not None:
        try:
            persistence._local.conn.close()
        except Exception:
            pass
        persistence._local.conn = None
