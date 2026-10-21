"""Regenerate the example bundles with the library, unpacked so they read well on GitHub.

The fetchers are injected with stubs so the US example is reproducible without network or an LLM key.
That injection point (`resolve(..., lookup_ein=, crawl_site=, draft=)`) is also how an integrator swaps
in their own registry or scraper.   Run:  python examples/make_examples.py
"""
from __future__ import annotations

import io
import re
import shutil
import zipfile
from pathlib import Path

from nonprofit_backpack import Intake, LocalStorage, build, confirm, resolve
from nonprofit_backpack.draft import Draft
from nonprofit_backpack.propublica import LookupResult, PAGE
from nonprofit_backpack.scrape import Page

ROOT = Path(__file__).parent
FIXED_AT = "2026-10-21T12:00:00Z"


def unpack(bp, dest: Path):
    shutil.rmtree(dest, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(bp.to_bytes())) as z:
        z.extractall(dest)
    print(f"wrote {dest.relative_to(ROOT.parent)}")


def pin_timestamps(bp):
    bp.log = [re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", FIXED_AT, line) for line in bp.log]
    for c in bp.concepts:
        c.frontmatter["generated"]["at"] = FIXED_AT
        for v in c.frontmatter.get("verified", []):
            v["at"] = FIXED_AT


# --- US: typed name + stubbed EIN lookup + stubbed crawl + stubbed draft -----------------------------
def fake_lookup(ein):
    return LookupResult(name="Riverbend Food Pantry Inc", source={
        "id": "propublica", "resource": PAGE.format(ein=ein.replace("-", "")),
        "title": f"IRS Form 990 data for EIN {ein} via ProPublica Nonprofit Explorer"}, fields=[
        ("name", "Riverbend Food Pantry Inc", "IRS name on record; the everyday name may differ"),
        ("legal_name", "Riverbend Food Pantry Inc", "legal name on the IRS record"),
        ("country", "US", ""), ("registration_scheme", "IRS-EIN", ""), ("registration_id", ein, ""),
        ("year_founded", "2009", "IRS ruling year, when tax-exempt status was granted, which is not always the founding year"),
        ("annual_budget", "412350", "total expenses in USD from the Form 990 for the fiscal year ending 2025-06")])


def fake_crawl(url):
    return [Page(url, "Riverbend Food Pantry", "We distribute groceries to households in Riverbend County, Ohio…")]


def fake_draft(pages):
    return Draft(model="openrouter:anthropic/claude-sonnet-4.5", texts={
        "summary": "Riverbend Food Pantry distributes groceries to households in Riverbend County, Ohio, through a weekly "
                   "client-choice pantry and a mobile delivery route.[^website] It is staffed by a small team and a volunteer "
                   "corps, and sources most of its food from a regional food bank and local grocers.[^website]",
        "mission": "To make sure no family in Riverbend County goes without groceries.[^website]",
        "vision": ""}, fields={"staff_count": "6"})


us = Intake.from_file(ROOT / "facts-us.yaml")
us.id = "0f3d2a1b-9c8e-4d7f-8a6b-5c4d3e2f1a0b"
us.documents[0].path = str(ROOT / "files" / "riverbend-fy2025-audit.txt")
resolved = resolve(us, lookup_ein=fake_lookup, crawl_site=fake_crawl, draft=fake_draft, log=print)
creator = "human:7f1e6c0a-3b2d-4e8f-9a1b-2c3d4e5f6a7b"
bp = build(resolved, creator, LocalStorage(), log=print)
pin_timestamps(bp)
confirm(bp, creator, ["organization.md"])         # the organization self-confirms the registration facts only
pin_timestamps(bp)
unpack(bp, ROOT / "us-riverbend-food-pantry")

# --- KE: everything typed, no fetching --------------------------------------------------------------
ke = Intake.from_file(ROOT / "facts-ke.yaml")
ke.id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
ke.documents[0].path = str(ROOT / "files" / "maji-safi-registration.txt")
resolved = resolve(ke, fetch=False, log=print)
creator = "human:c2a9d4e1-7b3f-4c6a-8d2e-1f0a9b8c7d6e"
bp = build(resolved, creator, LocalStorage(), log=print)
pin_timestamps(bp)
confirm(bp, creator)                                # everything self-confirmed
pin_timestamps(bp)
unpack(bp, ROOT / "ke-maji-safi-initiative")
