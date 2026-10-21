"""`nbp`: create, confirm, add-doc, check, schemes."""
from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml

from . import VERSION, create_backpack
from .bundle import Backpack, add_document, confirm as confirm_bp
from .check import check as run_check
from .identity import get_creator_id
from .intake import ACCESS_VALUES, FIELDS, TEXTS, DocumentInput, Intake
from .schemes import SCHEMES

echo = lambda m: click.echo(f"  {m}", err=True)


@click.group()
@click.version_option(VERSION, prog_name="nbp")
def main():
    """Nonprofit Backpack: facts in, OKF v0.2 bundle out."""


def _ask_access(what: str, default: str) -> str:
    return click.prompt(f"  {what}: access", type=click.Choice(ACCESS_VALUES), default=default, show_choices=True)


def _ask_file_access(intake: Intake) -> None:
    click.echo("\nWho may read each file? public = anyone the backpack is shared with; private = the organization decides per request.")
    intake.access["organization"] = _ask_access("organization.md (registration and headline facts)", intake.access.get("organization", "public"))
    intake.access["about"] = _ask_access("about.md (summary, mission, vision)", intake.access.get("about", "public"))
    for d in intake.documents:
        d.access = _ask_access(f"documents/{Path(d.path or d.url).name}", d.access)
    intake.access_asked = True  # type: ignore[attr-defined]


def _interactive() -> Intake:
    """The funnel as prompts. Enter skips any step."""
    intake = Intake()
    click.echo("\nStep 1 of 4: the essentials, typed by you. Enter to skip any field.")
    for k, label in FIELDS[:3] + TEXTS[:1]:
        v = click.prompt(f"  {label}", default="", show_default=False)
        if v.strip():
            intake.typed[k] = v.strip()
    if click.confirm("  More fields (mission, vision, year founded, budget, staff, registration, website)?", default=False):
        for k, label in TEXTS[1:] + FIELDS[3:]:
            v = click.prompt(f"  {label}", default="", show_default=False)
            if v.strip():
                intake.typed[k] = v.strip()
    _ask_file_access(intake)

    click.echo("\nStep 2 of 4: EIN, for US organizations. Fills registration, budget and year founded where still empty.")
    intake.ein = click.prompt("  EIN", default="", show_default=False).strip()

    click.echo("\nStep 3 of 4: website. Crawled up to 10 pages; drafts summary/mission/vision where still empty (needs OPENROUTER_API_KEY).")
    intake.website = click.prompt("  Website", default=intake.typed.get("website", ""), show_default=True).strip()

    click.echo("\nStep 4 of 4: documents (audits, certificates, reports). Hashed, not parsed. Enter to finish.")
    while True:
        p = click.prompt("  File path or URL", default="", show_default=False).strip()
        if not p:
            break
        if not p.lower().startswith(("http://", "https://")) and not Path(p).is_file():
            click.echo(f"  not found: {p}"); continue
        d = DocumentInput(url=p) if p.lower().startswith("http") else DocumentInput(path=p)
        d.title = click.prompt("  Title", default=Path(p).stem)
        d.kind = click.prompt("  Kind (audit, registration certificate, annual report…)", default="")
        d.period = click.prompt("  Period (e.g. FY2025)", default="", show_default=False)
        d.access = _ask_access(Path(p).name, "private")
        intake.documents.append(d)
    return intake


def default_out(name: str) -> str:
    """~/Downloads/<name>-backpack.zip when ~/Downloads exists, else the current directory. Never the repo by default."""
    fname = f"{(name or 'backpack').lower().replace(' ', '-')}-backpack.zip"
    dl = Path.home() / "Downloads"
    return str(dl / fname) if dl.is_dir() else fname


