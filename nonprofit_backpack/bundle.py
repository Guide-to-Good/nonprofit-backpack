"""Build, read, write and confirm a backpack.

Bundle shape (OKF v0.2):
  backpack/index.md, log.md, organization.md, about.md
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .identity import new_backpack_id
from .intake import Origin, Resolved, FIELDS, TEXTS

RESERVED = ("index.md", "log.md")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- concepts ------------------------------------------------------------------------------------

@dataclass
class Concept:
    path: str                      # relative to backpack/, e.g. "organization.md"
    frontmatter: dict
    body: str

    def render(self) -> str:
        fm = yaml.safe_dump(self.frontmatter, sort_keys=False, allow_unicode=True, width=10_000)
        return f"---\n{fm}---\n\n{self.body.rstrip()}\n"

    @classmethod
    def parse(cls, path: str, text: str) -> "Concept":
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
        if not m:
            raise ValueError(f"{path}: no frontmatter block")
        return cls(path, yaml.safe_load(m.group(1)) or {}, m.group(2).lstrip("\n"))


def canonical_content(frontmatter: dict, body: str) -> str:
    """1. drop `verified`  2. YAML with keys sorted recursively  3. LF, no trailing whitespace per line
    4. `---\\n<yaml>---\\n<body>`."""
    fm = {k: v for k, v in frontmatter.items() if k != "verified"}
    y = yaml.safe_dump(fm, sort_keys=True, allow_unicode=True, width=10_000)
    b = "\n".join(line.rstrip(" \t") for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return f"---\n{y}---\n{b}"


def canonical_hash(frontmatter: dict, body: str) -> str:
    """What a `verified[].sha256` is compared against."""
    return sha256_hex(canonical_content(frontmatter, body).encode("utf-8"))


# ---- the backpack --------------------------------------------------------------------------------

@dataclass
class Backpack:
    concepts: list[Concept] = field(default_factory=list)
    log: list[str] = field(default_factory=list)               # log.md lines under today's date, newest first
    title: str = ""
    issues: list[str] = field(default_factory=list)            # funnel steps that did not succeed (not written to the bundle)

    @property
    def id(self) -> str:
        return str(self.concept("organization.md").frontmatter.get("id", ""))

    def concept(self, path: str) -> Concept:
        return next(c for c in self.concepts if c.path == path)

    def write(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for c in self.concepts:
                z.writestr(f"backpack/{c.path}", c.render())
            z.writestr("backpack/index.md", self._index())
            z.writestr("backpack/log.md", self._log())
        return buf.getvalue()

    @classmethod
    def read(cls, path: str | Path) -> "Backpack":
        bp = cls()
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.startswith("backpack/") and name.endswith(".md") and Path(name).name not in RESERVED:
                    bp.concepts.append(Concept.parse(name[len("backpack/"):], z.read(name).decode("utf-8")))
            bp._old_log = z.read("backpack/log.md").decode("utf-8") if "backpack/log.md" in z.namelist() else ""
        bp.title = str(bp.concept("organization.md").frontmatter.get("title", ""))
        return bp

    _old_log: str = ""

    def _index(self) -> str:
        return (f'---\nokf_version: "0.2"\n---\n\n# Nonprofit Backpack: {self.title}\n\n'
                f"* [{self.title}](organization.md) - Organization: name and registration\n"
                f"* [About](about.md) - About: summary and tags\n")

    def _log(self) -> str:
        today = now_iso()[:10]
        new = "".join(f"* {line}\n" for line in reversed(self.log))   # newest first
        old = self._old_log
        if old.startswith("# Backpack Update Log"):
            rest = old.split("\n", 1)[1].lstrip("\n")
            if rest.startswith(f"## {today}\n"):          # same day: merge under the existing heading
                return f"# Backpack Update Log\n\n## {today}\n{new}{rest[len(f'## {today}') + 1:]}"
            return f"# Backpack Update Log\n\n## {today}\n{new}\n{rest}"
        return f"# Backpack Update Log\n\n## {today}\n{new}"


# ---- building ------------------------------------------------------------------------------------

def _footnotes(sources: list[dict], ids: set[str]) -> str:
    return "\n".join(f"[^{s['id']}]: {s.get('title') or s['resource']}" for s in sources if s["id"] in ids)


def _generated(r: Resolved, keys: list[str], tool: str, at: str) -> dict:
    """`generated.by` is always the creator who ran the tool, so every file names the person. When any present
    value was fetched or drafted, `generated.tool` records the tool version (and model) that supplied it; the
    body's Provenance section says which values."""
    present = [k for k in keys if (r.values.get(k) or r.texts.get(k) or "").strip() or (k == "tags" and r.tags)]
    g = {"by": r.creator, "at": at}  # type: ignore[attr-defined]
    if any(r.origin[k].by != "human" for k in present):
        g["tool"] = tool + (f"+{r.llm_model}" if any(r.origin[k].by == "llm" for k in present) and r.llm_model else "")
    return g


