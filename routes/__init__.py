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
