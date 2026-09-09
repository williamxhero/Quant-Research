"""Impact-selected acceptance planning and execution for QuantResearch."""

from .architecture import validate_test001_admission
from .cache import ArtifactCache
from .core import (
    AcceptanceFailure,
    AcceptancePlan,
    AcceptanceSelector,
    PlanStep,
    historical_timeout,
)
from .fixtures import AcceptanceSession, SQLiteSession
from .local import (
    FixedBaseProver,
    JsonlEventSink,
    LocalWheelBuilder,
    LocalWheelInstaller,
    build_fixed_base_diff,
    git_source_fingerprint,
)
from .migration import LegacyScopeMigration, migrate_legacy_scope
from .observability import audit_performance
from .runner import (
    InstalledEnvironment,
    PlanRunner,
    ProcessResult,
    RunReceipt,
    SubprocessProcess,
)
from .train import EnvironmentOutcome, GateRequest, ReleaseTrain

__all__ = [
    "AcceptanceFailure",
    "AcceptancePlan",
    "AcceptanceSelector",
    "AcceptanceSession",
    "ArtifactCache",
    "EnvironmentOutcome",
    "FixedBaseProver",
    "GateRequest",
    "InstalledEnvironment",
    "JsonlEventSink",
    "LegacyScopeMigration",
    "LocalWheelBuilder",
    "LocalWheelInstaller",
    "PlanRunner",
    "PlanStep",
    "ProcessResult",
    "ReleaseTrain",
    "RunReceipt",
    "SQLiteSession",
    "SubprocessProcess",
    "audit_performance",
    "build_fixed_base_diff",
    "git_source_fingerprint",
    "historical_timeout",
    "migrate_legacy_scope",
    "validate_test001_admission",
]
