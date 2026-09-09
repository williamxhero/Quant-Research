# ruff: noqa: E402
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantresearch_acceptance import AcceptanceFailure, AcceptanceSelector

BASES = {
    "apex-research": "7cd4d1c97fcfb95194be6710d18191622f753049",
    "quant-research": "3975b0e799a02cdc35a6d3035d884916764e519c",
    "quant-runtime": "72a1dfec6ebdbe132e7359afc61ed9ca07dd15e4",
    "strategy-reporting": "087ae2be9a0e0b7c04eef5e4dee4c735e5a6a082",
    "strategy-workspace": "1e9c58251efcf48dd8e4d8bc66007dbe105affba",
}


def scope_literal() -> dict[str, object]:
    return {
        "schema": "quant-research.acceptance-scope.v2",
        "spec": "TEST-001",
        "owners": {
            name: {
                "fixed_base": sha,
                "repository": "." if name == "quant-research" else name,
                "diff_prefixes": ["src/" if name == "quant-research" else f"{name}/src/"],
                "source_patterns": ["src/"],
                "import_names": (
                    ["quantresearch_acceptance"]
                    if name == "quant-research"
                    else [name.replace("-", "_")]
                ),
                "build_argv": ["uv", "build", "--wheel", "--out-dir", "{wheel_dir}"],
                "source_fingerprint": "sha256:" + ("1" if name == "quant-research" else "2") * 64,
            }
            for name, sha in BASES.items()
        },
        "public_contract_sources": ["src/quantresearch_acceptance/core.py"],
        "source_to_direct_tests": {
            "src/quantresearch_acceptance/core.py": ["tools/test_acceptance_selector.py"]
        },
        "levels": {
            "L0": {
                "budget_seconds": 60,
                "commands": [
                    {
                        "owner": "quant-research",
                        "argv": ["python", "-m", "compileall", "-q", "src"],
                        "markers": [],
                        "history_samples_seconds": [7, 8, 9, 10],
                    }
                ],
            },
            "L1": {
                "budget_seconds": 180,
                "commands": [
                    {
                        "owner": "quant-research",
                        "argv": [
                            "python",
                            "-m",
                            "pytest",
                            "-m",
                            "not slow and not oci and not connected and not release",
                            "--junitxml={junit}",
                            "{direct_tests}",
                        ],
                        "markers": [],
                        "history_samples_seconds": [20, 24, 25, 30],
                    }
                ],
            },
            "L2": {
                "budget_seconds": 600,
                "commands": [
                    {
                        "owner": "quant-research",
                        "argv": [
                            "python",
                            "-m",
                            "pytest",
                            "-m",
                            "not slow and not oci and not connected and not release",
                            "--junitxml={junit}",
                            "tools/test_acceptance_selector.py",
                        ],
                        "markers": [],
                        "history_samples_seconds": [40, 42, 50, 55],
                    }
                ],
            },
            "L3": {
                "budget_seconds": 300,
                "commands": [
                    {
                        "owner": "quant-research",
                        "argv": [
                            "{python}",
                            "-m",
                            "pytest",
                            "-m",
                            "not slow and not oci and not connected and not release",
                            "--junitxml={junit}",
                            "--pyargs",
                            "quantresearch_acceptance._installed_test",
                        ],
                        "markers": [],
                        "history_samples_seconds": [35, 40, 45, 48],
                    }
                ],
            },
        },
        "marker_policy": {
            "allowed": ["connected", "oci", "release", "slow"],
            "ordinary_exclusion": "not slow and not oci and not connected and not release",
        },
        "evidence": {
            "artifact_root": "artifacts/acceptance/{plan_id}",
            "event_log": "events.jsonl",
            "plan": "plan.json",
        },
    }


def diff_literal() -> dict[str, object]:
    return {
        "schema": "quant-research.fixed-base-diff.v1",
        "fixed_bases": dict(BASES),
        "source_fingerprints": {
            name: "sha256:" + ("1" if name == "quant-research" else "2") * 64 for name in BASES
        },
        "changed_sources": [
            {
                "path": "src/quantresearch_acceptance/core.py",
                "fingerprint": "sha256:" + "a" * 64,
            }
        ],
    }


