"""The intake funnel: typed essentials first, then EIN, then website.

Precedence is fixed: typed beats fetched, fetched beats drafted. Each resolved value keeps the
origin of whichever source won, which is what the provenance footnotes are written from.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

Access = str  # "public" | "private"
ACCESS_VALUES = ("public", "private")

# The organization fields, in display order. `label` is what a prompt or form shows.
FIELDS: list[tuple[str, str]] = [
    ("name", "Organization name"),
    ("country", "Country (ISO 3166-1 code, e.g. US, KE)"),
    ("registration_id", "Nonprofit registration ID"),
]
TEXTS: list[tuple[str, str]] = [
    ("summary", "Summary (one sentence: who you are and what you do)"),
]
REQUIRED_FOR_COMPLETE = ("name", "country", "summary")
INTAKE_KEYS = ("ein", "website", "crawl", "access", "id")   # facts-file keys that steer the funnel rather than being stored


@dataclass
class Intake:
    """Everything the organization gives us. Every part is optional."""
    typed: dict[str, str] = field(default_factory=dict)   # field/text name -> value typed by the organization
    ein: str = ""
    website: str = ""
    crawl: bool = True                                     # crawl `website` when set
    access: dict[str, Access] = field(default_factory=lambda: {"organization": "public", "about": "public"})
    id: str = ""                                           # the backpack's organization UUID, kept across runs
    ignored: list[str] = field(default_factory=list)       # facts-file keys this version does not record (reported, not stored)

    @classmethod
    def from_file(cls, path: str | Path) -> "Intake":
        data = yaml.safe_load(Path(path).read_text()) or {}
        typed = {k: str(data[k]).strip() for k, _ in FIELDS + TEXTS if data.get(k) not in (None, "")}
        access = {"organization": "public", "about": "public", **(data.get("access") or {})}
        known = {k for k, _ in FIELDS + TEXTS} | set(INTAKE_KEYS)
        return cls(typed=typed, ein=str(data.get("ein", "") or ""), website=str(data.get("website", "") or ""),
                   crawl=bool(data.get("crawl", True)), access=access, id=str(data.get("id", "") or ""),
                   ignored=[k for k in data if k not in known])


@dataclass
class Origin:
    by: str                  # "human" | "tool" | "llm"
    source: str = ""         # sources[].id the value came from, if any
    note: str = ""           # shown next to uncertain mappings


@dataclass
class Resolved:
    values: dict[str, str] = field(default_factory=dict)        # field name -> value
    origin: dict[str, Origin] = field(default_factory=dict)     # field or text name -> origin
    texts: dict[str, str] = field(default_factory=dict)         # summary
    tags: list[str] = field(default_factory=list)               # always drafted by the LLM, never typed
    sources: list[dict] = field(default_factory=list)           # OKF sources entries
    pages: list = field(default_factory=list)                   # crawled pages, for the record
    llm_model: str = ""                                         # set when the LLM drafted anything
    issues: list[str] = field(default_factory=list)             # steps that did not succeed, in plain words
    website: str = ""                                           # crawled, recorded as a source, not stored as a field
    access: dict[str, Access] = field(default_factory=dict)
    id: str = ""

    def missing_for_complete(self) -> list[str]:
        have = {**self.values, **self.texts}
        return [k for k in REQUIRED_FOR_COMPLETE if not have.get(k, "").strip()]


def normalize_url(raw: str) -> str:
    v = (raw or "").strip()
    return f"https://{v}" if v and not v.lower().startswith(("http://", "https://")) else v


def resolve(intake: Intake, *, fetch: bool = True, redraft: bool = False, log: Callable[[str], None] = lambda m: None,
            lookup_ein: Callable | None = None, crawl_site: Callable | None = None, draft: Callable | None = None) -> Resolved:
    """Run the funnel. The three fetchers can be injected (for tests, examples, or your own sources).

    Drafting needs crawled pages, and sees everything: the typed summary, the IRS facts (context only) and the
    pages. It writes the summary only if it is still empty (typed beats drafted), unless `redraft=True`, and it
    always writes the tags, which come from the LLM alone.
    """
    from . import propublica, scrape, draft as drafting

    def fail(msg: str):
        r.issues.append(msg); log(msg)

    r = Resolved(access=dict(intake.access), id=intake.id)
    ignored = intake.ignored + [k for k in intake.typed if k not in {k2 for k2, _ in FIELDS + TEXTS} and k not in intake.ignored]
    if ignored:   # e.g. legal_name, mission or documents from a pre-0.2 facts file: say so rather than drop them quietly
        fail("Ignored fields this version does not record: " + ", ".join(ignored) + ".")
    for k, _ in FIELDS:
        if intake.typed.get(k, "").strip():
            r.values[k] = intake.typed[k].strip(); r.origin[k] = Origin("human")
    for k, _ in TEXTS:
        if intake.typed.get(k, "").strip():
            r.texts[k] = intake.typed[k].strip(); r.origin[k] = Origin("human")

    def fill(k: str, value, origin: Origin, store: dict):
        if value in (None, "") or store.get(k, "").strip():
            return
        store[k] = str(value); r.origin[k] = origin

    irs_name: tuple[str, Origin] | None = None
    ein = propublica.normalize_ein(intake.ein) if intake.ein else None
    if intake.ein and not ein:
        fail(f"EIN {intake.ein!r} is not nine digits; skipped.")
    if ein and fetch:
        log(f"Looking up EIN {ein} on ProPublica…")
        try:
            result = (lookup_ein or propublica.lookup)(ein)
        except Exception as e:
            fail(f"EIN lookup failed: {e}"); result = None
        if result:
            r.sources.append(result.source)
            for k, value, note in result.fields:
                if k == "name":      # the IRS name is usually the legal form; the everyday name comes from the site, this is the fallback
                    irs_name = (value, Origin("tool", result.source["id"], note))
                    continue
                fill(k, value, Origin("tool", result.source["id"], note), r.values)
            log(f"IRS record found: {result.name}")
        else:
            fail("No IRS record for that EIN.")

    website = r.website = normalize_url(intake.website)
    if website and intake.crawl and fetch:
        log(f"Crawling {website} (up to {scrape.MAX_PAGES} pages)…")
        try:
            on_page = lambda i, n, u: log(f"  page {i}/{n}: {u}")
            r.pages = (crawl_site or scrape.crawl)(website, on_page=on_page) if crawl_site is None else crawl_site(website)
            r.sources.append({"id": "website", "resource": website, "title": "Organization website"})
            log(f"Fetched {len(r.pages)} page(s).")
        except Exception as e:
            fail(f"Crawl failed: {e}")

    typed_texts = {k: r.texts[k] for k, _ in TEXTS if r.origin.get(k, Origin("")).by == "human" and r.texts.get(k, "").strip()}
    want = [k for k, _ in TEXTS if redraft or not r.texts.get(k, "").strip()]
    if r.pages and fetch:   # the IRS record alone (name, country, ID) is too little to describe an organization from
        if draft or os.environ.get("OPENROUTER_API_KEY"):
            material = draft_material(r, typed_texts)
            log(("Redrafting " if redraft else "Drafting ") + ", ".join(want + ["tags"]) + " with the LLM from " +
                ", ".join(sorted({m["id"] for m in material})) + "…")
            try:
                d = (draft or drafting.draft)(material)
                r.llm_model = d.model
                citable = {m["id"] for m in material if m["id"] != "propublica"}
                org_name = r.values.get("name") or d.fields.get("name", "")
                for k in want:
                    text = drafting.clean_citations(d.texts.get(k, ""), citable, "website", org_name)
                    text = drafting.normalize_statement(text, "website", org_name)
                    if not text:
                        continue
                    if k in typed_texts:   # redraft: the typed summary becomes a cited source of the new one
                        _add_source(r, "organization", "statements typed by the organization at intake", "Statements typed by the organization")
                    r.texts[k] = text; r.origin[k] = Origin("llm", "website")
                r.tags = drafting.clean_tags(d.tags)
                if r.tags:
                    r.origin["tags"] = Origin("llm", "website")
                notes = {"name": "the name the organization uses on its website"}
                for k, value in d.fields.items():
                    fill(k, value, Origin("llm", "website", notes.get(k, "suggested by the LLM from the website text")), r.values)
            except Exception as e:
                fail(f"Drafting failed: {e}")
        else:
            fail("OPENROUTER_API_KEY not set; skipped drafting. The summary stays as typed, and there are no tags.")
    if irs_name:   # nothing typed or found on the site: fall back to the IRS name, with its caveat
        fill("name", irs_name[0], irs_name[1], r.values)
    return r


def ein_facts(r: Resolved) -> str:
    """The IRS-derived values as one text block, with their caveats, so the LLM can use them alongside the pages."""
    rows = [f"{k}: {v}" + (f"   (note: {r.origin[k].note})" if r.origin[k].note else "")
            for k, v in r.values.items() if r.origin.get(k, Origin("")).source == "propublica"]
    return "\n".join(rows)


def draft_material(r: Resolved, typed_texts: dict[str, str]) -> list[dict]:
    """Everything the LLM sees: the typed summary (authoritative), IRS facts (context only), crawled pages. Each tagged with a source id."""
    material = []
    if typed_texts:
        material.append({"id": "organization", "title": "Summary typed by the organization (authoritative; keep its meaning)",
                         "text": "\n\n".join(f"{k.upper()}: {v}" for k, v in typed_texts.items())})
    facts = ein_facts(r)
    if facts:
        material.append({"id": "propublica", "title": "IRS facts via ProPublica (context only: do not cite)", "text": facts})
    material += [{"id": "website", "title": p.title or p.url, "text": p.text} for p in r.pages]
    return material


def _add_source(r: Resolved, id: str, resource: str, title: str):
    if not any(s["id"] == id for s in r.sources):
        r.sources.append({"id": id, "resource": resource, "title": title})
