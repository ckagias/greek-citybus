from dataclasses import dataclass


@dataclass(frozen=True)
class BusTrip:
    bus_number: str
    route: str
    time: str
    day_offset: int  # 0 = today, 1 = tomorrow
