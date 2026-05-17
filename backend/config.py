import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Waltti GTFS-RT ────────────────────────────────────────────────────────────
# Auth: HTTP Basic Auth — id:secret (not an API key header)
# Base URL confirmed: https://data.waltti.fi/jyvaskyla/api/gtfsrealtime/v1.0/feed/
WALTTI_ID      = os.getenv("WALTTI_ID", "")
WALTTI_SECRET  = os.getenv("WALTTI_SECRET", "")
WALTTI_BASE_URL = os.getenv("WALTTI_BASE_URL", "https://data.waltti.fi/jyvaskyla/api/gtfsrealtime/v1.0/feed")

# ── Static GTFS (Jyväskylä = authority 209) ──────────────────────────────────
# Public download — no auth required. Refreshed nightly at 01:00 EET by Waltti.
GTFS_STATIC_URL   = os.getenv("GTFS_STATIC_URL",  "https://tvv.fra1.digitaloceanspaces.com/209.zip")
GTFS_SCHEDULE_TTL = int(os.getenv("GTFS_SCHEDULE_TTL", "90000"))  # 25 h — outlasts one nightly cycle

# ── Digitransit ───────────────────────────────────────────────────────────────
DIGITRANSIT_API_KEY  = os.getenv("DIGITRANSIT_API_KEY", "")
DIGITRANSIT_BASE_URL = os.getenv("DIGITRANSIT_BASE_URL", "https://api.digitransit.fi")

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# ── Cache TTLs (seconds) ──────────────────────────────────────────────────────
VEHICLE_CACHE_TTL = int(os.getenv("VEHICLE_CACHE_TTL", "60"))
PLAN_CACHE_TTL    = int(os.getenv("PLAN_CACHE_TTL",    "300"))   # 5 min
GEO_CACHE_TTL     = int(os.getenv("GEO_CACHE_TTL",     "86400")) # 24 h
ALERTS_CACHE_TTL  = int(os.getenv("ALERTS_CACHE_TTL",  "60"))

# ── Freshness thresholds ──────────────────────────────────────────────────────
DELAYED_THRESHOLD = int(os.getenv("DELAYED_THRESHOLD", "60"))    # > 60s → DELAYED
STALE_THRESHOLD   = int(os.getenv("STALE_THRESHOLD",   "120"))   # > 120s → STALE

# ── Worker ────────────────────────────────────────────────────────────────────
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "30"))         # seconds

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent.parent          # vehicle-tracker/
FRONTEND_DIR = ROOT_DIR / "reference-frontend"
