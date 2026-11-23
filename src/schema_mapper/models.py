"""Data contracts between the LLM and the deterministic code.

Why so structured: sql_gen turns these objects into SQL with no LLM help,
so every field must be machine-usable. Free text (`reasoning`,
`condition_description`) is for humans only and never reaches SQL.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

ValueType = Literal["string", "int", "double"]
REVIEW_THRESHOLD = 0.7
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "target_schema.yaml"


class TargetEvent(BaseModel):
    name: str
    category: str
    description: str
    params: dict[str, ValueType]


def load_target_schema(path: Path = SCHEMA_PATH) -> dict[str, TargetEvent]:
    """Flatten category -> event into one lookup keyed by event name."""
    raw = yaml.safe_load(path.read_text())
    return {
        name: TargetEvent(name=name, category=category, **spec)
        for category, events in raw.items()
        for name, spec in events.items()
    }


class ParamMapping(BaseModel):
    """Fill one target param from a source param OR a constant (e.g. game_mode='quickplay')."""

    target_param: str
    source_param: str | None = None
    source_type: ValueType | None = None  # which event_params value column to read
    constant: str | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "ParamMapping":
        if (self.source_param is None) == (self.constant is None):
            raise ValueError(f"{self.target_param}: set exactly one of source_param or constant")
        if self.source_param is not None and self.source_type is None:
            raise ValueError(f"{self.target_param}: source_type is required with source_param")
        return self


class SplitCase(BaseModel):
    value: str  # compared as a string; sql_gen casts the param accordingly
    target_event: str


class EventMapping(BaseModel):
    source_event: str
    target_event: str | None = None  # null = unmapped (unless split is used)
    split_by_param: str | None = None
    split_param_type: ValueType | None = None
    split_cases: list[SplitCase] = Field(default_factory=list)
    condition_description: str | None = None
    params: list[ParamMapping] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    needs_human_review: bool

    @model_validator(mode="after")
    def check_shape_and_enforce_review(self) -> "EventMapping":
        """Enforce the review rules in code, not just in the prompt.

        Why: the model may forget a rule; a deterministic validator cannot.
        We only ever turn the flag ON, never off.
        """
        is_split = self.split_by_param is not None
        if is_split and self.target_event is not None:
            raise ValueError(f"{self.source_event}: use target_event OR split, not both")
        if is_split and (not self.split_cases or self.split_param_type is None):
            raise ValueError(f"{self.source_event}: split needs split_cases and split_param_type")
        if not is_split and self.split_cases:
            raise ValueError(f"{self.source_event}: split_cases given without split_by_param")

        if self.confidence < REVIEW_THRESHOLD or len(self.targets()) > 1:
            self.needs_human_review = True
        return self

    def targets(self) -> set[str]:
        if self.split_cases:
            return {case.target_event for case in self.split_cases}
        return {self.target_event} if self.target_event else set()


class MappingResult(BaseModel):
    mappings: list[EventMapping]


def schema_errors(result: MappingResult, schema: dict[str, TargetEvent]) -> list[str]:
    """Checks Pydantic cannot do alone because they need the target schema.

    Returned as plain strings so they can be sent back to the model on retry.
    """
    errors: list[str] = []
    for m in result.mappings:
        for target in m.targets():
            if target not in schema:
                errors.append(f"{m.source_event}: unknown target_event '{target}'")
                continue
            for p in m.params:
                if p.target_param not in schema[target].params:
                    errors.append(f"{m.source_event}: '{p.target_param}' is not a param of {target}")
    return errors
