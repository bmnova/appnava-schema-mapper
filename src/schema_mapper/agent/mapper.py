"""The agent loop: Claude explores the profile with read-only tools and
PROPOSES a mapping. Nothing here generates or runs SQL for the view.

Why a hand-written loop instead of a framework: every guardrail (call cap,
validation, retry, cost log) is a few visible lines we can explain.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
from pydantic import ValidationError

from schema_mapper.agent import tools
from schema_mapper.bigquery.client import BigQueryClient, QueryRejected
from schema_mapper.models import MappingResult, TargetEvent, load_target_schema, schema_errors

MAX_TOOL_CALLS = 15
MAX_SUBMIT_RETRIES = 1
OUTPUT_PATH = Path(__file__).resolve().parents[3] / "output" / "mapping.json"

# USD per million tokens: (input, output, cache_read). Update when prices change.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
CACHE_WRITE_MULTIPLIER = 1.25


class AgentFailed(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)

    def add(self, u: Any) -> None:
        self.input_tokens += u.input_tokens
        self.output_tokens += u.output_tokens
        self.cache_read_tokens += u.cache_read_input_tokens or 0
        self.cache_write_tokens += u.cache_creation_input_tokens or 0

    def cost_usd(self, model: str) -> float | None:
        if model not in PRICES:
            return None
        inp, out, cache_read = PRICES[model]
        return (
            self.input_tokens * inp
            + self.output_tokens * out
            + self.cache_read_tokens * cache_read
            + self.cache_write_tokens * inp * CACHE_WRITE_MULTIPLIER
        ) / 1_000_000


def _compact_profile(profile: dict[str, Any]) -> str:
    """One line per event so the model sees everything up front.

    Why: with a 15-call budget the agent cannot open all 33 events; it should
    spend calls only on the ones it is unsure about. firebase_* params are
    SDK noise and are dropped here (still available via get_event_profile).
    """
    lines = []
    for name, ev in profile["events"].items():
        params = [
            f"{p['key']}:{p['value_type']}={p['samples'][:3]}"
            for p in ev["params"] if not p["key"].startswith("firebase_")
        ]
        lines.append(f"- {name} rows={ev['row_count']} users={ev['user_count']} params: {'; '.join(params) or 'none'}")
    return "\n".join(lines)


def _schema_text(schema: dict[str, TargetEvent]) -> str:
    return "\n".join(
        f"- {t.name} [{t.category}]: {t.description} params={t.params}" for t in schema.values()
    )


def build_system_prompt(profile: dict[str, Any], schema: dict[str, TargetEvent]) -> str:
    return f"""You map a mobile app's raw Firebase/GA4 events to AppNava's standard event schema.
Your mapping is a PROPOSAL: deterministic code turns it into SQL and a human reviews flagged items.
Being honest about uncertainty is more valuable than being complete.

TARGET SCHEMA:
{_schema_text(schema)}

SOURCE EVENTS (Flood-It! game, {profile['date_range'][0]}-{profile['date_range'][1]}):
{_compact_profile(profile)}

RULES
- Produce exactly one mapping per source event listed above; use target_event=null if nothing fits.
- Map to a target only if its meaning truly matches; do not force SDK/system events into the schema.
- If one source event should become different targets depending on a param value, use
  split_by_param + split_param_type + split_cases, and only with evidence from get_param_samples.
  If the source has no param that distinguishes the outcomes, do NOT invent a split: map to null
  or the closest target and set needs_human_review=true, explaining why.
- params: fill target params from a source param (with its source_type) or a constant
  (e.g. game_mode='quickplay' for *_quickplay events). Only use target params listed in the schema.
- confidence 0-1; reasoning is one line citing the evidence.
- needs_human_review=true if confidence < 0.7, if one source maps to several targets, or if the
  event name alone is ambiguous.
