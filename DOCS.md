# DOCS

Technical reference for how this project works and why it's built this way. For install/usage,
see [README.md](README.md).

---

## Architecture overview

```
                    ┌─────────────────────┐
                    │  <city>.citybus.gr   │  (undocumented, no public API)
                    │  /el/stops (HTML)     │
                    └──────────┬───────────┘
                               │ scrape token + agencyCode
                               ▼
                    ┌─────────────────────┐
                    │   CityBusClient      │  src/greek_citybus/client.py
                    │  (auth + fetch +     │
                    │   normalize + cache) │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┼─────────────┐
                 ▼                           ▼
        ┌───────────────┐           ┌───────────────────┐
        │  CLI (cli.py)  │           │  web.py (FastAPI)  │
        │  greek-citybus │           │  JSON API + HTML UI │
        └───────────────┘           └───────────────────┘
```

There is no first-party API for citybus.gr. Each city's site
(`https://<city>.citybus.gr/el/stops`) server-renders a page whose inline `<script>` embeds:

- a short-lived bearer `token`
- a numeric `agencyCode` identifying that city on the shared backend

Both are extracted with regex (`TOKEN_PATTERN`, `AGENCY_CODE_PATTERN` in `client.py`) and then
used to call the real backend at `https://rest.citybus.gr/api/v1/el/<agencyCode>/...`. That
backend is shared across all ~29 cities on the platform, only the `agencyCode` differs.

This is inherently fragile. citybus.gr can change the HTML structure, the token format, or the
backend contract at any time without notice, since none of it is a published or versioned API.
See the root README's disclaimer.

## `src/greek_citybus/`

| File | Responsibility |
|---|---|
| `client.py` | `CityBusClient`. Scrapes auth, calls the upstream REST API, normalizes responses into typed models, retries once on 401 |
| `models.py` | Frozen dataclasses `BusTrip` and `Stop`, the public data shapes returned to callers |
| `cache.py` | `Cache` protocol plus `InMemoryCache` default implementation, used for auth token/agency-code caching |
| `cities.py` | `KNOWN_CITIES`, a convenience list of known city slugs. Not enforced, any valid slug works |
| `cli.py` | `greek-citybus` console script (argparse-based) |
| `web.py` | Optional FastAPI wrapper: JSON API plus minimal HTML UI |

### Auth flow (`client.py`)

1. `_get_auth()` checks the cache for a token and agency code for this city.
2. On a cache miss, `_scrape_auth()` GETs the city's `/el/stops` homepage HTML and regex-extracts
   both values, then caches them with a 1-hour TTL (`TOKEN_TTL_SECONDS`). That TTL is a guess at
   the token's real lifetime, since it's not documented anywhere.
3. `_fetch_json()` attaches the token as a `Bearer` header. On a `401`, the cached auth is evicted
   and the scrape-and-fetch is retried exactly once. The `retried` flag guards against an
   infinite retry loop if the upstream is genuinely down.

### Day-offset trip logic (`client.py: get_trips`)

citybus.gr's backend indexes weekdays `0=Sunday..6=Saturday`, which matches Python's
`datetime.isoweekday() % 7`. `get_trips`:

- Always fetches today's schedule.
- After 20:00 Europe/Athens local time, also fetches tomorrow's schedule and merges it in, since
  riders checking late in the evening usually care about the next morning's first buses. Each
  `BusTrip.day_offset` (`0`/`1`) tells the caller which day a trip belongs to.
- Deduplicates on `(day_offset, bus_number, time)`, since the upstream API has been observed to
  occasionally return the same trip twice.
- Drops rows missing a time or line number rather than filling in a placeholder. A fabricated
  `"00:00"` or `"??"` could collide with a legitimate midnight departure or otherwise mislead a
  caller.

### Caching (`cache.py`)

`CityBusClient` depends on the `Cache` protocol (`get`/`set`/`delete`), not a concrete
implementation. `InMemoryCache` is the default and is process-local. That's fine for a
long-lived CLI invocation or a single dev server, but it means each process or worker re-scrapes
its own auth on first use, and nothing is shared across horizontally-scaled instances. Swap in
your own implementation (Redis, SQLite, etc.) for multi-process deployments. See the README's
"Caching" section for an example.

