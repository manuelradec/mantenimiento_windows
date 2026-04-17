"""
Security Middleware - CSRF protection, Origin/Host validation, session hardening.

Protects the Flask application against:
- Cross-Site Request Forgery (CSRF)
- DNS rebinding attacks via Host header validation
- Forged requests from unexpected origins
- Session hijacking via hardened cookie flags

Host validation supports wildcards (*.example.com) and reads the full
allowed-host list from Config.ALLOWED_HOSTS, which is itself configurable
via the CLEANCPU_ALLOWED_HOSTS environment variable.  This makes it safe
to deploy behind Apache (WampServer / production) or AWS ALB without
touching source code.

When Config.TRUST_PROXY_HEADERS is True (set automatically for staging /
production environments) Werkzeug ProxyFix is installed so that
X-Forwarded-For and X-Forwarded-Proto are trusted and request.remote_addr /
request.is_secure work correctly behind a load balancer.
"""
import secrets
import logging

from flask import request, abort, g, session, jsonify

logger = logging.getLogger('cleancpu.security')

# Length of CSRF tokens (32 bytes = 64 hex chars)
CSRF_TOKEN_LENGTH = 32


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(CSRF_TOKEN_LENGTH)


def _host_matches_pattern(host_no_port: str, pattern: str) -> bool:
    """
    Return True if host_no_port matches a wildcard pattern.

    Pattern '*.example.com' matches 'sub.example.com' and 'example.com'
    but NOT 'other.com' or 'evilexample.com'.
    """
    if not pattern.startswith('*.'):
        return False
    suffix = pattern[1:]          # '*.example.com' → '.example.com'
    base = suffix[1:]             # '.example.com'  → 'example.com'
    return host_no_port == base or host_no_port.endswith(suffix)


def _build_security_sets(app) -> tuple[set, list, set]:
    """
    Build the allowed Host headers, wildcard patterns, and allowed Origins.

    Reads Config.ALLOWED_HOSTS and Config.PORT.  Falls back to loopback
    if the config is unavailable.

    Returns:
        allowed_hosts    — exact Host header strings (may include :port)
        wildcard_patterns — list of '*.domain' strings for pattern matching
        allowed_origins  — full Origin strings (http:// and https:// variants)
    """
    try:
        from config import Config
        port = Config.PORT
        raw_hosts = list(Config.ALLOWED_HOSTS)
    except Exception:
        port = 5000
        raw_hosts = ['127.0.0.1', 'localhost']

    allowed_hosts: set = set()
    wildcard_patterns: list = []
    allowed_origins: set = set()

    for entry in raw_hosts:
        h = entry.strip()
        if not h:
            continue

        # Wildcard patterns are kept separate for runtime matching
        if h.startswith('*.'):
            wildcard_patterns.append(h)
            # Origins cannot be wildcards — generate both scheme variants
            # for the apex domain (e.g. '*.foo.com' → 'foo.com')
            apex = h[2:]
            allowed_origins.add(f'http://{apex}')
            allowed_origins.add(f'https://{apex}')
            continue

        if ':' in h:
            # Entry already includes an explicit port (e.g. "192.168.1.1:8080")
            allowed_hosts.add(h)
            bare, _, _ = h.rpartition(':')
            allowed_hosts.add(bare)
            allowed_origins.update([
                f'http://{h}', f'https://{h}',
                f'http://{bare}', f'https://{bare}',
            ])
        else:
            # Plain host — add with and without the app port
            allowed_hosts.add(h)
            allowed_hosts.add(f'{h}:{port}')
            allowed_origins.update([
                f'http://{h}',
                f'http://{h}:{port}',
                f'https://{h}',
                f'https://{h}:{port}',
            ])

    logger.debug(
        f"Security sets: {len(allowed_hosts)} exact hosts, "
        f"{len(wildcard_patterns)} wildcard(s), "
        f"{len(allowed_origins)} origins"
    )
    return allowed_hosts, wildcard_patterns, allowed_origins


