#!/usr/bin/env python3
"""Fetch current weather from the OpenWeather API.

Deliberately network-dependent. On the host it works with an API key; inside a
sandbox that denies egress it fails, which is the point — running this alongside
``climate_lookup.py`` shows a sandbox executing real work while still refusing
outbound network access.

Set ``OPENWEATHER_API_KEY`` before running. Free keys: https://openweathermap.org/api
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL = 'https://api.openweathermap.org/data/2.5/weather'


def main() -> None:
    """Print current weather for the requested city as JSON."""
    parser = argparse.ArgumentParser(description='Fetch current weather from OpenWeather.')
    parser.add_argument('--city', required=True, help='City name, e.g. London')
    parser.add_argument('--units', choices=['metric', 'imperial'], default='metric')
    parser.add_argument('--timeout', type=int, default=10, help='Request timeout in seconds')
    args = parser.parse_args()

    api_key = os.environ.get('OPENWEATHER_API_KEY')
    if not api_key:
        print('OPENWEATHER_API_KEY is not set.', file=sys.stderr)
        raise SystemExit(2)

    query = urllib.parse.urlencode({'q': args.city, 'units': args.units, 'appid': api_key})
    try:
        with urllib.request.urlopen(f'{API_URL}?{query}', timeout=args.timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        print(f'OpenWeather returned HTTP {exc.code}: {exc.reason}', file=sys.stderr)
        raise SystemExit(1) from exc
    except OSError as exc:
        # A sandbox denying egress lands here, as does an offline host.
        print(f'Could not reach OpenWeather: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc

    print(
        json.dumps(
            {
                'city': payload.get('name', args.city),
                'description': (payload.get('weather') or [{}])[0].get('description'),
                'temp': payload.get('main', {}).get('temp'),
                'feels_like': payload.get('main', {}).get('feels_like'),
                'humidity': payload.get('main', {}).get('humidity'),
                'units': '°C' if args.units == 'metric' else '°F',
                'source': 'OpenWeather API',
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
