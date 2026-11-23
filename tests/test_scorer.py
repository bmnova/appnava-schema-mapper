from schema_mapper.evaluation.scorer import evaluate
from schema_mapper.models import MappingResult


def test_accuracy_and_review_catch() -> None:
    base = dict(reasoning="r", needs_human_review=False)
    mapping = MappingResult(mappings=[
        base | {"source_event": "a", "target_event": "level_start", "confidence": 0.9},
        base | {"source_event": "b", "target_event": "level_fail", "confidence": 0.5},   # wrong, flagged
        base | {"source_event": "c", "target_event": "purchase", "confidence": 0.9},     # wrong, not flagged
        base | {"source_event": "d", "target_event": None, "confidence": 0.9},
    ])
    truth = {
        "a": {"expected": "level_start"},
        "b": {"expected": None},
        "c": {"expected": "subscription_start"},
        "d": {"expected": None},
        "e": {"expected": "TODO"},
    }
    report = evaluate(mapping, truth)
    assert report.unlabeled == ["e"]
    assert report.accuracy == 0.5
    assert [r.event for r in report.wrong_and_flagged] == ["b"]
    assert len(report.wrong) == 2
