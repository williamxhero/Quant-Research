from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantresearch_acceptance import (
    AcceptanceFailure,
    AcceptanceSelector,
    InstalledEnvironment,
    PlanRunner,
    ProcessResult,
)
from tools.test_acceptance_selector import diff_literal, scope_literal


class ProcessSpy:
    def __init__(self, *, duration_seconds: float = 1.0) -> None:
        self.calls: list[dict[str, object]] = []
        self.duration_seconds = duration_seconds

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        environment: dict[str, str],
        timeout_seconds: int,
        on_event: object,
    ) -> ProcessResult:
        self.calls.append(
            {
                "argv": argv,
                "cwd": cwd,
                "environment": environment,
                "timeout_seconds": timeout_seconds,
            }
        )
        return ProcessResult(0, self.duration_seconds, "ok", (), ())


class BuilderSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def build(self, plan_identity: str, owners: tuple[str, ...]) -> tuple[Path, ...]:
        self.calls.append((plan_identity, owners))
        return (Path("wheelhouse/quantresearch_acceptance-1-py3-none-any.whl"),)


class InstallerSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Path, ...]]] = []

    def install(
        self, plan_identity: str, wheels: tuple[Path, ...]
    ) -> InstalledEnvironment:
        self.calls.append((plan_identity, wheels))
        return InstalledEnvironment(
            python=Path("C:/isolated/venv/Scripts/python.exe"),
            cwd=Path("C:/isolated/run"),
            environment={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            source_roots=(ROOT.resolve(),),
        )


class PlanRunnerContractTests(unittest.TestCase):
    def test_public_runner_builds_installs_once_and_uses_exactly_two_replays(self) -> None:
        plan = AcceptanceSelector().select(scope_literal(), diff_literal(), phase="spec")
        process = ProcessSpy()
        builder = BuilderSpy()
        installer = InstallerSpy()

        receipt = PlanRunner(process, builder, installer).run(plan)

        self.assertEqual(builder.calls, [(plan.identity, ("quant-research",))])
        self.assertEqual(len(installer.calls), 1)
        self.assertEqual(len(process.calls), 5)
        replay_calls = process.calls[-2:]
        self.assertEqual(
            [call["argv"][0] for call in replay_calls],  # type: ignore[index]
            ["C:/isolated/venv/Scripts/python.exe"] * 2,
        )
        self.assertTrue(
            all("PYTHONPATH" not in call["environment"] for call in replay_calls)
        )
        self.assertEqual(
            [call["cwd"] for call in replay_calls], [Path("C:/isolated/run")] * 2
        )
        self.assertNotEqual(replay_calls[0]["argv"], replay_calls[1]["argv"])
        self.assertTrue(
            any(token.endswith("replay-1.xml") for token in replay_calls[0]["argv"])
        )
        self.assertTrue(
            any(token.endswith("replay-2.xml") for token in replay_calls[1]["argv"])
        )
        self.assertEqual(receipt.plan_identity, plan.identity)
        self.assertEqual(receipt.process_count, 5)
        self.assertEqual(receipt.replay_process_count, 2)

    def test_runner_enforces_each_step_budget_and_rejects_identity_drift(self) -> None:
        plan = AcceptanceSelector().select(scope_literal(), diff_literal(), phase="spec")
        with self.assertRaises(AcceptanceFailure):
            PlanRunner(ProcessSpy(), BuilderSpy(), InstallerSpy()).run(
                dataclasses.replace(plan, identity="0" * 64)
            )

        slow_process = ProcessSpy(duration_seconds=301)
        with self.assertRaises(AcceptanceFailure):
            PlanRunner(slow_process, BuilderSpy(), InstallerSpy()).run(plan)


if __name__ == "__main__":
    unittest.main()
