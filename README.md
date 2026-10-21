# Nonprofit Backpack

A **Nonprofit Backpack** is a small, portable bundle of facts about a nonprofit: who it is, where it is registered, its headline numbers, a short description, and hashes of the documents that back those up. It is an [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) bundle, markdown files with YAML frontmatter, and it records where every value came from and who confirmed it.

This repo is the piping to make one: a Python library and a command, `nbp`. Facts go in; a validated zip comes out. It is a deliberately minimal digital public good for others to fork and build on. It is not a web app.

## Install

```
git clone https://github.com/Guide-to-Good/nonprofit-backpack && cd nonprofit-backpack
python -m venv .venv && source .venv/bin/activate
pip install -e . && playwright install chromium
export OPENROUTER_API_KEY=sk-or-...      # optional: enables drafting of summary, mission, vision
```

## Who uses it, and how

| Audience | Use case | Entry point |
|---|---|---|
| **Nonprofit staff** (an ED, or someone helping one) | Make a backpack for their own organization, answering questions | `nbp create` |
| **Nonprofit staff** | Add a new audit or report later; review and sign off on what was drafted | `nbp add-doc`, `nbp confirm` |
| **Platform or data teams** (CRMs, grants portals, TechSoup-style registries) | Export facts they already hold, one file per organization, and generate backpacks in bulk | `nbp create facts.yaml` |
| **Developers and scripters** | Try a lookup quickly, or run from cron, CI or a Makefile | `nbp create --ein … --url … -y` |
| **Product developers at member orgs** | Fold backpack creation into their own app, with their users, storage and registries | Python API, `examples/integrate_fastapi.py` |
| **Funders, platforms, verifiers** | Check a backpack they received is valid, complete and still confirmed | `nbp check` |
| **Working-group demos** | Show the flow end to end, in a terminal or a bare web form | `docs/DEMO.md`, the FastAPI example |

### Nonprofit staff: `nbp create`

```
nbp create
```

Four prompts, Enter skips any: essentials, EIN, website, documents. Then who may read each file (`public` or `private`), then where to save the zip (default `~/Downloads`). It prints each step as it runs, lists any step that failed, and ends with your creator ID to keep.

Later:

```
nbp add-doc ~/Downloads/my-backpack.zip audit.pdf --kind audit --period FY2025 --access private
nbp confirm ~/Downloads/my-backpack.zip                      # sign off on every file
nbp confirm ~/Downloads/my-backpack.zip --concept about.md   # or just one
```

### Platform and data teams: a facts file

Another system writes one YAML file per organization; `nbp` turns each into a backpack. The file is also the thing you edit and re-run: the backpack ID is written back into it on the first run, so the organization keeps the same identity.

```yaml
# riverbend.yaml
name: Riverbend Food Pantry
legal_name: Riverbend Food Pantry Inc
country: US
summary: Riverbend Food Pantry distributes groceries to households in Riverbend County, Ohio.
ein: 12-3456789                # optional: fills what is still empty from the IRS record
website: riverbendpantry.example.org   # optional: crawled, used for drafting
access: { organization: public, about: public }
documents:
  - { path: audit.pdf, kind: audit, period: FY2025, access: private }
```

```
nbp create riverbend.yaml -o out/riverbend.zip
for f in exports/*.yaml; do nbp create "$f" -y -o "out/$(basename "$f" .yaml).zip"; done
```

All fields: `name`, `legal_name`, `country`, `registration_scheme` (`nbp schemes` lists codes), `registration_id`, `year_founded`, `annual_budget`, `staff_count`, `website`, `summary`, `mission`, `vision`, `ein`, `crawl`, `access`, `documents`, `id`. Examples: `examples/facts-us.yaml`, `examples/facts-ke.yaml`.

### Developers and scripters: flags

```
nbp create --ein 36-3673599 --url feedingamerica.org -o ~/Downloads/fa.zip    # asks access, then runs
nbp create --ein 36-3673599 --url feedingamerica.org -y                       # no prompts, defaults
```

| Option | Effect |
|---|---|
| `--ein`, `--url`, `--doc` (repeatable) | Inputs, as in the funnel |
| `-o PATH` | Output zip; default `~/Downloads/<name>-backpack.zip` |
| `-y` | No prompts: public for organization and about, private for documents |
| `--confirm` | Self-confirm every file at creation |
| `--redraft` | Let the LLM rewrite typed statements using everything found |
| `--no-fetch` | Skip lookup, crawl and drafting |
| `--creator human:<uuid>` | Use a given creator ID instead of the saved one |
| `-i` | Interactive, even with flags |

