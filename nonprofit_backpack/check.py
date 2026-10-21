"""Validate a backpack zip: OKF conformance, the backpack's own rules, completeness, hashes, confirmations."""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from .bundle import Backpack, Concept, RESERVED, sha256_hex, verification_status
from .intake import ACCESS_VALUES, REQUIRED_FOR_COMPLETE
from .countries import COUNTRY_CODES


@dataclass
class Finding:
    level: str      # "error" | "warn" | "info"
    message: str


def _open(path: Path):
    """(names, read) for a zip file or an unpacked directory holding backpack/ and files/."""
    if path.is_dir():
        names = [str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()]
        return names, lambda n: (path / n).read_bytes()
    z = zipfile.ZipFile(path)
    return z.namelist(), z.read


def check(path: str | Path) -> list[Finding]:
    out: list[Finding] = []
    err = lambda m: out.append(Finding("error", m))
    warn = lambda m: out.append(Finding("warn", m))
    info = lambda m: out.append(Finding("info", m))

    names, read = _open(Path(path))
    if True:
        # OKF §11: every non-reserved .md has parseable frontmatter with a non-empty type
        concepts: list[Concept] = []
        for n in names:
            if n.startswith("backpack/") and n.endswith(".md") and Path(n).name not in RESERVED:
                try:
                    c = Concept.parse(n[len("backpack/"):], read(n).decode("utf-8"))
                except Exception as e:
                    err(f"{n}: {e}"); continue
                if not str(c.frontmatter.get("type", "")).strip():
                    err(f"{n}: frontmatter has no `type`")
                concepts.append(c)
        if "backpack/index.md" not in names:
            err("backpack/index.md is missing")
        else:
            idx = read("backpack/index.md").decode("utf-8")
            m = re.match(r"^---\n(.*?)\n---", idx, re.S)
            ver = (yaml.safe_load(m.group(1)) or {}).get("okf_version") if m else None
            if str(ver) != "0.2":
                err(f"index.md should declare okf_version \"0.2\", found {ver!r}")
        if "backpack/log.md" not in names:
            warn("backpack/log.md is missing")
        files = {n: read(n) for n in names if n.startswith("files/") and not n.endswith("/")}

    by_path = {c.path: c for c in concepts}
    org, about = by_path.get("organization.md"), by_path.get("about.md")
    if not org:
        err("organization.md is missing"); return out
    if not about:
        err("about.md is missing")

    # Backpack rules
    fm = org.frontmatter
    for k in ("id", "type", "title", "legal_name", "access", "generated"):
        if not fm.get(k):
            err(f"organization.md: `{k}` is required")
    if fm.get("type") != "Organization":
        err("organization.md: type must be Organization")
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", str(fm.get("id", ""))):
        err("organization.md: `id` is not a UUID v4")
    if isinstance(fm.get("generated"), dict) and not fm["generated"].get("by"):
        err("organization.md: generated.by is required")
    reg = fm.get("registration") or {}
    if reg.get("country") and reg["country"] not in COUNTRY_CODES:
        warn(f"organization.md: registration.country {reg['country']!r} is not an ISO 3166-1 alpha-2 code")
    if about and about.frontmatter.get("organization") != "./organization.md":
        err("about.md: `organization` must be ./organization.md")

    for c in concepts:
        a = c.frontmatter.get("access")
        if a not in ACCESS_VALUES:
            err(f"{c.path}: access must be one of {ACCESS_VALUES}, found {a!r}")
        # footnote labels resolve to sources[].id
        ids = {s.get("id") for s in (c.frontmatter.get("sources") or []) if isinstance(s, dict)}
        for label in set(re.findall(r"\[\^([\w-]+)\]", c.body)):
            if label not in ids:
                err(f"{c.path}: footnote [^{label}] has no matching sources[].id")
        # document hashes
        if c.path.startswith("documents/"):
            res, digest = str(c.frontmatter.get("resource", "")), str(c.frontmatter.get("sha256", ""))
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                err(f"{c.path}: sha256 is missing or not 64 hex chars")
            elif res.startswith("../../files/"):
                data = files.get("files/" + res[len("../../files/"):])
                if data is None:
                    err(f"{c.path}: resource {res} is not in the zip")
                elif sha256_hex(data) != digest:
                    err(f"{c.path}: sha256 does not match {res}")
            else:
                info(f"{c.path}: resource is external ({res}); hash not checked")
        status = verification_status(c)
        (warn if status == "lapsed" else info)(f"{c.path}: {status}" + (" (content changed after confirmation)" if status == "lapsed" else ""))

    # completeness
    have = {"name": fm.get("title", ""), "legal_name": fm.get("legal_name", ""), "country": reg.get("country", ""),
            "summary": "# Summary" in (about.body if about else "")}
    missing = [k for k in REQUIRED_FOR_COMPLETE if not have.get(k)]
    if missing:
        warn("valid but incomplete: missing " + ", ".join(missing))
    else:
        info("complete: name, legal name, country and summary are present")
    return out
