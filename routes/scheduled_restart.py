"""Scheduled restart routes — governance-compliant.

Toda ruta mutante (create/delete) pasa por core.governance.execute_governed_action
(CLAUDE.md §6). La lógica concreta de schtasks vive en services/scheduled_restart.py.

Read-only (uptime, status) llaman al servicio directo — no son acciones gobernadas.
"""

import json
import logging

from flask import Blueprint, render_template, jsonify, request

from services import scheduled_restart as svc
from core.governance import execute_governed_action

scheduled_restart_bp = Blueprint("scheduled_restart", __name__)
logger = logging.getLogger("cleancpu.scheduled_restart")


@scheduled_restart_bp.route("/")
def index():
    return render_template("scheduled_restart.html")


# ---------------------------------------------------------------------------
# Read-only endpoints
# ---------------------------------------------------------------------------


@scheduled_restart_bp.route("/api/uptime")
def api_uptime():
    """Tiempo de actividad del equipo. Read-only, sin governance."""
    result = svc.get_uptime()

    if result.output:
        try:
            data = json.loads(result.output)
            return jsonify({"status": "success", **data})
        except (json.JSONDecodeError, ValueError):
            pass

    return jsonify(
        {
            "status": "error",
            "message": "No se pudo leer el tiempo de actividad.",
            "days": None,
            "hours": None,
            "minutes": None,
            "boot_time": None,
        }
    )


@scheduled_restart_bp.route("/api/status")
def api_status():
    """Estado de la tarea programada. Read-only, sin governance."""
    result = svc.get_task_status()
    try:
        if result.output:
            return jsonify(json.loads(result.output))
    except (json.JSONDecodeError, ValueError):
        pass
    return jsonify({"exists": False})


# ---------------------------------------------------------------------------
# Mutating endpoints — TODOS por governance
# ---------------------------------------------------------------------------


@scheduled_restart_bp.route("/api/create", methods=["POST"])
def api_create():
    """Crea/actualiza la tarea programada. Va por governance."""
    data = request.get_json(silent=True) or {}

    # Pasar contexto de sesión al service para audit trail
    from flask import current_app

    session_id = current_app.config.get("SESSION_ID", "")
    username = current_app.config.get("USERNAME", "")

    result = execute_governed_action(
        "scheduled_restart.create",
        svc.create_task,
        params={
            "date": data.get("date", "").strip(),
            "time": data.get("time", "").strip(),
            "recurrence": data.get("recurrence", "Once"),
            "grace_period": data.get("grace_period", 5),
            "force": bool(data.get("force", False)),
            "force_confirmed": bool(data.get("force_confirmed", False)),
            "session_id": session_id,
            "username": username,
        },
        confirmation_token=data.get("confirmation_token"),
    )
    return jsonify(result)


@scheduled_restart_bp.route("/api/delete", methods=["POST"])
def api_delete():
    """Borra la tarea programada. Va por governance."""
    data = request.get_json(silent=True) or {}

    from flask import current_app

    session_id = current_app.config.get("SESSION_ID", "")
    username = current_app.config.get("USERNAME", "")

    result = execute_governed_action(
        "scheduled_restart.delete",
        svc.delete_task,
        params={
            "session_id": session_id,
            "username": username,
        },
        confirmation_token=data.get("confirmation_token"),
    )
    return jsonify(result)
