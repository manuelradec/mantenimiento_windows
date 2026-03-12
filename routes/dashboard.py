"""Dashboard route."""
from flask import Blueprint, render_template, jsonify

from services.system_info import get_system_overview
from services.permissions import get_elevation_info
from services.reports import get_log

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    info = get_system_overview()
    elevation = get_elevation_info()
    return render_template('dashboard.html',
                           system_info=info,
                           elevation=elevation)


@dashboard_bp.route('/api/system-overview')
def api_system_overview():
    return jsonify(get_system_overview())


@dashboard_bp.route('/api/elevation')
def api_elevation():
    return jsonify(get_elevation_info())
