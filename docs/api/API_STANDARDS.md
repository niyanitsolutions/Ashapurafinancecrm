# API Standards

## Versioning

Every route is under `/api/v1/` (`backend/app/constants/api.py:API_V1_PREFIX`). Breaking changes get a new prefix (`/api/v2/`) rather than mutating v1's contract in place.

## Response Envelope

Every response, success or failure, has this shape (`backend/app/core/response.py`):

```json
{
  "success": true,
  "data": { "...": "..." },
  "error": null,
  "meta": null
}
```

On failure:

```json
{
  "success": false,
  "data": null,
  "error": { "code": "not_found", "message": "Lead not found.", "details": null },
  "meta": null
}
```

Paginated list responses populate `meta.pagination`:

```json
{ "page": 1, "page_size": 20, "total": 137, "total_pages": 7 }
```

## HTTP Status Codes

The envelope's `success` flag is not a substitute for correct HTTP status codes — both are always set consistently. `AppError` subclasses in `backend/app/core/exceptions.py` map 1:1 to a status code (404 for `NotFoundError`, 401 for `UnauthorizedError`, 403 for `ForbiddenError`, 409 for `ConflictError`, 422 for `ValidationError`, 429 for `RateLimitedError`). Routes raise these rather than constructing `HTTPException` directly, so every error goes through the same envelope.

## Pagination, Filtering, Sorting, Search

List endpoints accept the shared query params from `backend/app/core/pagination.py`:

```
?page=1&page_size=20&sort_by=created_at&sort_dir=desc&search=...
```

Feature-specific filters are added as additional query params on top of these, documented per-endpoint in `docs/api/API.md`.

## Auth

Bearer JWT (`Authorization: Bearer <token>`) — no cookies, so the same contract works for the React web app and the future Flutter apps. See `backend/app/middleware/auth.py` and `backend/app/security/jwt.py`.
