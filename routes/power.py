"""Power management routes - ALL mutating endpoints governed."""
from flask import Blueprint, render_template, jsonify, request

from services import power_tools as power_svc
from core.governance import execute_governed_action

power_bp = Blueprint('power', __name__)


@power_bp.route('/')
def index():
    return render_template('power.html')


# --- Read-only ---

@power_bp.route('/api/active-plan')
def api_active_plan():
    return jsonify(power_svc.get_active_power_plan().to_dict())


@power_bp.route('/api/plan-details')
def api_plan_details():
    return jsonify(power_svc.get_power_plan_details().to_dict())


@power_bp.route('/api/list-plans')
def api_list_plans():
    return jsonify(power_svc.list_power_plans().to_dict())


@power_bp.route('/api/processor-info')
def api_processor_info():
    return jsonify(power_svc.get_processor_power_info().to_dict())


# --- Mutating endpoints - ALL governed ---

@power_bp.route('/api/set-high-performance', methods=['POST'])
def api_set_high_perf():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'power.set_high_performance', power_svc.set_high_performance,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@power_bp.route('/api/set-balanced', methods=['POST'])
def api_set_balanced():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'power.set_balanced', power_svc.set_balanced,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@power_bp.route('/api/battery-report', methods=['POST'])
def api_battery_report():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'power.battery_report', power_svc.get_battery_report,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@power_bp.route('/api/disable-hibernation', methods=['POST'])
def api_disable_hibernation():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'power.disable_hibernation', power_svc.disable_hibernation,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)


@power_bp.route('/api/enable-hibernation', methods=['POST'])
def api_enable_hibernation():
    data = request.get_json(silent=True) or {}
    result = execute_governed_action(
        'power.enable_hibernation', power_svc.enable_hibernation,
        confirmation_token=data.get('confirmation_token'),
    )
    return jsonify(result)
