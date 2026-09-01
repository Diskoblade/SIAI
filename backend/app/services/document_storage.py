"""Private, backend-controlled document storage.

Files are addressed by an opaque random `storage_key` (a 32-char hex id), never
by a client-supplied path. Keys are strictly validated, so a caller can never
traverse outside the storage root. Writes are atomic (temp file + os.replace)
so a failed save never corrupts an existing document.
"""

from __future__ import annotations

import os
import re
import secrets
import tempfile
from pathlib import Path

from app.core.config import settings

_KEY_RE = re.compile(r"^[a-f0-9]{32}$")
# Only these logical buckets exist; nothing else is addressable.
_BUCKETS = {"templates", "approval_notes"}

# backend/ dir (two levels up from app/services/).
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class StorageError(Exception):
    """Raised on an invalid key/bucket or a missing file."""


def _root() -> Path:
    root = Path(settings.document_storage_dir)
    if not root.is_absolute():
        root = _BACKEND_DIR / root
    return root


def new_key() -> str:
    return secrets.token_hex(16)


def _resolve(bucket: str, storage_key: str) -> Path:
    if bucket not in _BUCKETS:
        raise StorageError("Invalid storage bucket.")
    if not _KEY_RE.match(storage_key or ""):
        raise StorageError("Invalid storage key.")
    base = (_root() / bucket).resolve()
    base.mkdir(parents=True, exist_ok=True)
    target = (base / f"{storage_key}.docx").resolve()
    # Defense in depth: the resolved path must stay inside the bucket.
    if base not in target.parents:
        raise StorageError("Resolved path escapes the storage root.")
    return target


def save_bytes(bucket: str, data: bytes, *, storage_key: str | None = None) -> str:
    """Write bytes atomically; return the storage key."""
    key = storage_key or new_key()
    target = _resolve(bucket, key)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, target)  # atomic on the same filesystem
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return key


def read_bytes(bucket: str, storage_key: str) -> bytes:
    target = _resolve(bucket, storage_key)
    if not target.exists():
        raise StorageError("Stored document not found.")
    return target.read_bytes()


def exists(bucket: str, storage_key: str) -> bool:
    try:
        return _resolve(bucket, storage_key).exists()
    except StorageError:
        return False


def delete(bucket: str, storage_key: str) -> None:
    try:
        _resolve(bucket, storage_key).unlink(missing_ok=True)
    except StorageError:
        pass
