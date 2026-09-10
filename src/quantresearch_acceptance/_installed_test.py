"""Named installed-wheel acceptance nodes shipped inside the wheel."""

from __future__ import annotations

from pathlib import Path

from .core import AcceptanceSelector
from .observability import audit_performance
from .train import ReleaseTrain


def _scope() -> dict[str, object]:
    command = {
        "owner": "quant-research",
        "argv": ["python", "-c", "pass"],
        "markers": [],
        "history_samples_seconds": [1, 2, 3],
    }
    return {
        "schema": "quant-research.acceptance-scope.v2",
        "spec": "TEST-001",
        "owners": {
            "quant-research": {
                "fixed_base": "1" * 40,
                "repository": ".",
                "diff_prefixes": ["src/"],
                "source_patterns": ["src/"],
                "import_names": ["quantresearch_acceptance"],
                "build_argv": ["uv", "build"],
                "source_fingerprint": "sha256:" + "2" * 64,
            }
        },
        "public_contract_sources": ["src/contract.py"],
        "source_to_direct_tests": {"src/contract.py": ["installed/test_contract.py"]},
        "levels": {
            level: {"budget_seconds": budget, "commands": [dict(command)]}
            for level, budget in (("L0", 60), ("L1", 180), ("L2", 600), ("L3", 300))
        },
        "marker_policy": {
            "allowed": ["connected", "oci", "release", "slow"],
            "ordinary_exclusion": "not slow and not oci and not connected and not release",
        },
        "evidence": {
            "artifact_root": "artifacts/{plan_id}",
            "event_log": "events.jsonl",
            "plan": "plan.json",
        },
    }


def _diff() -> dict[str, object]:
    return {
        "schema": "quant-research.fixed-base-diff.v1",
        "fixed_bases": {"quant-research": "1" * 40},
        "source_fingerprints": {"quant-research": "sha256:" + "2" * 64},
        "changed_sources": [{"path": "src/contract.py", "fingerprint": "sha256:" + "3" * 64}],
    }


def test_installed_wheel_has_no_source_checkout_precedence() -> None:
    package = Path(__file__).resolve()
    assert "site-packages" in package.as_posix()
    assert not (Path.cwd() / "src/quantresearch_acceptance").exists()


def test_installed_selector_replays_the_frozen_public_contract() -> None:
    plan = AcceptanceSelector().select(_scope(), _diff(), phase="spec")
    assert plan.levels == ("L0", "L1", "L2", "L3")
    assert plan.steps[-1].replay_count == 2
    assert plan.steps[-1].environment == "installed-no-source"


def test_installed_marker_and_release_train_contracts() -> None:
    assert (
        audit_performance(
            [
                {
                    "nodeid": "installed::fast",
                    "duration_seconds": 1,
                    "file_duration_seconds": 1,
                    "markers": [],
                    "explanation": "",
                }
            ]
        )
        == ()
    )
    specs = tuple(f"SPEC-{number:03d}" for number in range(1, 33))
    train = ReleaseTrain(specs)
    gates = train.record(specs[0], "sha256:" + "4" * 64)
    assert tuple(gate.kind for gate in gates) == ("incremental",)
