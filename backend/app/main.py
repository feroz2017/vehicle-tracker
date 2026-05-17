import logging
import redis.asyncio as aioredis

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import REDIS_URL, FRONTEND_DIR
from app.logging_config import setup_logging
from app.routes import router

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Vehicle Tracker API",
    description="Jyväskylä real-time bus tracking — TJTS5901",
    version="0.1.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allows the frontend (running on any origin during dev) to call the API.
# TODO: restrict origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup / Shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    """Connect to Redis on startup. App runs without Redis (dummy mode) if unavailable."""
    try:
        r = await aioredis.from_url(REDIS_URL, decode_responses=True)
        await r.ping()
        app.state.redis = r
        logger.info("Redis connected: %s", REDIS_URL)
    except Exception as exc:
        app.state.redis = None
        logger.warning("Redis unavailable (%s) — running in dummy mode", exc)


@app.on_event("shutdown")
async def shutdown() -> None:
    if getattr(app.state, "redis", None):
        await app.state.redis.aclose()
        logger.info("Redis connection closed")


# ── API routes ────────────────────────────────────────────────────────────────
app.include_router(router)

# ── Serve reference-frontend ──────────────────────────────────────────────────
# Serves JS and CSS from /static/*
# The frontend team replaces this with their own server — nothing in the
# backend needs to change.
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def no_frontend():
        return {"message": "API running. Reference frontend not found.", "docs": "/docs"}
