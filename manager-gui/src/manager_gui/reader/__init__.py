"""Reader v1 UI-only contract; v0 owner/API schemas remain unchanged."""

from .models import (
    READER_PROJECTION_SCHEMA,
    READER_PROJECTION_VERSION,
    SAMPLE_BANNER_KEY,
    ClaimKind,
    FrozenJSON,
    ProjectionMode,
    ProjectionReference,
    RawSource,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    SampleData,
    TemplateValue,
    project_read_model,
)
from .provider import (
    ReadOnlyReaderProjectionProvider,
    ReaderProjectionProvider,
    ReaderProvider,
    V0ReaderProjectionProvider,
    project_v0,
)
from .schema import READER_PROJECTION_JSON_SCHEMA

__all__ = [
    "READER_PROJECTION_JSON_SCHEMA",
    "READER_PROJECTION_SCHEMA",
    "READER_PROJECTION_VERSION",
    "SAMPLE_BANNER_KEY",
    "ClaimKind",
    "FrozenJSON",
    "ProjectionMode",
    "ProjectionReference",
    "RawSource",
    "ReadOnlyReaderProjectionProvider",
    "ReaderAvailability",
    "ReaderAvailabilityStatus",
    "ReaderClaim",
    "ReaderProjection",
    "ReaderProjectionProvider",
    "ReaderProvider",
    "ReaderSummary",
    "SampleData",
    "TemplateValue",
    "V0ReaderProjectionProvider",
    "project_read_model",
    "project_v0",
]
