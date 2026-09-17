"""The decision layer that stops a true duplicate before any research spend.

#396 gave an append-only exposure event log with request idempotency.  #397 and
#398 gave a frozen, paginated, rebuildable research Context.  None of them
decides *whether the research should happen at all*.  That decision is this
module, and it keeps three questions strictly apart, because conflating any two
of them is how a memory turns either into a rubber stamp or into a wall:

**Request idempotency** is mechanical.  Same action key plus the same frozen
input recovers the existing decision; the same key with a different input is
rejected outright.  An action whose delivery is ``delivery_uncertain`` in the
#396 log is reconciled first and is never blindly resent.

**Run reuse** is a fact about execution.  A prior run may be reused only when
the whole execution contract matches -- Package, parameter digest, data snapshot
and range, cost and execution environment, and the declared randomness -- and
only when that run reached a *qualifying* terminal state.  Genome identity is
one field of that contract, never a substitute for it, and a field that only
changes how a result is *interpreted* (the statistical protocol) is deliberately
kept out of the run key: that is what makes "same run, different protocol"
expressible as an attach rather than as a re-backtest.

**Research duplication** is a fact about the question.  It compares the research
question, its real failure direction, the comparison target, the evidence
requirements and the statistical protocol against the prior published judgment
for the same research key.  Only an equivalent, already-*completed* judgment
stops the work.  A new sample, a new execution configuration, a different
protocol, a randomness experiment or a repaired data blocker all produce a fresh
governed judgment.

Two asymmetries hold this together.  Renaming a proposal proves nothing: the
display name is excluded from every key, so a re-titled equivalent request is
still a duplicate.  And a *declared* intent proves nothing either: calling a
request a "replication" when its run key, protocol and question are byte-for-byte
the prior ones is still a duplicate, because the independence has to be visible
in the frozen inputs rather than asserted in a label.

The order of operations is fixed in ``DECISION_STEP_CONTRACT`` and every
executed step is recorded in a public call trace.  A true duplicate stops after
the canonical decision readback: no research-engine Context is published, no
external budget is reserved, no run is executed and the engine is not called --
four counters, asserted separately rather than as one "nothing bad happened".
Only a non-duplicate reaches the visibility gate (#394/#395 through #398's
delivery seam) and the required-completeness check, and only material that
passes both reaches the engine seam.

What this module deliberately does not do: it holds no statistical or
eligibility authority (multiplicity and independence stay with the originating
owner), it never resets a test family, it never treats a stale data blocker as a
falsified strategy, and it offers no read-only path that can reach the engine.
Recovery replays a frozen public record; it never issues a "latest" query and
never guesses from a checkpoint whether an external side effect happened.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .research_context import ContextAssemblyFailure, _flag
from .research_exposure import ExposureKey, ExposureLog, ResearchFamilyRef
from .research_pagination import (
    PaginatedResearchContext,
    deliver_paginated_research_brief,
    freeze_paginated_research_context,
)
from .research_visibility import (
    _SAFE_DIGEST,
    _digest,
    _fields_subset,
    _list,
    _mapping,
    _token,
    _tokens,
)

DECISION_REQUEST_SCHEMA = "quant-research.research-decision-request.v1"
DECISION_RECORD_SCHEMA = "quant-research.research-decision-record.v1"
DECISION_READBACK_SCHEMA = "quant-research.research-decision-readback.v1"
DECISION_HISTORY_SCHEMA = "quant-research.research-decision-history.v1"
RUN_LEDGER_SCHEMA = "quant-research.research-run-record.v1"
JUDGMENT_LEDGER_SCHEMA = "quant-research.research-judgment-record.v1"

#: The declared order of operations.  ``phase`` separates the steps that only
#: read or decide from the steps that actually spend something.  Nothing in the
#: ``act`` phase is reachable without every ``gate`` step having passed first.
DECISION_STEP_CONTRACT: tuple[tuple[str, str], ...] = (
    ("read_predecessor_policy", "read"),
    ("read_approved_sources", "read"),
    ("decide_request_idempotency", "decide"),
    ("decide_run_reuse", "decide"),
    ("decide_research_duplication", "decide"),
    ("publish_decision_readback", "publish"),
    ("stop_on_research_duplicate", "stop"),
    ("check_visibility", "gate"),
    ("check_required_completeness", "gate"),
    ("publish_engine_context", "act"),
    ("reserve_budget", "act"),
    ("execute_run", "act"),
    ("call_research_engine", "act"),
)
DECISION_STEPS: tuple[str, ...] = tuple(step for step, _phase in DECISION_STEP_CONTRACT)
_STEP_PHASE: dict[str, str] = dict(DECISION_STEP_CONTRACT)
_STEP_INDEX: dict[str, int] = {step: index for index, step in enumerate(DECISION_STEPS)}
DECISION_STEP_CONTRACT_DIGEST = _digest(
    [{"step": step, "phase": phase} for step, phase in DECISION_STEP_CONTRACT]
)

#: Only a run that actually finished may be reused.  A failed, blocked, running
#: or cancelled run is not an execution fact anybody can attach to, and a stale
#: blocker is explicitly not a falsified strategy.
RUN_TERMINAL_STATES: frozenset[str] = frozenset(
    {"completed", "failed", "blocked", "cancelled", "running"}
)
QUALIFYING_RUN_STATES: frozenset[str] = frozenset({"completed"})

#: What the requester says it is doing.  A declared intent is evidence about
#: purpose, never proof of independence.
RESEARCH_INTENTS: frozenset[str] = frozenset(
    {
        "initial",
        "replication",
        "revalidation",
        "new_sample",
        "new_execution_config",
        "randomness_experiment",
        "protocol_change",
        "blocker_retry",
    }
)

#: The published state of a prior research judgment.
JUDGMENT_STATES: frozenset[str] = frozenset({"completed", "blocked_by_data", "withdrawn"})

RequestDisposition = str
RunDisposition = str
ResearchDisposition = str
DecisionOutcomeState = str

#: Request-level dispositions.
REQUEST_DISPOSITIONS: frozenset[str] = frozenset(
    {"new_request", "recovered_existing", "rejected_key_conflict", "reconcile_required"}
)
#: Execution-fact dispositions.  ``attached_run`` is a reuse whose statistical
#: protocol differs from the run's original one: the execution fact is reused and
#: no backtest is re-run, but a fresh research judgment is still produced.
RUN_DISPOSITIONS: frozenset[str] = frozenset({"new_run", "reused_run", "attached_run"})
#: Question-level dispositions.
RESEARCH_DISPOSITIONS: frozenset[str] = frozenset(
    {"duplicate_research", "new_research", "blocked_prior_data_blocker"}
)
#: The terminal states of the gate itself.
DECISION_OUTCOMES: frozenset[str] = frozenset(
    {
        "proceeded",
        "stopped_duplicate",
        "rejected_key_conflict",
        "recovered_existing",
        "reconcile_required",
        "blocked_prior_data_blocker",
        "blocked_by_gate",
    }
)

_REQUEST_FIELDS = frozenset(
    {
        "schema",
        "key",
        "display_name",
        "policy",
        "research_family",
        "approved_source_ids",
        "intent",
        "question",
        "run",
        "blocker_repair",
        "budget_request",
        "paginated_context",
        "visibility_request",
    }
)
_POLICY_FIELDS = frozenset({"policy_id", "policy_version", "predecessor_decision_id"})
_QUESTION_FIELDS = frozenset(
    {
        "question_id",
        "failure_direction",
        "comparison_target",
        "evidence_requirements",
        "protocol",
    }
)
_PROTOCOL_FIELDS = frozenset(
    {"protocol_id", "protocol_version", "multiplicity_policy", "inference_fields"}
)
_RUN_FIELDS = frozenset(
    {
        "package_id",
        "genome_id",
        "parameter_digest",
        "data_snapshot_id",
        "data_range",
        "cost_environment",
        "execution_environment",
        "randomness",
        "terminal_state",
    }
)
_RANDOMNESS_FIELDS = frozenset({"seed_policy", "seed_ref", "replicates"})
_REPAIR_FIELDS = frozenset({"blocker_id", "new_condition", "owner_permitted", "repair_ref"})
_BUDGET_FIELDS = frozenset({"budget_id", "units"})

MAX_REPLICATES = 4096
MAX_BUDGET_UNITS = 1_000_000


class DecisionRefusal(ContextAssemblyFailure):
    """A malformed or self-contradictory decision declaration.

    As in #397 and #398, an honest "this is a duplicate" or "the gate blocked
    this" is *not* an exception.  Those are frozen, publicly readable decision
    records with an explicit outcome, so the refusal to spend stays auditable.
    """


class ResearchEngineSeam(Protocol):
    """The existing consumer seam this decision layer guards.

    Four capabilities are named separately on purpose, because the acceptance
    criteria count them separately.  Publishing a research-engine Context,
    reserving external budget, executing a run and invoking the research engine
    are four distinct spends, and a true duplicate must reach none of them.
    """

    def publish_context(self, record: Mapping[str, object]) -> str:
        """Publish the frozen Context to the research engine; return its handle."""

    def reserve_budget(self, budget_id: str, units: int) -> str:
        """Reserve external budget for the required action; return its handle."""

    def execute_run(self, run_key: str, contract: Mapping[str, object]) -> str:
        """Execute the backtest / run described by the contract; return its id."""

    def call_research_engine(self, request: Mapping[str, object]) -> str:
        """Invoke the existing research consumer; return its invocation id."""


@dataclass(frozen=True, slots=True)
class DecisionPolicyRef:
    policy_id: str
    policy_version: str
    predecessor_decision_id: str | None

    @classmethod
    def parse(cls, value: object) -> DecisionPolicyRef:
        item = _mapping(value, "policy")
        _fields_subset(item, _POLICY_FIELDS, "policy")
        raw = item.get("predecessor_decision_id")
        return cls(
            policy_id=_token(item.get("policy_id"), "policy.policy_id"),
            policy_version=_token(item.get("policy_version"), "policy.policy_version"),
            predecessor_decision_id=(
                None if raw is None else _token(raw, "policy.predecessor_decision_id")
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "predecessor_decision_id": self.predecessor_decision_id,
        }


@dataclass(frozen=True, slots=True)
class StatisticalProtocol:
    """How a result is *interpreted*.

    None of this ever enters the run key.  Changing the multiplicity policy or
    the inference fields does not make the backtest a different backtest; it
    makes the *judgment* a different judgment.
    """

    protocol_id: str
    protocol_version: str
    multiplicity_policy: str
    inference_fields: tuple[str, ...]

    @classmethod
    def parse(cls, value: object) -> StatisticalProtocol:
        item = _mapping(value, "question.protocol")
        _fields_subset(item, _PROTOCOL_FIELDS, "question.protocol")
        return cls(
            protocol_id=_token(item.get("protocol_id"), "question.protocol.protocol_id"),
            protocol_version=_token(
                item.get("protocol_version"), "question.protocol.protocol_version"
            ),
            multiplicity_policy=_token(
                item.get("multiplicity_policy"), "question.protocol.multiplicity_policy"
            ),
            inference_fields=_tokens(
                item.get("inference_fields", []),
                "question.protocol.inference_fields",
                empty=True,
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "multiplicity_policy": self.multiplicity_policy,
            "inference_fields": list(self.inference_fields),
        }

    def identity(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RandomnessContract:
    seed_policy: str
    seed_ref: str
    replicates: int

    @classmethod
    def parse(cls, value: object) -> RandomnessContract:
        item = _mapping(value, "run.randomness")
        _fields_subset(item, _RANDOMNESS_FIELDS, "run.randomness")
        replicates = item.get("replicates")
        if (
            not isinstance(replicates, int)
            or isinstance(replicates, bool)
            or not 1 <= replicates <= MAX_REPLICATES
        ):
            raise DecisionRefusal("run.randomness.replicates is invalid")
        return cls(
            seed_policy=_token(item.get("seed_policy"), "run.randomness.seed_policy"),
            seed_ref=_token(item.get("seed_ref"), "run.randomness.seed_ref"),
            replicates=replicates,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "seed_policy": self.seed_policy,
            "seed_ref": self.seed_ref,
            "replicates": self.replicates,
        }


@dataclass(frozen=True, slots=True)
class RunContract:
    """The original Runtime / Workspace execution contract, as declared.

    ``run_key`` is the identity a reuse is matched on.  It contains the whole
    execution contract -- and only the execution contract.  ``terminal_state``
    is *not* part of the key: the same execution input that failed and then
    succeeded is the same run identity in two different states, and pretending
    otherwise would let a failure hide a later success.
    """

    package_id: str
    genome_id: str
    parameter_digest: str
    data_snapshot_id: str
    data_range: str
    cost_environment: str
    execution_environment: str
    randomness: RandomnessContract
    terminal_state: str

    @classmethod
    def parse(cls, value: object) -> RunContract:
        item = _mapping(value, "run")
        _fields_subset(item, _RUN_FIELDS, "run")
        digest = item.get("parameter_digest")
        if not isinstance(digest, str) or _SAFE_DIGEST.fullmatch(digest) is None:
            raise DecisionRefusal("run.parameter_digest is invalid")
        terminal_state = _token(item.get("terminal_state"), "run.terminal_state")
        if terminal_state not in RUN_TERMINAL_STATES:
            raise DecisionRefusal(f"run.terminal_state is invalid: {terminal_state}")
        return cls(
            package_id=_token(item.get("package_id"), "run.package_id"),
            genome_id=_token(item.get("genome_id"), "run.genome_id"),
            parameter_digest=digest,
            data_snapshot_id=_token(item.get("data_snapshot_id"), "run.data_snapshot_id"),
            data_range=_token(item.get("data_range"), "run.data_range"),
            cost_environment=_token(item.get("cost_environment"), "run.cost_environment"),
            execution_environment=_token(
                item.get("execution_environment"), "run.execution_environment"
            ),
            randomness=RandomnessContract.parse(item.get("randomness")),
            terminal_state=terminal_state,
        )

    def contract_dict(self) -> dict[str, object]:
        """Everything a run reuse is matched on.  No protocol field appears here."""

        return {
            "package_id": self.package_id,
            "genome_id": self.genome_id,
            "parameter_digest": self.parameter_digest,
            "data_snapshot_id": self.data_snapshot_id,
            "data_range": self.data_range,
            "cost_environment": self.cost_environment,
            "execution_environment": self.execution_environment,
            "randomness": self.randomness.as_dict(),
        }

    def as_dict(self) -> dict[str, object]:
        return {**self.contract_dict(), "terminal_state": self.terminal_state}

    def run_key(self) -> str:
        return _digest(self.contract_dict())

    @property
    def qualifies_for_reuse(self) -> bool:
        return self.terminal_state in QUALIFYING_RUN_STATES


@dataclass(frozen=True, slots=True)
class ResearchQuestion:
    """The question, its real failure direction, and what would answer it."""

    question_id: str
    failure_direction: str
    comparison_target: str
    evidence_requirements: tuple[str, ...]
    protocol: StatisticalProtocol

    @classmethod
    def parse(cls, value: object) -> ResearchQuestion:
        item = _mapping(value, "question")
        _fields_subset(item, _QUESTION_FIELDS, "question")
        return cls(
            question_id=_token(item.get("question_id"), "question.question_id"),
            # The *reason* the prior attempt failed, not the words used to
            # propose it.  U1 turns on this field rather than on a title.
            failure_direction=_token(item.get("failure_direction"), "question.failure_direction"),
            comparison_target=_token(item.get("comparison_target"), "question.comparison_target"),
            evidence_requirements=_tokens(
                item.get("evidence_requirements"), "question.evidence_requirements"
            ),
            protocol=StatisticalProtocol.parse(item.get("protocol")),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "question_id": self.question_id,
            "failure_direction": self.failure_direction,
            "comparison_target": self.comparison_target,
            "evidence_requirements": list(self.evidence_requirements),
            "protocol": self.protocol.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class BlockerRepair:
    """A repaired data / infrastructure blocker and the new condition it adds."""

    blocker_id: str
    new_condition: str
    owner_permitted: bool
    repair_ref: str

    @classmethod
    def parse(cls, value: object) -> BlockerRepair | None:
        if value is None:
            return None
        item = _mapping(value, "blocker_repair")
        _fields_subset(item, _REPAIR_FIELDS, "blocker_repair")
        return cls(
            blocker_id=_token(item.get("blocker_id"), "blocker_repair.blocker_id"),
            new_condition=_token(item.get("new_condition"), "blocker_repair.new_condition"),
            owner_permitted=_flag(item.get("owner_permitted"), "blocker_repair.owner_permitted"),
            repair_ref=_token(item.get("repair_ref"), "blocker_repair.repair_ref"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "blocker_id": self.blocker_id,
            "new_condition": self.new_condition,
            "owner_permitted": self.owner_permitted,
            "repair_ref": self.repair_ref,
        }


@dataclass(frozen=True, slots=True)
class BudgetRequest:
    budget_id: str
    units: int

    @classmethod
    def parse(cls, value: object) -> BudgetRequest:
        item = _mapping(value, "budget_request")
        _fields_subset(item, _BUDGET_FIELDS, "budget_request")
        units = item.get("units")
        if (
            not isinstance(units, int)
            or isinstance(units, bool)
            or not 1 <= units <= MAX_BUDGET_UNITS
        ):
            raise DecisionRefusal("budget_request.units is invalid")
        return cls(budget_id=_token(item.get("budget_id"), "budget_request.budget_id"), units=units)

    def as_dict(self) -> dict[str, object]:
        return {"budget_id": self.budget_id, "units": self.units}


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    """One research request, frozen before any decision is taken."""

    key: ExposureKey
    display_name: str
    policy: DecisionPolicyRef
    research_family: ResearchFamilyRef
    approved_source_ids: tuple[str, ...]
    intent: str
    question: ResearchQuestion
    run: RunContract
    blocker_repair: BlockerRepair | None
    budget_request: BudgetRequest
    paginated_context: dict[str, object]
    visibility_request: dict[str, object]

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> DecisionRequest:
        item = _mapping(value, "decision request")
        _fields_subset(item, _REQUEST_FIELDS, "decision request")
        if item.get("schema") != DECISION_REQUEST_SCHEMA:
            raise DecisionRefusal("decision request schema is invalid")
        intent = _token(item.get("intent"), "intent")
        if intent not in RESEARCH_INTENTS:
            raise DecisionRefusal(f"intent is invalid: {intent}")
        return cls(
            key=ExposureKey.parse(item.get("key")),
            # A label for humans.  It enters no key, so a rename cannot buy a
            # second pass at an already-answered question.
            display_name=_token(item.get("display_name"), "display_name"),
            policy=DecisionPolicyRef.parse(item.get("policy")),
            research_family=ResearchFamilyRef.parse(item.get("research_family")),
            approved_source_ids=_tokens(
                item.get("approved_source_ids", []), "approved_source_ids", empty=True
            ),
            intent=intent,
            question=ResearchQuestion.parse(item.get("question")),
            run=RunContract.parse(item.get("run")),
            blocker_repair=BlockerRepair.parse(item.get("blocker_repair")),
            budget_request=BudgetRequest.parse(item.get("budget_request")),
            paginated_context=dict(_mapping(item.get("paginated_context"), "paginated_context")),
            visibility_request=dict(_mapping(item.get("visibility_request"), "visibility_request")),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": DECISION_REQUEST_SCHEMA,
            "key": self.key.as_dict(),
            "display_name": self.display_name,
            "policy": self.policy.as_dict(),
            "research_family": self.research_family.as_dict(),
            "approved_source_ids": list(self.approved_source_ids),
            "intent": self.intent,
            "question": self.question.as_dict(),
            "run": self.run.as_dict(),
            "blocker_repair": (
                None if self.blocker_repair is None else self.blocker_repair.as_dict()
            ),
            "budget_request": self.budget_request.as_dict(),
            "paginated_context": self.paginated_context,
            "visibility_request": self.visibility_request,
        }

    def action_key(self) -> str:
        return self.key.action_key()

    def input_digest(self) -> str:
        """The frozen input of this action.

        The display name is excluded deliberately: renaming a request is not a
        different input, so it neither recovers under a different identity nor
        conflicts with the original.
        """

        return _digest(
            {
                "key": self.key.as_dict(),
                "policy": self.policy.as_dict(),
                "research_family": self.research_family.as_dict(),
                "approved_source_ids": list(self.approved_source_ids),
                "intent": self.intent,
                "question": self.question.as_dict(),
                "run": self.run.as_dict(),
                "blocker_repair": (
                    None if self.blocker_repair is None else self.blocker_repair.as_dict()
                ),
                "budget_request": self.budget_request.as_dict(),
            }
        )

    def run_key(self) -> str:
        return self.run.run_key()

    def research_key(self) -> str:
        """The question-level identity.

        It binds the question semantics, the execution contract and the
        statistical protocol -- so a new sample, a new execution configuration or
        a different protocol is a different piece of research -- and it binds
        neither the display name nor the declared intent, so neither a rename nor
        a self-declared "replication" can manufacture novelty.
        """

        return _digest(
            {
                "question_id": self.question.question_id,
                "failure_direction": self.question.failure_direction,
                "comparison_target": self.question.comparison_target,
                "evidence_requirements": list(self.question.evidence_requirements),
                "protocol": self.question.protocol.as_dict(),
                "run_contract": self.run.contract_dict(),
            }
        )


@dataclass(frozen=True, slots=True)
class RunRecord:
    """A published execution fact."""

    run_id: str
    run_key: str
    protocol_identity: str
    terminal_state: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": RUN_LEDGER_SCHEMA,
            "run_id": self.run_id,
            "run_key": self.run_key,
            "protocol_identity": self.protocol_identity,
            "terminal_state": self.terminal_state,
            "qualifies_for_reuse": self.terminal_state in QUALIFYING_RUN_STATES,
        }


@dataclass(frozen=True, slots=True)
class JudgmentRecord:
    """A published research judgment: the answer to one research key."""

    judgment_id: str
    research_key: str
    run_key: str
    family_id: str
    test_family: str
    prior_result_ids: tuple[str, ...]
    state: str
    blocker_id: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": JUDGMENT_LEDGER_SCHEMA,
            "judgment_id": self.judgment_id,
            "research_key": self.research_key,
            "run_key": self.run_key,
            "family_id": self.family_id,
            "test_family": self.test_family,
            "prior_result_ids": list(self.prior_result_ids),
            "state": self.state,
            "blocker_id": self.blocker_id,
            # Memory publishes relations.  Multiplicity, independence and
            # qualification stay with the originating statistical owner.
            "grants_eligibility": False,
        }


class DecisionLedger:
    """The append-only public records the three decisions are read back from.

    There is no second authority here and no "latest" selector.  Runs are keyed
    by their execution contract, judgments by their research key, and decisions
    by the #396 action key plus the frozen input digest.
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._judgments: dict[str, JudgmentRecord] = {}
        self._decisions: dict[str, dict[str, object]] = {}
        self._blockers: dict[str, JudgmentRecord] = {}
        self._in_flight: dict[str, str] = {}

    def publish_run(
        self,
        *,
        run_id: str,
        run_contract: RunContract,
        protocol: StatisticalProtocol,
    ) -> RunRecord:
        record = RunRecord(
            run_id=_token(run_id, "run_id"),
            run_key=run_contract.run_key(),
            protocol_identity=protocol.identity(),
            terminal_state=run_contract.terminal_state,
        )
        existing = self._runs.get(record.run_key)
        if existing is not None and existing.as_dict() != record.as_dict():
            # A published execution fact is never rewritten under the same key.
            raise DecisionRefusal("run record conflicts with the published execution fact")
        self._runs[record.run_key] = record
        return record

    def publish_judgment(
        self,
        *,
        judgment_id: str,
        research_key: str,
        run_key: str,
        family: ResearchFamilyRef,
        state: str,
        blocker_id: str | None = None,
    ) -> JudgmentRecord:
        if state not in JUDGMENT_STATES:
            raise DecisionRefusal(f"judgment state is invalid: {state}")
        existing = self._judgments.get(research_key)
        if existing is not None and existing.test_family != family.test_family:
            # A new Campaign, a rename, or a fresh request never resets the
            # statistical test family a question already belongs to.
            raise DecisionRefusal("research judgment would reset the test family")
        prior = () if existing is None else existing.prior_result_ids
        record = JudgmentRecord(
            judgment_id=_token(judgment_id, "judgment_id"),
            research_key=research_key,
            run_key=run_key,
            family_id=family.family_id,
            test_family=family.test_family,
            prior_result_ids=tuple(sorted(set(prior) | set(family.prior_result_ids))),
            state=state,
            blocker_id=blocker_id,
        )
        self._judgments[research_key] = record
        if state == "blocked_by_data" and blocker_id is not None:
            self._blockers[blocker_id] = record
        return record

    def run_for(self, run_key: str) -> RunRecord | None:
        return self._runs.get(run_key)

    def judgment_for(self, research_key: str) -> JudgmentRecord | None:
        return self._judgments.get(research_key)

    def decision_for(self, action_key: str) -> dict[str, object] | None:
        return self._decisions.get(action_key)

    def record_decision(self, action_key: str, record: Mapping[str, object]) -> None:
        self._decisions[action_key] = dict(record)
        if record.get("outcome") == "proceeded":
            recorded = DecisionRequest.parse(
                _mapping(record.get("request"), "decision record request")
            )
            self._in_flight.setdefault(recorded.research_key(), action_key)

    def in_flight_for(self, research_key: str) -> str | None:
        """The action key of an equivalent research action that already spent.

        A conclusion is the owner's to publish, not this layer's, so an
        authorised-but-unfinished piece of research leaves no judgment behind.
        Without this index a second request under a *different* idempotency key
        would pay for the identical question all over again; with it, the second
        request is what it is -- a duplicate.
        """

        return self._in_flight.get(research_key)

    def blockers(self) -> dict[str, JudgmentRecord]:
        return dict(self._blockers)

    def export(self) -> dict[str, object]:
        return {
            "runs": [self._runs[key].as_dict() for key in sorted(self._runs)],
            "judgments": [self._judgments[key].as_dict() for key in sorted(self._judgments)],
            "decisions": [self._decisions[key] for key in sorted(self._decisions)],
        }


