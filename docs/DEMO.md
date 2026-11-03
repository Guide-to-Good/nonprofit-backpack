# Demo: five minutes in a terminal

Setup once: `pip install -e . && playwright install chromium`. Optional: `export OPENROUTER_API_KEY=...` to see drafting.

**1. The typed path, no network.** Show `examples/facts-ke.yaml`, then:

```
nbp create examples/facts-ke.yaml --no-fetch --confirm -o maji-safi.zip
unzip -o maji-safi.zip -d maji-safi && cat maji-safi/backpack/organization.md maji-safi/backpack/about.md
```

Point at: `generated.by` is the creator, `access` on each file, the `verified` entry with its content hash, and no `tags`: only the LLM writes them, and this run did not fetch.

**2. The lookup path.** A real EIN and a real website, nothing typed:

```
nbp create --ein 36-3673599 --url feedingamerica.org -o ~/Downloads/feeding-america.zip
```

It first asks who may read `organization.md` and `about.md` (add `-y` to skip). Then watch the step log: IRS record found (Feeding America, EIN 36-3673599), each of the 10 pages as it loads, then drafting (or a clear "OPENROUTER_API_KEY not set" under *Steps that did not succeed*). The creator ID is printed at the end with a reminder to keep it. Open `organization.md`: the Provenance section footnotes the country and registration ID to the IRS record. Open `about.md`: a one-sentence drafted summary with `[^website]`, and the `tags`, or neither if no key.

**3. Combinations.** Typed essentials plus an EIN and a website: typed values win, the rest fills in, and the LLM sees all of it (typed summary, IRS facts, pages) when drafting the tags and anything missing. Add `--redraft` to let it rewrite a typed summary too.

```
nbp create -i          # type a name and summary, then give the EIN and website
```

**4. Change after confirmation.** Edit `organization.md` inside `maji-safi.zip` (any value), then:

```
nbp check maji-safi.zip        # organization.md: lapsed (content changed after confirmation)
nbp confirm maji-safi.zip --concept organization.md
nbp check maji-safi.zip        # confirmed again
```

**5. Folding it into a UI.** Run `uvicorn examples.integrate_fastapi:app --reload --port 8765` (after `pip install fastapi uvicorn python-multipart`) and open http://localhost:8765. Submit the form: a progress page shows the same step log as the terminal, live, then any failed steps and a download button. Open `examples/integrate_fastapi.py` to show it is the same calls as the CLI, run in a worker thread.
