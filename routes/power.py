"""Power management routes."""
from flask import Blueprint, render_template, jsonify

from services import power_tools as power_svc
from services.reports import get_log

power_bp = Blueprint('power', __name__)


@power_bp.route('/')
def index():
    return render_template('power.html')


@power_bp.route('/api/active-plan')
def api_active_plan():
    return jsonify(power_svc.get_active_power_plan().to_dict())


@power_bp.route('/api/plan-details')
def api_plan_details():
    return jsonify(power_svc.get_power_plan_details().to_dict())


@power_bp.route('/api/list-plans')
def api_list_plans():
    return jsonify(power_svc.list_power_plans().to_dict())


@power_bp.route('/api/set-high-performance', methods=['POST'])
def api_set_high_perf():
    result = power_svc.set_high_performance()
    get_log().add_entry('power', 'Set High Performance', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@power_bp.route('/api/set-balanced', methods=['POST'])
def api_set_balanced():
    result = power_svc.set_balanced()
    get_log().add_entry('power', 'Set Balanced', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@power_bp.route('/api/battery-report', methods=['POST'])
def api_battery_report():
    result = power_svc.get_battery_report()
    get_log().add_entry('power', 'Generate battery report', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@power_bp.route('/api/disable-hibernation', methods=['POST'])
def api_disable_hibernation():
    result = power_svc.disable_hibernation()
    get_log().add_entry('power', 'Disable hibernation', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@power_bp.route('/api/enable-hibernation', methods=['POST'])
def api_enable_hibernation():
    result = power_svc.enable_hibernation()
    get_log().add_entry('power', 'Enable hibernation', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@power_bp.route('/api/processor-info')
def api_processor_info():
    return jsonify(power_svc.get_processor_power_info().to_dict())
