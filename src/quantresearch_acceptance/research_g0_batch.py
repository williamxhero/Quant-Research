"""The G0 acceptance batch revision (SPEC #476, ticket #499).

G0 is a *second* batch under the existing ``quant-research.acceptance-batch.v1``
wrapper.  It has its own batch id, its own revision and its own fixture digest,
and it is deliberately not appended to the historical 32-SPEC release ledger:
that ledger has a fixed topology and a different meaning.

What this module owns is the machine-readable side of the G0 catalog published
by apex-research (``docs/research/g0/G0-v0.json`` plus its expectations table
``G0-v0-expectations.json``): which batch case each catalog task maps to, which
direct test actually backs it, and what the batch is allowed to report today.

Two boundaries are load-bearing here.

* **Nothing is green yet.**  The fifteen tasks are executed for real in S4.
  Until a run exists, every reported status is ``not_run``; only ``pass``
  counts, so the batch summary shows a pass count of zero rather than a silent
  green.
* **No task without a direct test.**  Every case in the config names at least
  one test file that exists in this package, so a scenario can never reach the
  ledger — and therefore can never be recorded as ``pass`` — without one.

Tasks whose catalog row cites A0 scenarios reuse the A0 evidence that already
exists in this package rather than restating it.  The remaining tasks are
backed by the G0 contract test, which asserts the catalog row is well formed
and that its reported status is still ``not_run``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from .batch import BatchStatus

G0_BATCH_ID = "G0"
G0_BATCH_REVISION = 1
G0_SCOPE_SCHEMA = "quant-research.acceptance-scope.v2"
G0_SCOPE_REVISION = "acceptance-scope.v2"

G0_CATALOG_ID = "G0-v0"
G0_CATALOG_SCHEMA = "apex-research.g0-catalog-request.v1"
G0_EXPECTATIONS_SCHEMA = "apex-research.g0-expectations-request.v1"

#: apex-research content identity the expectations table binds itself to.
G0_CATALOG_CONTENT_ID = "e49981611cd9d847470e2bc851d8841e80e984cbf69a7bbc6dca709852531490"

#: The apex-research commit that publishes both G0 documents.
G0_FIXTURE_COMMIT = "3f29bf521694d0ab5fc2474bbfc1ca648e74a9d0"

#: sha256 of each published G0 document, exactly as committed.
G0_FIXTURE_FILE_DIGESTS: tuple[tuple[str, str], ...] = (
    (
        "docs/research/g0/G0-v0-expectations.json",
        "c401e26cbc687bd86733b9a78119aee41a57c49d68462fd63fb2c8241fa60aae",
    ),
    (
        "docs/research/g0/G0-v0.json",
        "3a2a88d77ecfc8d7d2757d94ceb44a774f086415d0095a7c62b6732c9481697d",
    ),
)

_A0_ORACLE_TESTS = ("quantresearch_acceptance/_a0_r2_real_evidence_test.py",)
_A0_IDENTITY_TESTS = (
    "quantresearch_acceptance/_research_decision_test.py",
    "quantresearch_acceptance/_research_genome_flow_test.py",
)
_G0_CONTRACT_TESTS = ("quantresearch_acceptance/_g0_batch_test.py",)


@dataclass(frozen=True, slots=True)
class G0Task:
    """One G0 catalog task as this batch revision binds it."""

    task_id: str
    behaviour: str
    input_kind: Literal["fixture", "real_data"]
    evidence_role: Literal["process_behaviour_only", "research_evidence"]
    object_reference: str
    expected_batch_status: BatchStatus
    a0_scenarios: tuple[str, ...]
    direct_tests: tuple[str, ...]
    reported_status: BatchStatus


#: The fifteen ``G0-v0`` tasks, in catalog order.
G0_TASKS: tuple[G0Task, ...] = (
    G0Task(
        task_id="G0-T01",
        behaviour="event_should_trigger",
        input_kind="fixture",
        evidence_role="process_behaviour_only",
        object_reference="CPA-EMA-Crossback-v0",
        expected_batch_status="pass",
        a0_scenarios=("A0-X01",),
        direct_tests=_A0_ORACLE_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T02",
        behaviour="event_should_trigger",
        input_kind="fixture",
        evidence_role="process_behaviour_only",
        object_reference="FX-G0-A-ENTRY-01",
        expected_batch_status="pass",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T03",
        behaviour="event_should_not_trigger",
        input_kind="fixture",
        evidence_role="process_behaviour_only",
        object_reference="CPA-EMA-Crossback-v0",
        expected_batch_status="pass",
        a0_scenarios=("A0-X01", "A0-X02"),
        direct_tests=_A0_ORACLE_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T04",
        behaviour="event_should_not_trigger",
        input_kind="fixture",
        evidence_role="process_behaviour_only",
        object_reference="FX-G0-A-NOENTRY-01",
        expected_batch_status="pass",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T05",
        behaviour="volume_boundary",
        input_kind="fixture",
        evidence_role="process_behaviour_only",
        object_reference="CPA-EMA-Crossback-v0",
        expected_batch_status="pass",
        a0_scenarios=("A0-X01",),
        direct_tests=_A0_ORACLE_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T06",
        behaviour="multi_instrument_state_isolation",
        input_kind="fixture",
        evidence_role="process_behaviour_only",
        object_reference="FX-G0-ISO-01",
        expected_batch_status="pass",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T07",
        behaviour="exit_and_stop",
        input_kind="fixture",
        evidence_role="process_behaviour_only",
        object_reference="FX-G0-EXIT-01",
        expected_batch_status="pass",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T08",
        behaviour="zero_trades",
        input_kind="real_data",
        evidence_role="process_behaviour_only",
        object_reference="CPA-EMA-Crossback-v0",
        expected_batch_status="pass",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T09",
        behaviour="random_signal",
        input_kind="real_data",
        evidence_role="research_evidence",
        object_reference="Matched-Random-v0",
        expected_batch_status="pass",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T10",
        behaviour="leaked_input",
        input_kind="real_data",
        evidence_role="research_evidence",
        object_reference="Known-Leakage-Control-v0-plus",
        expected_batch_status="expected-deny",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T11",
        behaviour="leaked_input",
        input_kind="real_data",
        evidence_role="research_evidence",
        object_reference="Known-Leakage-Control-v0-minus",
        expected_batch_status="expected-deny",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T12",
        behaviour="costs_erase_edge",
        input_kind="real_data",
        evidence_role="research_evidence",
        object_reference="CPA-EMA-Crossback-v0",
        expected_batch_status="pass",
        a0_scenarios=(),
        direct_tests=_G0_CONTRACT_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T13",
        behaviour="execution_failure",
        input_kind="real_data",
        evidence_role="process_behaviour_only",
        object_reference="Reference-Strategy-v0",
        expected_batch_status="pass",
        a0_scenarios=("A0-E03",),
        direct_tests=_A0_ORACLE_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T14",
        behaviour="repeated_run_identity",
        input_kind="real_data",
        evidence_role="process_behaviour_only",
        object_reference="CPA-EMA-Crossback-v0",
        expected_batch_status="pass",
        a0_scenarios=("A0-L01",),
        direct_tests=_A0_IDENTITY_TESTS,
        reported_status="not_run",
    ),
    G0Task(
        task_id="G0-T15",
        behaviour="interruption_recovery_and_reuse",
        input_kind="real_data",
        evidence_role="process_behaviour_only",
        object_reference="CPA-EMA-Crossback-v0",
        expected_batch_status="pass",
        a0_scenarios=("A0-L03", "A0-R01"),
        direct_tests=_A0_IDENTITY_TESTS,
        reported_status="not_run",
    ),
)

#: The twelve process behaviours the catalog is required to cover.
G0_BEHAVIOURS: tuple[str, ...] = tuple(sorted({task.behaviour for task in G0_TASKS}))


def g0_fixture_digest() -> str:
    """Return the manifest digest binding both published G0 documents."""
    manifest = {path.rsplit("/", 1)[-1]: digest for path, digest in G0_FIXTURE_FILE_DIGESTS}
    material = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(material).hexdigest()


def g0_task(task_id: str) -> G0Task:
    for task in G0_TASKS:
        if task.task_id == task_id:
            return task
    raise KeyError(task_id)


def g0_batch_config() -> dict[str, object]:
    """Return the ``quant-research.acceptance-batch.v1`` document for G0."""
    return {
        "schema": "quant-research.acceptance-batch.v1",
        "batch_id": G0_BATCH_ID,
        "revision": G0_BATCH_REVISION,
        "scope_schema": G0_SCOPE_SCHEMA,
        "scope_revision": G0_SCOPE_REVISION,
        "required_cases": [task.task_id for task in G0_TASKS],
        "scenario_to_direct_tests": {task.task_id: list(task.direct_tests) for task in G0_TASKS},
        "fixture_binding": {
            "fixture_revision": G0_CATALOG_ID,
            "fixture_digest": g0_fixture_digest(),
            "fixture_commit": G0_FIXTURE_COMMIT,
            # The bound artifacts are the catalog and its expectations table:
            # process definitions, never market evidence.
            "role": "synthetic-test-only",
        },
    }


def g0_reported_statuses() -> dict[str, BatchStatus]:
    """Return what the batch may report today, before the S4 run exists."""
    return {task.task_id: task.reported_status for task in G0_TASKS}
