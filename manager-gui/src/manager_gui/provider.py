"""Public read-only adapter seam for Manager GUI data sources."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import ManagerReadModel

FORBIDDEN_PROVIDER_METHODS = frozenset(
    {
        "publish",
        "propose",
        "retry",
        "delete",
        "retire",
        "revalidate",
        "create",
        "update",
        "write",
    }
)


@runtime_checkable
class ManagerDataProvider(Protocol):
    """Read-only source contract consumed by all Manager GUI pages.

    Implementations may call an approved public API or return a fixture, but
    they must not expose domain mutations.  Resource names and snapshot tokens
    are opaque to this package and are carried only for provenance.
    """

    def read(
        self,
        resource: str = "atlas",
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        """Read one resource without changing owner state."""


ReadOnlyManagerDataProvider = ManagerDataProvider


def public_provider_methods(provider: object) -> tuple[str, ...]:
    """List callable public methods for the smoke-test/read-audit seam."""

    return tuple(
        sorted(
            name
            for name in dir(provider)
            if not name.startswith("_") and callable(getattr(provider, name))
        )
    )


__all__ = [
    "FORBIDDEN_PROVIDER_METHODS",
    "ManagerDataProvider",
    "ReadOnlyManagerDataProvider",
    "public_provider_methods",
]
