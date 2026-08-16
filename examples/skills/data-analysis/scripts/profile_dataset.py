#!/usr/bin/env python3
"""Profile the bundled sales dataset: shape, columns and numeric statistics.

Standard library only, so it runs identically on the host and inside a sandbox.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

# Lives at the skill root, one level up from scripts/.
DATA_FILE = Path(__file__).resolve().parent.parent / 'resources' / 'sales.csv'


def load_rows(path: Path) -> list[dict[str, str]]:
    """Read the CSV into a list of dict rows."""
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def numeric_values(rows: list[dict[str, str]], column: str) -> list[float]:
    """Return the values of a column that parse as numbers."""
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row[column]))
        except (TypeError, ValueError):
            continue
    return values


def describe(values: list[float]) -> dict[str, float]:
    """Compute summary statistics for a list of numbers."""
    return {
        'count': len(values),
        'sum': round(sum(values), 2),
        'mean': round(statistics.fmean(values), 2),
        'median': round(statistics.median(values), 2),
        'stdev': round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        'min': round(min(values), 2),
        'max': round(max(values), 2),
    }


def main() -> None:
    """Print a profile of the dataset as JSON."""
    parser = argparse.ArgumentParser(description='Profile the bundled sales dataset.')
    parser.add_argument('--column', help='Profile a single numeric column instead of all of them')
    args = parser.parse_args()

    rows = load_rows(DATA_FILE)
    if not rows:
        print('Dataset is empty.', file=sys.stderr)
        raise SystemExit(1)

    columns = list(rows[0])
    if args.column:
        if args.column not in columns:
            print(f'Unknown column: {args.column}. Available: {", ".join(columns)}', file=sys.stderr)
            raise SystemExit(2)
        targets = [args.column]
    else:
        targets = columns

    stats: dict[str, dict[str, float]] = {}
    categorical: dict[str, int] = {}
    for column in targets:
        values = numeric_values(rows, column)
        if len(values) == len(rows) and values:
            stats[column] = describe(values)
        else:
            categorical[column] = len({row[column] for row in rows})

    report = {
        'rows': len(rows),
        'columns': columns,
        'numeric': stats,
        'distinct_values': categorical,
    }
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
