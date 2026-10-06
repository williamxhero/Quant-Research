"""Read-only seams that turn the published ManagerReadModel v0 into Reader v1."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from manager_gui.models import ManagerReadModel
from manager_gui.provider import ManagerDataProvider

from .models import ProjectionMode, ProjectionReference, ReaderProjection, project_read_model


@runtime_checkable
class ReaderProjectionProvider(Protocol):
    """A provider that only reads and projects one public envelope."""

    def read(
        self,
        resource: str = "atlas",
        *,
        snapshot_token: str | None = None,
        mode: ProjectionMode | str = ProjectionMode.READER,
    ) -> ReaderProjection:
        """Read one projection; ``mode`` is a reference, not a v0 mutation."""


class V0ReaderProjectionProvider:
    """Adapter from the existing public v0 provider; it never changes that model."""

    def __init__(self, provider: ManagerDataProvider) -> None:
        if not isinstance(provider, ManagerDataProvider):
            raise TypeError("provider must implement the read-only ManagerDataProvider seam")
        self._provider = provider

    def read(
        self,
        resource: str = "atlas",
        *,
        snapshot_token: str | None = None,
        mode: ProjectionMode | str = ProjectionMode.READER,
    ) -> ReaderProjection:
        ProjectionMode(mode)  # Validate the compatibility reference at the seam.
        model = self._provider.read(resource, snapshot_token=snapshot_token)
        return project_read_model(model)

    def mode_reference(
        self,
        projection: ReaderProjection,
        mode: ProjectionMode | str,
    ) -> ProjectionReference:
        """Return Expert/Raw compatibility metadata without rewriting v0."""

        return projection.mode_reference(mode)


# Explicit spelling used by callers that prefer the seam's purpose in a type name.
ReadOnlyReaderProjectionProvider = ReaderProjectionProvider
ReaderProvider = ReaderProjectionProvider


def project_v0(
    model: ManagerReadModel,
    *,
    raw_bytes: bytes | None = None,
) -> ReaderProjection:
    """Project an already-read v0 envelope without sample-data inheritance."""

    return project_read_model(model, raw_bytes=raw_bytes)


__all__ = [
    "ReadOnlyReaderProjectionProvider",
    "ReaderProjectionProvider",
    "ReaderProvider",
    "V0ReaderProjectionProvider",
    "project_v0",
]