@dataclass(frozen=True, slots=True)
class SpendCounters:
    """The four spends, counted separately.

    They are separate because "nothing bad happened" is not an assertion.  A
    true duplicate must leave all four at zero; a reuse or attach must leave
    ``runs_executed`` at zero while still producing a judgment.
    """

    engine_contexts_published: int
    budget_reservations: int
    runs_executed: int
    research_engine_calls: int

    @classmethod
    def zero(cls) -> SpendCounters:
        return cls(0, 0, 0, 0)

    def total_external_calls(self) -> int:
        return (
            self.engine_contexts_published
            + self.budget_reservations
            + self.runs_executed
            + self.research_engine_calls
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "engine_contexts_published": self.engine_contexts_published,
            "budget_reservations": self.budget_reservations,
            "runs_executed": self.runs_executed,
            "research_engine_calls": self.research_engine_calls,
            "total_external_calls": self.total_external_calls(),
        }


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """The frozen, publicly readable result of one pass through the gate."""

    request: DecisionRequest
    outcome: DecisionOutcomeState
    request_disposition: RequestDisposition
    run_disposition: RunDisposition
    research_disposition: ResearchDisposition
    reasons: tuple[str, ...]
    trace: tuple[str, ...]
    counters: SpendCounters
    reused_run_id: str | None
    prior_judgment_id: str | None
    preserved_prior_result_ids: tuple[str, ...]
    context: PaginatedResearchContext | None
    identity: str

    @property
    def proceeded(self) -> bool:
        return self.outcome == "proceeded"

    def decision_dict(self) -> dict[str, object]:
        """The canonical decision readback: three decisions, never one flag."""

        return {
            "request_idempotency": {
                "disposition": self.request_disposition,
                "action_key": self.request.action_key(),
                "input_digest": self.request.input_digest(),
                "resend_allowed": False,
            },
            "run_reuse": {
                "disposition": self.run_disposition,
                "run_key": self.request.run_key(),
                "reused_run_id": self.reused_run_id,
                "protocol_identity": self.request.question.protocol.identity(),
                # Stated explicitly so no reader has to infer it from the key.
                "matched_on": "execution_contract",
                "protocol_in_run_key": False,
            },
            "research_duplication": {
                "disposition": self.research_disposition,
                "research_key": self.request.research_key(),
                "prior_judgment_id": self.prior_judgment_id,
                "declared_intent": self.request.intent,
                "intent_is_evidence_not_proof": True,
                "strategy_falsified": False,
            },
        }

    def readback(self) -> dict[str, object]:
        return {
            "schema": DECISION_READBACK_SCHEMA,
            "decision_identity": self.identity,
            "outcome": self.outcome,
            "reasons": list(self.reasons),
            "key": self.request.key.as_dict(),
            "policy": self.request.policy.as_dict(),
            "research_family": self.request.research_family.as_dict(),
            "preserved_prior_result_ids": list(self.preserved_prior_result_ids),
            "decisions": self.decision_dict(),
            "step_contract_digest": DECISION_STEP_CONTRACT_DIGEST,
            "trace": list(self.trace),
            "counters": self.counters.as_dict(),
            "context_identity": None if self.context is None else self.context.context.identity,
            "paginated_identity": None if self.context is None else self.context.identity,
            # Memory publishes; it never qualifies a research result and it never
            # manufactures evidence that was not already public.
            "grants_eligibility": False,
            "fabricates_evidence": False,
            "scanned_full_history": False,
        }

    def public_record(self) -> dict[str, object]:
        """Everything needed to replay this decision, and nothing else."""

        return {
            "schema": DECISION_RECORD_SCHEMA,
            "decision_identity": self.identity,
            "request": self.request.as_dict(),
            "outcome": self.outcome,
            "reasons": list(self.reasons),
            "request_disposition": self.request_disposition,
            "run_disposition": self.run_disposition,
            "research_disposition": self.research_disposition,
            "reused_run_id": self.reused_run_id,
            "prior_judgment_id": self.prior_judgment_id,
            "preserved_prior_result_ids": list(self.preserved_prior_result_ids),
            "trace": list(self.trace),
            "counters": self.counters.as_dict(),
        }

    @property
    def context_identity(self) -> str | None:
        return None if self.context is None else self.context.context.identity


