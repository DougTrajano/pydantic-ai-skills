#!/usr/bin/env python3
"""Group, filter and aggregate the bundled sales dataset.

Standard library only, so it runs identically on the host and inside a sandbox.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Lives at the skill root, one level up from scripts/.
DATA_FILE = Path(__file__).resolve().parent.parent / 'resources' / 'sales.csv'

AGGREGATORS = {
    'sum': lambda values: round(sum(values), 2),
    'mean': lambda values: round(statistics.fmean(values), 2),
    'median': lambda values: round(statistics.median(values), 2),
    'min': lambda values: round(min(values), 2),
    'max': lambda values: round(max(values), 2),
    'count': len,
}


def load_rows(path: Path) -> list[dict[str, str]]:
    """Read the CSV into a list of dict rows."""
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def apply_filters(rows: list[dict[str, str]], filters: list[str]) -> list[dict[str, str]]:
    """Keep rows matching every ``column=value`` filter.

    Args:
        rows: Rows to filter.
        filters: Filter expressions such as ``region=north``.

    Returns:
        The matching rows.

    Raises:
        SystemExit: If a filter is malformed or names an unknown column.
    """
    for expression in filters:
        if '=' not in expression:
            print(f'Malformed filter: {expression}. Use column=value.', file=sys.stderr)
            raise SystemExit(2)
        column, value = expression.split('=', 1)
        if rows and column not in rows[0]:
            print(f'Unknown filter column: {column}', file=sys.stderr)
            raise SystemExit(2)
        rows = [row for row in rows if row[column] == value]
    return rows


def main() -> None:
    """Print a grouped aggregation of the dataset as JSON."""
    parser = argparse.ArgumentParser(description='Aggregate the bundled sales dataset.')
    parser.add_argument('--group-by', required=True, help='Column to group by, e.g. region')
    parser.add_argument('--metric', default='revenue', help='Numeric column to aggregate')
    parser.add_argument('--agg', default='sum', choices=sorted(AGGREGATORS), help='Aggregation')
    parser.add_argument('--where', action='append', default=[], help='Filter as column=value; repeatable')
    parser.add_argument('--top', type=int, help='Keep only the highest N groups')
    args = parser.parse_args()

    rows = load_rows(DATA_FILE)
    columns = list(rows[0]) if rows else []
    for column in (args.group_by, args.metric):
        if column not in columns:
            print(f'Unknown column: {column}. Available: {", ".join(columns)}', file=sys.stderr)
            raise SystemExit(2)

    rows = apply_filters(rows, args.where)
    if not rows:
        print('No rows matched the given filters.', file=sys.stderr)
        raise SystemExit(1)

    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        try:
            grouped[row[args.group_by]].append(float(row[args.metric]))
        except (TypeError, ValueError):
            continue

    aggregate = AGGREGATORS[args.agg]
    results = [{'group': key, args.agg: aggregate(values), 'rows': len(values)} for key, values in grouped.items()]
    results.sort(key=lambda item: item[args.agg], reverse=True)
    if args.top:
        results = results[: args.top]

    print(
        json.dumps(
            {
                'group_by': args.group_by,
                'metric': args.metric,
                'agg': args.agg,
                'filters': args.where,
                'matched_rows': len(rows),
                'results': results,
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
