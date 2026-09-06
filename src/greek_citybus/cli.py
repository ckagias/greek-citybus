import argparse
import sys
import textwrap

from .client import CityBusClient
from .cities import KNOWN_CITIES


def _known_cities_block() -> str:
    wrapped = textwrap.fill(", ".join(KNOWN_CITIES), width=78)
    return f"known cities:\n{textwrap.indent(wrapped, '  ')}"


def _run_trips(args: argparse.Namespace) -> None:
    client = CityBusClient(args.city)
    try:
        trips = client.get_trips(args.stop_id, routes=args.routes)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not trips:
        msg = f"No trips found for {args.city}, stop {args.stop_id}."
        if args.routes:
            msg += f" (routes filter {args.routes} may not serve this stop; try without --routes to see all lines.)"
        print(msg)
        return

    label = {0: "today", 1: "tomorrow"}
    try:
        for trip in trips:
            print(f"[{label[trip.day_offset]}] {trip.time}  bus {trip.bus_number:<5} {trip.route}")
    except BrokenPipeError:
        sys.stderr.close()


def _run_stops(args: argparse.Namespace) -> None:
    client = CityBusClient(args.city)
    try:
        stops = client.get_stops()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.search:
        needle = args.search.lower()
        stops = [s for s in stops if needle in s.name.lower()]

    if not stops:
        print(f"No stops found for {args.city}.")
        return

    stops = sorted(stops, key=lambda s: s.name)
    try:
        for stop in stops:
            lines = ",".join(stop.line_codes)
            print(f"{stop.stop_id:<8} {stop.name:<40} lines: {lines}")
    except BrokenPipeError:
        sys.stderr.close()


def _build_trips_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greek-citybus",
        description="Look up live bus arrival/departure times for a citybus.gr stop.",
        epilog=_known_cities_block(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("city", help="city slug, e.g. patra, ioannina, volos (see known cities below)")
    parser.add_argument("stop_id", help="numeric stop ID from <city>.citybus.gr/el/stops (see 'greek-citybus stops')")
    parser.add_argument("-r", "--routes", nargs="+", metavar="LINE", help="only show these bus/line numbers, e.g. -r 601 609")
    return parser


def _build_stops_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greek-citybus stops",
        description="List every stop ID available in a citybus.gr city.",
        epilog=_known_cities_block(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("city", help="city slug, e.g. patra, ioannina, volos (see known cities below)")
    parser.add_argument("-s", "--search", metavar="TEXT", help="only show stops whose name contains this text (case-insensitive)")
    return parser


def main() -> None:
    # `greek-citybus stops <city>` lists stops; anything else is the original
    # `greek-citybus <city> <stop_id>` trips lookup, kept for backwards compatibility.
    argv = sys.argv[1:]
    if argv and argv[0] == "stops":
        args = _build_stops_parser().parse_args(argv[1:])
        _run_stops(args)
        return

    args = _build_trips_parser().parse_args(argv)
    _run_trips(args)


if __name__ == "__main__":
    main()
