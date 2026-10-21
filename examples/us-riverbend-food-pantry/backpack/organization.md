---
id: 0f3d2a1b-9c8e-4d7f-8a6b-5c4d3e2f1a0b
type: Organization
title: Riverbend Food Pantry
legal_name: Riverbend Food Pantry Inc
access: public
generated:
  by: human:7f1e6c0a-3b2d-4e8f-9a1b-2c3d4e5f6a7b
  at: '2026-10-21T12:00:00Z'
  tool: nonprofit-backpack/0.1.0+openrouter:anthropic/claude-sonnet-4.5
registration:
  country: US
  scheme: IRS-EIN
  id: 12-3456789
year_founded: 2009
annual_budget: 412350
staff_count: 6
website: https://riverbendpantry.example.org
sources:
- id: propublica
  resource: https://projects.propublica.org/nonprofits/organizations/123456789
  title: IRS Form 990 data for EIN 12-3456789 via ProPublica Nonprofit Explorer
- id: website
  resource: https://riverbendpantry.example.org
  title: Organization website
verified:
- by: human:7f1e6c0a-3b2d-4e8f-9a1b-2c3d4e5f6a7b
  at: '2026-10-21T12:00:00Z'
  sha256: 47ade9790762d696ffd91f25893bcad4462475154141745028419e262a0ea016
---

# Provenance

- `legal_name`: legal name on the IRS record[^propublica]
- `country`[^propublica]
- `registration_scheme`[^propublica]
- `registration_id`[^propublica]
- `year_founded`: IRS ruling year, when tax-exempt status was granted, which is not always the founding year[^propublica]
- `annual_budget`: total expenses in USD from the Form 990 for the fiscal year ending 2025-06[^propublica]
- `staff_count`: suggested by the LLM from the website text[^website]
- typed by the organization: `name`

[^propublica]: IRS Form 990 data for EIN 12-3456789 via ProPublica Nonprofit Explorer
[^website]: Organization website
