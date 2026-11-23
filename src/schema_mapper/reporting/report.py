"""Build report.md from the saved artifacts. No model or BigQuery calls.

Why from files: the report is reproducible offline and always reflects the
exact mapping, validation run and eval that were reviewed.
"""

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "output"
REPORT_PATH = ROOT / "report.md"


def _read(name: str) -> Any:
    path = OUTPUT / name
    return json.loads(path.read_text()) if path.exists() else None


def _target_text(m: dict[str, Any]) -> str:
    if m["split_cases"]:
        return "<br>".join(f"`{m['split_by_param']}={c['value']}` → {c['target_event']}"
                           for c in m["split_cases"])
    return m["target_event"] or "unmapped"


def _params_text(m: dict[str, Any]) -> str:
    return ", ".join(f"{p['target_param']} ← {p['source_param'] or repr(p['constant'])}"
                     for p in m["params"]) or ""


def _mapping_table(mappings: list[dict[str, Any]], rows_by_event: dict[str, int]) -> list[str]:
    lines = ["| Source event | Rows (profile) | Target | Params | Conf. | Review | Reasoning |",
             "|---|---:|---|---|---:|:---:|---|"]
    for m in sorted(mappings, key=lambda m: -rows_by_event.get(m["source_event"], 0)):
        lines.append(
            f"| `{m['source_event']}` | {rows_by_event.get(m['source_event'], 0):,} | {_target_text(m)} "
            f"| {_params_text(m)} | {m['confidence']:.2f} | {'⚠️' if m['needs_human_review'] else ''} "
            f"| {m['reasoning']} |")
    return lines


