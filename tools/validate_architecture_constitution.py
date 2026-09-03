"""Validate the QuantResearch architecture constitution and future-SPEC admissions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "architecture-constitution.v1.json"
EXPECTED_FLOW = [
    "source-evidence",
    "strategy-package",
    "quant-runtime",
    "apex-research-evidence",
    "strategy-reporting",
]
REQUIRED_DECLARATIONS = {
    "canonical_owner",
    "public_seam",
    "identity_impact",
    "evidence_level",
    "fail_closed_behavior",
}


class ConstitutionError(ValueError):
    """The policy or an admission record violates the architecture constitution."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConstitutionError(f"cannot read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConstitutionError(f"JSON root must be an object: {path}")
    return value


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema") != "quant-research.architecture-constitution.v1":
        raise ConstitutionError("policy schema must be quant-research.architecture-constitution.v1")
    if policy.get("canonical_flow") != EXPECTED_FLOW:
        raise ConstitutionError("policy canonical_flow does not match the constitutional flow")

    owners = policy.get("owners")
    if not isinstance(owners, dict) or set(owners) != {
        "strategy_workspace",
        "quant_runtime",
        "apex_research",
        "strategy_reporting",
        "markethub",
    }:
        raise ConstitutionError("policy must declare exactly the five canonical owners")
    for owner, definition in owners.items():
        if not isinstance(definition, dict) or not definition.get("owns") or not definition.get(
            "public_seams"
        ):
            raise ConstitutionError(f"owner {owner} must declare owned capabilities and public seams")

    evidence = policy.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("formal_truth") != "nautilustrader-output":
        raise ConstitutionError("NautilusTrader output must remain the formal truth")
    if evidence.get("discovery_engine") != "qlib" or evidence.get("discovery_is_formal_truth") is not False:
        raise ConstitutionError("Qlib must remain discovery-only")

    adoption = policy.get("external_adoption")
    if not isinstance(adoption, dict) or set(adoption.get("categories", [])) != {
        "adapter",
        "internalized-idea",
        "benchmark",
        "rejected-dependency",
    }:
        raise ConstitutionError("policy must define the four external-adoption categories")
    if set(adoption.get("required_reverification", [])) != {"license", "upstream-interface"}:
        raise ConstitutionError("external adoption must reverify license and upstream interface")

    lifecycle = policy.get("lifecycle")
    if not isinstance(lifecycle, dict) or set(lifecycle.get("terminal_states", [])) != {
        "research_qualified",
        "retired",
    }:
        raise ConstitutionError("lifecycle must terminate at research_qualified or retired")
    if not {"approved", "active", "order", "position", "live-trading"} <= set(
        lifecycle.get("forbidden_states", [])
    ):
        raise ConstitutionError("production-trading lifecycle states must be forbidden")

    admission = policy.get("future_spec_admission")
    if not isinstance(admission, dict):
        raise ConstitutionError("policy must declare future_spec_admission")
    if set(admission.get("required_declarations", [])) != REQUIRED_DECLARATIONS:
        raise ConstitutionError("future SPEC declarations are incomplete")
    if set(admission.get("allowed_owners", [])) != set(owners):
        raise ConstitutionError("admission owners must match canonical owners")


def validate_candidate(candidate: dict[str, Any], policy: dict[str, Any]) -> None:
    declarations = policy["future_spec_admission"]["required_declarations"]
    missing = [name for name in declarations if not candidate.get(name)]
    if missing:
        raise ConstitutionError(f"candidate is missing required declarations: {', '.join(missing)}")
    if candidate["canonical_owner"] not in policy["future_spec_admission"]["allowed_owners"]:
        raise ConstitutionError("candidate canonical_owner is not a constitutional owner")

    claims = set(candidate.get("claims", []))
    forbidden = claims & set(policy["future_spec_admission"]["forbidden_claims"])
    if forbidden:
        raise ConstitutionError(f"candidate makes forbidden claims: {', '.join(sorted(forbidden))}")

    lifecycle_states = set(candidate.get("lifecycle_states", []))
    forbidden_states = lifecycle_states & set(policy["lifecycle"]["forbidden_states"])
    if forbidden_states:
        raise ConstitutionError(
            f"candidate declares forbidden lifecycle states: {', '.join(sorted(forbidden_states))}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--candidate", type=Path)
    arguments = parser.parse_args(argv)

    try:
        policy = read_json(arguments.policy)
        validate_policy(policy)
        if arguments.candidate is not None:
            validate_candidate(read_json(arguments.candidate), policy)
    except ConstitutionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "policy": str(arguments.policy.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