def build(resolved: Resolved, creator: str, *, log=lambda m: None) -> Backpack:
    from . import TOOL, VERSION
    r, tool, at = resolved, f"{TOOL}/{VERSION}", now_iso()
    r.creator = creator  # type: ignore[attr-defined]
    v = r.values
    if not r.id:
        r.id = new_backpack_id()
    bp = Backpack(title=v.get("name", ""))

    # organization.md
    fm: dict = {"id": r.id, "type": "Organization", "title": v.get("name", ""),
                "access": r.access.get("organization", "public"),
                "generated": _generated(r, [k for k, _ in FIELDS], tool, at)}
    reg = {k2: v[k1] for k1, k2 in (("country", "country"), ("registration_id", "id")) if v.get(k1)}
    if reg:
        fm["registration"] = reg
    if r.sources:
        fm["sources"] = r.sources
    used, lines = set(), []
    for k, _ in FIELDS:
        o = r.origin.get(k)
        if o and o.source and v.get(k, "").strip():
            used.add(o.source)
            lines.append(f"- `{k}`" + (f": {o.note}" if o.note else "") + f"[^{o.source}]")
    human = [k for k, _ in FIELDS if r.origin.get(k, Origin("")).by == "human" and v.get(k, "").strip()]
    if lines and human:
        lines.append("- typed by the organization: " + ", ".join(f"`{k}`" for k in human))
    body = ("# Provenance\n\n" + "\n".join(lines) + "\n\n" + _footnotes(r.sources, used) + "\n") if lines \
        else "# Provenance\n\nAll values entered by the organization.\n"
    bp.concepts.append(Concept("organization.md", fm, body))

    # about.md
    fm = {"type": "About", "title": f"About {v.get('name', '')}", "organization": "./organization.md",
          "access": r.access.get("about", "public"),
          "generated": _generated(r, [k for k, _ in TEXTS] + ["tags"], tool, at)}
    if r.tags:
        fm["tags"] = r.tags
    if r.sources:
        fm["sources"] = r.sources
    sections = [f"# {k.capitalize()}\n\n{r.texts[k].strip()}" for k, _ in TEXTS if r.texts.get(k, "").strip()]
    text = "\n\n".join(sections)
    used = set(re.findall(r"\[\^([\w-]+)\]", text))
    defs = _footnotes(r.sources, used)
    bp.concepts.append(Concept("about.md", fm, text + ("\n\n" + defs if defs else "") + "\n"))

    bp.log.append(f"**Creation**: created by {creator} with {tool} at {at}.")
    log(f"Built backpack {r.id}.")
    return bp


# ---- confirmation --------------------------------------------------------------------------------

def confirm(bp: Backpack, creator: str, paths: list[str] | None = None) -> list[str]:
    """Append a self-attestation `{by, at, sha256}` to each named concept (default: all). Returns the paths."""
    done = []
    for c in bp.concepts:
        if paths and c.path not in paths:
            continue
        entry = {"by": creator, "at": now_iso(), "sha256": canonical_hash(c.frontmatter, c.body)}
        c.frontmatter.setdefault("verified", [])
        if isinstance(c.frontmatter["verified"], dict):
            c.frontmatter["verified"] = [c.frontmatter["verified"]]
        c.frontmatter["verified"].append(entry)
        done.append(c.path)
    if done:
        bp.log.append(f"**Confirmation**: {creator} confirmed {', '.join(done)}.")
    return done


def verification_status(c: Concept) -> str:
    """unconfirmed | confirmed | lapsed, judged against the concept's current canonical hash."""
    entries = c.frontmatter.get("verified") or []
    if isinstance(entries, dict):
        entries = [entries]
    if not entries:
        return "unconfirmed"
    current = canonical_hash(c.frontmatter, c.body)
    return "confirmed" if any(e.get("sha256") == current for e in entries) else "lapsed"
