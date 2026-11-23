"""Summarise the raw events table so the agent starts from facts, not guesses.

Why cache to JSON: the demo must run offline and repeatable, and every
`map` run would otherwise re-scan BigQuery for the same answer.
"""

import json
from pathlib import Path
from typing import Any

from schema_mapper.bigquery.client import BigQueryClient
from schema_mapper.config import PROFILE_END, PROFILE_START, SOURCE_TABLE

CACHE_PATH = Path(__file__).resolve().parents[3] / "cache" / "flood_it_profile.json"

# Firebase stores each param value in one of four typed columns; exactly one is set.
PROFILE_SQL = f"""
WITH events AS (
  SELECT event_name, user_pseudo_id, event_params
  FROM `{SOURCE_TABLE}`
  WHERE _TABLE_SUFFIX BETWEEN '{PROFILE_START}' AND '{PROFILE_END}'
),
totals AS (
  SELECT event_name, COUNT(*) AS row_count, COUNT(DISTINCT user_pseudo_id) AS user_count
  FROM events
  GROUP BY event_name
),
param_values AS (
  SELECT
    e.event_name,
    p.key,
    CASE
      WHEN p.value.string_value IS NOT NULL THEN 'string'
      WHEN p.value.int_value IS NOT NULL THEN 'int'
      WHEN p.value.double_value IS NOT NULL OR p.value.float_value IS NOT NULL THEN 'double'
      ELSE 'null'
    END AS value_type,
    COALESCE(
      p.value.string_value,
      CAST(p.value.int_value AS STRING),
      CAST(p.value.double_value AS STRING),
      CAST(p.value.float_value AS STRING)
    ) AS value
  FROM events AS e, UNNEST(e.event_params) AS p
),
param_stats AS (
  SELECT
    event_name, key, value_type,
    COUNT(*) AS occurrences,
    COUNT(DISTINCT value) AS distinct_values,
    ARRAY_AGG(DISTINCT value IGNORE NULLS ORDER BY value LIMIT 5) AS samples
  FROM param_values
  GROUP BY event_name, key, value_type
)
SELECT
  t.event_name, t.row_count, t.user_count,
  ARRAY_AGG(
    STRUCT(s.key, s.value_type, s.occurrences, s.distinct_values, s.samples)
    ORDER BY s.key
  ) AS params
FROM totals AS t
LEFT JOIN param_stats AS s USING (event_name)
GROUP BY t.event_name, t.row_count, t.user_count
ORDER BY t.row_count DESC
"""


def build_profile(bq: BigQueryClient) -> dict[str, Any]:
    rows = bq.run_select(PROFILE_SQL)
    events = {}
    for row in rows:
        # LEFT JOIN yields one all-null struct for events without params.
        params = [dict(p) for p in row["params"] if p["key"] is not None]
        events[row["event_name"]] = {
            "row_count": row["row_count"],
            "user_count": row["user_count"],
            "params": params,
        }
    return {
        "source_table": SOURCE_TABLE,
        "description": "Flood-It! mobile puzzle game, Firebase export",
        "date_range": [PROFILE_START, PROFILE_END],
        "events": events,
    }


def save_profile(profile: dict[str, Any], path: Path = CACHE_PATH) -> None:
    path.write_text(json.dumps(profile, indent=2))


def load_profile(path: Path = CACHE_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run `schema-mapper profile` first")
    return json.loads(path.read_text())
