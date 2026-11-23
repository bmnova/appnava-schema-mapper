"""Turn a reviewed mapping into BigQuery SQL. No LLM here.

Why deterministic: the same mapping must always produce the same SQL, and
every line must be auditable. The mapping is treated as untrusted input:
names are checked against the profile and literals are escaped, so model
output can never inject SQL.
"""

import re
from typing import Any

from schema_mapper.config import SOURCE_TABLE
from schema_mapper.models import EventMapping, MappingResult, TargetEvent, ValueType

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
VIEW_NAME = "appnava_standard_events"


class MappingNotUsable(Exception):
    pass


def _literal(value: str) -> str:
    """BigQuery string literal with backslashes and quotes escaped."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _param_value(key: str, as_type: ValueType) -> str:
    """Read one event_params value, whichever typed column it landed in.

    Why read every column: the same key changes type across app versions
    (e.g. `level` arrives as int AND double in Flood-It). Reading a single
    column would silently return NULL for part of the rows.
    """
    v = "p.value"
    if as_type == "int":
        expr = (f"COALESCE({v}.int_value, CAST({v}.double_value AS INT64), "
                f"CAST({v}.float_value AS INT64), SAFE_CAST({v}.string_value AS INT64))")
    elif as_type == "double":
        expr = (f"COALESCE({v}.double_value, {v}.float_value, "
                f"CAST({v}.int_value AS FLOAT64), SAFE_CAST({v}.string_value AS FLOAT64))")
    else:
        expr = (f"COALESCE({v}.string_value, CAST({v}.int_value AS STRING), "
                f"CAST({v}.double_value AS STRING), CAST({v}.float_value AS STRING))")
    return f"(SELECT {expr} FROM UNNEST(event_params) AS p WHERE p.key = {_literal(key)})"


def _check_names(m: EventMapping, profile: dict[str, Any]) -> None:
    event = profile["events"].get(m.source_event)
    if event is None or not _IDENTIFIER.match(m.source_event):
        raise MappingNotUsable(f"Unknown source event '{m.source_event}'")
    known_keys = {p["key"] for p in event["params"]}
    used = [p.source_param for p in m.params if p.source_param] + (
        [m.split_by_param] if m.split_by_param else [])
    for key in used:
        if key not in known_keys:
            raise MappingNotUsable(f"{m.source_event}: param '{key}' not in profile")


def _target_case(mappings: list[EventMapping]) -> str:
    lines = []
    for m in mappings:
        src = _literal(m.source_event)
        if m.split_cases:
            split = _param_value(m.split_by_param, "string")
            for case in m.split_cases:
                lines.append(f"    WHEN event_name = {src} AND {split} = {_literal(case.value)} "
                             f"THEN {_literal(case.target_event)}")
        else:
            lines.append(f"    WHEN event_name = {src} THEN {_literal(m.target_event)}")
    return "  CASE\n" + "\n".join(lines) + "\n  END AS target_event"


def _param_column(name: str, as_type: ValueType, mappings: list[EventMapping]) -> str | None:
    """One output column: a CASE over the source events that fill this param."""
    lines = []
    for m in mappings:
        for p in m.params:
            if p.target_param != name:
                continue
            value = _param_value(p.source_param, as_type) if p.source_param else (
                f"SAFE_CAST({_literal(p.constant)} AS {_BQ_TYPE[as_type]})")
            lines.append(f"    WHEN event_name = {_literal(m.source_event)} THEN {value}")
    if not lines:
        return None
    return "  CASE\n" + "\n".join(lines) + f"\n  END AS {name}"


_BQ_TYPE = {"string": "STRING", "int": "INT64", "double": "FLOAT64"}


def build_select(
    result: MappingResult, profile: dict[str, Any], schema: dict[str, TargetEvent],
    suffix_filter: tuple[str, str] | None = None,
) -> str:
    """The view body. `suffix_filter` limits shards for cheap validation runs."""
    mapped = [m for m in result.mappings if m.targets()]
    for m in mapped:
        _check_names(m, profile)

    # Output params = union of params of every target used, typed by the target schema.
    param_types: dict[str, ValueType] = {}
    for m in mapped:
        for target in m.targets():
            param_types.update(schema[target].params)
    param_cols = [c for n, t in sorted(param_types.items()) if (c := _param_column(n, t, mapped))]

    where = f"event_name IN ({', '.join(_literal(m.source_event) for m in mapped)})"
    if suffix_filter:
        where += f"\n    AND _TABLE_SUFFIX BETWEEN {_literal(suffix_filter[0])} AND {_literal(suffix_filter[1])}"

    columns = ",\n".join([
        "  PARSE_DATE('%Y%m%d', event_date) AS event_date",
        "  TIMESTAMP_MICROS(event_timestamp) AS event_ts",
        "  user_pseudo_id",
        "  event_name AS source_event",
        _target_case(mapped),
        *param_cols,
    ])
    return (f"SELECT * FROM (\n  SELECT\n{columns}\n  FROM `{SOURCE_TABLE}`\n  WHERE {where}\n)\n"
            f"WHERE target_event IS NOT NULL")


def build_view(select_sql: str, project: str, dataset: str) -> str:
    return f"CREATE OR REPLACE VIEW `{project}.{dataset}.{VIEW_NAME}` AS\n{select_sql}"


def build_counts_query(select_sql: str) -> str:
    """Rows per (target, source) on the validation day: did each mapping actually fire?"""
    return (f"SELECT target_event, source_event, COUNT(*) AS row_count\n"
            f"FROM (\n{select_sql}\n)\nGROUP BY target_event, source_event\n"
            f"ORDER BY target_event, row_count DESC")