def init_security(app):
    """
    Initialize security middleware on the Flask app.

    Sets up:
    - ProxyFix (when TRUST_PROXY_HEADERS is True) — must be first
    - Ephemeral per-instance secret key
    - Hardened session cookie configuration
    - CSRF token generation and validation
    - Host header validation (with wildcard support)
    - Origin/Referer validation
    - Security response headers
    """
    # ---- Reverse-proxy support ----
    # Install ProxyFix BEFORE anything else so that request.host,
    # request.remote_addr, and request.is_secure are correct when
    # the app sits behind Apache / nginx / AWS ALB.
    trust_proxy = app.config.get('TRUST_PROXY_HEADERS', False)
    proxy_count = app.config.get('PROXY_COUNT', 1)
    if trust_proxy:
        try:
            from werkzeug.middleware.proxy_fix import ProxyFix
            app.wsgi_app = ProxyFix(
                app.wsgi_app,
                x_for=proxy_count,
                x_proto=proxy_count,
                x_host=proxy_count,
                x_prefix=proxy_count,
            )
            logger.info(
                f"ProxyFix enabled — trusting {proxy_count} upstream proxy hop(s)"
            )
        except ImportError:
            logger.warning("ProxyFix not available (werkzeug not installed?)")

    # ---- Ephemeral Secret Key ----
    app.secret_key = secrets.token_hex(32)
    logger.info("Generated ephemeral per-instance secret key")

    # ---- Session Cookie Hardening ----
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    # SESSION_COOKIE_SECURE must be True only when the browser→server path
    # is HTTPS.  In production behind an HTTPS load balancer this should be
    # True.  In local HTTP setups it must stay False or sessions break.
    app.config['SESSION_COOKIE_SECURE'] = app.config.get('SESSION_COOKIE_SECURE', False)
    app.config['SESSION_COOKIE_NAME'] = 'cleancpu_session'
    app.config['PERMANENT_SESSION_LIFETIME'] = 28800  # 8 hours

    # ---- Pre-compute security sets (read from Config once at startup) ----
    allowed_hosts, wildcard_patterns, allowed_origins = _build_security_sets(app)
    environment = app.config.get('ENVIRONMENT', 'local')

    logger.info(
        f"Host validation: {sorted(allowed_hosts)} + "
        f"{wildcard_patterns} wildcards | "
        f"env={environment} | proxy={trust_proxy}"
    )

    @app.before_request
    def _security_checks():
        """Run security checks before every request."""
        # 1. Host header validation (DNS rebinding protection)
        _validate_host(allowed_hosts, wildcard_patterns)

        # 2. Generate CSRF token if not already in session
        if 'csrf_token' not in session:
            session['csrf_token'] = generate_csrf_token()
            session.permanent = True

        g.csrf_token = session['csrf_token']

        # 3. Skip further checks for safe (read-only) methods
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return

        # 4. Origin / Referer validation for state-changing requests
        _validate_origin(allowed_origins, wildcard_patterns)

        # 5. CSRF token validation for state-changing requests
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

    @app.errorhandler(403)
    def _handle_forbidden(err):
        """
        Return JSON for XHR/fetch clients instead of an HTML error page.

        This prevents the frontend from seeing 'Unexpected token <' when it
        tries to JSON.parse an error response from a failed CSRF / Origin /
        Host check.
        """
        description = getattr(err, 'description', 'Forbidden')
        if _wants_json_response():
            return jsonify({
                'status': 'error',
                'error': description,
                'code': 403,
            }), 403
        # Fall back to default HTML rendering for browser navigations.
        return description, 403

    @app.errorhandler(400)
    def _handle_bad_request(err):
        description = getattr(err, 'description', 'Bad Request')
        if _wants_json_response():
            return jsonify({
                'status': 'error',
                'error': description,
                'code': 400,
            }), 400
        return description, 400


