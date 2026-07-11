import logging
from typing import Awaitable, Callable

from aiohttp import web


SESSION_COOKIE = "rai_web_admin_session"
STATE_COOKIE = "rai_web_admin_oauth_state"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
STATE_MAX_AGE_SECONDS = 10 * 60
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ),
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

log = logging.getLogger(__name__)


def apply_security_headers(response: web.StreamResponse) -> web.StreamResponse:
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


@web.middleware
async def security_headers_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    try:
        response = await handler(request)
    except web.HTTPException as response:
        pass
    except Exception:
        log.exception("Unhandled web admin request error")
        response = web.Response(text="Internal server error.", status=500, content_type="text/plain")
    return apply_security_headers(response)
