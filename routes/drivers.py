"""Driver diagnostics routes."""
from flask import Blueprint, render_template, jsonify

from services import drivers as drv_svc

drivers_bp = Blueprint('drivers', __name__)


@drivers_bp.route('/')
def index():
    return render_template('drivers.html')


@drivers_bp.route('/api/overview')
def api_overview():
    return jsonify(drv_svc.get_driver_overview())


@drivers_bp.route('/api/all')
def api_all():
    return jsonify(drv_svc.enum_drivers().to_dict())


@drivers_bp.route('/api/problems')
def api_problems():
    return jsonify(drv_svc.enum_problem_devices().to_dict())


@drivers_bp.route('/api/third-party')
def api_third_party():
    return jsonify(drv_svc.get_driver_details().to_dict())


@drivers_bp.route('/api/display')
def api_display():
    return jsonify(drv_svc.get_display_drivers().to_dict())


@drivers_bp.route('/api/errors')
def api_errors():
    return jsonify(drv_svc.get_driver_errors().to_dict())