def _wants_json_response() -> bool:
    """
    Decide whether the current request expects a JSON error response.

    True when the request was sent as JSON, was an XHR/fetch (declared via
    X-Requested-With), targets an /api/ path, or explicitly accepts JSON
    over HTML in the Accept header.
    """
    if request.is_json:
        return True
    if request.headers.get('X-Requested-With', '').lower() == 'xmlhttprequest':
        return True
    if request.headers.get('X-CSRF-Token'):
        # Frontend fetch helpers always send this — strong JSON signal.
        return True
    if '/api/' in request.path:
        return True
    accept = request.accept_mimetypes
    return (
        accept.best_match(['application/json', 'text/html']) == 'application/json'
    )


def _validate_host(allowed_hosts: set, wildcard_patterns: list):
    """
    Validate the Host header to prevent DNS rebinding attacks.

    Accepted if the header is in allowed_hosts (exact match) OR
    matches any wildcard pattern (e.g. *.radec.com.mx).
    """
    host = request.host
    if host in allowed_hosts:
        return

    # Wildcard matching — strip port before comparing
    host_no_port = host.rsplit(':', 1)[0] if ':' in host else host
    for pattern in wildcard_patterns:
        if _host_matches_pattern(host_no_port, pattern):
            return

    logger.warning(f"Blocked request with unexpected Host header: {host!r}")
    abort(403, description='Invalid Host header')


def _extract_origin(url: str) -> str:
    """
    Return the scheme://host[:port] portion of a URL.

    Used to normalise a Referer header (full URL) into an origin string
    before comparison, so that the same _origin_allowed logic handles both
    Origin and Referer headers.

    Returns the original string unchanged if it cannot be parsed.
    """
    try:
        scheme, rest = url.split('://', 1)
        host_with_port = rest.split('/', 1)[0]
        return f'{scheme}://{host_with_port}'
    except ValueError:
        return url


def _origin_allowed(origin: str, allowed_origins: set, wildcard_patterns: list) -> bool:
    """
    Return True if origin (scheme://host[:port]) is allowed.

    Checks exact set membership first, then wildcard patterns using the
    same _host_matches_pattern logic as Host header validation.
    """
    if origin in allowed_origins:
        return True
    try:
        host_with_port = origin.split('://', 1)[1]
        host_no_port = host_with_port.rsplit(':', 1)[0] if ':' in host_with_port else host_with_port
    except IndexError:
        return False
    return any(_host_matches_pattern(host_no_port, p) for p in wildcard_patterns)


def _validate_origin(allowed_origins: set, wildcard_patterns: list = ()):
    """
    Validate that the request originates from an allowed application origin.

    Checks Origin header first, then Referer.
    Blocks requests that provide neither (prevents cross-site fetches that
    strip those headers).
    """
    origin = request.headers.get('Origin', '')
    referer = request.headers.get('Referer', '')

    if origin:
        if _origin_allowed(origin, allowed_origins, wildcard_patterns):
            return
        logger.warning(f"Blocked request with invalid Origin: {origin!r}")
        abort(403, description='Invalid request origin')

    if referer:
        # Referer is a full URL — normalise to scheme://host for comparison
        referer_origin = _extract_origin(referer)
        if _origin_allowed(referer_origin, allowed_origins, wildcard_patterns):
            return
        logger.warning(f"Blocked request with invalid Referer: {referer!r}")
        abort(403, description='Invalid request origin')

    # Neither Origin nor Referer present
    logger.warning(
        f"Blocked request missing Origin and Referer: "
        f"{request.method} {request.path}"
    )
    abort(403, description='Missing Origin/Referer header')


def _validate_csrf_token():
    """
    Validate the CSRF token on state-changing requests.

    Token accepted via:
    - X-CSRF-Token header (primary, for AJAX)
    - csrf_token form field (HTML forms)
    - csrf_token key in JSON body
    """
    expected = session.get('csrf_token', '')
    if not expected:
        abort(403, description='No CSRF session')

    provided = request.headers.get('X-CSRF-Token', '')

    if not provided:
        if request.is_json:
            provided = (request.get_json(silent=True) or {}).get('csrf_token', '')
        else:
            provided = request.form.get('csrf_token', '')

    if not provided or not secrets.compare_digest(provided, expected):
        logger.warning(f"CSRF validation failed for {request.method} {request.path}")
        abort(403, description='CSRF validation failed')
