"""Regression coverage for the reported "Swagger sometimes shows a blank white page"
bug. Root cause: the global `SecurityHeadersMiddleware` CSP (`default-src 'self'`)
silently blocked Swagger UI/ReDoc's CDN-hosted JS/CSS and FastAPI's own inline bootstrap
script — with no visible HTTP error, since the HTML page itself still returned 200, it
just rendered as an empty shell. Fixed by loosening the CSP for exactly the doc-tooling
paths (`/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`); every other route
keeps the original strict policy, asserted below too so this fix can never silently
regress into "loosened for everything."
"""


async def test_openapi_schema_generates_without_error(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200, r.text
    schema = r.json()
    assert schema["openapi"]
    assert len(schema["paths"]) > 0


async def test_swagger_docs_page_loads_with_cdn_permissive_csp(client):
    r = await client.get("/docs")
    assert r.status_code == 200, r.text
    # The two concrete things a blocked CSP would have silently dropped from the page.
    assert "swagger-ui-bundle.js" in r.text
    assert "SwaggerUIBundle(" in r.text
    csp = r.headers.get("content-security-policy", "")
    assert "cdn.jsdelivr.net" in csp
    assert "script-src" in csp  # not just falling back to a bare default-src


async def test_redoc_page_loads_with_cdn_permissive_csp(client):
    r = await client.get("/redoc")
    assert r.status_code == 200, r.text
    assert "cdn.jsdelivr.net" in r.headers.get("content-security-policy", "")


async def test_ordinary_api_routes_keep_the_strict_csp_unchanged(client):
    # Any real API path — a 404 still goes through the same middleware stack (including
    # SecurityHeadersMiddleware) that a real 200 would, without needing live Mongo/Redis.
    r = await client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    csp = r.headers.get("content-security-policy", "")
    assert csp == "default-src 'self'; frame-ancestors 'none'; img-src 'self' https: data:; connect-src 'self' https:"
    assert "cdn.jsdelivr.net" not in csp
