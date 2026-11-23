import pytest

from schema_mapper.models import MappingResult, load_target_schema
from schema_mapper.sql.generator import MappingNotUsable, build_select

SCHEMA = load_target_schema()
PROFILE = {"events": {
    "lvl_win": {"params": [{"key": "level_name"}, {"key": "outcome"}]},
    "quick_start": {"params": []},
}}


def mapping(*items: dict) -> MappingResult:
    base = dict(confidence=0.9, reasoning="r", needs_human_review=False)
    return MappingResult(mappings=[base | i for i in items])


def test_simple_mapping_with_param_and_constant() -> None:
    sql = build_select(mapping(
        {"source_event": "lvl_win", "target_event": "level_complete",
         "params": [{"target_param": "level_name", "source_param": "level_name", "source_type": "string"}]},
        {"source_event": "quick_start", "target_event": "level_start",
         "params": [{"target_param": "game_mode", "constant": "quickplay"}]},
    ), PROFILE, SCHEMA)
    assert "WHEN event_name = 'lvl_win' THEN 'level_complete'" in sql
    assert "SAFE_CAST('quickplay' AS STRING)" in sql
    assert "p.key = 'level_name'" in sql


def test_split_builds_one_when_per_case() -> None:
    sql = build_select(mapping({
        "source_event": "lvl_win", "split_by_param": "outcome", "split_param_type": "string",
        "split_cases": [{"value": "win", "target_event": "level_complete"},
                        {"value": "lose", "target_event": "level_fail"}]}), PROFILE, SCHEMA)
    assert sql.count("WHEN event_name = 'lvl_win' AND") == 2
    assert "= 'lose' THEN 'level_fail'" in sql


def test_unmapped_events_are_excluded() -> None:
    sql = build_select(mapping(
        {"source_event": "lvl_win", "target_event": "level_complete"},
        {"source_event": "quick_start", "target_event": None},
    ), PROFILE, SCHEMA)
    assert "quick_start" not in sql


def test_constant_with_quote_is_escaped() -> None:
    sql = build_select(mapping({"source_event": "quick_start", "target_event": "level_start",
        "params": [{"target_param": "game_mode", "constant": "x'; DROP TABLE t; --"}]}), PROFILE, SCHEMA)
    assert "'x\\'; DROP TABLE t; --'" in sql


def test_param_missing_from_profile_is_rejected() -> None:
    with pytest.raises(MappingNotUsable):
        build_select(mapping({"source_event": "lvl_win", "target_event": "level_complete",
            "params": [{"target_param": "score", "source_param": "invented", "source_type": "int"}]}),
            PROFILE, SCHEMA)
