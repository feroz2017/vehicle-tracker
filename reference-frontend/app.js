/* ════════════════════════════════════════════════════════════════════════════
   app.js — Vehicle Tracker reference frontend
   This file will be replaced by the frontend team.
   ════════════════════════════════════════════════════════════════════════════ */

const API_BASE = "";          // same origin — FastAPI serves this file
const DEBOUNCE_MS = 400;      // geocode debounce delay

// ── State ─────────────────────────────────────────────────────────────────────
let map, markers = {}, selectedRoute = null, ws = null;
let fromLocation = null, toLocation = null;

// ── Init map ──────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  map = L.map("map").setView([62.2416, 25.7209], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
  }).addTo(map);
});

// ── Geocoding (debounced) ─────────────────────────────────────────────────────
let debounceTimer = null;

function onInput(field) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => fetchSuggestions(field), DEBOUNCE_MS);
}

async function fetchSuggestions(field) {
  const input = document.getElementById(`input-${field}`);
  const list  = document.getElementById(`suggestions-${field}`);
  const q     = input.value.trim();

  if (q.length < 2) { list.classList.add("hidden"); return; }

  try {
    const res  = await fetch(`${API_BASE}/api/geocode?q=${encodeURIComponent(q)}`);
    const data = await res.json();

    list.innerHTML = "";
    data.forEach(loc => {
      const li = document.createElement("li");
      li.textContent = loc.name;
      li.onclick = () => selectLocation(field, loc);
      list.appendChild(li);
    });

    list.classList.toggle("hidden", data.length === 0);
  } catch (e) {
    console.error("Geocode error:", e);
  }
}

function selectLocation(field, loc) {
  document.getElementById(`input-${field}`).value = loc.name;
  document.getElementById(`suggestions-${field}`).classList.add("hidden");

  if (field === "from") fromLocation = loc;
  else                  toLocation   = loc;
}

// Hide suggestions when clicking outside
document.addEventListener("click", e => {
  if (!e.target.closest(".search-field")) {
    document.querySelectorAll(".suggestions").forEach(el => el.classList.add("hidden"));
  }
});

// Wire up input events
document.getElementById("input-from").addEventListener("input", () => onInput("from"));
document.getElementById("input-to").addEventListener("input",   () => onInput("to"));

// ── Search ────────────────────────────────────────────────────────────────────
async function search() {
  if (!fromLocation || !toLocation) {
    showError("Please select both a starting point and a destination from the suggestions.");
    return;
  }

  showLoading(true);
  hideError();
  document.getElementById("routes-panel").classList.add("hidden");

  try {
    const res  = await fetch(`${API_BASE}/api/plan`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        from_lat:  fromLocation.lat,
        from_lon:  fromLocation.lon,
        to_lat:    toLocation.lat,
        to_lon:    toLocation.lon,
        from_name: fromLocation.name,
        to_name:   toLocation.name,
      }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Planning failed");

    renderRoutes(data.routes);
  } catch (e) {
    showError("Could not find routes. " + e.message);
  } finally {
    showLoading(false);
  }
}

// ── Render route cards ────────────────────────────────────────────────────────
function renderRoutes(routes) {
  const panel = document.getElementById("routes-panel");
  const list  = document.getElementById("routes-list");

  if (!routes || routes.length === 0) {
    showError("No routes found between these locations.");
    return;
  }

  list.innerHTML = "";
  routes.forEach(route => {
    const card = document.createElement("div");
    card.className = "route-card";
    card.dataset.routeId = route.route_id;
    card.innerHTML = `
      <span class="route-badge">${route.route_id}</span>
      <span>${route.route_name}</span>
      <span class="route-time">${route.departure_time} → ${route.arrival_time} (${route.duration_minutes} min)</span>
    `;
    card.onclick = () => selectRoute(route.route_id, card);
    list.appendChild(card);
  });

  panel.classList.remove("hidden");
}

// ── Select route → open WebSocket ────────────────────────────────────────────
function selectRoute(routeId, card) {
  // Update active card styling
  document.querySelectorAll(".route-card").forEach(c => c.classList.remove("active"));
  card.classList.add("active");

  // Close existing WebSocket
  if (ws) { ws.close(); ws = null; }
  clearMarkers();
  document.getElementById("status-bar").classList.remove("hidden");
  selectedRoute = routeId;

  // Fetch alerts for this route
  fetchAlerts(routeId);

  // Open WebSocket
  openWebSocket(routeId);
}

