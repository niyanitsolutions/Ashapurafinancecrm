from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# FastAPI's auto-generated docs tooling — registered at these exact root paths
# regardless of `settings.api_v1_prefix` (confirmed via `app.routes`, not assumed).
# Swagger UI (`/docs`) and ReDoc (`/redoc`) load their JS/CSS from a CDN
# (cdn.jsdelivr.net) plus an inline bootstrap `<script>` FastAPI embeds directly in the
# HTML it returns — both are exactly what the strict `default-src 'self'` CSP below
# silently blocks, with zero visible error: the browser just drops the blocked
# script/style and the page renders as a blank shell. That's the "Swagger sometimes
# shows a blank white page" symptom — "sometimes" because a browser that already had
# the CDN bundle cached from an earlier visit (before this header existed, or from a
# different local port) still rendered fine; a fresh load never could.
_DOCS_TOOLING_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline banking-grade response headers — defense in depth alongside the
    application-level auth/RBAC checks that already gate every route, not a substitute
    for them. This backend is API-only (no HTML/cookies of its own — auth is bearer
    tokens, see docs/decisions/DECISIONS.md #008), so CSP/frame-ancestors mainly protect
    any future HTML error pages; Cache-Control is the header doing real work here,
    keeping authenticated JSON responses out of shared/browser caches. Deliberately
    permissive on img-src/connect-src rather than risk breaking S3 presigned document/
    photo URLs, which are dynamic, per-request hosts.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path in _DOCS_TOOLING_PATHS:
            # A loosened CSP scoped to exactly these dev-tooling paths — every real API
            # response (including every route under `settings.api_v1_prefix`) keeps the
            # strict policy below, completely unchanged.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' https: data:; "
                "connect-src 'self' https:; frame-ancestors 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; frame-ancestors 'none'; img-src 'self' https: data:; connect-src 'self' https:"
            )
        # Inert over plain http (local dev); takes effect once deployed behind TLS.
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store"
        return response
