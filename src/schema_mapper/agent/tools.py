"""The three tools the agent may call.

Why the agent never writes SQL: tools take only names, which are checked
against the profile before any query is built. That closes off SQL
injection, and the query still goes through the read-only gateway.
"""

import json
from typing import Any, Callable

from schema_mapper.bigquery.client import BigQueryClient
from schema_mapper.config import PROFILE_END, PROFILE_START, SOURCE_TABLE
from schema_mapper.models import MappingResult

MAX_SAMPLE_LIMIT = 20

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_event_profile",
        "description": "Full profile of one source event: row/user counts and every param "
                       "with its value type, distinct count and sample values. Reads a local cache.",
        "input_schema": {
            "type": "object",
            "properties": {"event_name": {"type": "string"}},
            "required": ["event_name"],
        },
    },
    {
        "name": "get_param_samples",
        "description": "Most frequent values of one param of one event, with counts, from BigQuery. "
                       "Use it to find evidence for a conditional split.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_name": {"type": "string"},
                "param_key": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_SAMPLE_LIMIT},
            },
            "required": ["event_name", "param_key"],
        },
    },
    {
        "name": "submit_mapping",
        "description": "Submit the final mapping covering EVERY source event. Call exactly once at the end. "
                       "If validation fails you get the errors back and one chance to resubmit.",
        "input_schema": MappingResult.model_json_schema(),
    },
]


class ToolError(Exception):
    """Returned to the model as an is_error tool_result, so it can correct itself."""


def get_event_profile(profile: dict[str, Any], event_name: str) -> str:
    event = profile["events"].get(event_name)
    if event is None:
        raise ToolError(f"Unknown event '{event_name}'.")
    return json.dumps(event)


# (event_name, param_key, limit) -> [{"value": ..., "n": ...}]. Names are already validated.
Sampler = Callable[[str, str, int], list[dict[str, Any]]]


def get_param_samples(
    profile: dict[str, Any], sampler: Sampler, event_name: str, param_key: str, limit: int = 10
) -> str:
    """Validate names against the profile, then ask the data source for value counts.

    Why a pluggable sampler: the same agent runs on BigQuery (Flood-It!) and on
    a CSV export (Adapty) without knowing which one it is talking to.
    """
    event = profile["events"].get(event_name)
    if event is None:
        raise ToolError(f"Unknown event '{event_name}'.")
    if param_key not in {p["key"] for p in event["params"]}:
        raise ToolError(f"Event '{event_name}' has no param '{param_key}'.")
    limit = max(1, min(int(limit), MAX_SAMPLE_LIMIT))
    return json.dumps(sampler(event_name, param_key, limit))


def bigquery_sampler(bq: BigQueryClient) -> Sampler:
    def sample(event_name: str, param_key: str, limit: int) -> list[dict[str, Any]]:
        # Names were validated against the profile before we get here, so formatting them in is safe.
        sql = f"""
    SELECT
      COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING),
               CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) AS value,
      COUNT(*) AS n
    FROM `{SOURCE_TABLE}`, UNNEST(event_params) AS p
    WHERE _TABLE_SUFFIX BETWEEN '{PROFILE_START}' AND '{PROFILE_END}'
      AND event_name = '{event_name}' AND p.key = '{param_key}'
    GROUP BY value
    ORDER BY n DESC
    LIMIT {limit}
    """
        return bq.run_select(sql)
    return sample
