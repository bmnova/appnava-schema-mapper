"""Command-line entry point: schema-mapper profile | map | sql | eval | report | all."""

import argparse

from schema_mapper.bigquery.client import BigQueryClient
from schema_mapper.bigquery.profiler import CACHE_PATH, build_profile, save_profile
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


COMMANDS = {"profile": cmd_profile}


def main() -> None:
    parser = argparse.ArgumentParser(prog="schema-mapper")
    parser.add_argument("command", choices=[*COMMANDS, "all"])
    args = parser.parse_args()
    steps = list(COMMANDS) if args.command == "all" else [args.command]
    for step in steps:
        COMMANDS[step]()


if __name__ == "__main__":
    main()
