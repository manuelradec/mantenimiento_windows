"""Tests for the maintenance module — T-03 changes.

Cubre:
- MAINTENANCE_STEPS reorganizada (paso 5 eliminado, paso 7 repurposed).
- Single-step endpoint con validación + lockeo (409).
- _step_disk_cleanup usa clean_disk_extras (no cleanmgr).
- _step_dism_restorehealth ejecuta DISM RestoreHealth.
- clean_disk_extras maneja papelera + carpetas extras.
- Audit trail: cada paso queda registrado en audit_log.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.command_runner import CommandResult, CommandStatus

# ============================================================
# Fixtures locales (mismo patrón que test_routes.py)
# ============================================================


@pytest.fixture
def app(tmp_path):
    import config as cfg

    cfg.Config.LOG_DIR = str(tmp_path / "logs")
    cfg.Config.REPORT_DIR = str(tmp_path / "reports")
    os.makedirs(cfg.Config.LOG_DIR, exist_ok=True)
    os.makedirs(cfg.Config.REPORT_DIR, exist_ok=True)

    from app import create_app
    from core.persistence import init_db, SessionStore

    a = create_app()
    a.config["TESTING"] = True
    a.config["SESSION_ID"] = "test-session"
    a.config["HOSTNAME"] = "testhost"
    a.config["USERNAME"] = "testuser"
    init_db()
    SessionStore.create(
        session_id="test-session",
        hostname="testhost",
        username="testuser",
        is_admin=False,
    )
    return a


@pytest.fixture
def client(app):
    return app.test_client()


# ============================================================
# MAINTENANCE_STEPS structure
# ============================================================


class TestStepsStructure:
    """Confirma que la lista de pasos refleja la decisión de T-03."""

    def test_eight_steps(self):
        from routes.maintenance import MAINTENANCE_STEPS

        assert len(MAINTENANCE_STEPS) == 8

    def test_temp_cleanup_removed(self):
        from routes.maintenance import MAINTENANCE_STEPS

        ids = [s["id"] for s in MAINTENANCE_STEPS]
        assert "temp_cleanup" not in ids

    def test_sfc_renamed_to_dism_restorehealth(self):
        from routes.maintenance import MAINTENANCE_STEPS

        ids = [s["id"] for s in MAINTENANCE_STEPS]
        assert "sfc" not in ids
        assert "dism_restorehealth" in ids

    def test_disk_cleanup_present_with_new_description(self):
        from routes.maintenance import MAINTENANCE_STEPS

        disk = next(s for s in MAINTENANCE_STEPS if s["id"] == "disk_cleanup")
        assert (
            "extendida" in disk["description"].lower()
            or "papelera" in disk["description"].lower()
        )

    def test_handlers_match_steps(self):
        """No debe haber paso sin handler ni handler huérfano."""
        from routes.maintenance import MAINTENANCE_STEPS

        # Build the same handlers dict as _run_maintenance does.
        from routes.maintenance import (
            _step_malwarebytes,
            _step_ccleaner,
            _step_advancedsystemcare,
            _step_defrag,
            _step_disk_cleanup,
            _step_dism_restorehealth,
            _step_windows_update,
            _step_lenovo_update,
        )

        handlers = {
            "malwarebytes": _step_malwarebytes,
            "ccleaner": _step_ccleaner,
            "advancedsystemcare": _step_advancedsystemcare,
            "defrag": _step_defrag,
            "disk_cleanup": _step_disk_cleanup,
            "dism_restorehealth": _step_dism_restorehealth,
            "windows_update": _step_windows_update,
            "lenovo_update": _step_lenovo_update,
        }
        step_ids = {s["id"] for s in MAINTENANCE_STEPS}
        handler_ids = set(handlers.keys())
        assert step_ids == handler_ids


class TestApiStepsEndpoint:
    def test_returns_eight_steps(self, client):
        resp = client.get("/maintenance/api/steps")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "steps" in data
        assert len(data["steps"]) == 8


# ============================================================
# Single-step endpoint
# ============================================================


def _csrf(client):
    """Genera y devuelve un CSRF token de la sesión Flask."""
    client.get("/")
    with client.session_transaction() as sess:
        return sess.get("csrf_token", "")


class TestSingleStepEndpoint:
    def _post(self, client, step_id):
        return client.post(
            f"/maintenance/api/start-step/{step_id}",
            headers={
                "Origin": "http://127.0.0.1:5000",
                "X-CSRF-Token": _csrf(client),
            },
            content_type="application/json",
            data="{}",
        )

    def test_invalid_step_id_returns_400(self, client):
        resp = self._post(client, "nonexistent_step")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "no reconocido" in (data.get("error") or "").lower()

    def test_valid_step_starts_session(self, client, monkeypatch):
        # Mock el handler para evitar invocar PowerShell real.
        import routes.maintenance as mod

        monkeypatch.setattr(
            mod,
            "_step_lenovo_update",
            lambda: {"status": "completed", "message": "mocked"},
        )
        # Reapunta el handler en la dispatch table interna.
        # _run_maintenance arma el dict cada vez, así que solo necesitamos
        # mockear la función a nivel módulo y dejar que se reuse.

        resp = self._post(client, "lenovo_update")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "started"
        assert "session_id" in data
        assert data["step_id"] == "lenovo_update"

    def test_409_when_active_session(self, client, monkeypatch):
        import routes.maintenance as mod

        # Inyectar una sesión "activa" en el store interno.
        with mod._sessions_lock:
            mod._sessions["fake-active"] = {
                "id": "fake-active",
                "status": "running",
                "cancelled": False,
                "steps": [],
            }
        try:
            resp = self._post(client, "lenovo_update")
            assert resp.status_code == 409
            data = resp.get_json()
            assert "curso" in (data.get("error") or "").lower()
        finally:
            with mod._sessions_lock:
                mod._sessions.pop("fake-active", None)


# ============================================================
# Step handlers — paso 6 (disk_cleanup) y paso 7 (dism_restorehealth)
# ============================================================


class TestStepDiskCleanup:
    """Paso 6: usa clean_disk_extras, NO cleanmgr."""

    def test_calls_clean_disk_extras(self, monkeypatch):
        from routes import maintenance as mod
        import services.cleanup as cleanup_mod

        called = {}

        def fake_clean_disk_extras():
            called["yes"] = True
            return CommandResult(
                status=CommandStatus.SUCCESS,
                output="mocked",
                details={"freed_mb": 12.3, "actions": [{"action": "X"}]},
            )

        monkeypatch.setattr(cleanup_mod, "clean_disk_extras", fake_clean_disk_extras)
        monkeypatch.setattr(mod, "clean_disk_extras", fake_clean_disk_extras, raising=False)

        result = mod._step_disk_cleanup()
        assert called.get("yes") is True
        assert result["status"] == "completed"
        assert result["space_freed_mb"] == 12.3

    def test_propagates_error_status(self, monkeypatch):
        from routes import maintenance as mod
        import services.cleanup as cleanup_mod

        error_result = lambda: CommandResult(status=CommandStatus.ERROR, error="Disk locked")
        monkeypatch.setattr(cleanup_mod, "clean_disk_extras", error_result)
        monkeypatch.setattr(mod, "clean_disk_extras", error_result, raising=False)
        result = mod._step_disk_cleanup()
        assert result["status"] == "failed"
        assert "Disk locked" in result["message"]


class TestStepDismRestoreHealth:
    """Paso 7: ejecuta DISM /Online /Cleanup-Image /RestoreHealth."""

    def test_calls_dism_restorehealth(self, monkeypatch):
        from routes import maintenance as mod

        captured = {}

        def fake_run_cmd(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return CommandResult(status=CommandStatus.SUCCESS, output="No corruption.")

        monkeypatch.setattr(mod, "run_cmd", fake_run_cmd)

        result = mod._step_dism_restorehealth()
        assert result["status"] == "completed"
        cmd = captured["cmd"]
        # Lista o string — admitimos ambos.
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        assert "DISM" in cmd_str
        assert "RestoreHealth" in cmd_str
        assert captured["kwargs"].get("requires_admin") is True

    def test_no_corruption_message(self, monkeypatch):
        from routes import maintenance as mod

        monkeypatch.setattr(
            mod,
            "run_cmd",
            lambda cmd, **kw: CommandResult(
                status=CommandStatus.SUCCESS,
                output="No component store corruption detected.",
            ),
        )
        result = mod._step_dism_restorehealth()
        assert "no se detectó corrupción" in result["message"].lower()


# ============================================================
# clean_disk_extras
# ============================================================


class TestCleanDiskExtras:
    """services.cleanup.clean_disk_extras — papelera + 4 carpetas extras."""

    def test_skips_on_non_windows(self, monkeypatch):
        import services.cleanup as cleanup_mod

        monkeypatch.setattr(cleanup_mod.sys, "platform", "linux")
        result = cleanup_mod.clean_disk_extras()
        assert result.status == CommandStatus.NOT_APPLICABLE

    def test_calls_clear_recyclebin_via_powershell(self, monkeypatch, tmp_path):
        import services.cleanup as cleanup_mod

        captured = {"ps": []}

        def fake_run_powershell(*args, **kwargs):
            captured["ps"].append(args[0] if args else kwargs.get("script", ""))
            return CommandResult(status=CommandStatus.SUCCESS, output="OK")

        monkeypatch.setattr(cleanup_mod.sys, "platform", "win32")
        monkeypatch.setattr(cleanup_mod, "run_powershell", fake_run_powershell)
        # Forzar que ninguna carpeta extra exista (USERPROFILE/SystemRoot apuntan a tmp_path).
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "userprofile"))
        monkeypatch.setenv("SystemRoot", str(tmp_path / "windows"))

        result = cleanup_mod.clean_disk_extras()
        assert result.status == CommandStatus.SUCCESS
        # Primera invocación PowerShell debe ser Clear-RecycleBin.
        assert any("Clear-RecycleBin" in s for s in captured["ps"])
        # Y todas las carpetas extras deben aparecer skipped (no existen).
        actions = result.details.get("actions", [])
        assert any(a["action"] == "Vaciar papelera" for a in actions)
        assert any(a["status"] == "skipped" for a in actions)


# ============================================================
# Audit trail
# ============================================================


class TestAuditTrailOnSession:
    """Tras completar la sesión, _persist_session_audit escribe en audit_log."""

    def test_audit_entry_per_step(self, client, monkeypatch):
        """Mock todos los handlers para que la sesión termine rápido."""
        import routes.maintenance as mod

        for hname in (
            "_step_malwarebytes",
            "_step_ccleaner",
            "_step_advancedsystemcare",
            "_step_defrag",
            "_step_disk_cleanup",
            "_step_dism_restorehealth",
            "_step_windows_update",
            "_step_lenovo_update",
        ):
            monkeypatch.setattr(
                mod,
                hname,
                lambda: {"status": "completed", "message": "mocked"},
            )

        # Lanzar un paso individual (más rápido que la secuencia completa).
        resp = client.post(
            "/maintenance/api/start-step/lenovo_update",
            headers={
                "Origin": "http://127.0.0.1:5000",
                "X-CSRF-Token": _csrf(client),
            },
            content_type="application/json",
            data="{}",
        )
        assert resp.status_code == 200
        sid = resp.get_json()["session_id"]

        # Esperar a que termine (es un solo paso mockeado, debería ser inmediato).
        import time as _t

        for _ in range(20):
            _t.sleep(0.1)
            with mod._sessions_lock:
                s = mod._sessions.get(sid)
                if s and s.get("status") == "completed":
                    break
        else:
            pytest.fail("Sesión single-step no completó a tiempo.")

        # Verificar en audit_log.
        from core.persistence import AuditStore

        entries = AuditStore.get_all("test-session", limit=100)
        maint_entries = [e for e in entries if e.get("module") == "maintenance"]
        assert len(maint_entries) >= 1
        assert any(e.get("action") == "step_lenovo_update" for e in maint_entries)
