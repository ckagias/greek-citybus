import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .cache import Cache, InMemoryCache
from .models import BusTrip, Stop

API_HOST = "https://rest.citybus.gr/api/v1/el"
DEFAULT_TIMEOUT_SECONDS = 8

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Each city's homepage embeds its own short-lived auth token and numeric
# agencyCode in the same inline <script> block, e.g.:
#   const agencyCode = 112;
#   const token = 'eyJhbGciOi...';
TOKEN_PATTERN = re.compile(r"(?:const|var|let)\s+token\s*=\s*'([^']+)'")
AGENCY_CODE_PATTERN = re.compile(r"(?:const|var|let)\s+agencyCode\s*=\s*(\d+)")

TOKEN_TTL_SECONDS = 3600


class CityBusAPIError(RuntimeError):
    """Raised when citybus.gr responds with an unexpected non-2xx status."""

    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"citybus.gr returned HTTP {status_code} for {url}")


class CityBusClient:
    """Client for the (unofficial, reverse-engineered) citybus.gr platform,
    which powers live bus arrival/departure boards for ~29 Greek cities
    (e.g. patra, ioannina, volos, larisa, chania). See README for the full list.

    Each city's site (`<city>.citybus.gr/el/stops`) embeds a short-lived auth
    token and a numeric agency code in its homepage HTML rather than exposing
    a public API key, so this client scrapes both and caches them per city
    until they expire or a request comes back 401.
    """

    def __init__(self, city: str, cache: Cache | None = None, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        self.city = city
        self.homepage_url = f"https://{city}.citybus.gr/el/stops"
        self._cache = cache or InMemoryCache()
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    @property
    def _token_cache_key(self) -> str:
        return f"citybus_token:{self.city}"

    @property
    def _agency_cache_key(self) -> str:
        return f"citybus_agency:{self.city}"

    def _scrape_auth(self) -> tuple[str, str] | None:
        res = self._session.get(
            self.homepage_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
            },
            timeout=self._timeout,
        )
        res.raise_for_status()

        token_match = TOKEN_PATTERN.search(res.text)
        agency_match = AGENCY_CODE_PATTERN.search(res.text)
        if not token_match or not agency_match:
            return None

        token, agency_code = token_match.group(1), agency_match.group(1)
        self._cache.set(self._token_cache_key, token, TOKEN_TTL_SECONDS)
        self._cache.set(self._agency_cache_key, agency_code, TOKEN_TTL_SECONDS)
        return token, agency_code

    def _get_auth(self) -> tuple[str, str] | None:
        token = self._cache.get(self._token_cache_key)
        agency_code = self._cache.get(self._agency_cache_key)
        if token and agency_code:
            return token, agency_code
        return self._scrape_auth()

    def _agency_code(self) -> str:
        auth = self._get_auth()
        if not auth:
            raise RuntimeError(f"Could not obtain bus API credentials for city '{self.city}'")
        _, agency_code = auth
        return agency_code

    def _fetch_json(self, url: str, retried: bool = False) -> Any:
        auth = self._get_auth()
        if not auth:
            raise RuntimeError(f"Could not obtain bus API credentials for city '{self.city}'")
        token, _ = auth

        res = self._session.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Referer": self.homepage_url,
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )

        if res.status_code == 401 and not retried:
            self._cache.delete(self._token_cache_key)
            self._cache.delete(self._agency_cache_key)
            return self._fetch_json(url, retried=True)

        if not res.ok:
            raise CityBusAPIError(res.status_code, url)

        return res.json()

    def _fetch_trips(self, stop_id: str, day_id: int) -> list[dict[str, Any]]:
        agency_code = self._agency_code()
        return self._fetch_json(f"{API_HOST}/{agency_code}/trips/stop/{stop_id}/day/{day_id}")

    def get_stops(self) -> list[Stop]:
        agency_code = self._agency_code()
        raw_stops = self._fetch_json(f"{API_HOST}/{agency_code}/stops")

        return [
            Stop(
                stop_id=str(raw["code"]),
                name=raw.get("name", ""),
                latitude=raw.get("latitude", 0.0),
                longitude=raw.get("longitude", 0.0),
                line_codes=raw.get("lineCodes") or [],
            )
            for raw in raw_stops
        ]

    def get_trips(self, stop_id: str, routes: list[str] | None = None) -> list[BusTrip]:
        """Fetch today's (and, after 20:00 local time, tomorrow's) trips for a stop.

        `routes`, if given, filters to only those bus/line numbers (e.g. ["601", "609"]).
        """
        if not stop_id.isdigit():
            raise ValueError("stop_id must be numeric")

        now = datetime.now(ZoneInfo("Europe/Athens"))
        today_index = now.isoweekday() % 7  # citybus.gr: 0=Sunday, matching Python's isoweekday()%7
        tomorrow_index = (today_index + 1) % 7

        today_trips = self._fetch_trips(stop_id, today_index)
        tomorrow_trips = (
            self._fetch_trips(stop_id, tomorrow_index) if now.hour >= 20 else []
        )

        def to_bus_trips(raw_trips: list[dict[str, Any]], day_offset: int) -> list[BusTrip]:
            result = []
            for trip in raw_trips:
                raw_time = trip.get("tripTime") or trip.get("ArrivalTime")
                raw_line = trip.get("lineCode") or trip.get("LineID")
                if raw_time is None or raw_line is None:
                    # Missing required fields from the API - skip rather than
                    # fabricate a "00:00"/"??" placeholder that could collide
                    # with a legitimate midnight departure.
                    continue
                result.append(
                    BusTrip(
                        bus_number=str(raw_line),
                        route=trip.get("routeName") or trip.get("RouteDescr") or "Διαδρομή",
                        time=str(raw_time)[:5],
                        day_offset=day_offset,
                    )
                )
            return result

        combined = to_bus_trips(today_trips, 0) + to_bus_trips(tomorrow_trips, 1)

        seen: set[tuple[int, str, str]] = set()
        unique: list[BusTrip] = []
        for trip in combined:
            key = (trip.day_offset, trip.bus_number, trip.time)
            if key in seen:
                continue
            seen.add(key)
            if routes is not None and trip.bus_number not in routes:
                continue
            unique.append(trip)

        return unique