- You have at most {MAX_TOOL_CALLS} tool calls in total. Investigate only what is uncertain,
  then call submit_mapping once with all events."""


def _run_tool(name: str, args: dict[str, Any], profile: dict[str, Any], bq: BigQueryClient) -> str:
    if name == "get_event_profile":
        return tools.get_event_profile(profile, args["event_name"])
    if name == "get_param_samples":
        return tools.get_param_samples(
            profile, bq, args["event_name"], args["param_key"], args.get("limit", 10)
        )
    raise tools.ToolError(f"Unknown tool '{name}'.")


def _validate_submission(
    args: dict[str, Any], profile: dict[str, Any], schema: dict[str, TargetEvent]
) -> tuple[MappingResult | None, list[str]]:
    """Pydantic shape check, then checks that need the schema and the profile."""
    try:
        result = MappingResult.model_validate(args)
    except ValidationError as e:
        return None, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
    errors = schema_errors(result, schema)
    submitted = [m.source_event for m in result.mappings]
    missing = set(profile["events"]) - set(submitted)
    unknown = set(submitted) - set(profile["events"])
    if missing:
        errors.append(f"Missing mappings for: {sorted(missing)}")
    if unknown:
        errors.append(f"Unknown source events: {sorted(unknown)}")
    if len(submitted) != len(set(submitted)):
        errors.append("Each source event must appear exactly once.")
    return (result if not errors else None), errors


def run_agent(profile: dict[str, Any], bq: BigQueryClient) -> tuple[MappingResult, Usage, str]:
    model = os.environ.get("ANTHROPIC_MODEL")
    if not model:
        raise RuntimeError("ANTHROPIC_MODEL is not set (see .env.example)")
    client = anthropic.Anthropic()
    schema = load_target_schema()
    system = build_system_prompt(profile, schema)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Map every source event, then call submit_mapping."}
    ]
    usage = Usage()
    tool_calls = 0
    submit_failures = 0

    while True:
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            tools=tools.TOOL_DEFINITIONS,
            messages=messages,
            cache_control={"type": "ephemeral"},  # schema + profile prefix is re-sent every turn
        )
        usage.add(response.usage)
        print(f"  [turn] in={response.usage.input_tokens} out={response.usage.output_tokens} "
              f"cache_read={response.usage.cache_read_input_tokens or 0} stop={response.stop_reason}")

        if response.stop_reason in ("max_tokens", "refusal"):
            raise AgentFailed(f"Model stopped with '{response.stop_reason}'.")
        # Append full content (not just text) so tool_use ids and thinking blocks stay intact.
        messages.append({"role": "assistant", "content": response.content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            messages.append({"role": "user", "content": "Please call submit_mapping with the full mapping."})
            continue

        results = []
        for block in tool_uses:
            tool_calls += 1
            entry = {"n": tool_calls, "tool": block.name, "input": block.input if block.name != "submit_mapping" else "<mapping>"}
            usage.log.append(entry)
            print(f"  [tool {tool_calls}/{MAX_TOOL_CALLS}] {block.name} {entry['input']}")

            if block.name == "submit_mapping":
                result, errors = _validate_submission(block.input, profile, schema)
                if result is not None:
                    return result, usage, model
                submit_failures += 1
                entry["errors"] = errors
                print(f"    invalid submission ({len(errors)} errors): {errors[:3]}")
                if submit_failures > MAX_SUBMIT_RETRIES:
                    raise AgentFailed(f"Invalid mapping after retry: {errors}")
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": "Validation failed, fix and resubmit:\n" + "\n".join(errors)})
                continue

            if tool_calls > MAX_TOOL_CALLS:
                content, is_error = "Tool budget exhausted. Call submit_mapping now.", True
            else:
                try:
                    content, is_error = _run_tool(block.name, block.input, profile, bq), False
                except (tools.ToolError, QueryRejected) as e:
                    content, is_error = str(e), True
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": content, "is_error": is_error})

        # All tool results for one assistant turn go back in a single user message.
        messages.append({"role": "user", "content": results})
        if tool_calls > MAX_TOOL_CALLS + 3:
            raise AgentFailed("Agent kept calling tools after the budget was exhausted.")


def save_mapping(result: MappingResult, usage: Usage, model: str, path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(exist_ok=True)
    payload = {
        "model": model,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "cache_write_tokens": usage.cache_write_tokens,
            "cost_usd": usage.cost_usd(model),
            "tool_calls": usage.log,
        },
        "mappings": [m.model_dump() for m in result.mappings],
    }
    path.write_text(json.dumps(payload, indent=2))
