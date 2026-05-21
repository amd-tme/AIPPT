"""HTTP middleware for the AIPPT web app."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Paths that accept deck binary uploads. Any POST here is subject to the
# size limit; everything else (auth, slide reads, etc.) is unaffected.
_UPLOAD_PATH_PREFIXES = (
    "/api/decks/upload",         # /upload and /upload-stream
    "/api/decks/create",         # outline-driven create can attach images
)


class UploadSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject POSTs to the upload endpoints whose ``Content-Length`` exceeds
    ``request.app.state.max_upload_bytes``.

    Returns a JSON 413 in the same shape as the rest of the API
    (``{"error": "..."}``) so the SPA's existing 4xx handling renders a
    useful message. Chunked uploads that omit Content-Length bypass this
    check; the in-handler post-read length check catches them.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method != "POST" or not request.url.path.startswith(_UPLOAD_PATH_PREFIXES):
            return await call_next(request)

        max_bytes = getattr(request.app.state, "max_upload_bytes", 0) or 0
        if max_bytes <= 0:
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if not content_length:
            # Chunked transfer — fall through; in-handler check enforces.
            return await call_next(request)

        try:
            declared = int(content_length)
        except ValueError:
            return _too_large_response(max_bytes, observed=None)

        if declared > max_bytes:
            return _too_large_response(max_bytes, observed=declared)

        return await call_next(request)


def _too_large_response(max_bytes: int, *, observed: int | None) -> JSONResponse:
    """Build the 413 JSON response shared by the middleware and handlers."""
    payload = {
        "error": f"Upload exceeds maximum size of {max_bytes} bytes "
                 f"({max_bytes // (1024 * 1024)} MB).",
        "max_bytes": max_bytes,
    }
    if observed is not None:
        payload["observed_bytes"] = observed
    return JSONResponse(payload, status_code=413)
