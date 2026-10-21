"""The storage socket. The library hashes document bytes itself, then hands them to a Storage.

`put` returns the `resource` written into the document concept: a bundle-relative path for the
default LocalStorage, or a URL for anything remote. `access` is the organization's intent for that
document; a remote adapter is where it gets enforced. OKF itself has no access control.
"""
from __future__ import annotations

from typing import Protocol


class Storage(Protocol):
    def put(self, data: bytes, filename: str, access: str) -> str: ...
    def collect(self) -> dict[str, bytes]: ...   # files to add to the zip, if any


class LocalStorage:
    """Default: the file travels inside the zip, in `files/` next to the OKF tree."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def put(self, data: bytes, filename: str, access: str) -> str:
        name, n = filename, 1
        while name in self.files:
            n += 1
            stem, dot, ext = filename.rpartition(".")
            name = f"{stem or ext}-{n}.{ext}" if dot else f"{filename}-{n}"
        self.files[name] = data
        return f"../../files/{name}"

    def collect(self) -> dict[str, bytes]:
        return {f"files/{name}": data for name, data in self.files.items()}
