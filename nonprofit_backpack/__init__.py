"""Nonprofit Backpack: facts about an organization in, an OKF v0.2 bundle out."""
from .intake import Intake, DocumentInput, Resolved, resolve
from .bundle import Backpack, build, confirm, canonical_hash, add_document
from .storage import Storage, LocalStorage
from .identity import get_creator_id

TOOL = "nonprofit-backpack"
VERSION = "0.1.0"


def create_backpack(intake: Intake, *, creator: str | None = None, storage: Storage | None = None,
                    fetch: bool = True, self_confirm: bool = False, log=lambda msg: None) -> Backpack:
    """The whole funnel in one call: resolve the intake, build the bundle, optionally self-confirm."""
    resolved = resolve(intake, fetch=fetch, log=log)
    creator_id = get_creator_id(creator)
    backpack = build(resolved, creator_id, storage or LocalStorage(), log=log)
    if self_confirm:
        confirm(backpack, creator_id)
    return backpack


__all__ = ["Intake", "DocumentInput", "Resolved", "resolve", "Backpack", "build", "confirm", "canonical_hash",
           "add_document", "Storage", "LocalStorage", "get_creator_id", "create_backpack", "TOOL", "VERSION"]
