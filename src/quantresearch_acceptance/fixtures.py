"""Session-owned Workspace and SQLite isolation fixtures."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .core import AcceptanceFailure

_NAMESPACE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}")


class SQLiteSession:
    """One session connection with a rolled-back savepoint per test namespace."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path, isolation_level=None)
        self.initialization_count = 1

    @contextmanager
    def transaction(self, namespace: str) -> Iterator[sqlite3.Connection]:
        if _NAMESPACE.fullmatch(namespace) is None:
            raise AcceptanceFailure(f"invalid fixture namespace: {namespace}")
        savepoint = f"acceptance_{namespace}"
        self._connection.execute(f"SAVEPOINT {savepoint}")
        try:
            yield self._connection
        finally:
            self._connection.execute(f"ROLLBACK TO {savepoint}")
            self._connection.execute(f"RELEASE {savepoint}")

    def close(self) -> None:
        self._connection.close()


class AcceptanceSession:
    """Initialize expensive workspace state once and isolate callers by namespace."""

    def __init__(self, root: Path) -> None:
        self._workspace = (root.resolve() / "workspace")
        self._workspace.mkdir(parents=True, exist_ok=True)
        self.initialization_count = 1
        self.sqlite = SQLiteSession(self._workspace / "acceptance.sqlite3")

    @property
    def workspace(self) -> Path:
        return self._workspace

    def namespace(self, name: str) -> Path:
        if _NAMESPACE.fullmatch(name) is None:
            raise AcceptanceFailure(f"invalid fixture namespace: {name}")
        path = self._workspace / "namespaces" / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def close(self) -> None:
        self.sqlite.close()