class _Trace:
    """The call trace.  Steps may be skipped, never reordered."""

    __slots__ = ("_steps",)

    def __init__(self) -> None:
        self._steps: list[str] = []

    def step(self, name: str) -> None:
        if self._steps and _STEP_INDEX[name] <= _STEP_INDEX[self._steps[-1]]:
            raise DecisionRefusal(f"decision step out of order: {name}")
        self._steps.append(name)

    def frozen(self) -> tuple[str, ...]:
        return tuple(self._steps)


def decide_research_request(
    value: Mapping[str, object],
    *,
    ledger: DecisionLedger,
    exposure: ExposureLog,
    engine: ResearchEngineSeam,
) -> DecisionOutcome:
    """Decide, in the declared order, whether this research may spend anything.

    The whole point of the ordering is that the expensive steps are unreachable
    from the cheap ones.  Everything before ``stop_on_research_duplicate`` reads
    frozen inputs and published records only; nothing before it touches
    ``engine``.  A duplicate returns from that step, so the engine seam is not
    merely "not used" on that path -- it is not reachable.
    """

    request = DecisionRequest.parse(value)
    trace = _Trace()

    # 1-2. Predecessor / policy, then the approved sources.  Both are frozen
    # declarations; neither opens a store or issues a "latest" query.
    trace.step("read_predecessor_policy")
    trace.step("read_approved_sources")

    # 3. Request idempotency, over the #396 action key and the frozen input.
    trace.step("decide_request_idempotency")
    recovered = _recover_or_reject(request, ledger, exposure)
    if recovered is not None:
        return recovered

    # 4. Run reuse, against the original execution contract only.
    trace.step("decide_run_reuse")
    run_disposition, reused_run_id = _decide_run_reuse(request, ledger)

    # 5. Research duplication, against the prior published judgment.
    trace.step("decide_research_duplication")
    research_disposition, research_reasons, prior = _decide_research_duplication(request, ledger)

    # 6. Publish the canonical readback of all three decisions.
    trace.step("publish_decision_readback")
    preserved = () if prior is None else prior.prior_result_ids

    if research_disposition != "new_research":
        # 7. Stop.  A duplicate -- or an unrepaired data blocker -- ends here,
        # before a Context is frozen, before budget, before any call.
        trace.step("stop_on_research_duplicate")
        outcome_state = (
            "stopped_duplicate"
            if research_disposition == "duplicate_research"
            else "blocked_prior_data_blocker"
        )
        return _freeze(
            request,
            outcome=outcome_state,
            request_disposition="new_request",
            run_disposition=run_disposition,
            research_disposition=research_disposition,
            reasons=research_reasons,
            trace=trace,
            counters=SpendCounters.zero(),
            reused_run_id=reused_run_id,
            prior=prior,
            preserved=preserved,
            context=None,
            ledger=ledger,
        )

    # 8-9. Only now: visibility, then required completeness.  A reuse is not
    # exempt -- current authorization, currency and protection are re-checked
    # here through the existing #394/#395 gate, not by a new authority.
    trace.step("check_visibility")
    context = freeze_paginated_research_context(request.paginated_context)
    delivery = deliver_paginated_research_brief(context, request.visibility_request)
    # Three delivery outcomes stay distinct here exactly as #398 keeps them
    # distinct: only ``blocked`` is an authorization answer.  A ``refused``
    # retrieval is an honest completeness answer and belongs to the next step,
    # so a gap in the evidence is never reported as a permission problem.
    if delivery.get("delivery") == "blocked":
        return _freeze(
            request,
            outcome="blocked_by_gate",
            request_disposition="new_request",
            run_disposition=run_disposition,
            research_disposition=research_disposition,
            reasons=(f"visibility:{delivery.get('reason', 'blocked')}",),
            trace=trace,
            counters=SpendCounters.zero(),
            reused_run_id=reused_run_id,
            prior=prior,
            preserved=preserved,
            context=context,
            ledger=ledger,
        )

    trace.step("check_required_completeness")
    incomplete = _required_completeness_failure(context)
    if incomplete is not None:
        return _freeze(
            request,
            outcome="blocked_by_gate",
            request_disposition="new_request",
            run_disposition=run_disposition,
            research_disposition=research_disposition,
            reasons=(incomplete,),
            trace=trace,
            counters=SpendCounters.zero(),
            reused_run_id=reused_run_id,
            prior=prior,
            preserved=preserved,
            context=context,
            ledger=ledger,
        )

    # 10-13. The spending phase, in the declared order.
    trace.step("publish_engine_context")
    engine.publish_context(context.public_record())
    trace.step("reserve_budget")
    engine.reserve_budget(request.budget_request.budget_id, request.budget_request.units)
    runs_executed = 0
    if run_disposition == "new_run":
        # A reused or attached run is an execution fact that already exists.
        # Re-running it would manufacture a second, spurious piece of evidence.
        trace.step("execute_run")
        engine.execute_run(request.run_key(), request.run.contract_dict())
        runs_executed = 1
    trace.step("call_research_engine")
    engine.call_research_engine(
        {
            "action_key": request.action_key(),
            "research_key": request.research_key(),
            "run_key": request.run_key(),
            "context_identity": context.context.identity,
            "paginated_identity": context.identity,
        }
    )
    return _freeze(
        request,
        outcome="proceeded",
        request_disposition="new_request",
        run_disposition=run_disposition,
        research_disposition=research_disposition,
        reasons=research_reasons,
        trace=trace,
        counters=SpendCounters(
            engine_contexts_published=1,
            budget_reservations=1,
            runs_executed=runs_executed,
            research_engine_calls=1,
        ),
        reused_run_id=reused_run_id,
        prior=prior,
        preserved=preserved,
        context=context,
        ledger=ledger,
    )


