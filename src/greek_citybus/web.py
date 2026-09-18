"""FastAPI wrapper around CityBusClient: a small JSON API plus a browsable HTML UI.

Run with:
    uvicorn greek_citybus.web:app --reload

Then open http://127.0.0.1:8000/
"""

import time
from dataclasses import asdict
from functools import lru_cache
from html import escape
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .cities import KNOWN_CITIES
from .client import CityBusClient

RESULT_CACHE_TTL_SECONDS = 60

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Greek City Bus",
    description="Unofficial live bus arrival/departure lookup for citybus.gr cities.",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_result_cache: dict[tuple, tuple[Any, float]] = {}


def _cached(key: tuple, fetch: Callable[[], Any]) -> Any:
    """Cache the result of `fetch()` under `key` for RESULT_CACHE_TTL_SECONDS.

    Bus times only change on the scale of minutes, and this endpoint is polled
    by uptime monitors as well as real users, so a short TTL avoids hammering
    citybus.gr's undocumented upstream API for data that hasn't changed.
    """
    now = time.monotonic()
    cached = _result_cache.get(key)
    if cached is not None:
        value, expires_at = cached
        if now < expires_at:
            return value

    value = fetch()
    _result_cache[key] = (value, now + RESULT_CACHE_TTL_SECONDS)
    return value


class TripOut(BaseModel):
    bus_number: str
    route: str
    time: str
    day_offset: int


class StopOut(BaseModel):
    stop_id: str
    name: str
    latitude: float
    longitude: float
    line_codes: list[str]


@lru_cache(maxsize=64)
def _client_for(city: str) -> CityBusClient:
    return CityBusClient(city)


@app.get("/api/cities", response_model=list[str])
@limiter.limit("30/minute")
def list_cities(request: Request) -> list[str]:
    return KNOWN_CITIES


@app.get("/api/stops", response_model=list[StopOut])
@limiter.limit("30/minute")
def get_stops(
    request: Request,
    city: str = Query(..., description="city slug, e.g. patra, ioannina, volos"),
    search: str = Query("", description="only include stops whose name contains this text (case-insensitive)"),
) -> list[StopOut]:
    client = _client_for(city)
    try:
        stops = _cached(("stops", city), client.get_stops)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if search:
        needle = search.lower()
        stops = [s for s in stops if needle in s.name.lower()]

    return [StopOut(**asdict(s)) for s in sorted(stops, key=lambda s: s.name)]


@app.get("/api/trips", response_model=list[TripOut])
@limiter.limit("30/minute")
def get_trips(
    request: Request,
    city: str = Query(..., description="city slug, e.g. patra, ioannina, volos"),
    stop_id: str = Query(..., description="numeric stop ID from <city>.citybus.gr/el/stops"),
    routes: list[str] | None = Query(
        None, description="only include these bus/line numbers, e.g. ?routes=601&routes=609"
    ),
) -> list[TripOut]:
    client = _client_for(city)
    try:
        trips = _cached(("trips", city, stop_id), lambda: client.get_trips(stop_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if routes is not None:
        trips = [t for t in trips if t.bus_number in routes]
    return [TripOut(**asdict(t)) for t in trips]


@app.get("/", response_class=HTMLResponse)
@limiter.limit("30/minute")
def index(
    request: Request,
    city: str = "",
    stop_id: str = "",
    route_search: str = "",
) -> str:
    city = city.strip()
    stop_id = stop_id.strip()
    route_search = route_search.strip()

    city_options = "".join(
        f'<option value="{escape(c)}"{" selected" if c == city else ""}>{escape(c)}</option>'
        for c in KNOWN_CITIES
    )

    stops_html = ""
    if city:
        try:
            client = _client_for(city)
            stops = sorted(_cached(("stops", city), client.get_stops), key=lambda s: s.name)
        except RuntimeError as e:
            stops_html = f'<p class="error">{escape(str(e))}</p>'
        else:
            options = "".join(
                f'<option value="{escape(s.stop_id)}">{escape(s.name)} (#{escape(s.stop_id)})</option>'
                for s in stops
            )
            stops_html = f"""
            <label style="margin-bottom: 1.5rem;">Browse stops in {escape(city)} ({len(stops)} found)
              <select onchange="document.getElementsByName('stop_id')[0].value=this.value">
                <option value="" disabled selected>select a stop&hellip;</option>
                {options}
              </select>
            </label>
            """

    results_html = ""
    if city and stop_id:
        try:
            client = _client_for(city)
            trips = _cached(("trips", city, stop_id), lambda: client.get_trips(stop_id))
        except ValueError as e:
            results_html = f'<p class="error">{escape(str(e))}</p>'
        except RuntimeError as e:
            results_html = f'<p class="error">{escape(str(e))}</p>'
        else:
            if route_search:
                needle = route_search.lower()
                trips = [
                    t for t in trips
                    if needle in t.bus_number.lower() or needle in t.route.lower()
                ]

            if not trips:
                results_html = "<p>No trips found.</p>"
            else:
                label = {0: "today", 1: "tomorrow"}
                rows = "".join(
                    f"<tr><td>{label[t.day_offset]}</td><td>{escape(t.time)}</td>"
                    f"<td>{escape(t.bus_number)}</td><td>{escape(t.route)}</td></tr>"
                    for t in trips
                )
                results_html = f"""
                <table>
                  <thead><tr><th>Day</th><th>Time</th><th>Bus</th><th>Route</th></tr></thead>
                  <tbody>{rows}</tbody>
                </table>
                """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Greek City Bus</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }}
  form {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
  label {{ display: flex; flex-direction: column; font-size: 0.85rem; gap: 0.25rem; }}
  input, select {{ padding: 0.4rem; font-size: 1rem; }}
  button {{ padding: 0.4rem 1rem; font-size: 1rem; cursor: pointer; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; }}
  .error {{ color: #b00020; }}
</style>
</head>
<body>
<h1>Greek City Bus</h1>
<p>Live arrival/departure times from citybus.gr. Unofficial, not affiliated with citybus.gr.</p>
<form method="get" action="/">
  <label>City
    <select name="city" required onchange="this.form.submit()">
      <option value="" disabled {"selected" if not city else ""}>select a city</option>
      {city_options}
    </select>
  </label>
  <label>Stop ID
    <input type="text" name="stop_id" value="{escape(stop_id)}" placeholder="e.g. 266" required>
  </label>
  <label>Search route/bus (optional)
    <input type="text" name="route_search" value="{escape(route_search)}" placeholder="e.g. 601 or campus">
  </label>
  <button type="submit" style="align-self: flex-end;">Search</button>
</form>
{stops_html}
{results_html}
<p style="margin-top:2rem;font-size:0.85rem;color:#666;">
  JSON API: <code>/api/trips?city=patra&amp;stop_id=266</code> &middot;
  <code>/api/stops?city=patra</code> &middot;
  <code>/api/cities</code> &middot; <a href="/docs">/docs</a>
</p>
</body>
</html>"""