@main.command()
@click.argument("facts", required=False, type=click.Path(exists=True, dir_okay=False))
@click.option("--ein", default="", help="US EIN to look up on ProPublica.")
@click.option("--url", "website", default="", help="Website to crawl.")
@click.option("--doc", multiple=True, type=click.Path(exists=True, dir_okay=False), help="Document file to hash and include (repeatable).")
@click.option("-o", "--out", default="", help="Output zip (default: ~/Downloads/<name>-backpack.zip; asked for interactively).")
@click.option("--creator", default=None, help="Creator actor, e.g. human:<uuid>. Default: the saved one in ~/.config/nonprofit-backpack.")
@click.option("--confirm", "self_confirm", is_flag=True, help="Self-confirm every concept (adds verified entries with content hashes).")
@click.option("--no-fetch", is_flag=True, help="Skip EIN lookup, crawling and drafting.")
@click.option("--redraft", is_flag=True, help="Let the LLM rewrite typed summary/mission/vision using everything (typed text, IRS facts, pages).")
@click.option("-i", "--interactive", is_flag=True, help="Prompt for everything step by step (default when no facts file or flags are given).")
@click.option("-y", "--yes", is_flag=True, help="Do not prompt for anything; use defaults (access public for organization/about, private for documents).")
def create(facts, ein, website, doc, out, creator, self_confirm, no_fetch, redraft, interactive, yes):
    """Create a backpack from a FACTS file, from flags, or interactively."""
    asked = False
    if facts:
        intake = Intake.from_file(facts)
    elif interactive or not (ein or website or doc):
        intake = _interactive(); asked = True
    else:
        intake = Intake()
    if ein:
        intake.ein = ein
    if website:
        intake.website = website
    intake.documents += [DocumentInput(path=p) for p in doc]
    if not intake.typed.get("name") and not intake.ein and not intake.website:
        raise click.UsageError("nothing to build from: give a name, an EIN or a website")
    # Sharing permissions are asked for every file at creation, in every mode, unless --yes or the facts file set them.
    if not yes and not asked and sys.stdin.isatty() and not (facts and "access" in (yaml.safe_load(Path(facts).read_text()) or {})):
        _ask_file_access(intake)

    if not yes and not out and sys.stdin.isatty():
        out = click.prompt("\nWhere should the backpack zip be written?", default=default_out(intake.typed.get("name", "")))
    click.echo("")
    bp = create_backpack(intake, creator=creator, fetch=not no_fetch, redraft=redraft, self_confirm=self_confirm, log=echo)
    out = str(Path(out or default_out(bp.title)).expanduser())
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    bp.write(out)
    if bp.issues:
        click.echo("\nSteps that did not succeed:", err=True)
        for i in bp.issues:
            click.echo(f"  ✗ {i}", err=True)
    if facts and not intake.id:            # keep the organization id stable across runs
        data = yaml.safe_load(Path(facts).read_text()) or {}
        data["id"] = bp.id
        Path(facts).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        echo(f"Wrote id {bp.id} back into {facts}.")
    elif not intake.id:
        echo(f"Backpack id {bp.id}: keep it, and pass it as `id:` next time so the backpack stays the same organization.")
    click.echo(f"\nYour creator ID is {get_creator_id(creator)}\nCopy it and keep it: it is written into every file as `generated.by`, and it is how your "
               f"confirmations are attributed. Pass it with --creator on another machine.\n", err=True)
    click.echo(f"Backpack written to {out}", err=True)
    _report(run_check(out))
    click.echo(out)


@main.command()
@click.argument("zip_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--concept", multiple=True, help="Concept path to confirm, e.g. organization.md (default: all).")
@click.option("--creator", default=None)
def confirm(zip_path, concept, creator):
    """Self-confirm concepts: append {by, at, sha256 of canonical content} to each."""
    bp = Backpack.read(zip_path)
    done = confirm_bp(bp, get_creator_id(creator), list(concept) or None)
    bp.write(zip_path)
    echo("Confirmed: " + ", ".join(done))


@main.command("add-doc")
@click.argument("zip_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("source")
@click.option("--title", default="")
@click.option("--kind", default="", help="audit, registration certificate, annual report…")
@click.option("--period", default="")
@click.option("--access", type=click.Choice(ACCESS_VALUES), default="private", show_default=True)
@click.option("--sha256", default="", help="For a URL: the known hash, if you have it; otherwise the file is fetched and hashed.")
@click.option("--creator", default=None)
def add_doc(zip_path, source, title, kind, period, access, sha256, creator):
    """Add a document (file path or URL) to an existing backpack."""
    bp = Backpack.read(zip_path)
    d = DocumentInput(url=source, sha256=sha256) if source.lower().startswith("http") else DocumentInput(path=source)
    d.title, d.kind, d.period, d.access = title, kind, period, access
    c = add_document(bp, d, get_creator_id(creator), log=echo)
    bp.write(zip_path)
    echo(f"Added {c.path} ({c.frontmatter['sha256'][:12]}…)")


@main.command()
@click.argument("zip_path", type=click.Path(exists=True))
def check(zip_path):
    """Validate a backpack (zip or unpacked directory): OKF conformance, required fields, footnotes, hashes, confirmations."""
    findings = run_check(zip_path)
    _report(findings)
    sys.exit(1 if any(f.level == "error" for f in findings) else 0)


@main.command()
def schemes():
    """List the curated registration scheme codes."""
    for code, label in SCHEMES:
        click.echo(f"{code:12} {label}")


def _report(findings):
    marks = {"error": "✗", "warn": "!", "info": "·"}
    for f in findings:
        click.echo(f"  {marks[f.level]} {f.message}", err=True)
