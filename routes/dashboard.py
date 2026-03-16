"""Dashboard route - read-only, no governance needed."""
from flask import Blueprint, render_template

from services.system_info import get_system_overview
from services.permissions import get_elevation_info

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    info = get_system_overview()
    elevation = get_elevation_info()
    return render_template('dashboard.html',
                           system_info=info,
                           elevation=elevation)
