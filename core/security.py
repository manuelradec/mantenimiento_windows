"""
Security Middleware - CSRF protection, Origin/Host validation, session hardening.

Protects the local Flask application against:
- Cross-Site Request Forgery (CSRF)
- Localhost-targeted abuse from malicious browser pages
- Forged requests from external origins
- DNS rebinding attacks via Host header validation
- Session hijacking via hardened cookie flags

Security Architecture:
- Per-instance secret key (ephemeral, regenerated each startup)
- Session-bound CSRF token (stored server-side in Flask session)
- X-CSRF-Token header required on all POST/PUT/DELETE/PATCH
- Origin AND Referer validation on state-changing requests
- Host header validation (only 127.0.0.1 / localhost accepted)
- Requests with no Origin AND no Referer are BLOCKED
- Hardened session cookie: HttpOnly, SameSite=Strict, no JS access
- Security response headers: CSP, X-Frame-Options, nosniff, etc.
"""
import secrets
import logging

from flask import request, abort, g, session

logger = logging.getLogger('cleancpu.security')

# Length of CSRF tokens (32 bytes = 64 hex chars)
CSRF_TOKEN_LENGTH = 32


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(CSRF_TOKEN_LENGTH)


def _get_allowed_hosts_and_origins(app) -> tuple[set, set]:
    """Build the sets of allowed Host headers and Origin values."""
    port = app.config.get('PORT', 5000)
    try:
        from config import Config
        port = Config.PORT
    except Exception:
        pass

    allowed_hosts = {
        f'127.0.0.1:{port}',
        f'localhost:{port}',
        '127.0.0.1',
        'localhost',
    }
    allowed_origins = {
        f'http://127.0.0.1:{port}',
        f'http://localhost:{port}',
    }
    return allowed_hosts, allowed_origins


def init_security(app):
    """
    Initialize security middleware on the Flask app.

    Sets up:
    - Ephemeral per-instance secret key
    - Hardened session cookie configuration
    - CSRF token generation and validation
    - Host header validation
    - Origin/Referer validation
    - Security response headers
    """
    # ---- Ephemeral Secret Key ----
    # Always generate a per-instance random key for session security
    app.secret_key = secrets.token_hex(32)
    logger.info("Generated ephemeral per-instance secret key")

    # ---- Session Cookie Hardening ----
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    # SESSION_COOKIE_SECURE=False because we run on HTTP localhost
    # Setting it True would break sessions over plain HTTP
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_NAME'] = 'cleancpu_session'
    # Session lifetime: 8 hours (one work shift)
    app.config['PERMANENT_SESSION_LIFETIME'] = 28800

    # Pre-compute allowed values
    allowed_hosts, allowed_origins = _get_allowed_hosts_and_origins(app)

    @app.before_request
    def _security_checks():
        """Run security checks before every request."""
        # 1. Validate Host header on ALL requests (DNS rebinding protection)
        _validate_host(allowed_hosts)

        # 2. Generate CSRF token if not in session
        if 'csrf_token' not in session:
            session['csrf_token'] = generate_csrf_token()
            session.permanent = True

        g.csrf_token = session['csrf_token']

        # 3. Skip further checks for safe methods
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return

        # 4. Validate Origin/Referer for state-changing requests
        _validate_origin(allowed_origins)

        # 5. Validate CSRF token for state-changing requests
        _validate_csrf_token()

    @app.after_request
    def _add_security_headers(response):
        """Add security headers to all responses."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        # CSP: only allow local resources
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self';"
        )
        return response

    @app.context_processor
    def _inject_csrf():
        """Make CSRF token available to all templates."""
        return {'csrf_token': session.get('csrf_token', '')}


def _validate_host(allowed_hosts: set):
    """
    Validate the Host header to prevent DNS rebinding attacks.
    Only 127.0.0.1 and localhost are accepted.
    """
    host = request.host
    if host not in allowed_hosts:
        logger.warning(f"Blocked request with unexpected Host header: {host}")
        abort(403, description='Invalid Host header')


def _validate_origin(allowed_origins: set):
    """
    Validate that the request originates from the local application.
    Checks Origin header first, falls back to Referer.
    BLOCKS requests with neither Origin nor Referer.
    """
    origin = request.headers.get('Origin', '')
    referer = request.headers.get('Referer', '')

    if origin:
        if origin not in allowed_origins:
            logger.warning(f"Blocked request with invalid Origin: {origin}")
            abort(403, description='Invalid request origin')
        return

    if referer:
        if not any(referer.startswith(o) for o in allowed_origins):
            logger.warning(f"Blocked request with invalid Referer: {referer}")
            abort(403, description='Invalid request origin')
        return

    # No Origin AND no Referer - BLOCK for safety
    # This prevents cross-site fetches that strip these headers
    logger.warning(f"Blocked request missing both Origin and Referer: "
                   f"{request.method} {request.path}")
    abort(403, description='Missing Origin/Referer header')


def _validate_csrf_token():
    """
    Validate the CSRF token on state-changing requests.

    Token can be provided via:
    - X-CSRF-Token header (primary, for AJAX)
    - csrf_token form field (fallback, for forms)
    - csrf_token in JSON body (fallback, for JSON APIs)
    """
    expected = session.get('csrf_token', '')
    if not expected:
        abort(403, description='No CSRF session')

    # Check header first (AJAX requests)
    provided = request.headers.get('X-CSRF-Token', '')

    # Fall back to form field or JSON body
    if not provided:
        if request.is_json:
            provided = (request.get_json(silent=True) or {}).get('csrf_token', '')
        else:
            provided = request.form.get('csrf_token', '')

    if not provided or not secrets.compare_digest(provided, expected):
        logger.warning(f"CSRF validation failed for {request.method} {request.path}")
        abort(403, description='CSRF validation failed')
