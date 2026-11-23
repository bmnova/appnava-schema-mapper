"""Score the agent's mapping against a small hand-labeled ground truth.

Why two metrics: accuracy says how often the agent is right; the review
metrics say whether `needs_human_review` catches the cases where it is
wrong. The second one is what makes the system safe to use.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from schema_mapper.models import MappingResult

GROUND_TRUTH_PATH = Path(__file__).resolve().parents[3] / "eval" / "ground_truth.yaml"


@dataclass
class EvalRow:
    event: str
    expected: set[str]
    predicted: set[str]
    flagged: bool

    @property
    def correct(self) -> bool:
        return self.expected == self.predicted


@dataclass
class EvalReport:
    rows: list[EvalRow]
    unlabeled: list[str]

    @property
    def accuracy(self) -> float:
        return sum(r.correct for r in self.rows) / len(self.rows) if self.rows else 0.0

    @property
    def wrong(self) -> list[EvalRow]:
        return [r for r in self.rows if not r.correct]

    @property
    def wrong_and_flagged(self) -> list[EvalRow]:
        return [r for r in self.wrong if r.flagged]

    @property
    def flagged(self) -> list[EvalRow]:
        return [r for r in self.rows if r.flagged]

    def to_dict(self) -> dict[str, Any]:
        return {
            "labeled": len(self.rows),
            "unlabeled": self.unlabeled,
            "accuracy": self.accuracy,
            "wrong": len(self.wrong),
            "wrong_caught_by_review_flag": len(self.wrong_and_flagged),
            "flagged": len(self.flagged),
            "rows": [
                {"event": r.event, "expected": sorted(r.expected), "predicted": sorted(r.predicted),
                 "correct": r.correct, "flagged": r.flagged}
                for r in self.rows
            ],
        }


def _as_set(expected: Any) -> set[str]:
    if expected is None:
        return set()
    if isinstance(expected, list):
        return set(expected)
    return {expected}


def load_ground_truth(path: Path = GROUND_TRUTH_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())["events"]


def evaluate(mapping: MappingResult, truth: dict[str, Any]) -> EvalReport:
    by_event = {m.source_event: m for m in mapping.mappings}
    rows, unlabeled = [], []
    for event, label in truth.items():
        if label["expected"] == "TODO":
            unlabeled.append(event)
            continue
        m = by_event.get(event)
        predicted = m.targets() if m else set()
        rows.append(EvalRow(event, _as_set(label["expected"]), predicted,
                            flagged=bool(m and m.needs_human_review)))
    return EvalReport(rows, unlabeled)
