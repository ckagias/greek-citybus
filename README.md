# Greek City Bus

Unofficial Python client for live bus arrival/departure times across the ~29 Greek cities
running on the [citybus.gr](https://citybus.gr) platform, including Patras, Ioannina, Volos,
Larisa, Chania, Irakleio, and more.

> **Disclaimer:** This is an independent, unofficial project. It is **not affiliated with,
> endorsed by, or supported by** citybus.gr, any Astiko KTEL operator, or any transit authority.
> It works by reading a public webpage and calling an **undocumented internal API** that the
> operator could change, rate-limit, or remove at any time without notice, so expect it to
> occasionally break. Use at your own risk, and don't rely on it for anything safety-critical.

Each city's site (`<city>.citybus.gr/el/stops`) has no public API. It embeds a short-lived auth
token and a numeric agency code in its homepage HTML, then calls a shared internal REST API with
them. This package scrapes both, caches them per city until they expire (or a request 401s), and
gives you a plain typed interface over the trip data.

---

## Install

Not yet published to PyPI, so install from source for now:

```bash
git clone https://github.com/ckagias/greek-citybus.git
cd greek-citybus
python3 -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -e .
```

Once published, this will become `pip install greek-citybus`.

## CLI

Installing the package also puts a `greek-citybus` command on your PATH:

```bash
greek-citybus patra 266
greek-citybus ioannina 100 --routes 3
```

```
[today] 06:08  bus 301   ΘΕΡΜΟΠΥΛΩΝ-ΖΑΡΟΥΧΛΕΙΚΑ
[today] 06:11  bus 201   ΝΕΟΣ ΔΡΟΜΟΣ-ΤΑΡΑΜΠΟΥΡΑ
[today] 06:37  bus 101   ΠΛΑΖ-ΕΓΛΥΚΑΔΑ
...
```

Run `greek-citybus --help` for the full list of options, including `-r/--routes` to filter to
specific bus/line numbers. You'll need to know the numeric stop ID for the stop you want. Look it
up with the `stops` command, optionally filtering by name with `-s/--search`:

```bash
greek-citybus stops patra
greek-citybus stops patra --search "πλατεια"
```

```
290      ΑΓ. ΔΙΟΝΥΣΙΟΣ - ΕΠΙΚΕΝΤΡΟ                lines: 111,502,503,804
745      ΚΕΝΤΡΟ ΒΡΑΧΝΕΪΚΑ                         lines: 503
...
```

## Library usage

```python
from greek_citybus import CityBusClient

client = CityBusClient("patra")
trips = client.get_trips(stop_id="266", routes=["201", "301"])

for trip in trips:
    print(trip.bus_number, trip.route, trip.time)
```

To discover stop IDs programmatically, use `get_stops()`:

```python
stops = client.get_stops()
for stop in stops:
    print(stop.stop_id, stop.name, stop.line_codes)
```

- `city`: the citybus.gr subdomain slug, e.g. `"patra"`, `"ioannina"`, `"volos"`. See
  `greek_citybus.KNOWN_CITIES` for the full list of cities on the platform at time of writing,
  or check [citybus.gr](https://citybus.gr) directly. Any valid slug works even if it's not in that list.
- `stop_id`: numeric stop ID, specific to that city
- `routes`: optional list of line numbers to filter to; omit to get everything. Filtering to a
  line that doesn't serve the given stop returns an empty list, it's not an error.
- After 20:00 local time, `get_trips` also includes tomorrow's schedule (each `BusTrip` has a `day_offset` of `0` or `1`)

### Caching

By default each client's auth token and agency code are cached in-process (`InMemoryCache`), so
they won't survive a restart or be shared across processes. For a long-running service, or a
serverless deployment where each invocation is a fresh process, implement the `Cache` protocol
against Redis, SQLite, or whatever you already have:

```python
from greek_citybus import Cache, CityBusClient

class RedisCache:
    def __init__(self, redis_client):
        self._r = redis_client

    def get(self, key: str) -> str | None:
        return self._r.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._r.set(key, value, ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self._r.delete(key)

client = CityBusClient("patra", cache=RedisCache(my_redis_client))
```

## Web UI / HTTP API

A small FastAPI wrapper is included for browsing trips from a browser or calling over HTTP:

```bash
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -e ".[web]"
uvicorn greek_citybus.web:app --reload
```

Then open `http://127.0.0.1:8000/` for a simple form (pick a city, browse/select a stop from the
dropdown it populates, optionally search/filter by bus number or route text). The same data is
available as JSON:

```bash
curl "http://127.0.0.1:8000/api/trips?city=patra&stop_id=266"
curl "http://127.0.0.1:8000/api/trips?city=patra&stop_id=266&routes=601&routes=609"
curl "http://127.0.0.1:8000/api/stops?city=patra"
curl "http://127.0.0.1:8000/api/stops?city=patra&search=πλατεια"
curl "http://127.0.0.1:8000/api/cities"
```

Interactive API docs are at `http://127.0.0.1:8000/docs`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE). Unofficial client built by reverse-engineering the public citybus.gr platform;
not affiliated with or endorsed by the operator.