class AcceptanceSelectorContractTests(unittest.TestCase):
    def test_spec_plan_is_canonical_immutable_and_public_contract_selects_l3(self) -> None:
        plan = AcceptanceSelector().select(scope_literal(), diff_literal(), phase="spec")

        self.assertEqual(plan.spec, "TEST-001")
        self.assertEqual(plan.phase, "spec")
        self.assertEqual(plan.levels, ("L0", "L1", "L2", "L3"))
        self.assertEqual(plan.owners, ("quant-research",))
        self.assertEqual(plan.steps[1].direct_tests, ("tools/test_acceptance_selector.py",))
        self.assertTrue(all(isinstance(step.argv, tuple) for step in plan.steps))
        self.assertEqual(
            plan.identity,
            "4819b4a7f7c1783220a72373d492c6021a5f19ca1193c08c0d3174383619beb7",
        )
        self.assertIn(plan.identity, plan.artifact_root)
        with self.assertRaises((AttributeError, TypeError)):
            plan.levels += ("L4",)  # type: ignore[misc]

        reordered = scope_literal()
        reordered["owners"] = dict(reversed(list(reordered["owners"].items())))  # type: ignore[union-attr]
        self.assertEqual(
            plan.identity,
            AcceptanceSelector().select(reordered, diff_literal(), phase="spec").identity,
        )

    def test_plan_identity_changes_when_a_meaningful_input_changes(self) -> None:
        first = AcceptanceSelector().select(scope_literal(), diff_literal(), phase="spec")
        changed = diff_literal()
        changed["changed_sources"][0]["fingerprint"] = "sha256:" + "b" * 64  # type: ignore[index]

        second = AcceptanceSelector().select(scope_literal(), changed, phase="spec")

        self.assertNotEqual(first.identity, second.identity)
        changed_scope = scope_literal()
        changed_scope["owners"]["quant-research"]["build_argv"] = [
            "uv",
            "build",
            "--no-build-logs",
        ]
        self.assertNotEqual(
            first.identity,
            AcceptanceSelector().select(changed_scope, diff_literal(), phase="spec").identity,
        )

    def test_release_plan_adds_owner_full_and_independent_environment_gates(self) -> None:
        scope = scope_literal()
        command = {
            "owner": "quant-research",
            "argv": ["python", "-c", "pass"],
            "markers": ["release"],
            "history_samples_seconds": [10, 12, 14],
        }
        scope["levels"]["L4"] = {"budget_seconds": 3600, "commands": [command]}
        scope["levels"]["L5"] = {
            "budget_seconds": 1800,
            "commands": [
                {
                    **command,
                    "owner": "quant-runtime",
                    "markers": ["connected", "release"],
                }
            ],
        }

        plan = AcceptanceSelector().select(scope, diff_literal(), phase="release")

        self.assertEqual(plan.levels, ("L0", "L1", "L2", "L3", "L4", "L5"))
        self.assertIn("quant-runtime", {step.owner for step in plan.steps})

    def test_unknown_ambiguous_unmapped_and_drifted_inputs_fail_closed(self) -> None:
        cases: list[tuple[dict[str, object], dict[str, object]]] = []
        unknown = scope_literal()
        unknown["surprise"] = True
        cases.append((unknown, diff_literal()))
        traversal = diff_literal()
        traversal["changed_sources"][0]["path"] = "../escape.py"  # type: ignore[index]
        cases.append((scope_literal(), traversal))
        unmapped = diff_literal()
        unmapped["changed_sources"][0]["path"] = "src/unknown.py"  # type: ignore[index]
        cases.append((scope_literal(), unmapped))
        drifted = diff_literal()
        drifted["fixed_bases"]["quant-research"] = "0" * 40  # type: ignore[index]
        cases.append((scope_literal(), drifted))
        ambiguous = scope_literal()
        ambiguous["owners"]["apex-research"]["diff_prefixes"] = ["src/"]  # type: ignore[index]
        cases.append((ambiguous, diff_literal()))
        shell_string = scope_literal()
        shell_string["levels"]["L0"]["commands"][0]["argv"] = "python -m compileall src"  # type: ignore[index]
        cases.append((shell_string, diff_literal()))

        for scope, diff in cases:
            with (
                self.subTest(scope=json.dumps(scope, sort_keys=True)[:100]),
                self.assertRaises(AcceptanceFailure),
            ):
                AcceptanceSelector().select(scope, diff, phase="spec")


if __name__ == "__main__":
    unittest.main()