def inspect_decision_history(
    ledger: DecisionLedger,
    exposure: ExposureLog,
    *,
    research_key: str | None = None,
    family_id: str | None = None,
) -> dict[str, object]:
    """Read published decision history.  Read-only, and structurally so.

    This function takes no engine seam at all, so a manual inspection has no
    path to a research-engine Context, a budget reservation, a run, or a call.
    It is not a bypass around the gate and it cannot start an iteration; an
    MLflow dashboard or a future Optuna study reading this is in exactly the
    same position as a person reading it.
    """

    judgment = None if research_key is None else ledger.judgment_for(research_key)
    return {
        "schema": DECISION_HISTORY_SCHEMA,
        "access": "read_only",
        "research_key": research_key,
        "judgment": None if judgment is None else judgment.as_dict(),
        "run": (
            None
            if judgment is None or ledger.run_for(judgment.run_key) is None
            else ledger.run_for(judgment.run_key).as_dict()  # type: ignore[union-attr]
        ),
        "exposure_usage": exposure.usage_history(family_id=family_id),
        "invokes_engine": False,
        "reserves_budget": False,
        "publishes_context": False,
        "bypasses_duplicate_gate": False,
        "grants_eligibility": False,
        "scanned_full_history": False,
    }


def reconstruct_decision_outcome(record: Mapping[str, object]) -> dict[str, object]:
    """Replay a frozen decision record and re-derive its identity.

    Nothing is re-queried.  The record's own frozen request is re-parsed, the
    three keys are recomputed from it, and the recorded identity must come back
    out.  A record edited after the fact -- a swapped disposition, a doctored
    counter, a newer run key -- fails loudly rather than being patched from a
    "latest" lookup or guessed at from a checkpoint.
    """

    item = _mapping(record, "decision record")
    _fields_subset(
        item,
        {
            "schema",
            "decision_identity",
            "request",
            "outcome",
            "reasons",
            "request_disposition",
            "run_disposition",
            "research_disposition",
            "reused_run_id",
            "prior_judgment_id",
            "preserved_prior_result_ids",
            "trace",
            "counters",
        },
        "decision record",
    )
    if item.get("schema") != DECISION_RECORD_SCHEMA:
        raise DecisionRefusal("decision record schema is invalid")
    recorded = item.get("decision_identity")
    if not isinstance(recorded, str) or _SAFE_DIGEST.fullmatch(recorded) is None:
        raise DecisionRefusal("decision record identity is invalid")
    request = DecisionRequest.parse(_mapping(item.get("request"), "decision record request"))
    counters = _mapping(item.get("counters"), "decision record counters")
    rebuilt = _identity(
        request,
        outcome=_token(item.get("outcome"), "decision record outcome"),
        request_disposition=_token(item.get("request_disposition"), "decision record request"),
        run_disposition=_token(item.get("run_disposition"), "decision record run"),
        research_disposition=_token(item.get("research_disposition"), "decision record research"),
        reasons=_ordered_tokens(item.get("reasons", []), "decision record reasons"),
        trace=_ordered_tokens(item.get("trace", []), "decision record trace"),
        counters=SpendCounters(
            engine_contexts_published=_count(counters.get("engine_contexts_published")),
            budget_reservations=_count(counters.get("budget_reservations")),
            runs_executed=_count(counters.get("runs_executed")),
            research_engine_calls=_count(counters.get("research_engine_calls")),
        ),
        reused_run_id=_optional(item.get("reused_run_id"), "decision record reused_run_id"),
        prior_judgment_id=_optional(item.get("prior_judgment_id"), "decision record prior"),
        preserved=_ordered_tokens(
            item.get("preserved_prior_result_ids", []), "decision record prior result ids"
        ),
    )
    if rebuilt != recorded:
        raise DecisionRefusal("decision record does not reproduce its identity")
    return {
        **dict(item),
        "replayed_from": "frozen_public_record",
        "used_latest_query": False,
        "invoked_engine": False,
    }


