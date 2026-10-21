"""Build, read, write and confirm a backpack.

Bundle shape (OKF v0.2):
  backpack/index.md, log.md, organization.md, about.md, documents/index.md, documents/<slug>.md
  files/<original files>   (sidecar, outside the OKF tree, when LocalStorage is used)
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from .identity import new_backpack_id
from .intake import DocumentInput, Resolved, FIELDS, TEXTS
from .storage import Storage, LocalStorage

RESERVED = ("index.md", "log.md")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(s: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", s.lower())) or "document"


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
    files: dict[str, bytes] = field(default_factory=dict)      # files/<name> sidecar contents
    log: list[str] = field(default_factory=list)               # log.md lines under today's date, newest first
    title: str = ""

    @property
    def id(self) -> str:
        return str(self.concept("organization.md").frontmatter.get("id", ""))

    def concept(self, path: str) -> Concept:
        return next(c for c in self.concepts if c.path == path)

    def documents(self) -> list[Concept]:
        return [c for c in self.concepts if c.path.startswith("documents/")]

    def write(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for c in self.concepts:
                z.writestr(f"backpack/{c.path}", c.render())
            z.writestr("backpack/index.md", self._index())
            z.writestr("backpack/documents/index.md", self._documents_index())
            z.writestr("backpack/log.md", self._log())
            for name, data in self.files.items():
                z.writestr(name, data)
        return buf.getvalue()

    @classmethod
    def read(cls, path: str | Path) -> "Backpack":
        bp = cls()
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.startswith("backpack/") and name.endswith(".md") and Path(name).name not in RESERVED:
                    bp.concepts.append(Concept.parse(name[len("backpack/"):], z.read(name).decode("utf-8")))
                elif name.startswith("files/") and not name.endswith("/"):
                    bp.files[name] = z.read(name)
            bp._old_log = z.read("backpack/log.md").decode("utf-8") if "backpack/log.md" in z.namelist() else ""
        bp.title = str(bp.concept("organization.md").frontmatter.get("title", ""))
        return bp

    _old_log: str = ""

    def _index(self) -> str:
        return (f'---\nokf_version: "0.2"\n---\n\n# Nonprofit Backpack: {self.title}\n\n'
                f"* [{self.title}](organization.md) - Organization: registration and headline facts\n"
                f"* [About](about.md) - About: summary, mission and vision\n"
                f"* [Documents](documents/) - {len(self.documents())} document(s)\n")

    def _documents_index(self) -> str:
        rows = [f"* [{c.frontmatter.get('title')}]({Path(c.path).name}) - {c.frontmatter.get('kind', '')}"
                + (f", {c.frontmatter['period']}" if c.frontmatter.get("period") else "") for c in self.documents()]
        return "# Documents\n\n" + ("\n".join(rows) if rows else "No documents.") + "\n"

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


def _num(v: str):
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return float(v)
        except (TypeError, ValueError):
            return v


def _generated_by(r: Resolved, keys: list[str], tool: str) -> str:
    """Concept-level actor: the tool only if every present value is still tool- or LLM-provided.
    `website` is excluded: like the EIN, it is a key the organization supplies to run the tool, not a fact it authored."""
    present = [k for k in keys if k != "website" and (r.values.get(k) or r.texts.get(k) or "").strip()]
    if present and all(r.origin[k].by != "human" for k in present):
        return tool + (f"+{r.llm_model}" if any(r.origin[k].by == "llm" for k in present) and r.llm_model else "")
    return r.creator  # type: ignore[attr-defined]


def build(resolved: Resolved, creator: str, storage: Storage | None = None, *, log=lambda m: None) -> Backpack:
    from . import TOOL, VERSION
    r, tool, at = resolved, f"{TOOL}/{VERSION}", now_iso()
    r.creator = creator  # type: ignore[attr-defined]
    storage = storage or LocalStorage()
    v = r.values
    if not r.id:
        r.id = new_backpack_id()
    bp = Backpack(title=v.get("name", ""))

    # organization.md
    fm: dict = {"id": r.id, "type": "Organization", "title": v.get("name", ""), "legal_name": v.get("legal_name", ""),
                "access": r.access.get("organization", "public"),
                "generated": {"by": _generated_by(r, [k for k, _ in FIELDS], tool), "at": at}}
    reg = {k2: v[k1] for k1, k2 in (("country", "country"), ("registration_scheme", "scheme"), ("registration_id", "id")) if v.get(k1)}
    if reg:
        fm["registration"] = reg
    for k in ("year_founded", "annual_budget", "staff_count"):
        if v.get(k):
            fm[k] = _num(v[k])
    if v.get("website"):
        fm["website"] = v["website"]
    if r.sources:
        fm["sources"] = r.sources
    used, lines = set(), []
    for k, _ in FIELDS:
        o = r.origin.get(k)
        if o and o.source and v.get(k, "").strip():
            used.add(o.source)
            lines.append(f"- `{k}`" + (f": {o.note}" if o.note else "") + f"[^{o.source}]")
    body = ("# Provenance\n\n" + "\n".join(lines) + "\n\n" + _footnotes(r.sources, used) + "\n") if lines \
        else "# Provenance\n\nAll values entered by the organization.\n"
    bp.concepts.append(Concept("organization.md", fm, body))

    # about.md
    fm = {"type": "About", "title": f"About {v.get('name', '')}", "organization": "./organization.md",
          "access": r.access.get("about", "public"),
          "generated": {"by": _generated_by(r, [k for k, _ in TEXTS], tool), "at": at}}
    if r.sources:
        fm["sources"] = r.sources
    sections = [f"# {k.capitalize()}\n\n{r.texts[k].strip()}" for k, _ in TEXTS if r.texts.get(k, "").strip()]
    text = "\n\n".join(sections)
    used = set(re.findall(r"\[\^([\w-]+)\]", text))
    defs = _footnotes(r.sources, used)
    bp.concepts.append(Concept("about.md", fm, text + ("\n\n" + defs if defs else "") + "\n"))

    # documents
    for d in r.documents:
        _add_document_concept(bp, d, creator, storage, at, log)
    bp.files.update(storage.collect())
    bp.log.append(f"**Creation**: created by {tool} at {at}.")
    log(f"Built backpack {r.id} with {len(bp.documents())} document(s).")
    return bp


def _add_document_concept(bp: Backpack, d: DocumentInput, creator: str, storage: Storage, at: str, log) -> Concept:
    if d.path:
        data = Path(d.path).read_bytes()
        filename = Path(d.path).name
    elif d.url:
        if d.sha256:
            data, filename = b"", Path(d.url).name or "document"
        else:
            log(f"Fetching {d.url} to hash it…")
            resp = httpx.get(d.url, follow_redirects=True, timeout=60.0)
            resp.raise_for_status()
            data, filename = resp.content, Path(d.url).name or "document"
    else:
        raise ValueError("a document needs a path or a url")
    digest = d.sha256 or sha256_hex(data)
    resource = d.url if d.url else storage.put(data, filename, d.access)
    title = d.title or Path(filename).stem
    slug = slugify(Path(filename).stem)
    while any(c.path == f"documents/{slug}.md" for c in bp.concepts):
        slug += "-2"
    fm = {"type": "Document", "title": title, "kind": d.kind, "resource": resource, "sha256": digest,
          "access": d.access, "generated": {"by": creator, "at": at}}
    if d.period:
        fm["period"] = d.period
    c = Concept(f"documents/{slug}.md", fm, "Provided by the organization. Not parsed; the hash is of the file bytes.\n")
    bp.concepts.append(c)
    return c


def add_document(bp: Backpack, d: DocumentInput, creator: str, storage: Storage | None = None, *, log=lambda m: None) -> Concept:
    """Add a document to an existing backpack: hash, store, write the concept, log it."""
    storage = storage or LocalStorage()
    if isinstance(storage, LocalStorage):
        storage.files = {Path(k).name: v for k, v in bp.files.items()}
    c = _add_document_concept(bp, d, creator, storage, now_iso(), log)
    bp.files.update(storage.collect())
    bp.log.append(f"**Update**: added document [{c.frontmatter['title']}]({c.path}).")
    return c


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