### Product developers: the Python API

```python
from nonprofit_backpack import Intake, DocumentInput, create_backpack

intake = Intake(typed={"name": "Riverbend Food Pantry", "country": "US", "summary": "..."},
                ein="12-3456789", website="riverbendpantry.example.org",
                documents=[DocumentInput(path="audit.pdf", kind="audit", access="private")],
                access={"organization": "public", "about": "public"})
bp = create_backpack(intake, creator=f"human:{user.id}", storage=my_storage, log=progress.append)
bp.issues          # steps that did not succeed, to show the user
bp.to_bytes()      # the zip, for an HTTP response; or bp.write(path)
```

Three sockets to plug your own pieces in:

- **Identity**: pass `creator=` with your user's ID.
- **Storage**: implement `Storage.put(data, filename, access) -> resource` to keep documents in your store and enforce `access` there. `examples/storage_s3.py` is one.
- **Fetchers**: call `resolve(intake, lookup_ein=…, crawl_site=…, draft=…)` to swap in your own registry lookup (say, a UK Charity Commission client), scraper or model. `examples/make_examples.py` does this with stubs.

`examples/integrate_fastapi.py` shows it behind a web form with a live progress log. Run the crawl in a worker thread, not an `async` handler: the browser API it uses cannot run inside an event loop.

### Funders, platforms, verifiers: `nbp check`

```
nbp check riverbend.zip              # or an unpacked directory
```

Reports errors, warnings and notes: OKF conformance, required keys, a UUID v4 `id`, `access` values, footnotes that resolve to `sources`, document hashes against the files, each file's confirmation status (confirmed, lapsed, unconfirmed), and completeness. Exits non-zero on errors, so it works in CI.

### Demos

```
cat docs/DEMO.md                                                     # five-minute terminal walk-through
uvicorn examples.integrate_fastapi:app --reload --port 8765          # the bare web form
python examples/make_examples.py                                     # regenerate the example bundles
```

## How it works

The organization is asked for the essentials first. Each later step is optional and only fills what is still empty.

1. **Typed values** are recorded as the organization's own.
2. **EIN** (US only): one call to ProPublica's Nonprofit Explorer API, which returns the IRS record and figures ProPublica already extracted from e-filed Form 990s. We do not fetch the 990 itself. Seven values fill empty fields: name, legal name, country, scheme, registration ID, year founded (the IRS ruling year, with a caveat) and annual budget (total expenses from the latest filing).
3. **Website**: headless Chromium renders up to 10 same-domain pages, about, team and mission pages first, and extracts their text. The text is held in memory only, never stored in the backpack; the bundle records the site as a source.
4. **Drafting**, once, if a key is set and there is something to write: the LLM receives the typed statements (marked authoritative), the IRS values with their caveats, and the page text. It writes only the summary, mission or vision that are still empty, unless `--redraft`. It never sees documents.
5. **Documents** are hashed with SHA-256 and stored. They are never parsed.
6. **Build** writes the files with provenance, then **check** validates them.

**Precedence is fixed: typed beats fetched, fetched beats drafted.** Every value keeps the origin of whichever source won. Nothing is required for a *valid* backpack; a *complete* one has name, legal name, country and summary.

## Bundle shape

```
backpack/
  index.md            # okf_version: "0.2"; lists the concepts
  log.md              # creation, confirmations, documents added; newest first
  organization.md     # type: Organization
  about.md            # type: About: Summary, Mission, Vision sections
  documents/
    index.md
    <slug>.md         # type: Document, one per file or link
files/
  <original files>    # sidecar, outside the OKF tree, when documents travel with the zip
```

An annotated `organization.md` (complete bundles in [examples/](examples/)):

