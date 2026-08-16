---
name: data-analysis
description: Profile and aggregate a bundled sales dataset - group revenue by region, category, channel or month, apply filters, and compute sums, means, medians and ranges. Use for questions about sales figures, trends, or which segments perform best.
compatibility: Standard library only, no network - runs unchanged on the host or inside a sandbox executor
---

# Data Analysis Skill

Answers questions about a bundled sales dataset (`resources/sales.csv`): 96 rows
covering six months, four regions, four product categories and three sales
channels.

This is the reference skill for exercising sandbox executors. Both scripts are
standard library only and read their data from the skill folder, so they do real
work with no network, no third-party packages and no host access — exactly the
shape a sandbox is meant to run.

## When to Use This Skill

- "Which region had the highest revenue?" → `aggregate`
- "What were average units sold per category?" → `aggregate`
- "How many rows are in the dataset and what does revenue look like?" → `profile_dataset`
- "Compare online versus retail sales in the north" → `aggregate` with filters

## Skill Scripts

### profile_dataset

Reports dataset shape, column names, summary statistics for every numeric column
(count, sum, mean, median, stdev, min, max) and distinct-value counts for the
categorical ones.

- `column` (optional): Profile a single numeric column instead of all of them

Exits 2 for an unknown column.

### aggregate

Groups rows and aggregates a numeric column, optionally filtered and truncated.

- `group-by` (required): Column to group by — `month`, `region`, `category`, `channel`
- `metric` (optional): Numeric column to aggregate, default `revenue`
- `agg` (optional): `sum` (default), `mean`, `median`, `min`, `max`, `count`
- `where` (optional, repeatable): Filter as `column=value`, e.g. `region=north`
- `top` (optional): Keep only the highest N groups

Exits 2 for an unknown column or malformed filter, 1 when no rows match.

### Usage Examples

**Revenue by region, highest first:**

- group-by: region

**Top 3 categories by units sold, online only:**

- group-by: category
- metric: units
- agg: sum
- where: channel=online
- top: 3

**Average revenue per month in the west:**

- group-by: month
- agg: mean
- where: region=west

## Data Source

`resources/sales.csv` is generated sample data, included so the skill is
self-contained and deterministic. It is not real sales data.

## Sandbox Behaviour

Both scripts produce byte-identical output on the host and under
`LocalSandboxScriptExecutor` or `OpenSandboxScriptExecutor`, including the
`../resources/sales.csv` read through the skill root and non-zero exit codes for
bad arguments. That equivalence is the point: swapping the executor changes where
the script runs, not what the model sees.
