from dataclasses import dataclass


@dataclass(frozen=True)
class BusTrip:
    bus_number: str
    route: str
    time: str
    day_offset: int  # 0 = today, 1 = tomorrow


@dataclass(frozen=True)
class Stop:
    stop_id: str  # numeric stop code, e.g. "266" - what get_trips expects
    name: str
    latitude: float
    longitude: float
    line_codes: list[str]