def _recover_or_reject(
    request: DecisionRequest,
    ledger: DecisionLedger,
    exposure: ExposureLog,
) -> DecisionOutcome | None:
    """Request idempotency, exactly as #396 defines it.

    Uncertainty is checked first.  A local record that says "prepared" and an
    external consumer that may already hold the request are not the same fact,
    so an action in ``delivery_uncertain`` is reconciled against public events
    before anything else is decided -- never resent because a retry arrived.
    """

    action_key = request.action_key()
    if exposure.state(action_key) == "delivery_uncertain":
        return _freeze(
            request,
            outcome="reconcile_required",
            request_disposition="reconcile_required",
            run_disposition="new_run",
            research_disposition="new_research",
            reasons=("delivery_uncertain_must_reconcile_first",),
            trace=_trace_to("decide_request_idempotency"),
            counters=SpendCounters.zero(),
            reused_run_id=None,
            prior=None,
            preserved=(),
            context=None,
            ledger=ledger,
            record=False,
        )
    previous = ledger.decision_for(action_key)
    if previous is None:
        return None
    recorded_input = DecisionRequest.parse(
        _mapping(previous.get("request"), "recorded request")
    ).input_digest()
    if recorded_input == request.input_digest():
        # Same key, same frozen input: recover the existing decision.  A retry
        # re-reads a fact; it never re-executes one.
        return _freeze(
            request,
            outcome="recovered_existing",
            request_disposition="recovered_existing",
            run_disposition=_token(previous.get("run_disposition"), "recorded run_disposition"),
            research_disposition=_token(
                previous.get("research_disposition"), "recorded research_disposition"
            ),
            reasons=("recovered_existing_action",),
            trace=_trace_to("decide_request_idempotency"),
            counters=SpendCounters.zero(),
            reused_run_id=_optional(previous.get("reused_run_id"), "recorded reused_run_id"),
            prior=None,
            preserved=_ordered_tokens(
                previous.get("preserved_prior_result_ids", []), "recorded prior result ids"
            ),
            context=None,
            ledger=ledger,
            record=False,
        )
    return _freeze(
        request,
        outcome="rejected_key_conflict",
        request_disposition="rejected_key_conflict",
        run_disposition="new_run",
        research_disposition="new_research",
        reasons=("idempotency_key_reused_with_different_input",),
        trace=_trace_to("decide_request_idempotency"),
        counters=SpendCounters.zero(),
        reused_run_id=None,
        prior=None,
        preserved=(),
        context=None,
        ledger=ledger,
        record=False,
    )


