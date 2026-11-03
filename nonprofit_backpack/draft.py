"""One LLM call, via OpenRouter, to draft the one-sentence summary and the tags from crawled pages.

Env: OPENROUTER_API_KEY (required), OPENROUTER_MODEL (default below). The prompt is
prompts/summary.md: neutral, no invented facts, footnote markers keyed to source ids.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import httpx

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
PROMPT = (Path(__file__).parent / "prompts" / "summary.md").read_text()
MAX_INPUT_CHARS = 60_000
FIELD_KEYS = ("name", "country")

MAX_TAGS = 8
MAX_TAG_WORDS = 4                     # longer than this is a phrase, not a tag
REACH = ("local", "regional", "national", "international")
# Spellings models reach for instead of the prompt's facet words. Folded so the same idea is one tag everywhere.
TAG_ALIASES = {
    "global": "international", "worldwide": "international", "multinational": "international", "transnational": "international",
    "statewide": "regional", "countywide": "regional", "nationwide": "national", "community-based": "local", "grassroots": "local",
    "direct-services": "direct-service", "service-delivery": "direct-service",
    "grant-making": "grantmaking", "grantmaker": "grantmaking", "philanthropy": "grantmaking", "regranting": "grantmaking",
    "policy-advocacy": "advocacy", "public-policy": "advocacy", "lobbying": "advocacy",
    "community-organising": "community-organizing", "organizing": "community-organizing", "organising": "community-organizing",
    "capacity-strengthening": "capacity-building", "technical-assistance": "capacity-building",
    "volunteer-led": "volunteer-run", "all-volunteer": "volunteer-run", "volunteer-based": "volunteer-run",
    "faith-based-organization": "faith-based", "religious": "faith-based", "church": "faith-based",
    "private-foundation": "foundation", "community-foundation": "foundation", "fiscal-sponsorship": "fiscal-sponsor",
    "membership-organization": "membership-association", "member-organization": "membership-association",
    "food-insecurity": "food-security", "hunger-relief": "food-security", "anti-hunger": "food-security",
    "wash": "clean-water", "water-sanitation-hygiene": "clean-water", "safe-water": "clean-water", "water-access": "clean-water",
    "affordable-housing": "housing", "homelessness-prevention": "housing",
    "healthcare": "public-health", "health-care": "public-health",
    "kids": "children", "child": "children", "youth-development": "youth", "young-people": "youth",
    "seniors": "older-adults", "elderly": "older-adults", "aging": "older-adults",
    "asylum-seekers": "refugees", "displaced-people": "refugees", "military-veterans": "veterans",
    "smallholder-farmers": "farmers", "agriculture": "farming", "animal-welfare": "animals",
    "environment": "conservation", "environmental-conservation": "conservation",
    "arts-and-culture": "arts", "culture": "arts", "families-with-children": "families", "low-income-families": "families",
}


@dataclass
class Draft:
    texts: dict[str, str]
    tags: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    model: str = ""


HEADINGS = r"\*{0,2}(?:SUMMARY|TAGS|FIELDS)(?::\*{0,2}|\*{0,2}:)"   # NAME:  **NAME:**  **NAME**:


def _section(raw: str, name: str) -> str:
    """Text between `NAME:` and the next section heading (or the end). Tolerates `**NAME:**` and an empty section."""
    m = re.search(rf"\*{{0,2}}{name}(?::\*{{0,2}}|\*{{0,2}}:)[ \t]*\n?(.*?)(?=\n?[ \t]*{HEADINGS}|\Z)", raw, re.S)
    return (m.group(1) if m else "").strip()


FOOTNOTE = re.compile(r"\[\^([\w-]+)\]")


def _sentences(text: str, name: str = "") -> list[str]:
    """Split on sentence ends. A new sentence starts with a capital, digit or quote, or with the organization's
    own name, which may be lowercase (charity: water)."""
    starts = r"[A-Z0-9\"'“]" + (f"|{re.escape(name)}" if name else "")
    return re.split(rf"(?<=[.!?\]])\s+(?=(?:{starts}))", text.strip())


def clean_citations(text: str, citable: set[str], fallback: str, name: str = "") -> str:
    """Keep only footnotes whose label is a source the model was allowed to cite. A sentence left with no
    footnote gets the fallback source, so every drafted sentence stays attributed. The model's citations
    are otherwise unchecked, so this is the guard against a footnote naming a source that never said it."""
    if not text.strip():
        return ""
    out = []
    for sent in _sentences(text, name):
        kept = [m for m in FOOTNOTE.findall(sent) if m in citable]
        bare = FOOTNOTE.sub("", sent).rstrip()
        if not kept and fallback:
            kept = [fallback]
        out.append(bare + "".join(f"[^{k}]" for k in dict.fromkeys(kept)))
    return " ".join(out)


def normalize_statement(text: str, fallback: str, name: str = "") -> str:
    """One consistent shape for the summary: a single sentence (any after the first are dropped), no wrapping quotes,
    a capital first letter (unless it opens with the organization's own name, kept as written), a final period,
    footnote(s) at the end."""
    if not text.strip():
        return ""
    text = _sentences(text, name)[0]
    notes = FOOTNOTE.findall(text) or ([fallback] if fallback else [])
    t = FOOTNOTE.sub("", text).strip().strip('"“”\'‘’').strip()
    t = re.sub(r"\s+", " ", t)
    if not t:
        return ""
    if not (name and t.lower().startswith(name.lower())):
        t = t[0].upper() + t[1:]
    elif not t.startswith(name):
        t = name + t[len(name):]
    if t[-1] not in ".!?":
        t += "."
    return t + "".join(f"[^{n}]" for n in dict.fromkeys(notes))


def clean_tags(raw: list[str]) -> list[str]:
    """The model's tags -> the tags stored in about.md. The prompt asks for 3-8 lowercase, hyphenated tags with no
    place names, but nothing enforces that; this is the deterministic pass that does, as clean_citations does for
    footnotes. Tags from different backpacks are only comparable if they come out of here in the same shape."""
    out: list[str] = []
    for t in raw:
        t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().replace("&", " and ")
        t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")          # Direct Service, direct_service, #direct/service -> direct-service
        t = TAG_ALIASES.get(t, t)
        if not t or t.isdigit() or t.count("-") >= MAX_TAG_WORDS or t in out:
            continue
        if t in REACH and any(r in out for r in REACH):        # one reach only: the model's first word on it wins
            continue
        out.append(t)
    return out[:MAX_TAGS]


def parse(raw: str, model: str) -> Draft:
    fields = {}
    for line in _section(raw, "FIELDS").splitlines():
        m = re.match(rf"\s*({'|'.join(FIELD_KEYS)})\s*:\s*(.+?)\s*$", line)
        if m:
            fields[m.group(1)] = m.group(2)
    tags = [t.strip(" -*`") for t in re.split(r"[,\n]", _section(raw, "TAGS"))]
    return Draft(texts={"summary": _section(raw, "SUMMARY")}, tags=[t for t in tags if t], fields=fields, model=model)


def draft(material: list[dict], model: str | None = None) -> Draft:
    """`material` is a list of {id, title, text}; ids are the sources[].id the footnotes must use."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    model = model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL
    material = "\n\n".join(f"=== source id: {m['id']} ({m['title']}) ===\n{m['text']}" for m in material)[:MAX_INPUT_CHARS]
    resp = httpx.post(ENDPOINT, timeout=120.0,
                      headers={"authorization": f"Bearer {key}", "content-type": "application/json",
                               "HTTP-Referer": "https://github.com/Guide-to-Good/nonprofit-backpack", "X-Title": "nonprofit-backpack"},
                      json={"model": model, "temperature": 0,
                            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": material}]})
    resp.raise_for_status()
    return parse(resp.json()["choices"][0]["message"]["content"], f"openrouter:{model}")
