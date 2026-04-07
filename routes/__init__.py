"""
Route blueprints registration.
"""
from routes.dashboard import dashboard_bp
from routes.diagnostics import diagnostics_bp
from routes.cleanup import cleanup_bp
from routes.repair import repair_bp
from routes.network import network_bp
from routes.update import update_bp
from routes.power import power_bp
from routes.drivers import drivers_bp
from routes.security import security_bp
from routes.reports import reports_bp
from routes.advanced import advanced_bp
from routes.logs import logs_bp
from routes.scheduled_restart import scheduled_restart_bp
from routes.maintenance import maintenance_bp
from routes.office import office_bp
from routes.startup import startup_bp
from routes.sharing import sharing_bp


def register_blueprints(app):
    """Register all Flask blueprints."""
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(diagnostics_bp, url_prefix='/diagnostics')
    app.register_blueprint(cleanup_bp, url_prefix='/cleanup')
    app.register_blueprint(repair_bp, url_prefix='/repair')
    app.register_blueprint(network_bp, url_prefix='/network')
    app.register_blueprint(update_bp, url_prefix='/update')
    app.register_blueprint(power_bp, url_prefix='/power')
    app.register_blueprint(drivers_bp, url_prefix='/drivers')
    app.register_blueprint(security_bp, url_prefix='/security')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(advanced_bp, url_prefix='/advanced')
    app.register_blueprint(logs_bp, url_prefix='/logs')
    app.register_blueprint(scheduled_restart_bp, url_prefix='/scheduled-restart')
    app.register_blueprint(maintenance_bp, url_prefix='/maintenance')
    app.register_blueprint(office_bp, url_prefix='/office')
    app.register_blueprint(startup_bp, url_prefix='/startup')
    app.register_blueprint(sharing_bp, url_prefix='/sharing')