def _decide_run_reuse(
    request: DecisionRequest,
    ledger: DecisionLedger,
) -> tuple[RunDisposition, str | None]:
    """Match the whole execution contract, or run again.

    A Genome match is necessary but never sufficient: the run key also carries
    the Package, the parameters, the data snapshot and range, the cost and
    execution environment and the randomness contract, so a legitimate new
    sample is a different run and is never absorbed into an old one.
    """

    published = ledger.run_for(request.run_key())
    if published is None or published.terminal_state not in QUALIFYING_RUN_STATES:
        return "new_run", None
    if published.protocol_identity != request.question.protocol.identity():
        # Same execution input, different statistical protocol: attach to the
        # existing run rather than re-executing it.  The judgment is still new.
        return "attached_run", published.run_id
    return "reused_run", published.run_id


def _decide_research_duplication(
    request: DecisionRequest,
    ledger: DecisionLedger,
) -> tuple[ResearchDisposition, tuple[str, ...], JudgmentRecord | None]:
    """Compare the question, not the label and not the declared intent."""

    in_flight = ledger.in_flight_for(request.research_key())
    if in_flight is not None and in_flight != request.action_key():
        # An equivalent research action was already authorised under another
        # idempotency key.  Paying again would buy the same answer twice.
        return (
            "duplicate_research",
            ("equivalent_research_already_in_flight", f"in_flight_action:{in_flight}"),
            None,
        )
    prior = ledger.judgment_for(request.research_key())
    if prior is None:
        return "new_research", (f"no_prior_judgment_for_research_key:{request.intent}",), None
    if prior.state == "withdrawn":
        return "new_research", ("prior_judgment_withdrawn",), prior
    if prior.state == "blocked_by_data":
        repair = request.blocker_repair
        if repair is None or not repair.owner_permitted:
            # The old blocker is preserved and is *not* a falsification.  It
            # simply has not been repaired under an owner-permitted condition
            # yet, so no new research spend is authorised either.
            return (
                "blocked_prior_data_blocker",
                ("prior_data_blocker_unresolved", "not_strategy_falsification"),
                prior,
            )
        if prior.blocker_id is not None and repair.blocker_id != prior.blocker_id:
            raise DecisionRefusal("blocker_repair does not name the recorded blocker")
        condition = f"new_condition:{repair.new_condition}"
        return (
            "new_research",
            ("blocker_repaired_under_owner_permitted_condition", condition),
            prior,
        )
    # A completed judgment exists for this exact research key.  Nothing in the
    # frozen inputs differs -- not the question, not the execution contract, not
    # the protocol -- so the declared intent cannot make it new.
    return (
        "duplicate_research",
        ("equivalent_completed_research", f"declared_intent_not_evidence:{request.intent}"),
        prior,
    )


