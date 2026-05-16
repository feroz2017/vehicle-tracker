# Running the Backend

This guide covers every way to start the backend — Docker Compose for the fast path, bare Python for day-to-day development, and what each environment variable controls.

---

## What the backend is

Three independent processes that must all be running for the full app to work:

| Process | What it does | Without it |
|---|---|---|
| **Redis** | Cache + Pub/Sub message bus | App falls back to dummy data |
| **FastAPI** | HTTP API + WebSocket server | Nothing works |
| **Worker** | Polls Waltti every 30 s, writes to Redis | No live bus data (dummy fallback) |

FastAPI and the Worker are both built from the same `backend/` codebase. Docker Compose starts them as separate containers with different `CMD` overrides. Locally you run them in separate terminals.

---

## Option A — Docker Compose (recommended starting point)

No Python setup needed. Requires Docker Desktop.

```bash
# Clone and enter the project root
cd vehicle-tracker

# Copy the example env file
cp .env.example .env
# Edit .env and add real API keys — see "Environment variables" below
# The app works without keys (dummy mode) if you skip this step

# Build images and start all three services
docker compose up --build

# Open the app
open http://localhost:8000
```

To stop:

```bash
docker compose down
```

To rebuild after changing backend code:

```bash
docker compose up --build
```

Logs from all services in one stream:

```bash
docker compose logs -f
```

Logs from one service only:

```bash
docker compose logs -f worker
docker compose logs -f fastapi
```

---

## Option B — Local Python (for active development)

Run FastAPI with `--reload` so the server restarts on every file save. Run the worker in a second terminal.

### Prerequisites

- Python 3.12 or newer
- Redis running locally

Start Redis if it is not already running:

```bash
# macOS (Homebrew)
brew services start redis

# Linux (systemd)
sudo systemctl start redis

# Verify it is up
redis-cli ping
# should print: PONG
```

### First-time setup

```bash
cd vehicle-tracker/backend

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Create your .env — config.py looks for it in backend/
cp ../.env.example .env
# Edit .env with real keys, or leave as-is for dummy mode
```

### Start FastAPI

```bash
# Must be run from vehicle-tracker/backend/
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000`. The Swagger UI is at `http://localhost:8000/docs`.

### Start the Worker (second terminal)

```bash
cd vehicle-tracker/backend
source .venv/bin/activate

python -m ingestion.worker
```

The worker connects to Redis on startup and immediately runs its first fetch cycle. You will see log output like:

```
2026-05-16 14:32:00 [worker] Worker starting. Interval: 30s
2026-05-16 14:32:00 [worker] Fetching all Waltti feeds...
2026-05-16 14:32:01 [worker] Parsed 87 vehicles
2026-05-16 14:32:01 [worker] Parsed 91 trip delays
2026-05-16 14:32:01 [worker] Parsed 0 alerts
2026-05-16 14:32:01 [worker] Enriched 87 vehicles with delay data
2026-05-16 14:32:01 [worker] Cycle done in 1.2s, sleeping 28.8s
```

---

## Environment variables

All config lives in `.env` at the project root (Docker) or at `backend/.env` (local).  
Every variable has a default — the app runs without any keys set.

### Waltti GTFS-RT (live bus positions)

```env
WALTTI_ID=your-waltti-id
WALTTI_SECRET=your-waltti-secret
WALTTI_BASE_URL=https://data.waltti.fi/jyvaskyla/api/gtfsrealtime/v1.0/feed
```

| Variable | What it is |
|---|---|
| `WALTTI_ID` | HTTP Basic Auth username for the Waltti API |
| `WALTTI_SECRET` | HTTP Basic Auth password for the Waltti API |
| `WALTTI_BASE_URL` | Base URL — do not change unless Waltti moves the feed |