function openWebSocket(routeId) {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const url      = `${protocol}://${location.host}/ws/vehicles/${routeId}`;

  ws = new WebSocket(url);

  ws.onopen = () => console.log(`WebSocket opened for route ${routeId}`);

  ws.onmessage = event => {
    const data = JSON.parse(event.data);
    updateFreshness(data.freshness);
    updateMarkers(data.vehicles);
    updateVehicleCount(data.vehicle_count);
    document.getElementById("empty-state").classList.toggle("hidden", data.vehicle_count > 0);
  };

  ws.onerror = err => {
    console.error("WebSocket error:", err);
    showError("Live connection error. Retrying in 5s…");
  };

  ws.onclose = () => {
    console.log("WebSocket closed, reconnecting in 5s…");
    setTimeout(() => {
      if (selectedRoute === routeId) openWebSocket(routeId);
    }, 5000);
  };
}

// ── Markers ───────────────────────────────────────────────────────────────────
function updateMarkers(vehicles) {
  const seen = new Set();

  vehicles.forEach(v => {
    seen.add(v.id);
    const latlng = [v.lat, v.lon];
    const icon   = buildBusIcon(v.bearing, v.delay_seconds);
    const popup  = buildPopup(v);

    if (markers[v.id]) {
      markers[v.id].setLatLng(latlng).setIcon(icon).setPopupContent(popup);
    } else {
      markers[v.id] = L.marker(latlng, { icon }).bindPopup(popup).addTo(map);
    }
  });

  // Remove markers for buses no longer in feed
  Object.keys(markers).forEach(id => {
    if (!seen.has(id)) { map.removeLayer(markers[id]); delete markers[id]; }
  });
}

function buildBusIcon(bearing, delaySeconds) {
  // Green = on time, yellow = slightly late, red = 3+ min late
  const color = delaySeconds > 180 ? "#ef4444"
              : delaySeconds > 60  ? "#f59e0b"
              : "#22c55e";

  return L.divIcon({
    className: "",
    html: `<div style="
      width:28px;height:28px;border-radius:50%;
      background:${color};border:2px solid white;
      display:flex;align-items:center;justify-content:center;
      color:white;font-size:13px;font-weight:700;
      transform:rotate(${bearing || 0}deg);
      box-shadow:0 2px 6px rgba(0,0,0,.3);">▲</div>`,
    iconSize:   [28, 28],
    iconAnchor: [14, 14],
  });
}

function buildPopup(v) {
  return `
    <div style="min-width:180px;font-size:12px;">
      <strong>Route ${v.route_id} — Bus ${v.label}</strong><br>
      <span style="color:#666">${v.current_stop || "—"} → ${v.next_stop || "—"}</span>
      <hr style="margin:6px 0;border:none;border-top:1px solid #eee;">
      <table style="width:100%">
        <tr><td style="color:#888">Delay</td>  <td><strong>${v.delay_label}</strong></td></tr>
        <tr><td style="color:#888">Speed</td>  <td>${v.speed_kmh ?? "?"} km/h</td></tr>
      </table>
    </div>`;
}

function clearMarkers() {
  Object.values(markers).forEach(m => map.removeLayer(m));
  markers = {};
}

// ── Alerts ────────────────────────────────────────────────────────────────────
async function fetchAlerts(routeId) {
  try {
    const res    = await fetch(`${API_BASE}/api/alerts/${routeId}`);
    const alerts = await res.json();
    const banner = document.getElementById("alert-banner");

    if (alerts.length === 0) {
      banner.classList.add("hidden");
    } else {
      banner.innerHTML = alerts.map(a => `<strong>⚠ ${a.effect}:</strong> ${a.header}`).join(" &nbsp;·&nbsp; ");
      banner.classList.remove("hidden");
    }
  } catch (e) {
    console.error("Alerts error:", e);
  }
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function updateFreshness(freshness) {
  const badge   = document.getElementById("freshness-badge");
  const cls     = { LIVE: "badge-live", DELAYED: "badge-delayed", STALE: "badge-stale" };
  badge.className = `badge ${cls[freshness.level] || ""}`;
  badge.textContent = freshness.label;
}

function updateVehicleCount(count) {
  document.getElementById("vehicle-count").textContent =
    `${count} bus${count !== 1 ? "es" : ""}`;
}

function showLoading(visible) {
  document.getElementById("loading").classList.toggle("hidden", !visible);
  document.getElementById("btn-search").disabled = visible;
}

function showError(msg) {
  const box = document.getElementById("error-box");
  box.textContent = msg;
  box.classList.remove("hidden");
}

function hideError() {
  document.getElementById("error-box").classList.add("hidden");
}
