from __future__ import annotations

from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.scoring import render_badge, score_results


def _result_with(*severities: Severity) -> ModuleResult:
    return ModuleResult(
        module="test",
        target="example.com",
        findings=[Finding(title="x", severity=s) for s in severities],
    )


def test_no_findings_scores_a_plus() -> None:
    score = score_results([_result_with()])
    assert score.points == 100
    assert score.grade == "A+"


def test_penalties_stack_across_results() -> None:
    score = score_results([_result_with(Severity.HIGH), _result_with(Severity.MEDIUM)])
    assert score.points == 100 - 15 - 6
    assert score.finding_counts[Severity.HIGH] == 1
    assert score.finding_counts[Severity.MEDIUM] == 1


def test_points_floor_at_zero() -> None:
    score = score_results([_result_with(*([Severity.CRITICAL] * 10))])
    assert score.points == 0
    assert score.grade == "F"


def test_grade_thresholds_are_inclusive_at_the_boundary() -> None:
    # Exactly one HIGH finding: 100 - 15 = 85, which should land in the B band (>= 80).
    score = score_results([_result_with(Severity.HIGH)])
    assert score.points == 85
    assert score.grade == "B"


def test_info_findings_do_not_affect_the_score() -> None:
    score = score_results([_result_with(*([Severity.INFO] * 20))])
    assert score.points == 100
    assert score.grade == "A+"


def test_render_badge_embeds_label_and_grade() -> None:
    score = score_results([_result_with(Severity.CRITICAL)])
    svg = render_badge(score, label="example.com")
    assert "<svg" in svg
    assert "example.com" in svg
    assert f">{score.grade}<" in svg
    assert score.color in svg


def test_worst_severity_is_none_with_no_findings() -> None:
    score = score_results([_result_with()])
    assert score.worst_severity is None


def test_worst_severity_picks_the_single_worst_across_multiple_findings() -> None:
    score = score_results([_result_with(Severity.LOW, Severity.HIGH, Severity.INFO)])
    assert score.worst_severity == Severity.HIGH


def test_meets_or_exceeds_true_when_worst_finding_matches_threshold_exactly() -> None:
    score = score_results([_result_with(Severity.MEDIUM)])
    assert score.meets_or_exceeds(Severity.MEDIUM) is True


def test_meets_or_exceeds_true_when_worst_finding_is_more_severe() -> None:
    score = score_results([_result_with(Severity.CRITICAL)])
    assert score.meets_or_exceeds(Severity.MEDIUM) is True


def test_meets_or_exceeds_false_when_worst_finding_is_less_severe() -> None:
    score = score_results([_result_with(Severity.LOW)])
    assert score.meets_or_exceeds(Severity.HIGH) is False


def test_meets_or_exceeds_false_with_no_findings_at_all() -> None:
    score = score_results([_result_with()])
    assert score.meets_or_exceeds(Severity.INFO) is False
