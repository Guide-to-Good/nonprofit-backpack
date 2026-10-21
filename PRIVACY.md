# Privacy

`nonprofit-backpack` is a library and a command that run on your own machine or inside your own application. It has no server, no accounts, no analytics and no telemetry. The maintainers receive nothing.

**What it keeps.** One file, `~/.config/nonprofit-backpack/creator.json`, holding the random creator ID it minted for you. Nothing else is written outside the output you ask for.

**What leaves your machine, and only when you use that step.**

- *EIN lookup*: the EIN is sent to ProPublica's Nonprofit Explorer API.
- *Website crawl*: your organization's own website is loaded in a headless browser from your machine.
- *Drafting*: the text of the crawled pages is sent to OpenRouter under your own API key, and from there to the model you chose. Their handling of that data is governed by their policies.
- *Linked documents*: a document given by URL without a hash is downloaded once to hash it.

**The backpack you produce** may contain personal data, for example staff names in an uploaded document. You decide what goes in and where it goes afterwards. The `access` label on each file records your intent; the file format does not enforce it, the storage you choose does.