def _required_completeness_failure(context: PaginatedResearchContext) -> str | None:
    if not context.outcome.deliverable:
        return f"retrieval:{context.outcome.state}"
    if context.context.brief.status != "assembled":
        first = context.context.brief.block_reasons[0]
        return f"brief_blocked:{first}"
    return None


def _freeze(
    request: DecisionRequest,
    *,
    outcome: DecisionOutcomeState,
    request_disposition: RequestDisposition,
    run_disposition: RunDisposition,
    research_disposition: ResearchDisposition,
    reasons: tuple[str, ...],
    trace: _Trace | tuple[str, ...],
    counters: SpendCounters,
    reused_run_id: str | None,
    prior: JudgmentRecord | None,
    preserved: tuple[str, ...],
    context: PaginatedResearchContext | None,
    ledger: DecisionLedger,
    record: bool = True,
) -> DecisionOutcome:
    steps = trace.frozen() if isinstance(trace, _Trace) else trace
    identity = _identity(
        request,
        outcome=outcome,
        request_disposition=request_disposition,
        run_disposition=run_disposition,
        research_disposition=research_disposition,
        reasons=reasons,
        trace=steps,
        counters=counters,
        reused_run_id=reused_run_id,
        prior_judgment_id=None if prior is None else prior.judgment_id,
        preserved=preserved,
    )
    result = DecisionOutcome(
        request=request,
        outcome=outcome,
        request_disposition=request_disposition,
        run_disposition=run_disposition,
        research_disposition=research_disposition,
        reasons=reasons,
        trace=steps,
        counters=counters,
        reused_run_id=reused_run_id,
        prior_judgment_id=None if prior is None else prior.judgment_id,
        preserved_prior_result_ids=preserved,
        context=context,
        identity=identity,
    )
    if record:
        ledger.record_decision(request.action_key(), result.public_record())
    return result


