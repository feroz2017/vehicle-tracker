import logging
import redis.asyncio as aioredis
from fastapi import Request

logger = logging.getLogger(__name__)


async def get_redis(request: Request):
    """
    Inject the shared Redis client into route handlers.
    Returns None if Redis is not available — routes fall back to dummy data.
    """
    return getattr(request.app.state, "redis", None)