```yaml
---
id: 0f3d2a1b-9c8e-4d7f-8a6b-5c4d3e2f1a0b   # UUID v4, minted once and kept across runs  (required)
type: Organization                         #                                           (required)
title: Riverbend Food Pantry               # organization name                         (required)
legal_name: Riverbend Food Pantry Inc      #                                           (required)
access: public                             # who may read this file: public | private  (required)
generated:                                 # who produced the current content          (required)
  by: human:7f1e6c0a-…                     # always the creator who ran the tool
  at: '2026-10-21T12:00:00Z'
  tool: nonprofit-backpack/0.1.0+openrouter:anthropic/claude-sonnet-4.5   # present when any value was fetched or drafted
registration: { country: US, scheme: IRS-EIN, id: 12-3456789 }   # optional from here on
year_founded: 2009
annual_budget: 412350                      # total annual expenses, a number
staff_count: 6
website: https://riverbendpantry.example.org
sources:                                   # one entry per fetched source, with a stable id
  - { id: propublica, resource: https://projects.propublica.org/nonprofits/organizations/123456789, title: IRS Form 990 data … }
  - { id: website, resource: https://riverbendpantry.example.org, title: Organization website }
verified:                                  # confirmations, see below
  - { by: human:7f1e6c0a-…, at: '2026-10-21T12:00:00Z', sha256: 887eb4e4… }
---

# Provenance

- `legal_name`: legal name on the IRS record[^propublica]
- `year_founded`: IRS ruling year, when tax-exempt status was granted, which is not always the founding year[^propublica]
- `annual_budget`: total expenses in USD from the Form 990 for the fiscal year ending 2025-06[^propublica]

[^propublica]: IRS Form 990 data for EIN 12-3456789 via ProPublica Nonprofit Explorer
```

`about.md` holds `# Summary`, `# Mission` and `# Vision` (only the ones present), points at `./organization.md`, and carries the same `sources`. A drafted summary footnotes each sentence to the source it came from. The `[^website]: …` lines at the end of a body are standard markdown footnote definitions so renderers show the footnotes; the real join key is `sources[].id` in the frontmatter, per OKF §5.1. It is a separate file so a verifier can vouch for the registration and financial facts without endorsing the narrative.

`documents/<slug>.md` has `title`, `kind`, optional `period`, `resource` (a path into `files/` or a URL), `sha256` of the bytes, and `access`. Documents are never parsed.

## Provenance, identity and confirmation

- **`generated.by`** is always the creator, `human:<uuid>`. When any value in a file was fetched or drafted, `generated.tool` records `nonprofit-backpack/<version>`, plus the model if an LLM drafted any of it. The body's Provenance section says which values came from where.
- **`sources`** lists every fetched source with a stable `id`; body footnotes cite those ids per OKF §5.1. The `[^id]: …` lines at the end of a body are standard markdown footnote definitions so renderers show them.
- **Creator ID**: a UUID v4 minted on first run, kept in `~/.config/nonprofit-backpack/creator.json`. Integrators pass their own. The final identity scheme is for the governance group.
- **Backpack ID**: minted on first build and written back into the facts file.
- **Confirmation**: `nbp confirm` appends to each file

  ```yaml
  verified:
    - by: human:<uuid>          # format of `by` left to the governance/access/storage group
      at: 2026-10-21T12:00:00Z
      sha256: <canonical hash of this file's content when confirmed>
      proof: <optional: URL to a verifier's record, or a path to an attestation>
  ```

  Edit the file afterwards and `nbp check` reports it **lapsed**. A third-party verifier uses the same shape with a `proof`. `canonical_hash()` in `bundle.py`: drop `verified`, YAML with keys sorted recursively, body with LF endings and no trailing whitespace, SHA-256 of `---\n<yaml>---\n<body>`.

## `access`: intent, enforced by storage

Every file carries `access: public | private`, chosen by the organization at creation. **OKF has no access control**: the label records intent, and whatever stores or serves the backpack enforces it. For documents, that is the `Storage` adapter. `index.md` and `log.md` are reserved by OKF and carry no frontmatter.

## Configuration

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Enables drafting. Unset: drafting is skipped and reported. |
| `OPENROUTER_MODEL` | Default `anthropic/claude-sonnet-4.5`. |

Nothing else is stored except the creator ID file. See [PRIVACY.md](PRIVACY.md).

## Limits

Sites behind aggressive bot protection may refuse a headless browser; the funnel falls back to what was typed and reports it. A crawl takes about a minute. EIN lookup covers US organizations only; other registries plug in through the fetcher socket.

## Non-goals

Hosting or storing backpacks, access enforcement, auth and accounts, cryptographic signatures, third-party verifier identity, parsing documents, a web UI, multi-language prompts, and profile depth beyond the minimum.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md). Apache-2.0.
