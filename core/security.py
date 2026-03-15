"""
Security Middleware - CSRF protection, Origin validation, session tokens.

Protects the local Flask application against:
- Cross-Site Request Forgery (CSRF)
- Localhost-targeted abuse from malicious browser pages
- Forged requests from external origins

Strategy:
- Ephemeral session token generated on app start
- CSRF token injected into all forms and required on all POST requests
- Origin/Referer header validation on state-changing requests
- Token transmitted via X-CSRF-Token header (JS) or hidden form field
"""
import os
import secrets
import logging
import hashlib
from functools import wraps

from flask import request, abort, g, session

logger = logging.getLogger('cleancpu.security')

# Length of CSRF tokens
CSRF_TOKEN_LENGTH = 32


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(CSRF_TOKEN_LENGTH)


def init_security(app):
    """
    Initialize security middleware on the Flask app.

    Sets up:
    - Secret key from environment or secure random
    - CSRF token generation and validation
    - Origin/Referer validation
    - Security response headers
    """
    # Use environment secret or generate a secure one per instance
    if app.config.get('SECRET_KEY', '').startswith('cleancpu-local'):
        # Replace the default insecure key with a per-instance random key
        app.secret_key = secrets.token_hex(32)
        logger.info("Generated per-instance secret key")
    else:
        app.secret_key = app.config['SECRET_KEY']

    @app.before_request
    def _security_checks():
        """Run security checks before every request."""
        # Generate CSRF token if not in session
        if 'csrf_token' not in session:
            session['csrf_token'] = generate_csrf_token()

        g.csrf_token = session['csrf_token']

        # Skip checks for safe methods
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return

        # Validate Origin/Referer for state-changing requests
        _validate_origin()

        # Validate CSRF token for state-changing requests
        _validate_csrf_token()

    @app.after_request
    def _add_security_headers(response):
        """Add security headers to all responses."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        # CSP: only allow local resources
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response

    @app.context_processor
    def _inject_csrf():
        """Make CSRF token available to all templates."""
        return {'csrf_token': session.get('csrf_token', '')}


def _validate_origin():
    """
    Validate that the request originates from the local application.

    Checks Origin header first, falls back to Referer.
    """
    origin = request.headers.get('Origin', '')
    referer = request.headers.get('Referer', '')

    allowed_origins = {
        'http://127.0.0.1:5000',
        'http://localhost:5000',
    }

    # Try to use dynamic port from config
    try:
        from config import Config
        port = Config.PORT
        allowed_origins.add(f'http://127.0.0.1:{port}')
        allowed_origins.add(f'http://localhost:{port}')
    except Exception:
        pass

    if origin:
        if origin not in allowed_origins:
            logger.warning(f"Blocked request with invalid Origin: {origin}")
            abort(403, description='Invalid request origin')
        return

    if referer:
        # Check if referer starts with any allowed origin
        if not any(referer.startswith(o) for o in allowed_origins):
            logger.warning(f"Blocked request with invalid Referer: {referer}")
            abort(403, description='Invalid request origin')
        return

    # No Origin or Referer header - block for safety
    # Exception: allow requests with valid CSRF token even without Origin
    # (some tools/clients don't send Origin)


def _validate_csrf_token():
    """
    Validate the CSRF token on state-changing requests.

    Token can be provided via:
    - X-CSRF-Token header (primary, for AJAX)
    - csrf_token form field (fallback, for forms)
    """
    expected = session.get('csrf_token', '')
    if not expected:
        abort(403, description='No CSRF session')

    # Check header first (AJAX requests)
    provided = request.headers.get('X-CSRF-Token', '')

    # Fall back to form field
    if not provided:
        if request.is_json:
            provided = (request.get_json(silent=True) or {}).get('csrf_token', '')
        else:
            provided = request.form.get('csrf_token', '')

    if not provided or not secrets.compare_digest(provided, expected):
        logger.warning(f"CSRF validation failed for {request.method} {request.path}")
        abort(403, description='CSRF validation failed')
