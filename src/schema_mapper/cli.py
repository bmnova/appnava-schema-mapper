"""Command-line entry point: schema-mapper profile | map | sql | eval | report | all."""

import argparse

from schema_mapper.bigquery.client import BigQueryClient
from schema_mapper.agent.mapper import OUTPUT_PATH, run_agent, save_mapping
from schema_mapper.bigquery.profiler import CACHE_PATH, build_profile, load_profile, save_profile
from schema_mapper.config import load_settings


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


COMMANDS = {"profile": cmd_profile, "map": cmd_map, "show": cmd_show}


def main() -> None:
    parser = argparse.ArgumentParser(prog="schema-mapper")
    parser.add_argument("command", choices=[*COMMANDS, "all"])
    args = parser.parse_args()
    steps = [c for c in COMMANDS if c != "show"] if args.command == "all" else [args.command]
    for step in steps:
        COMMANDS[step]()


if __name__ == "__main__":
    main()
