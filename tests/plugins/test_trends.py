from __future__ import annotations

from pathlib import Path

from nyxor.plugins.trends.analysis import analyze, z_scores
from nyxor.plugins.trends.store import TrendStore


def test_trend_store_records_and_returns_history(tmp_path: Path) -> None:
    store = TrendStore(path=tmp_path / "trends.json")
    store.record("example.com", 90, "A-")
    store.record("example.com", 80, "B")

    history = store.history("example.com")
    assert [sample["points"] for sample in history] == [90, 80]
    assert history[-1]["grade"] == "B"


def test_trend_store_all_domains_returns_everything(tmp_path: Path) -> None:
    store = TrendStore(path=tmp_path / "trends.json")
    store.record("a.com", 90, "A-")
    store.record("b.com", 50, "F")

    everything = store.all_domains()
    assert set(everything) == {"a.com", "b.com"}
    assert everything["a.com"][0]["points"] == 90


def test_trend_store_keeps_domains_separate(tmp_path: Path) -> None:
    store = TrendStore(path=tmp_path / "trends.json")
    store.record("a.com", 90, "A-")
    store.record("b.com", 50, "F")

    assert len(store.history("a.com")) == 1
    assert len(store.history("b.com")) == 1
    assert store.history("nonexistent.com") == []


def test_trend_store_limit_returns_only_the_most_recent(tmp_path: Path) -> None:
    store = TrendStore(path=tmp_path / "trends.json")
    for points in [50, 60, 70, 80, 90]:
        store.record("example.com", points, "X")

    recent = store.history("example.com", limit=2)
    assert [s["points"] for s in recent] == [80, 90]


def test_trend_store_clear(tmp_path: Path) -> None:
    store = TrendStore(path=tmp_path / "trends.json")
    store.record("example.com", 90, "A-")
    assert store.clear("example.com") is True
    assert store.history("example.com") == []
    assert store.clear("example.com") is False


def test_analyze_empty_history_returns_none() -> None:
    assert analyze([]) is None


def test_analyze_single_sample_has_zero_slope() -> None:
    stats = analyze([80])
    assert stats is not None
    assert stats.n == 1
    assert stats.slope_per_run == 0.0
    assert stats.direction == "flat"
    assert stats.mean == 80.0


def test_analyze_detects_improving_trend() -> None:
    stats = analyze([50, 60, 70, 80, 90])
    assert stats is not None
    assert stats.direction == "improving"
    assert stats.slope_per_run > 0


def test_analyze_detects_degrading_trend() -> None:
    stats = analyze([90, 80, 70, 60, 50])
    assert stats is not None
    assert stats.direction == "degrading"
    assert stats.slope_per_run < 0


def test_analyze_flat_trend_for_constant_scores() -> None:
    stats = analyze([80, 80, 80, 80])
    assert stats is not None
    assert stats.direction == "flat"
    assert stats.std == 0.0
    assert stats.sparkline == stats.sparkline[0] * 4  # all bars the same height


def test_analyze_reports_correct_min_max_mean() -> None:
    stats = analyze([10, 50, 90])
    assert stats is not None
    assert stats.minimum == 10
    assert stats.maximum == 90
    assert stats.mean == 50.0


def test_z_scores_flags_an_outlier() -> None:
    # Matches the >= 2 threshold `nyx trends show` actually uses to flag a run.
    scores = z_scores([80, 82, 79, 81, 5])
    assert abs(scores[-1]) >= 2


def test_z_scores_all_zero_when_no_variance() -> None:
    assert z_scores([80, 80, 80]) == [0.0, 0.0, 0.0]


def test_z_scores_handles_single_or_empty_input() -> None:
    assert z_scores([]) == []
    assert z_scores([80]) == [0.0]