Note that this is auth-token caching inside the client library, and it's a separate cache from
the result caching in `web.py` described below.

## `web.py`, the HTTP API layer

A thin FastAPI wrapper around `CityBusClient`, meant to be optional (installed via the `web`
extra) rather than a required part of the library.

### Routes

| Route | Purpose |
|---|---|
| `GET /` | HTML form UI: pick a city, browse/select a stop, optionally filter by route text |
| `GET /api/cities` | Returns `KNOWN_CITIES` |
| `GET /api/stops?city=&search=` | Stops for a city, optionally name-filtered (case-insensitive substring) |
| `GET /api/trips?city=&stop_id=&routes=` | Trips for a stop, optionally filtered to specific line numbers |
| `GET /docs` | Auto-generated interactive OpenAPI/Swagger docs (built into FastAPI) |

The FastAPI `version=` passed to the `FastAPI(...)` constructor is read from installed package
metadata (`importlib.metadata.version("greek-citybus")`) rather than hardcoded, so `/docs` and
the OpenAPI schema always reflect the actually-installed version instead of silently defaulting
to FastAPI's own `0.1.0` placeholder.

### Result caching

`_cached()` is a simple process-local TTL cache (`RESULT_CACHE_TTL_SECONDS = 60`), keyed by
`(endpoint, city[, stop_id])`. This exists purely to avoid hammering citybus.gr's undocumented
upstream on every request. A burst of requests for the same stop within 60 seconds only hits
upstream once. It's a separate cache from the auth-token cache in `cache.py`, with a different
purpose, and it's also process-local.

### Rate limiting

Each endpoint is limited to 30 requests/minute via `slowapi`, keyed by client IP
(`_client_ip()`). Render sits behind a proxy, so `request.client.host` would just be Render's
internal address. `_client_ip()` instead prefers Cloudflare's `True-Client-IP` header, which
can't be spoofed by the client, falling back to `X-Forwarded-For`, then finally the raw socket
address.

### Deployment

The live instance at [greek-citybus.onrender.com](https://greek-citybus.onrender.com) runs on
Render's free tier, which sleeps after inactivity. Expect up to ~60s cold-start latency on the
first request after idle.

## Release process

- **Package version** lives in exactly one place, `[project] version` in `pyproject.toml`. Bump
  it there and nothing else needs to change. The web app's reported version is derived from it
  at runtime, not duplicated.
- **Publishing to PyPI** is automated via `.github/workflows/python-publish.yml`, triggered on
  `release: published`. It uses
  [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC), with no stored
  API token or secret. To cut a release: bump the version, commit, then draft and publish a
  GitHub Release tagged `vX.Y.Z`. Re-using an already-published version number will fail. PyPI
  permanently blocks re-uploading a deleted or existing version string.
- Trusted publishing must be registered once on PyPI's project settings (owner `ckagias`, repo
  `greek-citybus`, workflow filename `python-publish.yml`, environment `pypi`) before the
  workflow can authenticate.
- The README's PyPI badge (shields.io) reflects PyPI's live state on its own, so this repo never
  needs to update it manually. It can lag by minutes to hours due to caching at both shields.io
  and GitHub's image proxy (camo). That's normal and not a sign anything failed.

## Known fragility and operator risk

Since this depends entirely on reverse-engineered, undocumented behavior of a third-party site,
the following changes upstream could break this package with no warning:

- HTML structure of `/el/stops` changing (breaks token/agencyCode regex extraction)
- Token format or auth scheme changing
- `rest.citybus.gr` REST contract changing (field names, status codes, pagination)
- Upstream rate-limiting or blocking scraper-like traffic, mitigated somewhat by result caching
  and a realistic `User-Agent`, but not guaranteed

There is no SLA or changelog from the operator to watch for this. Breakage will surface as
failing tests, user bug reports, or `CityBusAPIError`/`RuntimeError` in production.
