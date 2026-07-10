"""Local-model-powered enhancements shared across `nyx audit --dumber`,

`nyx watch --narrate`, and `nyx ask`. All optional, all silently skipped
(return ``None``) if no local model is reachable — nothing here ever
crashes a command that would otherwise work fine without AI. Same Ollama
client `nyx analyze` already uses: local-first, your GPU if Ollama is
configured to use one, nothing sent anywhere unless you point ``--host``
at something else yourself.
"""

from __future__ import annotations

from nyxor.core.models import ModuleResult, Severity
from nyxor.plugins.analyze.ollama import OllamaUnavailable, generate
from nyxor.plugins.trends.store import Sample

_SEVERITY_ORDER = list(Severity)

_DUMBER_PROMPT = """You are explaining a security scan to someone who has \
never heard of DNS, TLS, or HTTP headers before. Be plain, friendly, a \
little playful, no jargon without immediately explaining it in the same \
breath. Go finding by finding, in the order given, one short paragraph \
each. No preamble, no disclaimers, no markdown headers, no numbered list.

Target: {domain}

Findings:
{findings}
"""

_FIX_PROMPT = """You are a pragmatic security engineer writing remediation \
notes. For each finding below, give 1-3 concrete, specific steps to fix it \
— not generic advice like "review your configuration." If a finding is \
purely informational and needs no fix, say so in one line. No preamble.

Findings:
{findings}
"""

_WATCH_NARRATION_PROMPT = """You monitor a website's security posture over \
time. Something changed since the last check. In ONE short sentence, tell \
the person watching what changed and whether they should actually care. \
No preamble, no hedging.

Target: {domain}
Grade: {previous_grade} -> {grade}

New findings:
{new_findings}

Resolved findings:
{resolved_findings}
"""

_ASK_PROMPT = """You are NYXOR's local assistant, answering questions about \
this user's own recorded security-scan history. Only use the data given \
below — if it doesn't answer the question, say so plainly instead of \
guessing. Be concise.

Recorded history (domain: [(timestamp, grade, points), ...]):
{history}

Question: {question}
"""


def _findings_block(results: list[ModuleResult], *, min_severity: Severity | None = None) -> str:
    """
    Format findings as a newline-separated text block.
    
    Parameters:
    	results (list[ModuleResult]): Module results containing the findings to format.
    	min_severity (Severity | None): Minimum severity to include. Findings below this severity are omitted.
    
    Returns:
    	str: Formatted finding lines, or "(none)" when no findings meet the severity threshold.
    """
    lines = []
    for result in results:
        for finding in result.findings:
            if min_severity is not None and (
                _SEVERITY_ORDER.index(finding.severity) < _SEVERITY_ORDER.index(min_severity)
            ):
                continue
            lines.append(
                f"- [{finding.severity.value}] ({result.module}) "
                f"{finding.title}: {finding.description}"
            )
    return "\n".join(lines) if lines else "(none)"


async def dumber_writeup(
    domain: str,
    results: list[ModuleResult],
    *,
    host: str,
    model: str,
    timeout_seconds: float,
) -> str | None:
    """
    Generate a beginner-friendly walkthrough of all findings for a domain.
    
    Parameters:
    	domain (str): The domain associated with the findings.
    	results (list[ModuleResult]): The module results containing findings.
    
    Returns:
    	str | None: The generated walkthrough, or `None` if the local model is unavailable.
    """
    prompt = _DUMBER_PROMPT.format(domain=domain, findings=_findings_block(results))
    try:
        return await generate(prompt, host=host, model=model, timeout_seconds=timeout_seconds)
    except OllamaUnavailable:
        return None


async def fix_suggestions(
    results: list[ModuleResult],
    *,
    host: str,
    model: str,
    timeout_seconds: float,
) -> str | None:
    """
    Generate remediation guidance for findings with medium severity or higher.
    
    Parameters:
        results (list[ModuleResult]): Scan results containing findings to address.
    
    Returns:
        str | None: Generated remediation guidance, or `None` when no eligible
            findings exist or the local model is unavailable.
    """
    block = _findings_block(results, min_severity=Severity.MEDIUM)
    if block == "(none)":
        return None
    prompt = _FIX_PROMPT.format(findings=block)
    try:
        return await generate(prompt, host=host, model=model, timeout_seconds=timeout_seconds)
    except OllamaUnavailable:
        return None


async def watch_narration(
    domain: str,
    *,
    grade: str,
    previous_grade: str,
    new: list[tuple[str, str, str]],
    resolved: list[tuple[str, str, str]],
    host: str,
    model: str,
    timeout_seconds: float,
) -> str | None:
    """
    Describe changes in a website's security posture in one short sentence.
    
    Parameters:
        domain (str): Website whose security posture changed.
        grade (str): Current security grade.
        previous_grade (str): Security grade from the previous scan.
        new (list[tuple[str, str, str]]): Findings introduced since the previous scan.
        resolved (list[tuple[str, str, str]]): Findings resolved since the previous scan.
    
    Returns:
        str | None: A generated narration, or `None` when nothing changed or the local model is unavailable.
    """
    if not new and not resolved and grade == previous_grade:
        return None
    prompt = _WATCH_NARRATION_PROMPT.format(
        domain=domain,
        previous_grade=previous_grade,
        grade=grade,
        new_findings="\n".join(f"- [{m}] {t}: {d}" for m, t, d in new) or "(none)",
        resolved_findings="\n".join(f"- [{m}] {t}" for m, t, _d in resolved) or "(none)",
    )
    try:
        return await generate(prompt, host=host, model=model, timeout_seconds=timeout_seconds)
    except OllamaUnavailable:
        return None


def _history_block(history: dict[str, list[Sample]]) -> str:
    """
    Serialize scan history into a text block for assistant prompts.
    
    Parameters:
        history (dict[str, list[Sample]]): Recorded samples grouped by domain.
    
    Returns:
        str: A newline-separated history block, or a message indicating that no history is recorded.
    """
    if not history:
        return "(no recorded history — run `nyx audit`/`nyx trends` a few times first)"
    lines = []
    for domain, samples in history.items():
        points = ", ".join(f"({s['timestamp']}, {s['grade']}, {s['points']})" for s in samples)
        lines.append(f"{domain}: [{points}]")
    return "\n".join(lines)


async def ask(
    question: str,
    history: dict[str, list[Sample]],
    *,
    host: str,
    model: str,
    timeout_seconds: float,
) -> str:
    """
    Answer a question using recorded scan history.
    
    Parameters:
        question (str): The question to answer.
        history (dict[str, list[Sample]]): Recorded scan samples grouped by domain.
    
    Returns:
        str: The model-generated answer.
    """
    prompt = _ASK_PROMPT.format(history=_history_block(history), question=question)
    return await generate(prompt, host=host, model=model, timeout_seconds=timeout_seconds)
