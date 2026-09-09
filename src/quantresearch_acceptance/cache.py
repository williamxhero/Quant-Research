"""Immutable fixed-base artifact cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .core import AcceptanceFailure

_KEY = re.compile(r"[0-9a-f]{64}")


class ArtifactCache:
    """Content-safe cache whose key freezes source and build identities."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(
        *,
        owner: str,
        fixed_sha: str,
        source_fingerprint: str,
        build_argv: tuple[str, ...],
    ) -> str:
        material = json.dumps(
            {
                "owner": owner,
                "fixed_sha": fixed_sha,
                "source_fingerprint": source_fingerprint,
                "build_argv": list(build_argv),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(material).hexdigest()

    def lookup(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.is_file() else None

    def store(self, key: str, content: bytes) -> Path:
        path = self._path(key)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError as exc:
            if path.read_bytes() != content:
                raise AcceptanceFailure(f"immutable cache collision: {key}") from exc
            return path
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def _path(self, key: str) -> Path:
        if _KEY.fullmatch(key) is None:
            raise AcceptanceFailure("artifact cache key is invalid")
        return self.root / f"{key}.whl"
