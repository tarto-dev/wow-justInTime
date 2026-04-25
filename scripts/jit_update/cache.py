"""File-based HTTP response cache."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path


class FileCache:
    """Disk-backed cache keyed by URL hash with a TTL.

    Stores raw response bytes alongside a meta sidecar (timestamp).
    """

    def __init__(self, root: Path, ttl_seconds: float) -> None:
        self._root = root
        self._ttl = ttl_seconds
        self._root.mkdir(parents=True, exist_ok=True)

    def _paths(self, url: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        body = self._root / f"{digest}.bin"
        meta = self._root / f"{digest}.ts"
        return body, meta

    def get(self, url: str) -> bytes | None:
        """Return cached body if fresh, else None."""
        body, meta = self._paths(url)
        if not body.exists() or not meta.exists():
            return None
        try:
            ts = float(meta.read_text().strip())
        except (ValueError, OSError):
            return None
        if (time.time() - ts) > self._ttl:
            return None
        return body.read_bytes()

    def set(self, url: str, payload: bytes) -> None:
        """Write payload to disk and record the current timestamp."""
        body, meta = self._paths(url)
        body.write_bytes(payload)
        meta.write_text(str(time.time()))
