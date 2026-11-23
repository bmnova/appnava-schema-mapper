import pytest
from pydantic import ValidationError

from schema_mapper.models import EventMapping, MappingResult, load_target_schema, schema_errors

SCHEMA = load_target_schema()


def make(**kw) -> EventMapping:
    base = dict(source_event="e", confidence=0.9, reasoning="r", needs_human_review=False)
    return EventMapping(**(base | kw))


def test_schema_loads_all_targets() -> None:
    assert len(SCHEMA) == 24
    assert SCHEMA["level_complete"].category == "progression"


def test_low_confidence_forces_review() -> None:
    assert make(target_event="level_start", confidence=0.5).needs_human_review


def test_split_to_two_targets_forces_review() -> None:
    m = make(
        split_by_param="success", split_param_type="string",
        split_cases=[{"value": "1", "target_event": "level_complete"},
                     {"value": "0", "target_event": "level_fail"}],
    )
    assert m.needs_human_review and m.targets() == {"level_complete", "level_fail"}


def test_target_and_split_together_rejected() -> None:
    with pytest.raises(ValidationError):
        make(target_event="level_start", split_by_param="x", split_param_type="string",
             split_cases=[{"value": "1", "target_event": "level_fail"}])


def test_param_needs_exactly_one_source() -> None:
    with pytest.raises(ValidationError):
        make(target_event="level_start", params=[{"target_param": "game_mode"}])


def test_schema_errors_catch_unknown_target_and_param() -> None:
    result = MappingResult(mappings=[
        make(source_event="a", target_event="level_explode"),
        make(source_event="b", target_event="level_start",
             params=[{"target_param": "colour", "constant": "red"}]),
    ])
    errors = schema_errors(result, SCHEMA)
    assert len(errors) == 2 and "level_explode" in errors[0] and "colour" in errors[1]
