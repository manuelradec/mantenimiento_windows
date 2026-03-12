"""Advanced tools routes."""
from flask import Blueprint, render_template, jsonify

from services import restore_tools
from services import graphics_tools
from services.reports import get_log

advanced_bp = Blueprint('advanced', __name__)


@advanced_bp.route('/')
def index():
    return render_template('advanced.html')


# Restore tools
@advanced_bp.route('/api/create-restore-point', methods=['POST'])
def api_create_restore():
    result = restore_tools.create_restore_point()
    get_log().add_entry('restore', 'Create restore point', result.status.value,
                        result=result.output, error=result.error)
    return jsonify(result.to_dict())


@advanced_bp.route('/api/list-restore-points')
def api_list_restore():
    return jsonify(restore_tools.get_restore_points().to_dict())


# Graphics tools
@advanced_bp.route('/api/display-events')
def api_display_events():
    return jsonify(graphics_tools.get_display_events().to_dict())


@advanced_bp.route('/api/gpu-drivers')
def api_gpu_drivers():
    return jsonify(graphics_tools.get_gpu_drivers().to_dict())


@advanced_bp.route('/api/display-diagnostics')
def api_display_diag():
    return jsonify(graphics_tools.get_display_diagnostics())


@advanced_bp.route('/api/psr-check')
def api_psr_check():
    return jsonify(graphics_tools.check_panel_self_refresh().to_dict())
