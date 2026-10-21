# Demo: five minutes in a terminal

Setup once: `pip install -e . && playwright install chromium`. Optional: `export OPENROUTER_API_KEY=...` to see drafting.

**1. The typed path, no network.** Show `examples/facts-ke.yaml`, then:

```
nbp create examples/facts-ke.yaml --no-fetch --confirm -o maji-safi.zip
unzip -o maji-safi.zip -d maji-safi && cat maji-safi/backpack/organization.md maji-safi/backpack/about.md
```

Point at: `generated.by` is the creator, `access` on each file, the `verified` entry with its content hash, the document hashed into `files/`.

**2. The lookup path.** A real EIN and a real website, nothing typed:

```
nbp create --ein 36-3673599 --url feedingamerica.org -o ~/Downloads/feeding-america.zip
```

Watch the step log: IRS record found (Feeding America, EIN 36-3673599), each of the 10 pages as it loads, then drafting (or a clear "OPENROUTER_API_KEY not set" under *Steps that did not succeed*). The creator ID is printed at the end with a reminder to keep it. Open `organization.md`: the Provenance section footnotes each prefilled value to its source, with notes on the two uncertain mappings (ruling year, fiscal year of the budget). Open `about.md`: a drafted summary with `[^website]` on each sentence, or empty if no key.

**3. Combinations.** Typed essentials plus an EIN and a website: typed values win, the rest fills in, and the LLM sees all of it (typed statements, IRS facts, pages) when drafting what is missing. Add `--redraft` to let it rewrite the typed statements too.

```
nbp create -i          # answer the first three prompts, then give the EIN and website
```

**4. Change after confirmation.** Edit `organization.md` inside `maji-safi.zip` (any value), then:

```
nbp check maji-safi.zip        # organization.md: lapsed (content changed after confirmation)
nbp confirm maji-safi.zip --concept organization.md
nbp check maji-safi.zip        # confirmed again
```

**5. Add a document later, by file or by link.**

```
nbp add-doc maji-safi.zip annual-report.pdf --kind "annual report" --period FY2025 --access public
```

**6. Folding it into a UI.** Open `examples/integrate_fastapi.py`: forty lines, a form in, a zip out, same three calls as the CLI. Open `examples/storage_s3.py`: the one-method storage socket where `access` gets enforced.
