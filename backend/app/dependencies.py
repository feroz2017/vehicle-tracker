from starlette.requests import HTTPConnection


async def get_redis(request: HTTPConnection):
    """
    Inject the shared Redis client into route handlers.

    Uses HTTPConnection (base class of both Request and WebSocket) so this
    dependency works for both HTTP endpoints and WebSocket endpoints.
    Returns None if Redis is unavailable — routes fall back gracefully.
    """
    return getattr(request.app.state, "redis", None)