Without `WALTTI_ID` / `WALTTI_SECRET` the worker fetches nothing and the WebSocket falls back to dummy vehicles.  
Register at [data.waltti.fi](https://data.waltti.fi) or contact waltti.fi for credentials.

### Digitransit (geocoding + route planning)

```env
DIGITRANSIT_API_KEY=your-api-key
DIGITRANSIT_BASE_URL=https://api.digitransit.fi
```

| Variable | What it is |
|---|---|
| `DIGITRANSIT_API_KEY` | Sent as `digitransit-subscription-key` header |
| `DIGITRANSIT_BASE_URL` | Base URL — do not change |

Without a key, geocoding and route planning calls will be rejected (HTTP 401).  
Register at [portal-api.digitransit.fi](https://portal-api.digitransit.fi) — free for non-commercial use.

### Redis

```env
REDIS_URL=redis://localhost:6379
```

Docker Compose overrides this automatically to `redis://redis:6379` (the internal service name).  
For local dev the default `redis://localhost:6379` works if Redis is running on the same machine.

### Cache TTLs

These rarely need changing, but they are tunable:

```env
VEHICLE_CACHE_TTL=60      # seconds — how long vehicle positions stay in Redis
PLAN_CACHE_TTL=300        # seconds — how long route plans are cached (5 min)
GEO_CACHE_TTL=86400       # seconds — how long geocode results are cached (24 h)
ALERTS_CACHE_TTL=60       # seconds — how long alert data stays in Redis
```

### Freshness thresholds

Controls when the freshness badge changes from LIVE → DELAYED → STALE:

```env
DELAYED_THRESHOLD=60      # seconds — data older than this becomes DELAYED
STALE_THRESHOLD=120       # seconds — data older than this becomes STALE
```

### Worker interval

```env
WORKER_INTERVAL=30        # seconds between Waltti polls
```

Waltti publishes new vehicle positions roughly every 30 s. Setting this lower wastes API quota; setting it higher makes data go stale.

---

## Dummy mode

The app runs without Redis, without Waltti credentials, and without a Digitransit key.  
In that state:

| Feature | Behaviour |
|---|---|
| WebSocket vehicle stream | Sends 2–3 fake buses with jittered positions every 5 s |
| Geocoding | Returns HTTP 401 from Digitransit (show an error in the UI) |
| Route planning | Returns HTTP 401 from Digitransit |
| Freshness badge | Shows dummy freshness values |

Dummy mode is useful for frontend development when you just need the WebSocket to emit something. The fake vehicles appear on route IDs `"4"` and `"9"`.

To force dummy mode even with Redis running, simply do not start the worker — Redis will have no data and the WebSocket falls back to dummy.

---

## Verifying everything is healthy

### 1. FastAPI is running

```bash
curl http://localhost:8000/docs
# Should return HTML (Swagger UI)
```

Or open `http://localhost:8000/docs` in a browser — the interactive API docs load from there.

### 2. Redis is reachable

```bash
redis-cli ping
# PONG

redis-cli keys "vehicles:*"
# Should list keys like vehicles:4, vehicles:9, vehicles:fetched_at, vehicles:route_ids
# after the worker has completed at least one cycle
```

### 3. Worker has written data

```bash
redis-cli get vehicles:fetched_at
# Should print a Unix timestamp close to the current time

redis-cli get vehicles:route_ids
# Should print a JSON array of route IDs: ["12","16","25","4","9",...]
```

### 4. API endpoints return data

```bash
# Geocode
curl "http://localhost:8000/api/geocode?q=yliopisto"

# Active route IDs
curl http://localhost:8000/api/routes

# Route plan
curl -s -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{"from_lat":62.2416,"from_lon":25.7209,"to_lat":62.2297,"to_lon":25.7473}'
```

### 5. WebSocket emits positions

```bash
# Install wscat if needed: npm i -g wscat
wscat -c ws://localhost:8000/ws/vehicles/4
# Should immediately print a JSON message with vehicles array
```

---

## Running tests

```bash
cd vehicle-tracker/backend
source .venv/bin/activate

pytest tests/ -v
```

All tests pass in dummy mode — no live API keys or Redis required.

```
tests/test_vehicle_service.py    PASSED
tests/test_gtfs_parser.py        PASSED
tests/test_route_planner.py      PASSED
```

Tests marked with `pytest.skip` need real `.pb` protobuf fixtures. To capture them:

1. Set real Waltti credentials in `.env`
2. Run the worker once: `python -m ingestion.worker`
3. In a separate script, call `fetch_vehicle_positions()` and write the raw bytes to `tests/fixtures/vehicle_positions.pb`
4. Remove the `pytest.skip` decorator from the relevant test

---

## Common problems

### Port 8000 already in use

```bash
lsof -i :8000          # find what is using it
kill -9 <PID>
```

Or change the port:

```bash
uvicorn app.main:app --reload --port 8001
```

### Redis connection refused

FastAPI and the Worker both log a warning and continue in dummy mode:

```
WARNING Redis unavailable (Connection refused) — running in dummy mode
```

Fix: start Redis first, then restart FastAPI and the worker.

### Worker exits immediately with `ModuleNotFoundError`

You are probably running `python ingestion/worker.py` instead of `python -m ingestion.worker`.  
Always use the `-m` flag from the `backend/` directory:

```bash
cd vehicle-tracker/backend
python -m ingestion.worker
```

### Waltti returns HTTP 407

Credentials are wrong or missing. Check `WALTTI_ID` and `WALTTI_SECRET` in `.env`. The worker logs the HTTP status on every failed fetch.

### Geocode / plan returns HTTP 401

`DIGITRANSIT_API_KEY` is not set or is invalid. The FastAPI logs show the raw error from Digitransit.

### WebSocket disconnects immediately

Check the FastAPI logs — the most common cause is an unhandled exception in `_real_stream`. If Redis is unavailable the server correctly falls back to `_dummy_stream` instead of closing the socket.

### `reference-frontend not found` on startup

FastAPI looks for `reference-frontend/` one level above `backend/`. If you moved or renamed that directory, update `FRONTEND_DIR` in `config.py`, or mount your own frontend directory.

---

## Project layout (backend)

```
backend/
├── app/
│   ├── main.py              # FastAPI app setup, startup/shutdown hooks, static mount
│   ├── routes.py            # All HTTP endpoints + WebSocket handler
│   └── dependencies.py      # get_redis() dependency (works for HTTP + WebSocket)
├── processing/
│   ├── models.py            # Dataclasses: Vehicle, Route, TripDelay, etc.
│   ├── vehicle_service.py   # enrich_with_delays(), compute_freshness()
│   ├── route_planner.py     # parse_plan_response(), _decode_polyline()
│   ├── geocoder.py          # parse_geocoding_response()
│   └── alert_filter.py      # filter_by_route() for ServiceAlert
├── ingestion/
│   ├── waltti_client.py     # HTTP fetches to Waltti (Basic Auth)
│   ├── gtfs_parser.py       # Protobuf decoding → plain dicts
│   ├── digitransit_client.py # Geocode + route plan + trip shape API calls
│   ├── cache_writer.py      # Writes to Redis, publishes Pub/Sub event
│   └── worker.py            # Polling loop: fetch → parse → enrich → write
├── tests/
│   ├── fixtures/            # .pb binary files for offline parser tests
│   ├── test_vehicle_service.py
│   ├── test_gtfs_parser.py
│   └── test_route_planner.py
├── config.py                # Reads all settings from .env / environment
├── requirements.txt
└── Dockerfile
```
