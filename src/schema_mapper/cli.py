"""Command-line entry point: schema-mapper profile | map | sql | eval | report | all."""

import argparse

from schema_mapper.bigquery.client import BigQueryClient
from schema_mapper.agent.mapper import OUTPUT_PATH, run_agent, save_mapping
from schema_mapper.bigquery.profiler import CACHE_PATH, build_profile, load_profile, save_profile
from schema_mapper.config import SOURCE_TABLE, VALIDATION_DAY, load_settings
from schema_mapper.evaluation.scorer import evaluate, load_ground_truth
from schema_mapper.models import MappingResult, load_target_schema
from schema_mapper.reporting.report import write_report
from schema_mapper.sql.generator import build_counts_query, build_select, build_view


def cmd_profile() -> None:
    settings = load_settings()
    profile = build_profile(BigQueryClient(settings))
    save_profile(profile)
    events = profile["events"]
    print(f"Profiled {len(events)} events -> {CACHE_PATH}")
    for name, info in events.items():
        keys = ", ".join(p["key"] for p in info["params"])
        print(f"  {name:28} rows={info['row_count']:>6} users={info['user_count']:>5}  [{keys}]")


def cmd_map() -> None:
    settings = load_settings()
    result, usage, model = run_agent(load_profile(), BigQueryClient(settings))
    save_mapping(result, usage, model)
    print(f"\nMapping -> {OUTPUT_PATH}")
    for m in result.mappings:
        target = m.target_event or (" | ".join(f"{c.value}->{c.target_event}" for c in m.split_cases) or "-")
        flag = "REVIEW" if m.needs_human_review else ""
        print(f"  {m.source_event:28} -> {target:30} conf={m.confidence:.2f} {flag}")
    cost = usage.cost_usd(model)
    print(f"\nTokens: in={usage.input_tokens} out={usage.output_tokens} "
          f"cache_read={usage.cache_read_tokens} cache_write={usage.cache_write_tokens}")
    print(f"Tool calls: {len(usage.log)}  Estimated cost ({model}): "
          + (f"${cost:.4f}" if cost is not None else "unknown model price"))


def cmd_show() -> None:
    """Print the last saved mapping without calling the model again (free, offline)."""
    import json
    data = json.loads(OUTPUT_PATH.read_text())
    for m in data["mappings"]:
        cases = " | ".join(f"{c['value']}->{c['target_event']}" for c in m["split_cases"])
        target = m["target_event"] or cases or "(unmapped)"
        flag = "  [REVIEW]" if m["needs_human_review"] else ""
        print(f"{m['source_event']} -> {target}  conf={m['confidence']:.2f}{flag}")
        print(f"    why: {m['reasoning']}")
        for p in m["params"]:
            src = p["source_param"] or repr(p["constant"])
            print(f"    param: {p['target_param']} <- {src}")
    u = data["usage"]
    print(f"\nmodel={data['model']} tool_calls={len(u['tool_calls'])} cost=${u['cost_usd']:.4f}")


def _load_mapping() -> MappingResult:
    import json
    return MappingResult.model_validate({"mappings": json.loads(OUTPUT_PATH.read_text())["mappings"]})


def cmd_sql() -> None:
    import json
    import os
    settings = load_settings()
    bq = BigQueryClient(settings)
    mapping, profile, schema = _load_mapping(), load_profile(), load_target_schema()
    out_dir = OUTPUT_PATH.parent

    # The view itself is written to a file, not created: deploying it is a human decision.
    dataset = os.environ.get("VIEW_DATASET", "appnava_mapper")
    view_sql = build_view(build_select(mapping, profile, schema), settings.gcp_project, dataset)
    (out_dir / "view.sql").write_text(view_sql + "\n")
    full_bytes = bq.estimate_bytes(build_select(mapping, profile, schema))
    print(f"View SQL -> {out_dir / 'view.sql'}  (dry-run OK, full table scan = {full_bytes:,} bytes)")

    day = (VALIDATION_DAY, VALIDATION_DAY)
    counts_sql = build_counts_query(build_select(mapping, profile, schema, suffix_filter=day))
    print(f"Validation query dry-run: {bq.estimate_bytes(counts_sql):,} bytes")
    counts = bq.run_select(counts_sql)
    total = bq.run_select(f"SELECT COUNT(*) AS n FROM `{SOURCE_TABLE}` WHERE _TABLE_SUFFIX = '{VALIDATION_DAY}'")[0]["n"]

    mapped_rows = sum(r["row_count"] for r in counts)
    print(f"\nRows on {VALIDATION_DAY}: {mapped_rows:,} of {total:,} mapped ({mapped_rows / total:.1%})")
    for r in counts:
        print(f"  {r['target_event']:20} <- {r['source_event']:28} {r['row_count']:>6}")

    fired = {r["source_event"] for r in counts}
    silent = [m.source_event for m in mapping.mappings if m.targets() and m.source_event not in fired]
    if silent:
        print(f"\nMapped but produced 0 rows that day: {silent}")
    (out_dir / "sql_validation.json").write_text(json.dumps(
        {"day": VALIDATION_DAY, "total_rows": total, "mapped_rows": mapped_rows,
         "counts": counts, "silent_mappings": silent}, indent=2))


def cmd_eval() -> None:
    import json
    report = evaluate(_load_mapping(), load_ground_truth())
    if report.unlabeled:
        print(f"Skipping {len(report.unlabeled)} unlabeled events (expected: TODO): {report.unlabeled}")
    if not report.rows:
        print("Nothing to score yet: fill in eval/ground_truth.yaml.")
        return
    for r in report.rows:
        mark = "OK   " if r.correct else "WRONG"
        flag = "[REVIEW]" if r.flagged else ""
        print(f"  {mark} {r.event:24} expected={sorted(r.expected) or ['null']} "
              f"got={sorted(r.predicted) or ['null']} {flag}")
    print(f"\nAccuracy: {sum(r.correct for r in report.rows)}/{len(report.rows)} = {report.accuracy:.0%}")
    print(f"Wrong answers caught by the review flag: {len(report.wrong_and_flagged)}/{len(report.wrong)}")
    print(f"Flagged items that were actually correct: {len(report.flagged) - len(report.wrong_and_flagged)}/{len(report.flagged)}")
    (OUTPUT_PATH.parent / "eval.json").write_text(json.dumps(report.to_dict(), indent=2))


def cmd_report() -> None:
    print(f"Report -> {write_report()}")


COMMANDS = {"profile": cmd_profile, "map": cmd_map, "show": cmd_show, "sql": cmd_sql, "eval": cmd_eval, "report": cmd_report}


def main() -> None:
    parser = argparse.ArgumentParser(prog="schema-mapper")
    parser.add_argument("command", choices=[*COMMANDS, "all"])
    args = parser.parse_args()
    steps = [c for c in COMMANDS if c != "show"] if args.command == "all" else [args.command]
    for step in steps:
        COMMANDS[step]()


if __name__ == "__main__":
    main()
