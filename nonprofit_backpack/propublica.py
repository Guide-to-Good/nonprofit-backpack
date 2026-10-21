"""IRS Form 990 lookup via ProPublica's Nonprofit Explorer API (free, no key). US organizations only.

Only an EIN the organization typed is looked up; materials are never scanned for one, since a
number found in a report is too often a funder's or a fiscal sponsor's.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

API = "https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json"
PAGE = "https://projects.propublica.org/nonprofits/organizations/{ein}"
TIMEOUT = 20.0


def normalize_ein(raw: str) -> str | None:
    """A user-typed EIN -> 'NN-NNNNNNN', or None unless it is exactly nine digits."""
    digits = re.sub(r"\D", "", raw or "")
    return f"{digits[:2]}-{digits[2:]}" if len(digits) == 9 else None


@dataclass
class LookupResult:
    name: str
    source: dict                               # an OKF sources entry
    fields: list[tuple[str, str, str]]         # (field, value, note) with notes on uncertain mappings


def lookup(ein: str) -> LookupResult | None:
    digits = ein.replace("-", "")
    resp = httpx.get(API.format(ein=digits), timeout=TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return map_response(resp.json(), ein)


def map_response(data: dict, ein: str) -> LookupResult | None:
    """ProPublica JSON -> prefills. Not-quite-one-to-one mappings carry a note rather than a guess."""
    org = data.get("organization") or {}
    if not org.get("name"):
        return None
    digits = ein.replace("-", "")
    source = {"id": "propublica", "resource": PAGE.format(ein=digits),
              "title": f"IRS Form 990 data for EIN {ein} via ProPublica Nonprofit Explorer"}
    fields: list[tuple[str, str, str]] = [
        ("name", org["name"], "IRS name on record; the everyday name may differ"),
        ("legal_name", org["name"], "legal name on the IRS record"),
        ("country", "US", ""),
        ("registration_scheme", "IRS-EIN", ""),
        ("registration_id", ein, ""),
    ]
    if org.get("ruling_date"):
        fields.append(("year_founded", str(org["ruling_date"])[:4],
                       "IRS ruling year, when tax-exempt status was granted, which is not always the founding year"))
    filings = [f for f in data.get("filings_with_data") or [] if f.get("tax_prd")]
    filings.sort(key=lambda f: f["tax_prd"], reverse=True)
    if filings and filings[0].get("totfuncexpns") is not None:
        prd = str(filings[0]["tax_prd"])
        fields.append(("annual_budget", str(filings[0]["totfuncexpns"]),
                       f"total expenses in USD from the Form 990 for the fiscal year ending {prd[:4]}-{prd[4:]}"))
    return LookupResult(name=org["name"], source=source, fields=fields)
