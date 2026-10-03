"""Independent, read-only Manager GUI owner package."""

from .fixtures import FIXTURE_STATES, FixtureProvider, FixtureState, build_fixture, fixture_provider
from .models import (
    AVAILABILITY_JSON_SCHEMA,
    ERROR_JSON_SCHEMA,
    MANAGER_READ_MODEL_JSON_SCHEMA,
    MANAGER_READ_MODEL_SCHEMA,
    MANAGER_READ_MODEL_VERSION,
    SOURCE_REFERENCE_JSON_SCHEMA,
    STATUS_SEMANTICS,
    Availability,
    Derivation,
    Error,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
    Status,
)
from .provider import (
    FORBIDDEN_PROVIDER_METHODS,
    ManagerDataProvider,
    ReadOnlyManagerDataProvider,
    public_provider_methods,
)
from .seams import (
    HISTORICAL_DOCUMENT_INDEX_SEAM,
    PACKAGE_CATALOG_SEAM,
    READ_SEAM_DECISIONS,
    ReadSeamDecision,
)

__version__ = "0.1.0"

__all__ = [
    "AVAILABILITY_JSON_SCHEMA",
    "ERROR_JSON_SCHEMA",
    "FIXTURE_STATES",
    "FORBIDDEN_PROVIDER_METHODS",
    "HISTORICAL_DOCUMENT_INDEX_SEAM",
    "MANAGER_READ_MODEL_JSON_SCHEMA",
    "MANAGER_READ_MODEL_SCHEMA",
    "MANAGER_READ_MODEL_VERSION",
    "PACKAGE_CATALOG_SEAM",
    "READ_SEAM_DECISIONS",
    "SOURCE_REFERENCE_JSON_SCHEMA",
    "STATUS_SEMANTICS",
    "Availability",
    "Derivation",
    "Error",
    "FixtureProvider",
    "FixtureState",
    "ManagerDataProvider",
    "ManagerReadModel",
    "ReadModelError",
    "ReadModelStatus",
    "ReadOnlyManagerDataProvider",
    "ReadSeamDecision",
    "SourceReference",
    "Status",
    "__version__",
    "build_fixture",
    "fixture_provider",
    "public_provider_methods",
]
