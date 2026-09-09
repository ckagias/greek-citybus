# Contributing to Greek City Bus

### Help improve an unofficial Python client for live bus times on the citybus.gr platform

[Getting Started](#getting-started) • [Project Structure](#project-structure) • [Guidelines](#guidelines) • [Testing](#testing) • [Submitting a PR](#submitting-a-pr)

---

## Getting Started

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/ckagias/greek-citybus.git
   cd greek-citybus
   ```
2. **Create a virtualenv and install in editable mode with dev + web extras**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # on Windows: .venv\Scripts\activate
   pip install -e ".[dev,web]"
   ```
3. **Run the test suite** to confirm your environment is set up correctly
   ```bash
   pytest
   ```
4. **Create a branch** off `main` for your change:
   ```bash
   git checkout -b fix/my-fix
   ```

---

## Project Structure

```
greek-citybus/
├── src/greek_citybus/
│   ├── client.py      # CityBusClient: auth scraping, caching, stops/trips fetching
│   ├── models.py       # Stop, BusTrip dataclasses
│   ├── cache.py         # Cache protocol + InMemoryCache default
│   ├── cities.py         # KNOWN_CITIES list
│   ├── cli.py              # `greek-citybus` console entry point
│   └── web.py                # Optional FastAPI wrapper (JSON API + HTML UI)
└── tests/               # pytest, mirroring the source tree (see Testing)
```

---

## Guidelines

### General

- Keep `client.py` free of CLI- or web-specific concerns. It should work the same whether called from `cli.py`, `web.py`, or a user's own script.
- Never swallow a real error into an empty list or `None`. Distinguish "no data available" from "the request failed" by raising, not by returning an empty result (see `CityBusAPIError`).
- Add type hints on every new function signature; the codebase is fully typed.

### Commits

- Use short, imperative commit messages: `fix: raise instead of swallowing non-2xx responses`.
- One logical change per commit.

### What not to add

- Anything that depends on citybus.gr internals beyond what's already reverse-engineered (the token/agencyCode scrape and the trips/stops endpoints). Keep the surface area small and easy to re-verify when the site changes.
- Dependencies that aren't genuinely needed. `requests` for the core client, `fastapi`/`uvicorn` for the optional web extra — check before adding another.
- Config files or secrets.

---

## Testing

Run `pytest` to run the suite. Tests live under `tests/`, mirroring the source tree (`tests/test_client.py` covers `src/greek_citybus/client.py`). Network calls are mocked with the `responses` library, never hit citybus.gr in tests.

If you touch `client.py`, add or update a test in `tests/test_client.py` covering the new behavior, including the error path.

---

## Submitting a PR

1. Run `pytest` and make sure it passes.
2. Test the happy path **and** at least one error/edge case (a non-2xx response, missing API fields, an invalid stop ID).
3. Open a pull request against `main` with a clear title and a short description of what changed and why.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
