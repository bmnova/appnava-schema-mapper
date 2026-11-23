"""Phase 2: a SYNTHETIC Adapty-style subscription export, read from CSV.

Why CSV and not BigQuery: the point is to test the agent on an ambiguous
subscription schema, not the warehouse. The profile has the same shape as
the Firebase one, so the agent code is unchanged.
"""

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from schema_mapper.agent.tools import Sampler

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "SYNTHETIC_adapty_events.csv"
OUTPUT_PATH = ROOT / "output" / "adapty_mapping.json"
PARAM_COLUMNS = ["product_id", "price", "currency", "store"]


def load_rows(path: Path = CSV_PATH) -> list[dict[str, str]]:
    lines = [line for line in path.read_text().splitlines() if not line.startswith("#")]
    return list(csv.DictReader(lines))


def _value_type(values: list[str]) -> str:
    try:
        [float(v) for v in values]
        return "double"
    except ValueError:
        return "string"


def build_profile(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Same shape as the Firebase profile: per event, counts and per-param samples."""
    events: dict[str, Any] = {}
    for name in sorted({r["event_name"] for r in rows}):
        ev_rows = [r for r in rows if r["event_name"] == name]
        params = []
        for key in PARAM_COLUMNS:
            values = [r[key] for r in ev_rows if r[key]]
            if values:
                params.append({"key": key, "value_type": _value_type(values),
                               "occurrences": len(values), "distinct_values": len(set(values)),
                               "samples": sorted(set(values))[:5]})
        events[name] = {"row_count": len(ev_rows),
                        "user_count": len({r["user_id"] for r in ev_rows}),
                        "params": params}
    dates = sorted(r["event_timestamp"][:10].replace("-", "") for r in rows)
    return {"source_table": CSV_PATH.name,
            "description": "subscription app, Adapty event export (SYNTHETIC sample)",
            "date_range": [dates[0], dates[-1]], "events": events}


def csv_sampler(rows: list[dict[str, str]]) -> Sampler:
    def sample(event_name: str, param_key: str, limit: int) -> list[dict[str, Any]]:
        counts = Counter(r[param_key] for r in rows if r["event_name"] == event_name and r[param_key])
        return [{"value": v, "n": n} for v, n in counts.most_common(limit)]
    return sample
