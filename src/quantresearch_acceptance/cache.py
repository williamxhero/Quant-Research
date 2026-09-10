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
        directory = self._directory(key)
        matches = tuple(directory.glob("*.whl")) if directory.is_dir() else ()
        if len(matches) > 1:
            raise AcceptanceFailure(f"artifact cache entry is ambiguous: {key}")
        return matches[0] if matches else None

    def store(self, key: str, content: bytes, *, filename: str = "artifact.whl") -> Path:
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise AcceptanceFailure("artifact cache filename is invalid")
        directory = self._directory(key)
        directory.mkdir(parents=True, exist_ok=True)
        existing = self.lookup(key)
        if existing is not None:
            if existing.name == filename and existing.read_bytes() == content:
                return existing
            raise AcceptanceFailure(f"immutable artifact cache conflict: {key}")
        path = directory / filename
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

    def _directory(self, key: str) -> Path:
        if _KEY.fullmatch(key) is None:
            raise AcceptanceFailure("artifact cache key is invalid")
        return self.root / key
