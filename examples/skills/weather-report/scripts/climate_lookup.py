#!/usr/bin/env python3
"""Look up typical weather for a city and month from bundled climate normals.

Standard library only, no network: this is the script to run when testing a
sandbox executor, since it works identically on the host and inside a sandbox.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Lives at the skill root, one level up from scripts/, so this only resolves when
# the whole skill folder is available — locally and in a correctly staged sandbox.
DATA_FILE = Path(__file__).resolve().parent.parent / 'resources' / 'climate_normals.json'


def to_fahrenheit(celsius: float) -> float:
    """Convert a Celsius temperature to Fahrenheit."""
    return round(celsius * 9 / 5 + 32, 1)


def main() -> None:
    """Print climate normals for the requested city and month as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--city', required=True, help='City name, e.g. london')
    parser.add_argument('--month', help='Month name or number; omit for the full year')
    parser.add_argument('--units', choices=['c', 'f'], default='c', help='Temperature units')
    args = parser.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    months: list[str] = data['months']
    city_key = args.city.strip().lower()

    city = data['cities'].get(city_key)
    if city is None:
        print(f'Unknown city: {args.city}. Known: {", ".join(sorted(data["cities"]))}', file=sys.stderr)
        raise SystemExit(2)

    indexes = range(12)
    if args.month:
        month_key = args.month.strip().lower()[:3]
        if month_key.isdigit():
            index = int(args.month) - 1
        elif month_key in months:
            index = months.index(month_key)
        else:
            print(f'Unknown month: {args.month}', file=sys.stderr)
            raise SystemExit(2)
        if not 0 <= index < 12:
            print(f'Month out of range: {args.month}', file=sys.stderr)
            raise SystemExit(2)
        indexes = range(index, index + 1)

    convert = to_fahrenheit if args.units == 'f' else (lambda value: value)
    report = {
        'city': city_key,
        'country': city['country'],
        'units': '°F' if args.units == 'f' else '°C',
        'source': 'bundled climate normals (approximate, demo data)',
        'months': [
            {
                'month': months[i],
                'avg_high': convert(city['high_c'][i]),
                'avg_low': convert(city['low_c'][i]),
                'precip_mm': city['precip_mm'][i],
            }
            for i in indexes
        ],
    }
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
