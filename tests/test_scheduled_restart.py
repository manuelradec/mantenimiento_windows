"""Tests for the scheduled_restart module.

Cubre:
- Validaciones del service (sin invocar PowerShell real).
- Audit trail en SQLite via ScheduledRestartStore.
- Registro de acciones en action_registry.
- Rollback strategies en governance.
- Mutating routes pasan por governance (DISRUPTIVE → rejected en
  default safe_maintenance mode, lo que prueba el routing).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import scheduled_restart as svc
from services.command_runner import CommandResult, CommandStatus

# ============================================================
# Local app/client fixtures (mismo patrón que test_routes.py y
# test_smart_app_control.py — el conftest autouse aísla la DB pero
# la fixture `client` la necesita cada test file que la use).
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

    app = create_app()
    app.config["TESTING"] = True
    app.config["SESSION_ID"] = "test-session"
    app.config["HOSTNAME"] = "testhost"
    app.config["USERNAME"] = "testuser"
    init_db()
    SessionStore.create(
        session_id="test-session",
        hostname="testhost",
        username="testuser",
        is_admin=False,
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ============================================================
# Service-level validations (no PowerShell invocation)
# ============================================================


class TestCreateTaskValidations:
    """Validaciones de input en svc.create_task antes de tocar PowerShell."""

    def test_missing_date_returns_error(self):
        result = svc.create_task(date="", time="10:00")
        assert result.status == CommandStatus.ERROR
        assert "obligatorios" in result.error.lower()

    def test_missing_time_returns_error(self):
        result = svc.create_task(date="2099-01-01", time="")
        assert result.status == CommandStatus.ERROR
        assert "obligatorios" in result.error.lower()

    def test_invalid_date_format(self):
        result = svc.create_task(date="not-a-date", time="10:00")
        assert result.status == CommandStatus.ERROR
        assert "no válido" in result.error.lower()

    def test_past_datetime_for_once_recurrence(self):
        result = svc.create_task(date="2000-01-01", time="10:00", recurrence="Once")
        assert result.status == CommandStatus.ERROR
        assert "pasado" in result.error.lower()

    def test_invalid_recurrence(self):
        result = svc.create_task(date="2099-01-01", time="10:00", recurrence="Yearly")
        assert result.status == CommandStatus.ERROR
        assert "recurrencia" in result.error.lower()

    def test_invalid_grace_period(self):
        result = svc.create_task(
            date="2099-01-01", time="10:00", recurrence="Once", grace_period=999
        )
        assert result.status == CommandStatus.ERROR
        assert "gracia" in result.error.lower()

    def test_force_without_confirmation_rejected(self):
        result = svc.create_task(
            date="2099-01-01", time="10:00", force=True, force_confirmed=False
        )
        assert result.status == CommandStatus.ERROR
        assert (
            "confirmación" in result.error.lower() or "force_confirmed" in result.error
        )


class TestCreateTaskHappyPath:
    """create_task con PowerShell mockeado."""

    def test_normal_path_success(self, monkeypatch):
        captured_args = {}

        def fake_run_powershell(*args, **kwargs):
            captured_args["args"] = args
            captured_args["kwargs"] = kwargs
            return CommandResult(status=CommandStatus.SUCCESS, output="OK")

        monkeypatch.setattr(svc, "run_powershell", fake_run_powershell)

        result = svc.create_task(
            date="2099-12-31",
            time="23:00",
            recurrence="Once",
            grace_period=15,
        )
        assert result.status == CommandStatus.SUCCESS
        assert "2099-12-31" in result.output
        assert "15 min" in result.output
        # PowerShell fue invocado con un script que contenía /r /t 900 (15min)
        ps_script = captured_args["args"][0]
        assert "/r /t 900" in ps_script
        assert "Register-ScheduledTask" in ps_script

    def test_force_path_success_uses_force_flag(self, monkeypatch):
        captured_args = {}

        def fake_run_powershell(*args, **kwargs):
            captured_args["args"] = args
            return CommandResult(status=CommandStatus.SUCCESS, output="OK")

        monkeypatch.setattr(svc, "run_powershell", fake_run_powershell)

        result = svc.create_task(
            date="2099-12-31",
            time="23:00",
            recurrence="Once",
            force=True,
            force_confirmed=True,
        )
        assert result.status == CommandStatus.SUCCESS
        assert "FORZADO" in result.output
        ps_script = captured_args["args"][0]
        assert "/r /f /t 0" in ps_script


class TestDeleteTask:
    """delete_task con PowerShell mockeado."""

    def test_delete_success(self, monkeypatch):
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(status=CommandStatus.SUCCESS, output="OK"),
        )
        result = svc.delete_task()
        assert result.status == CommandStatus.SUCCESS
        assert "eliminada" in result.output.lower()

    def test_delete_propagates_error(self, monkeypatch):
        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.ERROR, error="No se pudo borrar"
            ),
        )
        result = svc.delete_task()
        assert result.status == CommandStatus.ERROR


# ============================================================
# Audit trail (ScheduledRestartStore)
# ============================================================


class TestAuditTrail:
    """ScheduledRestartStore guarda metadata de cada operación."""

    def test_record_create_success(self, monkeypatch):
        from core.persistence import init_db, ScheduledRestartStore

        init_db()

        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(status=CommandStatus.SUCCESS, output="OK"),
        )
        svc.create_task(
            date="2099-12-31",
            time="23:00",
            recurrence="Daily",
            grace_period=30,
            session_id="test-session",
            username="tech",
        )

        rows = ScheduledRestartStore.get_recent(limit=5)
        assert len(rows) >= 1
        last = rows[0]
        assert last["operation"] == "create"
        assert last["scheduled_at"] == "2099-12-31 23:00"
        assert last["recurrence"] == "Daily"
        assert last["grace_period"] == 30
        assert last["force"] == 0
        assert last["success"] == 1
        assert last["session_id"] == "test-session"
        assert last["username"] == "tech"

    def test_record_create_failure(self, monkeypatch):
        from core.persistence import init_db, ScheduledRestartStore

        init_db()

        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(
                status=CommandStatus.ERROR, error="Access denied"
            ),
        )
        svc.create_task(date="2099-12-31", time="23:00", session_id="s1", username="u1")

        rows = ScheduledRestartStore.get_recent(limit=5)
        last = rows[0]
        assert last["operation"] == "create"
        assert last["success"] == 0
        assert last["error"] == "Access denied"

    def test_record_delete(self, monkeypatch):
        from core.persistence import init_db, ScheduledRestartStore

        init_db()

        monkeypatch.setattr(
            svc,
            "run_powershell",
            lambda *a, **k: CommandResult(status=CommandStatus.SUCCESS, output="OK"),
        )
        svc.delete_task(session_id="sess", username="user")

        rows = ScheduledRestartStore.get_recent(limit=5)
        last = rows[0]
        assert last["operation"] == "delete"
        assert last["success"] == 1
        assert last["session_id"] == "sess"
        assert last["username"] == "user"


# ============================================================
# Action registry + governance integration
# ============================================================


class TestActionRegistration:
    """Las dos acciones de scheduled_restart están registradas."""

    def test_create_action_registered_as_disruptive(self):
        from core.action_registry import registry, RiskClass

        action = registry.get("scheduled_restart.create")
        assert action is not None
        assert action.risk_class == RiskClass.DISRUPTIVE
        assert action.requires_admin is True
        assert action.requires_confirmation is True

    def test_delete_action_registered_as_disruptive(self):
        from core.action_registry import registry, RiskClass

        action = registry.get("scheduled_restart.delete")
        assert action is not None
        assert action.risk_class == RiskClass.DISRUPTIVE
        assert action.requires_admin is True


class TestRollbackStrategies:
    """Ambas acciones tienen rollback info en governance."""

    def test_create_has_rollback(self):
        from core.governance import get_rollback_info

        info = get_rollback_info("scheduled_restart.create")
        assert info["classification"] == "manually_reversible"
        assert "CleanCPU_Restart" in info["instructions"]

    def test_delete_has_rollback(self):
        from core.governance import get_rollback_info

        info = get_rollback_info("scheduled_restart.delete")
        assert info["classification"] == "manually_reversible"


# ============================================================
# Routes integration (governance flow end-to-end)
# ============================================================


class TestRoutesGovernance:
    """Las rutas mutantes pasan por execute_governed_action.

    En el modo default (safe_maintenance), DISRUPTIVE actions deberían
    ser rejected por la policy. Eso es la prueba de que la ruta
    *está* yendo por governance — si sortease governance, el endpoint
    devolvería el resultado del service directamente sin status='rejected'.
    """

    def _get_csrf(self, client):
        client.get("/")
        with client.session_transaction() as sess:
            return sess.get("csrf_token", "")

    def test_create_route_goes_through_governance(self, client):
        csrf = self._get_csrf(client)
        resp = client.post(
            "/scheduled-restart/api/create",
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "http://127.0.0.1:5000",
            },
            content_type="application/json",
            data='{"date":"2099-12-31","time":"23:00","recurrence":"Once","grace_period":15}',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        # DISRUPTIVE en safe_maintenance → rejected o needs_confirmation
        # (ambos prueban que pasó por governance, no que ejecutó directo).
        assert data.get("status") in (
            "rejected",
            "needs_confirmation",
            "not_applicable",
        )

    def test_delete_route_goes_through_governance(self, client):
        csrf = self._get_csrf(client)
        resp = client.post(
            "/scheduled-restart/api/delete",
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "http://127.0.0.1:5000",
            },
            content_type="application/json",
            data="{}",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") in (
            "rejected",
            "needs_confirmation",
            "not_applicable",
        )

    def test_create_returns_action_id_on_needs_confirmation(self, client, app):
        """Cuando governance pide confirmación, la respuesta DEBE incluir
        action_id para que la UI pueda completar el 2-step automáticamente.
        Regresión: la UI rompía con 'Error al programar' cuando llegaba este
        status sin manejarlo (templates/scheduled_restart.html).
        """
        from core.policy_engine import policy, OperationMode

        with app.app_context():
            policy.set_mode(OperationMode.EXPERT)
        csrf = self._get_csrf(client)
        resp = client.post(
            "/scheduled-restart/api/create",
            headers={"X-CSRF-Token": csrf, "Origin": "http://127.0.0.1:5000"},
            content_type="application/json",
            data='{"date":"2099-12-31","time":"23:00","recurrence":"Once","grace_period":15}',
        )
        data = resp.get_json()
        if data.get("status") == "needs_confirmation":
            assert data.get("action_id") == "scheduled_restart.create"


# ============================================================
# Read-only endpoints (sin governance)
# ============================================================


class TestReadOnlyRoutes:
    """uptime + status pegan al service directo, sin governance."""

    def test_uptime_endpoint(self, client, monkeypatch):
        import services.scheduled_restart as svc_mod

        monkeypatch.setattr(
            svc_mod,
            "get_uptime",
            lambda: CommandResult(
                status=CommandStatus.SUCCESS,
                output='{"days":3,"hours":5,"minutes":12,"boot_time":"2026-05-02 02:18"}',
            ),
        )
        resp = client.get("/scheduled-restart/api/uptime")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["days"] == 3
        assert data["boot_time"] == "2026-05-02 02:18"

    def test_uptime_endpoint_handles_bad_json(self, client, monkeypatch):
        import services.scheduled_restart as svc_mod

        monkeypatch.setattr(
            svc_mod,
            "get_uptime",
            lambda: CommandResult(status=CommandStatus.ERROR, output=""),
        )
        resp = client.get("/scheduled-restart/api/uptime")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["days"] is None

    def test_status_endpoint_task_not_found(self, client, monkeypatch):
        import services.scheduled_restart as svc_mod

        monkeypatch.setattr(
            svc_mod,
            "get_task_status",
            lambda: CommandResult(
                status=CommandStatus.SUCCESS,
                output='{"exists":false}',
            ),
        )
        resp = client.get("/scheduled-restart/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["exists"] is False
