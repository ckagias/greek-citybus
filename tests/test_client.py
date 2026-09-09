from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import responses

from greek_citybus import CityBusAPIError, CityBusClient
from greek_citybus.client import API_HOST


HOMEPAGE_URL = "https://patra.citybus.gr/el/stops"
HOMEPAGE_HTML = "<html><script>const agencyCode = 112; const token = 'abc123';</script></html>"


def _today_index() -> int:
    now = datetime.now(ZoneInfo("Europe/Athens"))
    return now.isoweekday() % 7


def _fetches_tomorrow() -> bool:
    return datetime.now(ZoneInfo("Europe/Athens")).hour >= 20


def _trips_url(day_id: int) -> str:
    return f"{API_HOST}/112/trips/stop/1234/day/{day_id}"


@responses.activate
def test_get_trips_filters_and_dedupes():
    today_url = _trips_url(_today_index())
    responses.add(responses.GET, HOMEPAGE_URL, body=HOMEPAGE_HTML, status=200)
    responses.add(
        responses.GET,
        today_url,
        json=[
            {"tripTime": "08:15:00", "lineCode": "601", "routeName": "Campus - Center"},
            {"tripTime": "08:15:00", "lineCode": "601", "routeName": "Campus - Center"},
            {"tripTime": "08:20:00", "lineCode": "999", "routeName": "Other"},
        ],
        status=200,
    )
    if _fetches_tomorrow():
        responses.add(responses.GET, _trips_url((_today_index() + 1) % 7), json=[], status=200)

    client = CityBusClient("patra")
    trips = client.get_trips("1234", routes=["601", "609"])

    assert len(trips) == 1
    assert trips[0].bus_number == "601"
    assert trips[0].time == "08:15"


@responses.activate
def test_token_refetched_on_401():
    today_url = _trips_url(_today_index())
    responses.add(responses.GET, HOMEPAGE_URL, body=HOMEPAGE_HTML, status=200)
    responses.add(responses.GET, today_url, json={}, status=401)
    responses.add(responses.GET, HOMEPAGE_URL, body=HOMEPAGE_HTML, status=200)
    responses.add(responses.GET, today_url, json=[], status=200)
    if _fetches_tomorrow():
        responses.add(responses.GET, _trips_url((_today_index() + 1) % 7), json=[], status=200)

    client = CityBusClient("patra")
    trips = client.get_trips("1234")

    assert trips == []


@responses.activate
def test_server_error_raises_instead_of_empty_list():
    today_url = _trips_url(_today_index())
    responses.add(responses.GET, HOMEPAGE_URL, body=HOMEPAGE_HTML, status=200)
    responses.add(responses.GET, today_url, json={"error": "boom"}, status=500)

    client = CityBusClient("patra")
    with pytest.raises(CityBusAPIError) as exc_info:
        client.get_trips("1234")

    assert exc_info.value.status_code == 500


@responses.activate
def test_persistent_401_raises_after_retry():
    today_url = _trips_url(_today_index())
    responses.add(responses.GET, HOMEPAGE_URL, body=HOMEPAGE_HTML, status=200)
    responses.add(responses.GET, today_url, json={}, status=401)
    responses.add(responses.GET, HOMEPAGE_URL, body=HOMEPAGE_HTML, status=200)
    responses.add(responses.GET, today_url, json={}, status=401)

    client = CityBusClient("patra")
    with pytest.raises(CityBusAPIError) as exc_info:
        client.get_trips("1234")

    assert exc_info.value.status_code == 401


@responses.activate
def test_trip_with_missing_time_or_line_is_skipped_not_fabricated():
    today_url = _trips_url(_today_index())
    responses.add(responses.GET, HOMEPAGE_URL, body=HOMEPAGE_HTML, status=200)
    responses.add(
        responses.GET,
        today_url,
        json=[
            # legitimate midnight departure - must be kept
            {"tripTime": "00:00:00", "lineCode": "101", "routeName": "Night Line"},
            # missing time entirely - must be dropped, not fabricated as 00:00
            {"lineCode": "202", "routeName": "Broken"},
            # missing line entirely - must be dropped, not fabricated as ??
            {"tripTime": "07:30:00", "routeName": "Broken"},
        ],
        status=200,
    )
    if _fetches_tomorrow():
        responses.add(responses.GET, _trips_url((_today_index() + 1) % 7), json=[], status=200)

    client = CityBusClient("patra")
    trips = client.get_trips("1234")

    assert len(trips) == 1
    assert trips[0].bus_number == "101"
    assert trips[0].time == "00:00"


def test_invalid_stop_id_rejected():
    client = CityBusClient("patra")
    try:
        client.get_trips("not-a-number")
        assert False, "expected ValueError"
    except ValueError:
        pass


@responses.activate
def test_get_stops():
    responses.add(responses.GET, HOMEPAGE_URL, body=HOMEPAGE_HTML, status=200)
    responses.add(
        responses.GET,
        f"{API_HOST}/112/stops",
        json=[
            {
                "id": 12401368,
                "code": "263",
                "name": "12ου ΣΥΝΤΑΓΜΑΤΟΣ",
                "latitude": 38.239,
                "longitude": 21.747,
                "lineCodes": ["101", "102"],
            }
        ],
        status=200,
    )

    client = CityBusClient("patra")
    stops = client.get_stops()

    assert len(stops) == 1
    assert stops[0].stop_id == "263"
    assert stops[0].name == "12ου ΣΥΝΤΑΓΜΑΤΟΣ"
    assert stops[0].line_codes == ["101", "102"]


@responses.activate
def test_different_cities_use_different_agency_codes():
    responses.add(
        responses.GET,
        "https://ioannina.citybus.gr/el/stops",
        body="<html><script>const agencyCode = 106; const token = 'ioatoken';</script></html>",
        status=200,
    )
    responses.add(
        responses.GET,
        f"{API_HOST}/106/trips/stop/5678/day/{_today_index()}",
        json=[{"tripTime": "09:00:00", "lineCode": "3", "routeName": "Center"}],
        status=200,
    )
    if _fetches_tomorrow():
        responses.add(
            responses.GET,
            f"{API_HOST}/106/trips/stop/5678/day/{(_today_index() + 1) % 7}",
            json=[],
            status=200,
        )

    client = CityBusClient("ioannina")
    trips = client.get_trips("5678")

    assert len(trips) == 1
    assert trips[0].bus_number == "3"