def build_report() -> str:
    mapping = _read("mapping.json")
    if mapping is None:
        raise FileNotFoundError("output/mapping.json missing; run `schema-mapper map` first")
    profile = json.loads((ROOT / "cache" / "flood_it_profile.json").read_text())
    validation, evaluation = _read("sql_validation.json"), _read("eval.json")
    view_sql = (OUTPUT / "view.sql").read_text() if (OUTPUT / "view.sql").exists() else None
    if view_sql:
        # report.md is committed to a public repo: hide the real GCP project id.
        view_sql = re.sub(r"VIEW `[^.`]+\.", "VIEW `YOUR_PROJECT.", view_sql, count=1)

    mappings = mapping["mappings"]
    rows_by_event = {name: ev["row_count"] for name, ev in profile["events"].items()}
    mapped = [m for m in mappings if m["target_event"] or m["split_cases"]]
    review = [m for m in mappings if m["needs_human_review"]]
    unmapped = [m for m in mappings if not (m["target_event"] or m["split_cases"])]
    total_rows = sum(rows_by_event.values())
    mapped_rows = sum(rows_by_event.get(m["source_event"], 0) for m in mapped)

    out = ["# Flood-It! → AppNava schema mapping report", "",
           f"Source: `{profile['source_table']}`, profile range {profile['date_range'][0]}–{profile['date_range'][1]}. "
           f"Model: `{mapping['model']}`.", "",
           "> The LLM **proposed** this mapping. The SQL below was generated deterministically from it. "
           "Items marked ⚠️ need a human decision before the view is deployed.", "",
           "## Summary", "",
           "| Metric | Value |", "|---|---|",
           f"| Events mapped | {len(mapped)} / {len(mappings)} ({len(mapped) / len(mappings):.0%}) |",
           f"| Rows mapped (profile, 3 days) | {mapped_rows:,} / {total_rows:,} ({mapped_rows / total_rows:.1%}) |"]
    if validation:
        out.append(f"| Rows mapped by the view ({validation['day']}) | {validation['mapped_rows']:,} / "
                   f"{validation['total_rows']:,} ({validation['mapped_rows'] / validation['total_rows']:.1%}) |")
    out.append(f"| Needs human review | {len(review)} |")
    if evaluation:
        out.append(f"| Eval accuracy | {evaluation['accuracy']:.0%} on {evaluation['labeled']} labeled events |")
    usage = mapping["usage"]
    cost = f"${usage['cost_usd']:.4f}" if usage["cost_usd"] is not None else "n/a"
    out += [f"| Agent cost | {cost} ({len(usage['tool_calls'])} tool calls, "
            f"{usage['input_tokens'] + usage['cache_read_tokens'] + usage['cache_write_tokens']:,} input / "
            f"{usage['output_tokens']:,} output tokens) |", ""]

    out += ["## Needs human review", ""]
    out += [f"- **`{m['source_event']}`** → {_target_text(m).replace('<br>', '; ')} "
            f"(conf. {m['confidence']:.2f}): {m['reasoning']}" for m in review] + [""]

    out += ["## Mapping", ""] + _mapping_table(mappings, rows_by_event) + [""]

    out += ["## Unmapped events", "", "Kept out of the view on purpose (SDK/system events or no matching target):", ""]
    out += [f"- `{m['source_event']}` ({rows_by_event.get(m['source_event'], 0):,} rows): {m['reasoning']}"
            for m in unmapped] + [""]

    if validation:
        out += [f"## View validation on {validation['day']}", "",
                "| Target | Source | Rows |", "|---|---|---:|"]
        out += [f"| {r['target_event']} | `{r['source_event']}` | {r['row_count']:,} |" for r in validation["counts"]]
        silent = validation["silent_mappings"]
        out += ["", f"Mapped events that produced 0 rows: {', '.join(silent) if silent else 'none'}.", ""]

    if evaluation:
        out += ["## Eval against ground truth", "",
                f"Accuracy **{evaluation['accuracy']:.0%}** ({evaluation['labeled'] - evaluation['wrong']}/{evaluation['labeled']}). "
                f"Wrong answers caught by the review flag: {evaluation['wrong_caught_by_review_flag']}/{evaluation['wrong']}. "
                f"Flagged but correct: {evaluation['flagged'] - evaluation['wrong_caught_by_review_flag']}/{evaluation['flagged']}.", "",
                "| Event | Expected | Predicted | | Flagged |", "|---|---|---|:---:|:---:|"]
        for r in evaluation["rows"]:
            out.append(f"| `{r['event']}` | {', '.join(r['expected']) or 'null'} | {', '.join(r['predicted']) or 'null'} "
                       f"| {'✅' if r['correct'] else '❌'} | {'⚠️' if r['flagged'] else ''} |")
        out += ["", "Caveat: 15 labels, drafted by a separate Claude context (see `eval/ground_truth.yaml`); "
                "a larger human-labeled set would be a stronger test.", ""]

    adapty = _read("adapty_mapping.json")
    if adapty:
        out += ["## Phase 2: SYNTHETIC Adapty subscription export", "",
                "Same agent on `data/SYNTHETIC_adapty_events.csv` (30 hand-written rows, not real data). "
                "In this export `purchase` is sent for both a new subscription and a renewal, and no field "
                "says which. The expected behaviour is to flag it, not to pick one target blindly.", "",
                "| Source event | Target | Conf. | Review | Reasoning |", "|---|---|---:|:---:|---|"]
        out += [f"| `{m['source_event']}` | {_target_text(m)} | {m['confidence']:.2f} "
                f"| {'⚠️' if m['needs_human_review'] else ''} | {m['reasoning']} |" for m in adapty["mappings"]]
        a_cost = adapty["usage"]["cost_usd"]
        out += ["", f"Cost: ${a_cost:.4f}, {len(adapty['usage']['tool_calls'])} tool calls." if a_cost is not None else "", ""]

    out += ["## Agent tool calls", ""]
    out += [f"{c['n']}. `{c['tool']}` {c['input'] if isinstance(c['input'], dict) else ''}"
            + (f" — rejected: {c['errors'][0]}" if c.get("errors") else "") for c in usage["tool_calls"]] + [""]

    if view_sql:
        out += ["## Generated SQL", "", "Written to `output/view.sql`; not deployed automatically.", "",
                "```sql", view_sql.rstrip(), "```", ""]
    return "\n".join(out)


def write_report() -> Path:
    REPORT_PATH.write_text(build_report())
    return REPORT_PATH
