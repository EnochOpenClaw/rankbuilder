#!/usr/bin/env python3
"""
Shared Ollama client for RankBuilder drafting (HARO / guest outreach).

Why this exists: the drafting scripts originally hardcoded
`http://localhost:11434` and a single cloud model (kimi-k2.6:cloud). In the
production container "localhost" is the container itself and the VPS runs no
Ollama — so every draft attempt failed with [Errno 111] Connection refused.
And cloud models (kimi-k2.6:cloud) require an Ollama account login; a fresh
VPS instance returns 401 Unauthorized for them.

Rules:
- Endpoint comes from OLLAMA_HOST env (e.g. http://10.0.1.1:11434 on the
  VPS docker bridge), default http://localhost:11434.
- generate() tries the model chain in order and falls through on ANY error
  (connection refused, 401 Unauthorized, timeout, empty response), so a
  local model (llama3.2:latest) still produces drafts when the cloud model
  is unreachable or unauthenticated.
"""
import json
import os
import urllib.error
import urllib.request

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_CHAIN = ["kimi-k2.6:cloud", "llama3.2:latest"]


def _host() -> str:
    return os.environ.get("OLLAMA_HOST", DEFAULT_HOST).rstrip("/")


def call_model(
    model: str,
    prompt: str,
    system: str = None,
    options: dict = None,
    timeout: int = 120,
    think: bool = None,
) -> str:
    """Call /api/generate for one model. Returns text ('' on empty response)."""
    payload = {"model": model, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system
    if options:
        payload["options"] = options
    if think is not None:
        payload["think"] = think
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{_host()}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    text = result.get("response", "").strip()
    if not text and result.get("thinking"):
        text = result["thinking"].strip()
    return text


def generate(
    prompt: str,
    models: list = None,
    system: str = None,
    options: dict = None,
    timeout: int = 120,
) -> str:
    """
    Try each model in order; return first non-empty text.

    Raises RuntimeError only if EVERY model failed (message includes the last
    error, so callers can log why).
    """
    chain = models or [
        os.environ.get("OLLAMA_MODEL", "").strip() or DEFAULT_CHAIN[0]
    ] + DEFAULT_CHAIN[1:]
    last_err: Exception = None
    for model in chain:
        try:
            text = call_model(model, prompt, system=system, options=options, timeout=timeout)
            if text:
                return text
        except Exception as e:  # noqa: BLE001 — fall through to next model
            last_err = e
    raise RuntimeError(f"All Ollama models unavailable: {last_err}")


def tags() -> list:
    """List model names available on the endpoint (handy for diagnostics)."""
    req = urllib.request.Request(
        f"{_host()}/api/tags", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return [m.get("name", "") for m in result.get("models", [])]
