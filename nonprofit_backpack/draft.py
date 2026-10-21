"""One LLM call, via OpenRouter, to draft the summary, mission and vision from crawled pages.

Env: OPENROUTER_API_KEY (required), OPENROUTER_MODEL (default below). The prompt is
prompts/summary.md: neutral, no invented facts, footnote markers keyed to source ids.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
PROMPT = (Path(__file__).parent / "prompts" / "summary.md").read_text()
MAX_INPUT_CHARS = 60_000
FIELD_KEYS = ("year_founded", "website", "staff_count", "country")


@dataclass
class Draft:
    texts: dict[str, str]
    fields: dict[str, str] = field(default_factory=dict)
    model: str = ""


def _section(raw: str, name: str) -> str:
    m = re.search(rf"{name}:\s*(.*?)(?=\n\s*(?:SUMMARY|MISSION|VISION|FIELDS):|\Z)", raw, re.S)
    return (m.group(1) if m else "").strip()


def parse(raw: str, model: str) -> Draft:
    fields = {}
    for line in _section(raw, "FIELDS").splitlines():
        m = re.match(rf"\s*({'|'.join(FIELD_KEYS)})\s*:\s*(.+?)\s*$", line)
        if m:
            fields[m.group(1)] = m.group(2)
    return Draft(texts={k: _section(raw, k.upper()) for k in ("summary", "mission", "vision")}, fields=fields, model=model)


def draft(pages, model: str | None = None) -> Draft:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    model = model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL
    material = "\n\n".join(f"=== source id: website ({p.title or p.url}) ===\n{p.text}" for p in pages)[:MAX_INPUT_CHARS]
    resp = httpx.post(ENDPOINT, timeout=120.0,
                      headers={"authorization": f"Bearer {key}", "content-type": "application/json",
                               "HTTP-Referer": "https://github.com/Guide-to-Good/nonprofit-backpack", "X-Title": "nonprofit-backpack"},
                      json={"model": model, "temperature": 0,
                            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": material}]})
    resp.raise_for_status()
    return parse(resp.json()["choices"][0]["message"]["content"], f"openrouter:{model}")
