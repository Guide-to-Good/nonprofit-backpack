"""Creator identity: a UUID v4 minted once and kept in the home directory, written as `human:<uuid>`.

The actor format is OKF's convention for a person (§7). Whether a different identity scheme should
replace the UUID is for the governance group; the library only needs a stable string.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

CREATOR_FILE = Path.home() / ".config" / "nonprofit-backpack" / "creator.json"


def get_creator_id(explicit: str | None = None) -> str:
    """`human:<uuid>`. An explicit value (with or without the prefix) wins; else the saved one; else mint and save."""
    if explicit:
        return explicit if ":" in explicit else f"human:{explicit}"
    if CREATOR_FILE.exists():
        return json.loads(CREATOR_FILE.read_text())["creator_id"]
    creator = f"human:{uuid.uuid4()}"
    CREATOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREATOR_FILE.write_text(json.dumps({"creator_id": creator}, indent=2) + "\n")
    return creator


def new_backpack_id() -> str:
    return str(uuid.uuid4())
