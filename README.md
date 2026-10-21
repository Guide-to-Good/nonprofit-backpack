# Nonprofit Backpack

A **Nonprofit Backpack** is a small, portable bundle of facts about a nonprofit: who it is, where it is registered, its headline numbers, a short description, and hashes of the documents that back those up. It is an [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) bundle, a directory of markdown files with YAML frontmatter, so anything that reads OKF can read it, and it says where every value came from and who has confirmed it.

This repository is the piping to create one: a Python library and a command, `nbp`. Facts about an organization go in; a validated backpack zip comes out. It is published as a digital public good for a cross-org working group to fork, extend, and fold into their own products. It is deliberately minimal.

```
pip install -e . && playwright install chromium
nbp create                                   # interactive: four prompts, Enter skips any
nbp create facts.yaml -o riverbend.zip       # from a facts file
nbp create --ein 36-3673599 --url feedingamerica.org --doc audit.pdf -o ~/Downloads/fa.zip
nbp check riverbend.zip
```

## The funnel

The organization is asked for the essentials first, by hand. Each later step is optional and only fills what is still empty.

| Step | Input | Fills |
|---|---|---|
| 1 | Essentials, typed | name, legal name, country, summary; optionally mission, vision, year founded, budget, staff, registration scheme and ID, website. Plus `access` for each file. |
| 2 | EIN (US only) | registration, annual budget, year founded, from the IRS Form 990 via ProPublica |
| 3 | Website | crawled up to 10 pages in headless Chromium; summary, mission and vision drafted by an LLM if `OPENROUTER_API_KEY` is set |
| 4 | Documents | files or links, hashed with SHA-256, not parsed; each with a kind, period and `access` |

**Precedence is fixed: typed beats fetched, fetched beats drafted.** Every value keeps the origin of whichever source won, and that origin is written into the bundle as provenance. Any combination works: EIN and website with nothing typed gives a fully tool-drafted backpack marked as such; typed only skips everything. Nothing is required to produce a *valid* backpack; a *complete* one has name, legal name, country and summary.

The LLM sees everything when it drafts: the statements the organization typed (marked authoritative), the IRS facts, and the crawled pages. By default it writes only the statements that are still empty. `--redraft` lets it rewrite the typed ones too, using all of it; the typed originals are then cited as a source. Any step that does not succeed is reported at the end, and `backpack.issues` carries the same list for integrators.

The same funnel is one function for integrators:

```python
from nonprofit_backpack import Intake, DocumentInput, create_backpack

intake = Intake(typed={"name": "Riverbend Food Pantry", "country": "US", "summary": "..."},
                ein="12-3456789", website="https://riverbendpantry.example.org",
                documents=[DocumentInput(path="audit.pdf", kind="audit", access="private")])
backpack = create_backpack(intake, creator="human:<your user id>")
backpack.write("riverbend-backpack.zip")        # or backpack.to_bytes() for an HTTP response
```

`examples/integrate_fastapi.py` is the same thing behind a web form, in forty lines. The three fetchers can be swapped by passing your own callables to `resolve()`; `examples/make_examples.py` shows that.

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

- **`generated.by`** is always the creator who ran the tool, `human:<uuid>`, so every file names the person responsible. When any value in a file was fetched or drafted, `generated.tool` records `nonprofit-backpack/<version>`, with the model appended when an LLM drafted any of it, and the body's Provenance section says which values came from where and which were typed.
- **`sources`** and the body footnotes record which source each fetched value came from, keyed by `sources[].id` per OKF §5.1. Uncertain mappings carry a note rather than a silent guess.
- **Creator ID.** `nbp` mints a UUID v4 the first time it runs and keeps it in `~/.config/nonprofit-backpack/creator.json`, writing it as `human:<uuid>`. Integrators pass their own user identity instead. What identity scheme the `by` field should ultimately use is for the governance group.
- **Backpack ID.** The organization's UUID v4 is minted on first build and written back into the facts file, so regenerating next quarter keeps the same identity.
- **Confirmation.** `nbp confirm backpack.zip` (or `create --confirm`) appends a self-attestation to each concept:

  ```yaml
  verified:
    - by: human:<uuid>                 # the format of `by` is left to the governance/access/storage group
      at: 2026-10-21T12:00:00Z
      sha256: <canonical hash of this concept's content at check time>
      proof: <optional: a URL to the verifier's record, or a bundle-relative path to an attestation>
  ```

  `sha256` binds the confirmation to the exact content checked. Edit the concept afterwards and `nbp check` reports it as **lapsed** until it is confirmed again. A third party later uses the same shape with a `proof`. The canonical content is defined in one function, `canonical_hash()` in `bundle.py`: drop the `verified` key, serialize the rest as YAML with keys sorted recursively, normalize the body to LF with no trailing whitespace, hash the UTF-8 of `---\n<yaml>---\n<body>`.

## `access`: intent, enforced by storage

Every concept file carries `access: public | private`, chosen by the organization at creation. It is a label expressing intent. **OKF has no access control**; whatever stores or serves a backpack is responsible for honoring the label. `index.md` and `log.md` are reserved by OKF and carry no frontmatter.

Documents go through a one-method **storage socket**, `Storage.put(data, filename, access) -> resource`. The library hashes the bytes first, so the hash is the same whatever the backend. The default `LocalStorage` puts files in the zip's `files/` sidecar; `examples/storage_s3.py` shows the same socket against an object store that enforces `access`. Documents can be added later with `nbp add-doc`, by path or by URL.

## Validation

`nbp check <zip or directory>` reports errors, warnings and notes: OKF conformance (every concept has frontmatter and a `type`, the root index declares `okf_version`), the backpack's required keys, a UUID v4 `id`, `access` values, footnote labels that resolve to `sources[].id`, document hashes against the files in the zip, each concept's confirmation status, and completeness.

## Configuration

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | enables drafting; unset means summary, mission and vision stay as typed |
| `OPENROUTER_MODEL` | default `anthropic/claude-sonnet-4.5` |

There are no other settings and nothing is stored by the library except the creator ID file.

## What the website step does and does not do

It is a pure scrape: headless Chromium loads each page, waits for it to settle, scrolls so lazy content mounts, harvests embedded iframe text, and trafilatura extracts the readable text. Up to 10 same-domain pages, with pages that describe the organization (about, team, mission, impact…) first. Private and loopback addresses are refused. It takes about a minute. Sites behind aggressive bot protection may refuse a headless browser; the funnel then falls back to whatever was typed. Nothing from the pages is interpreted by code; only the LLM reads them, with the single prompt in `nonprofit_backpack/prompts/summary.md`.

## Fork it

Everything is self-contained: `git clone`, `pip install -e .`, `playwright install chromium`. Add your own fetchers by passing callables to `resolve()`, your own storage by implementing `Storage`, your own identity by passing `creator=`. The [demo walk-through](docs/DEMO.md) is five minutes in a terminal. See [CONTRIBUTING.md](CONTRIBUTING.md) and [PRIVACY.md](PRIVACY.md).

## Non-goals

Hosting or storing backpacks, access enforcement, auth and accounts, cryptographic signatures, third-party verifier identity, parsing documents, a web UI, multi-language prompts, and any organization-profile depth beyond the minimum.

## License

Apache-2.0.
