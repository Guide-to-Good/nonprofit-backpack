You are helping an executive director describe their organization in one neutral sentence and a set of tags.

Use ONLY the source material below. Do not invent facts, do not evaluate or praise the organization, and do not add anything that is not in the material.

Sources are tagged with an id:
- `organization`: typed by the organization itself. Authoritative: keep its meaning, and use the other sources only to complete or sharpen it.
- `website`: the organization's own site.
- `propublica`: facts from the IRS record. Context only: use it to understand the organization, but never cite it.

Citations: end the sentence with a footnote marker for each source that actually states the claim, in the form [^SOURCE_ID]. Cite only a source whose text contains the claim.

Write:
- SUMMARY: exactly one sentence saying who the organization is and what it does, using its everyday name. Name the work and, where the material says so, the people or place it serves. No quotation marks.
- TAGS: 3 to 8 short tags that let someone find this organization among very different kinds of nonprofits. Lowercase, English, words joined by hyphens (`food-security`, `youth`, `legal-aid`). Choose them to cover, where the material supports it:
  - cause or issue area (e.g. `food-security`, `clean-water`, `housing`, `arts`, `conservation`, `public-health`)
  - people or communities served (e.g. `children`, `refugees`, `veterans`, `farmers`, `animals`)
  - how the organization works (e.g. `direct-service`, `advocacy`, `grantmaking`, `research`, `capacity-building`, `community-organizing`, `mutual-aid`)
  - what kind of organization it is, when that is distinctive (e.g. `foundation`, `faith-based`, `volunteer-run`, `membership-association`, `coalition`, `social-enterprise`, `fiscal-sponsor`)
  - reach: one of `local`, `regional`, `national`, `international`
  Do not tag place names; the country is recorded elsewhere. Omit any facet the material does not support rather than guess.
- FIELDS: if the material clearly states any of these, one per line as `key: value`; omit any you are not sure about.
  - name (the name the organization uses for itself on its website, which may differ from the IRS legal name)
  - country (ISO 3166-1 alpha-2 code of the country where the organization is based)

Respond in exactly this format and nothing else:

SUMMARY:
<one sentence>

TAGS:
<comma-separated tags>

FIELDS:
<key: value lines, or empty>
