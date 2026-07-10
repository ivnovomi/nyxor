"""A thin client for a local Ollama server — the "local AI" half of `nyx analyze`.

Ollama runs entirely on the user's own machine (``ollama serve``, default
port 11434). NYXOR never ships a model or downloads one on your behalf —
it just asks whatever is already running locally. No API key, no per-token
cost, no data leaving the box. Anyone who'd rather not install and run a
model themselves can point ``--host`` at NYXOR Cloud's hosted endpoint
instead once it exists (see the pricing page) and get the same command
with zero local setup.
"""

from __future__ import annotations

import httpx

from nyxor.core.models import ModuleResult

PROMPT_TEMPLATE = """You are a terse security analyst. Summarize this scan \
in 3-5 sentences for someone who will act on it immediately. Lead with the \
single most important issue, if any. No preamble, no disclaimers.

Target: {domain}

Findings:
{findings}
"""


def build_prompt(domain: str, results: list[ModuleResult]) -> str:
    lines = []
    for result in results:
        for finding in result.findings:
            lines.append(
                f"- [{finding.severity.value}] ({result.module}) "
                f"{finding.title}: {finding.description}"
            )
    findings_block = "\n".join(lines) if lines else "(no findings)"
    return PROMPT_TEMPLATE.format(domain=domain, findings=findings_block)


class OllamaUnavailable(Exception):
    """Raised when the local (or Cloud) model endpoint can't be reached."""


async def generate(
    prompt: str,
    *,
    host: str = "http://localhost:11434",
    model: str = "llama3.2",
    timeout_seconds: float = 30.0,
) -> str:
    """POST to Ollama's `/api/generate` and return the model's text response.

    Every failure mode here — connection refused, a bad status, a timeout,
    any other transport error, or a response body that isn't the JSON we
    expect — raises :class:`OllamaUnavailable` and nothing else, so callers
    only ever need to catch that one type to get the "never crashes a
    command that would otherwise work fine without AI" guarantee.
    """
    url = host.rstrip("/") + "/api/generate"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                url,
                json={"model": model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            payload: dict[str, object] = response.json()
    except httpx.ConnectError as exc:
        raise OllamaUnavailable(f"no model server reachable at {host}") from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaUnavailable(
            f"model server at {host} returned {exc.response.status_code} "
            f"(is model {model!r} pulled? try: ollama pull {model})"
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaUnavailable(f"model server at {host} timed out") from exc
    except httpx.HTTPError as exc:
        # Any other transport-level failure (DNS, proxy, protocol errors, a
        # malformed --host, ...) that isn't one of the specific cases above.
        raise OllamaUnavailable(f"error talking to model server at {host}: {exc}") from exc
    except ValueError as exc:
        # response.json() raised — the server at `host` responded, but not
        # with valid JSON (e.g. --host pointed at something that isn't
        # Ollama at all).
        raise OllamaUnavailable(f"model server at {host} returned an invalid response") from exc

    text = payload.get("response")
    if not isinstance(text, str) or not text:
        raise OllamaUnavailable(f"model server at {host} returned an empty response")
    return text.strip()