def _trace_to(step: str) -> tuple[str, ...]:
    return DECISION_STEPS[: _STEP_INDEX[step] + 1]


def _identity(
    request: DecisionRequest,
    *,
    outcome: str,
    request_disposition: str,
    run_disposition: str,
    research_disposition: str,
    reasons: tuple[str, ...],
    trace: tuple[str, ...],
    counters: SpendCounters,
    reused_run_id: str | None,
    prior_judgment_id: str | None,
    preserved: tuple[str, ...],
) -> str:
    """Bind the frozen inputs, all three decisions, the call trace and the spend.

    The step-contract digest takes part, so renaming or reordering a declared
    step is a different decision rather than a silent relabelling of the same
    one.
    """

    return _digest(
        {
            "schema": DECISION_RECORD_SCHEMA,
            "step_contract_digest": DECISION_STEP_CONTRACT_DIGEST,
            "action_key": request.action_key(),
            "input_digest": request.input_digest(),
            "run_key": request.run_key(),
            "research_key": request.research_key(),
            "outcome": outcome,
            "request_disposition": request_disposition,
            "run_disposition": run_disposition,
            "research_disposition": research_disposition,
            "reasons": list(reasons),
            "trace": list(trace),
            "counters": counters.as_dict(),
            "reused_run_id": reused_run_id,
            "prior_judgment_id": prior_judgment_id,
            "preserved_prior_result_ids": list(preserved),
        }
    )


def _ordered_tokens(value: object, label: str) -> tuple[str, ...]:
    """Validate a token list *without* reordering it.

    The shared ``_tokens`` helper canonicalises by sorting, which is right for a
    set-like field and wrong here: a call trace and a reason list are sequences,
    and sorting them would silently rewrite the very order this contract exists
    to prove.
    """

    items = _list(value, label)
    return tuple(_token(item, label) for item in items)


def _count(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DecisionRefusal("decision record counter is invalid")
    return value


def _optional(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _token(value, label)


__all__ = [
    "DECISION_HISTORY_SCHEMA",
    "DECISION_OUTCOMES",
    "DECISION_READBACK_SCHEMA",
    "DECISION_RECORD_SCHEMA",
    "DECISION_REQUEST_SCHEMA",
    "DECISION_STEPS",
    "DECISION_STEP_CONTRACT",
    "DECISION_STEP_CONTRACT_DIGEST",
    "JUDGMENT_LEDGER_SCHEMA",
    "JUDGMENT_STATES",
    "QUALIFYING_RUN_STATES",
    "REQUEST_DISPOSITIONS",
    "RESEARCH_DISPOSITIONS",
    "RESEARCH_INTENTS",
    "RUN_DISPOSITIONS",
    "RUN_LEDGER_SCHEMA",
    "RUN_TERMINAL_STATES",
    "BlockerRepair",
    "BudgetRequest",
    "DecisionLedger",
    "DecisionOutcome",
    "DecisionPolicyRef",
    "DecisionRefusal",
    "DecisionRequest",
    "JudgmentRecord",
    "RandomnessContract",
    "ResearchEngineSeam",
    "ResearchQuestion",
    "RunContract",
    "RunRecord",
    "SpendCounters",
    "StatisticalProtocol",
    "decide_research_request",
    "inspect_decision_history",
    "reconstruct_decision_outcome",
]
