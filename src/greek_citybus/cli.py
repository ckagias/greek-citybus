import argparse
import sys
import textwrap

from .client import CityBusClient
from .cities import KNOWN_CITIES


def _known_cities_block() -> str:
    wrapped = textwrap.fill(", ".join(KNOWN_CITIES), width=78)
    return f"known cities:\n{textwrap.indent(wrapped, '  ')}"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="greek-citybus",
        description="Look up live bus arrival/departure times for a citybus.gr stop.",
        epilog=_known_cities_block(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("city", help="city slug, e.g. patra, ioannina, volos (see known cities below)")
    parser.add_argument("stop_id", help="numeric stop ID from <city>.citybus.gr/el/stops")
    parser.add_argument("-r", "--routes", nargs="+", metavar="LINE", help="only show these bus/line numbers, e.g. -r 601 609")
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
