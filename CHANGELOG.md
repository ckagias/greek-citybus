# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `CityBusClient._fetch_json` swallowed any non-2xx HTTP response (403, 404, 500, a persistent 401 after the retry) by silently returning `[]`. `get_stops()` and `get_trips()` looked identical whether citybus.gr had no data or was actually down, and both the CLI and web UI printed "No stops/trips found" for a real outage. It now raises the new `CityBusAPIError` (a `RuntimeError` subclass carrying `status_code` and `url`), which the CLI and web UI already catch via their existing `except RuntimeError` handlers.
- `get_trips` deduplication used a compound sentinel (`time == "00:00" and bus_number == "??"`) to detect trips with missing API fields. A legitimate midnight departure on a real line could in principle collide with this check, and a trip missing only one of the two fields wasn't caught at all. Missing `tripTime`/`ArrivalTime` or `lineCode`/`LineID` is now detected directly from the raw API response before formatting, so real midnight trips are always kept and any trip actually missing data is always dropped.

## [0.1.0] - 2026-09-06

Initial release: `CityBusClient`, CLI (`greek-citybus`), and optional FastAPI web UI covering live bus arrival/departure times for the ~29 Greek cities on the citybus.gr platform.
