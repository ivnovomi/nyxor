from __future__ import annotations

import pytest

from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.plugins.analyze import advisor
from nyxor.plugins.analyze.ollama import OllamaUnavailable


def _result(module: str, *severities: Severity) -> ModuleResult:
    """Construct a module result for the fixed example target with one finding per severity."""
    return ModuleResult(
        module=module,
        target="example.com",
        findings=[
            Finding(title=f"finding-{i}", severity=s, description="desc")
            for i, s in enumerate(severities)
        ],
    )


async def _fake_generate_ok(prompt: str, *, host: str, model: str, timeout_seconds: float) -> str:
    """
    Return a response containing the length of the provided prompt.
    
    Parameters:
    	prompt (str): The prompt whose length is included in the response.
    	host (str): Model server host.
    	model (str): Model identifier.
    	timeout_seconds (float): Request timeout in seconds.
    
    Returns:
    	str: A message containing the prompt length.
    """
    return f"model saw prompt of length {len(prompt)}"


async def _fake_generate_fails(
    prompt: str, *, host: str, model: str, timeout_seconds: float
) -> str:
    """
    Raise OllamaUnavailable to simulate an unreachable model server.
    
    Parameters:
        prompt (str): The generated prompt.
        host (str): The model server host.
        model (str): The model name.
        timeout_seconds (float): The request timeout.
    """
    raise OllamaUnavailable("no model server reachable")


@pytest.mark.asyncio
async def test_dumber_writeup_returns_none_when_model_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "generate", _fake_generate_fails)
    result = await advisor.dumber_writeup(
        "example.com", [_result("dns", Severity.INFO)], host="h", model="m", timeout_seconds=1.0
    )
    assert result is None


@pytest.mark.asyncio
async def test_dumber_writeup_returns_text_when_model_answers(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "generate", _fake_generate_ok)
    result = await advisor.dumber_writeup(
        "example.com", [_result("dns", Severity.INFO)], host="h", model="m", timeout_seconds=1.0
    )
    assert result is not None
    assert "model saw prompt" in result


@pytest.mark.asyncio
async def test_fix_suggestions_skips_when_nothing_medium_or_worse(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "generate", _fake_generate_ok)
    result = await advisor.fix_suggestions(
        [_result("dns", Severity.INFO, Severity.LOW)], host="h", model="m", timeout_seconds=1.0
    )
    assert result is None


@pytest.mark.asyncio
async def test_fix_suggestions_calls_model_when_medium_or_worse_present(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "generate", _fake_generate_ok)
    result = await advisor.fix_suggestions(
        [_result("http", Severity.INFO, Severity.HIGH)], host="h", model="m", timeout_seconds=1.0
    )
    assert result is not None


@pytest.mark.asyncio
async def test_watch_narration_returns_none_when_nothing_changed() -> None:
    result = await advisor.watch_narration(
        "example.com",
        grade="A",
        previous_grade="A",
        new=[],
        resolved=[],
        host="h",
        model="m",
        timeout_seconds=1.0,
    )
    assert result is None


@pytest.mark.asyncio
async def test_watch_narration_calls_model_on_grade_change(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "generate", _fake_generate_ok)
    result = await advisor.watch_narration(
        "example.com",
        grade="B",
        previous_grade="A",
        new=[],
        resolved=[],
        host="h",
        model="m",
        timeout_seconds=1.0,
    )
    assert result is not None


@pytest.mark.asyncio
async def test_ask_raises_when_model_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "generate", _fake_generate_fails)
    with pytest.raises(OllamaUnavailable):
        await advisor.ask("what changed?", {}, host="h", model="m", timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_ask_includes_history_in_the_prompt(monkeypatch) -> None:
    seen_prompt = None

    async def capture(prompt: str, *, host: str, model: str, timeout_seconds: float) -> str:
        nonlocal seen_prompt
        seen_prompt = prompt
        return "answer"

    monkeypatch.setattr(advisor, "generate", capture)
    history = {"example.com": [{"timestamp": "2026-01-01T00:00:00", "points": 90, "grade": "A-"}]}

    await advisor.ask("how's example.com doing?", history, host="h", model="m", timeout_seconds=1.0)

    assert seen_prompt is not None
    assert "example.com" in seen_prompt
    assert "90" in seen_prompt
    assert "how's example.com doing?" in seen_prompt


def test_findings_block_filters_by_minimum_severity() -> None:
    results = [_result("http", Severity.INFO, Severity.LOW, Severity.HIGH)]
    block = advisor._findings_block(results, min_severity=Severity.MEDIUM)
    assert "finding-2" in block  # the HIGH one
    assert "finding-0" not in block  # INFO
    assert "finding-1" not in block  # LOW
