"""The A0 second round: real memory use, a controlled model decision, correct reuse/stop.

#394/#395 decide what a consumer may *see*; #396 records what was actually
*delivered*; #397/#398 freeze the bounded brief and prove the pages behind it;
#399 decides whether a piece of research should happen at all; #401 says whether
the sources are still believed.  Each of those was built and accepted on its
own.  This module is the seam that runs them together for exactly one scenario:
the A0 second round.

Four rules shape everything below.

**An unauthorized engine is reported, never simulated.**  ``EngineAuthorization``
is read from already-published owner configuration.  It carries a public engine
reference and a transport; it must never carry a credential, and this module
refuses a declaration that does.  Nothing here creates an API key, copies one,
or reaches a paid provider.  When no authorized real engine exists, the model
delivery resolves to ``not_run`` (or ``blocked`` when a gate stopped it first),
and that is a truthful terminal outcome for the round — not a failure to paper
over.  ``delivered`` is reachable *only* from an authorized real transport, so a
recorded response, a stub, or a successful connectivity probe can never present
itself as actual research use.

**Delivered is not cognized.**  A delivery records that an envelope left the
boundary, nothing more.  ``ModelDelivery.proves_model_use`` is the single place
that claim is made, and it is true only for a real connected delivery.  Evidence
is reported in two separate layers — ``real_connected`` and
``offline_regression`` — and the offline layer can never produce ``delivered``,
so an offline branch cannot stand in for required connected evidence.

**The model may only continue, add evidence, or stop.**  A response is reviewed
structurally against the frozen policy: every cited source must already be
approved, every proposed step must already be permitted, and a request for a new
run or new budget is refused outright.  A conclusion with no cited source is
refused rather than accepted as verified.  A refused review never becomes a
pass, and it never yields a Candidate.

**Protection is checked before any read, and again on everything added.**  #399
already gates the Context before the first unit of spend.  This module gates the
*final envelope* and the *tool return* separately, because material that the
Context never declared arrives at both, and an addition must be neither silently
dropped nor silently delivered.  Uncertain delivery stays uncertain: it is
reconciled through #396, never washed back to "unseen" and never blindly resent.

What this module deliberately does not do: it adds no dependency, opens no
store, starts no backtest, and — absent an owner-authorized engine — makes no
model call at all.  It composes six already-accepted modules and reports what
actually happened.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .core import AcceptanceFailure
from .research_context import ContextAssemblyFailure
from .research_decision import (
    DecisionLedger,
    DecisionOutcome,
    ResearchEngineSeam,
    SpendCounters,
    decide_research_request,
)
from .research_exposure import EXPOSURE_EVENT_SCHEMA, ExposureLog, TransportKind
from .research_visibility import GateDecision, guard_visibility_delivery

ROUND2_DECLARATION_SCHEMA = "quant-research.a0-round-two-declaration.v1"
ROUND2_RECORD_SCHEMA = "quant-research.a0-round-two-record.v1"
ROUND2_READBACK_SCHEMA = "quant-research.a0-round-two-readback.v1"

AuthorizationState = Literal["authorized", "unauthorized", "unavailable"]
DeliveryState = Literal["delivered", "blocked", "not_run"]
ReviewVerdict = Literal["continue", "add_evidence", "stop", "refused"]
EvidenceLayer = Literal["real_connected", "offline_regression"]

#: The only actions a reviewed model response is ever allowed to propose.
ALLOWED_MODEL_ACTIONS: tuple[str, ...] = ("continue", "add_evidence", "stop")
AUTHORIZATION_STATES: tuple[AuthorizationState, ...] = (
    "authorized",
    "unauthorized",
    "unavailable",
)
DELIVERY_STATES: tuple[DeliveryState, ...] = ("delivered", "blocked", "not_run")
EVIDENCE_LAYERS: tuple[EvidenceLayer, ...] = ("real_connected", "offline_regression")

#: Field names that would mean a credential travelled with the declaration.  The
#: check is on the *name*, so a value is never inspected, logged, or echoed.
CREDENTIAL_FIELDS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "auth_token",
        "authorization",
        "bearer",
        "credential",
        "credentials",
        "password",
        "secret",
        "token",
    }
)

_AUTHORIZATION_FIELDS = frozenset(
    {"state", "engine_ref", "transport", "evidence_ref", "reason"}
)
_FREEZE_FIELDS = frozenset(
    {
        "schema",
        "knowledge_cutoff",
        "purpose",
        "consumer",
        "required_closure",
        "optional_scope",
        "template_version",
        "model_version",
        "parameter_digest",
        "tool_input_version",
        "allowed_actions",
        "authorization",
        "decision_request",
        "envelope_request",
        "tool_return_request",
    }
)
_RESPONSE_FIELDS = frozenset(
    {
        "proposed_action",
        "cited_source_ids",
        "proposed_step_ids",
        "assumptions",
        "boundaries",
        "requests_new_run",
        "requests_new_budget",
        "requests_new_strategy",
    }
)
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}")
_TRANSPORTS: frozenset[str] = frozenset({"offline_stand_in", "real_process"})


class RoundTwoRefusal(ContextAssemblyFailure):
    """The second round refused a declaration, a response, or a claim."""


# --- engine authorization ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineAuthorization:
    """Whether an owner-authorized real research engine exists for this round.

    This is *read*, never arranged.  ``authorized`` requires both a public
    engine reference and a real transport, so an offline stand-in can never
    describe itself as authorized.
    """

    state: AuthorizationState
    engine_ref: str | None
    transport: TransportKind
    evidence_ref: str
    reason: str

    @classmethod
    def parse(cls, value: object) -> EngineAuthorization:
        mapping = _mapping(value, "engine authorization")
        leaked = sorted(set(mapping) & CREDENTIAL_FIELDS)
        if leaked:
            # Naming the fields is safe; their values are never read.
            raise RoundTwoRefusal(
                "engine authorization must not carry credentials: " + ", ".join(leaked)
            )
        _fields_subset(mapping, _AUTHORIZATION_FIELDS, "engine authorization")
        state = mapping.get("state")
        if state not in AUTHORIZATION_STATES:
            raise RoundTwoRefusal("engine authorization state is invalid")
        transport = mapping.get("transport")
        if transport not in _TRANSPORTS:
            raise RoundTwoRefusal("engine authorization transport is invalid")
        engine_ref = mapping.get("engine_ref")
        if engine_ref is not None:
            engine_ref = _token(engine_ref, "engine authorization engine_ref")
        evidence_ref = _token(mapping.get("evidence_ref"), "engine authorization evidence_ref")
        reason = _reason(mapping.get("reason"), "engine authorization reason")
        if state == "authorized" and (engine_ref is None or transport != "real_process"):
            raise RoundTwoRefusal(
                "an authorized engine requires a public engine_ref and a real transport"
            )
        return cls(
            state=state,
            engine_ref=engine_ref,
            transport=transport,
            evidence_ref=evidence_ref,
            reason=reason,
        )

    @property
    def authorized(self) -> bool:
        return self.state == "authorized" and self.transport == "real_process"

    @property
    def layer(self) -> EvidenceLayer:
        """Which evidence layer anything produced under this authorization sits in."""

        return "real_connected" if self.authorized else "offline_regression"

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "engine_ref": self.engine_ref,
            "transport": self.transport,
            "evidence_ref": self.evidence_ref,
            "reason": self.reason,
            "layer": self.layer,
        }


def unauthorized_engine(reason: str, *, evidence_ref: str) -> EngineAuthorization:
    """The honest default: no owner-authorized engine was found for this round."""

    return EngineAuthorization.parse(
        {
            "state": "unauthorized",
            "engine_ref": None,
            "transport": "offline_stand_in",
            "evidence_ref": evidence_ref,
            "reason": reason,
        }
    )


# --- the governed engine seam ------------------------------------------------


class GovernedRoundTwoEngine:
    """#399's engine seam, with the model call gated on owner authorization.

    The Context, budget and run seams are delegated unchanged — those are the
    original owner's already-permitted actions.  ``call_research_engine`` is the
    one that would reach a provider, so an unauthorized round records the
    attempt and returns a ``not_run`` marker instead of calling anything.  The
    attempt count and the real-call count are kept apart, because "we tried" and
    "a model saw it" are different facts.
    """

    def __init__(self, delegate: ResearchEngineSeam, authorization: EngineAuthorization) -> None:
        self.delegate = delegate
        self.authorization = authorization
        self.attempted_calls: list[Mapping[str, object]] = []
        self.real_calls: list[Mapping[str, object]] = []
        self.invocations: list[str] = []
        self.not_run_reasons: list[str] = []

    def publish_context(self, record: Mapping[str, object]) -> str:
        return self.delegate.publish_context(record)

    def reserve_budget(self, budget_id: str, units: int) -> str:
        return self.delegate.reserve_budget(budget_id, units)

    def execute_run(self, run_key: str, contract: Mapping[str, object]) -> str:
        return self.delegate.execute_run(run_key, contract)

    def call_research_engine(self, request: Mapping[str, object]) -> str:
        self.attempted_calls.append(dict(request))
        if not self.authorization.authorized:
            self.not_run_reasons.append(self.authorization.reason)
            return "not_run:engine_not_authorized"
        invocation = self.delegate.call_research_engine(request)
        self.real_calls.append(dict(request))
        self.invocations.append(invocation)
        return invocation

    def counts(self) -> dict[str, int]:
        return {
            "attempted_calls": len(self.attempted_calls),
            "real_calls": len(self.real_calls),
            "not_run": len(self.not_run_reasons),
        }


# --- the model delivery ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelDelivery:
    """What actually reached a model, and under which evidence layer.

    Constructed through :meth:`build` so the invariants hold everywhere: only an
    authorized real transport can be ``delivered``, and anything that is not
    ``delivered`` carries no response at all.
    """

    state: DeliveryState
    layer: EvidenceLayer
    authorization: EngineAuthorization
    invocation_id: str | None
    response_ref: str | None
    response_digest: str | None
    reason: str

    @classmethod
    def build(
        cls,
        *,
        state: DeliveryState,
        authorization: EngineAuthorization,
        reason: str,
        invocation_id: str | None = None,
        response_ref: str | None = None,
        raw_response: Mapping[str, object] | None = None,
    ) -> ModelDelivery:
        if state not in DELIVERY_STATES:
            raise RoundTwoRefusal("model delivery state is invalid")
        # Only a real delivery is connected evidence; a blocked or not-run round
        # stays in the offline layer even when the engine itself was authorized.
        layer: EvidenceLayer = (
            "real_connected"
            if state == "delivered" and authorization.authorized
            else "offline_regression"
        )
        if state == "delivered":
            if not authorization.authorized:
                raise RoundTwoRefusal("a delivered response requires an authorized real engine")
            if invocation_id is None or response_ref is None or raw_response is None:
                raise RoundTwoRefusal("a delivered response requires an invocation and a response")
        else:
            # A blocked or not-run round has no response; claiming one here is
            # exactly the confusion this ticket exists to prevent.
            if invocation_id is not None or response_ref is not None or raw_response is not None:
                raise RoundTwoRefusal(f"a {state} delivery must not carry a model response")
        return cls(
            state=state,
            layer=layer,
            authorization=authorization,
            invocation_id=invocation_id,
            response_ref=response_ref,
            response_digest=None if raw_response is None else _digest(dict(raw_response)),
            reason=_reason(reason, "model delivery reason"),
        )

    @property
    def proves_model_use(self) -> bool:
        """True only for a real connected delivery.  The single claim of use."""

        return self.state == "delivered" and self.layer == "real_connected"

    @property
    def e02_status(self) -> Literal["passed", "blocked", "not_run"]:
        if self.proves_model_use:
            return "passed"
        return "blocked" if self.state == "blocked" else "not_run"

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "layer": self.layer,
            "invocation_id": self.invocation_id,
            "response_ref": self.response_ref,
            # A digest is a controlled reference, never the delivered content.
            "response_digest": self.response_digest,
            "reason": self.reason,
            "proves_model_use": self.proves_model_use,
            "e02_status": self.e02_status,
            "authorization": self.authorization.as_dict(),
        }


# --- the structured review ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelReview:
    """A structured check of one model response against the frozen policy."""

    verdict: ReviewVerdict
    codes: tuple[str, ...]
    cited_source_ids: tuple[str, ...]
    unapproved_source_ids: tuple[str, ...]
    proposed_step_ids: tuple[str, ...]
    unpermitted_step_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    boundaries: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.verdict in ALLOWED_MODEL_ACTIONS

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "codes": list(self.codes),
            "cited_source_ids": list(self.cited_source_ids),
            "unapproved_source_ids": list(self.unapproved_source_ids),
            "proposed_step_ids": list(self.proposed_step_ids),
            "unpermitted_step_ids": list(self.unpermitted_step_ids),
            "assumptions": list(self.assumptions),
            "boundaries": list(self.boundaries),
            "accepted": self.accepted,
        }


def review_model_response(
    response: Mapping[str, object],
    *,
    approved_source_ids: tuple[str, ...],
    permitted_step_ids: tuple[str, ...],
    allowed_actions: tuple[str, ...] = ALLOWED_MODEL_ACTIONS,
) -> ModelReview:
    """Judge a model response on source, assumption and boundary — never on wording.

    The check is structural: which sources it cites, which already-permitted
    steps it proposes, whether it declared its assumptions and boundaries, and
    whether it tried to buy something the policy never granted.  Two responses
    that say the same thing in different words review the same; a response that
    reaches past the policy is refused whatever it says.
    """

    mapping = _mapping(response, "model response")
    _fields_subset(mapping, _RESPONSE_FIELDS, "model response")
    action = mapping.get("proposed_action")
    cited = _tokens(mapping.get("cited_source_ids", []), "cited_source_ids", empty=True)
    steps = _tokens(mapping.get("proposed_step_ids", []), "proposed_step_ids", empty=True)
    assumptions = _statements(mapping.get("assumptions", []), "model response assumptions")
    boundaries = _statements(mapping.get("boundaries", []), "model response boundaries")

    approved = set(approved_source_ids)
    permitted = set(permitted_step_ids)
    unapproved = tuple(source for source in cited if source not in approved)
    unpermitted = tuple(step for step in steps if step not in permitted)

    codes: list[str] = []
    if not isinstance(action, str) or action not in allowed_actions:
        codes.append("action_not_permitted")
    if unapproved:
        codes.append("source_not_approved")
    if unpermitted:
        codes.append("step_not_permitted")
    if _flag(mapping.get("requests_new_run"), "requests_new_run"):
        codes.append("new_run_not_authorized")
    if _flag(mapping.get("requests_new_budget"), "requests_new_budget"):
        codes.append("new_budget_not_authorized")
    if _flag(mapping.get("requests_new_strategy"), "requests_new_strategy"):
        codes.append("new_strategy_not_authorized")
    if not boundaries:
        codes.append("boundary_declaration_missing")
    # Continuing or adding evidence is a claim about the sources; with none
    # cited there is nothing to verify, so it never becomes a conclusion.
    if action in {"continue", "add_evidence"} and not cited:
        codes.append("unsourced_conclusion")

    verdict: ReviewVerdict = "refused" if codes else action  # type: ignore[assignment]
    return ModelReview(
        verdict=verdict,
        codes=tuple(sorted(codes)),
        cited_source_ids=cited,
        unapproved_source_ids=unapproved,
        proposed_step_ids=steps,
        unpermitted_step_ids=unpermitted,
        assumptions=assumptions,
        boundaries=boundaries,
    )


# --- the frozen second round -------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoundTwoFreeze:
    """The frozen second-round declaration: cutoff, purpose, versions, authorization."""

    knowledge_cutoff: str
    purpose: str
    consumer: str
    required_closure: tuple[str, ...]
    optional_scope: tuple[str, ...]
    template_version: str
    model_version: str
    parameter_digest: str
    tool_input_version: str
    allowed_actions: tuple[str, ...]
    authorization: EngineAuthorization
    decision_request: dict[str, Any]
    envelope_request: dict[str, Any] | None
    tool_return_request: dict[str, Any] | None
    identity: str

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> RoundTwoFreeze:
        mapping = _mapping(value, "round-two declaration")
        if mapping.get("schema") != ROUND2_DECLARATION_SCHEMA:
            raise RoundTwoRefusal("round-two declaration schema is invalid")
        _fields_subset(mapping, _FREEZE_FIELDS, "round-two declaration")
        allowed = _tokens(mapping.get("allowed_actions"), "round-two allowed_actions")
        if set(allowed) - set(ALLOWED_MODEL_ACTIONS):
            raise RoundTwoRefusal("round-two allowed_actions exceed the permitted actions")
        authorization = EngineAuthorization.parse(mapping.get("authorization"))
        decision_request = dict(_mapping(mapping.get("decision_request"), "decision_request"))
        envelope = mapping.get("envelope_request")
        tool_return = mapping.get("tool_return_request")
        frozen = cls(
            knowledge_cutoff=_token(mapping.get("knowledge_cutoff"), "knowledge_cutoff"),
            purpose=_token(mapping.get("purpose"), "purpose"),
            consumer=_token(mapping.get("consumer"), "consumer"),
            required_closure=_tokens(mapping.get("required_closure"), "required_closure"),
            optional_scope=_tokens(
                mapping.get("optional_scope", []), "optional_scope", empty=True
            ),
            template_version=_token(mapping.get("template_version"), "template_version"),
            model_version=_token(mapping.get("model_version"), "model_version"),
            parameter_digest=_token(mapping.get("parameter_digest"), "parameter_digest"),
            tool_input_version=_token(mapping.get("tool_input_version"), "tool_input_version"),
            allowed_actions=allowed,
            authorization=authorization,
            decision_request=decision_request,
            envelope_request=None if envelope is None else dict(_mapping(envelope, "envelope")),
            tool_return_request=(
                None if tool_return is None else dict(_mapping(tool_return, "tool_return"))
            ),
            identity="",
        )
        return _with_identity(frozen)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": ROUND2_DECLARATION_SCHEMA,
            "knowledge_cutoff": self.knowledge_cutoff,
            "purpose": self.purpose,
            "consumer": self.consumer,
            "required_closure": list(self.required_closure),
            "optional_scope": list(self.optional_scope),
            "template_version": self.template_version,
            "model_version": self.model_version,
            "parameter_digest": self.parameter_digest,
            "tool_input_version": self.tool_input_version,
            "allowed_actions": list(self.allowed_actions),
            "authorization": self.authorization.as_dict(),
        }


def _with_identity(frozen: RoundTwoFreeze) -> RoundTwoFreeze:
    identity = _digest(
        {
            "declaration": frozen.as_dict(),
            "decision_request": frozen.decision_request,
            "envelope_request": frozen.envelope_request,
            "tool_return_request": frozen.tool_return_request,
        }
    )
    return RoundTwoFreeze(
        knowledge_cutoff=frozen.knowledge_cutoff,
        purpose=frozen.purpose,
        consumer=frozen.consumer,
        required_closure=frozen.required_closure,
        optional_scope=frozen.optional_scope,
        template_version=frozen.template_version,
        model_version=frozen.model_version,
        parameter_digest=frozen.parameter_digest,
        tool_input_version=frozen.tool_input_version,
        allowed_actions=frozen.allowed_actions,
        authorization=frozen.authorization,
        decision_request=frozen.decision_request,
        envelope_request=frozen.envelope_request,
        tool_return_request=frozen.tool_return_request,
        identity=identity,
    )


# --- the round outcome -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoundTwoOutcome:
    """Everything the second round actually produced, layered and honest."""

    freeze: RoundTwoFreeze
    decision: DecisionOutcome
    envelope_gate: GateDecision | None
    tool_return_gate: GateDecision | None
    delivery: ModelDelivery
    review: ModelReview | None
    candidate_id: str | None
    no_candidate_reason: str
    counters: SpendCounters
    engine_counts: dict[str, int]
    exposure_readback: dict[str, object]
    identity: str

    @property
    def e02_status(self) -> Literal["passed", "blocked", "not_run"]:
        return self.delivery.e02_status

    @property
    def evidence_layers(self) -> dict[str, dict[str, object]]:
        """The two layers, reported separately and never merged.

        The connected layer is empty unless a real authorized delivery happened;
        the offline layer holds the regression facts either way.
        """

        connected: dict[str, object] = {
            "status": self.e02_status,
            "proves_model_use": self.delivery.proves_model_use,
            "reason": self.delivery.reason,
            "invocation_id": self.delivery.invocation_id,
            "response_digest": self.delivery.response_digest,
        }
        offline: dict[str, object] = {
            "decision_outcome": self.decision.outcome,
            "run_disposition": self.decision.run_disposition,
            "research_disposition": self.decision.research_disposition,
            "counters": self.counters.as_dict(),
            "engine_counts": dict(self.engine_counts),
            "substitutes_for_connected": False,
        }
        return {"real_connected": connected, "offline_regression": offline}

    def public_record(self) -> dict[str, object]:
        return {
            "schema": ROUND2_RECORD_SCHEMA,
            "freeze": self.freeze.as_dict(),
            "freeze_identity": self.freeze.identity,
            "decision": self.decision.public_record(),
            "delivery": self.delivery.as_dict(),
            "review": None if self.review is None else self.review.as_dict(),
            "candidate_id": self.candidate_id,
            "no_candidate_reason": self.no_candidate_reason,
            "identity": self.identity,
        }

    def readback(self) -> dict[str, object]:
        return {
            "schema": ROUND2_READBACK_SCHEMA,
            "round_identity": self.identity,
            "freeze_identity": self.freeze.identity,
            "e02_status": self.e02_status,
            "evidence_layers": self.evidence_layers,
            "gates": {
                "final_envelope": (
                    None if self.envelope_gate is None else self.envelope_gate.status
                ),
                "tool_return": (
                    None if self.tool_return_gate is None else self.tool_return_gate.status
                ),
            },
            "decision": self.decision.readback(),
            "delivery": self.delivery.as_dict(),
            "review": None if self.review is None else self.review.as_dict(),
            "candidate_id": self.candidate_id,
            "no_candidate_reason": self.no_candidate_reason,
            "counters": self.counters.as_dict(),
            "engine_counts": dict(self.engine_counts),
            "exposure": self.exposure_readback,
        }


def run_a0_round_two(
    value: Mapping[str, object],
    *,
    ledger: DecisionLedger,
    exposure: ExposureLog,
    engine: ResearchEngineSeam,
    model_response: Mapping[str, object] | None = None,
) -> RoundTwoOutcome:
    """Run the frozen A0 second round end to end and report what happened.

    ``model_response`` is only ever consulted when the owner's authorization is
    real; with an unauthorized engine it is ignored entirely, so a response
    handed in by a test or a replay can never become connected evidence.
    """

    freeze = RoundTwoFreeze.parse(value)
    governed = GovernedRoundTwoEngine(engine, freeze.authorization)

    decision = decide_research_request(
        freeze.decision_request, ledger=ledger, exposure=exposure, engine=governed
    )
    if not decision.proceeded:
        return _finish(
            freeze,
            decision,
            governed,
            exposure,
            envelope_gate=None,
            tool_return_gate=None,
            delivery=ModelDelivery.build(
                state="blocked",
                authorization=freeze.authorization,
                reason=f"decision:{decision.outcome}",
            ),
            review=None,
            no_candidate_reason=f"decision_did_not_proceed:{decision.outcome}",
        )

    # The Context was really prepared, whether or not a model ever sees it, so
    # #396 records it here.  Only the *delivery* waits on authorization.
    _append_context_prepared(exposure, freeze, decision)

    # Protection is re-checked on everything the Context never declared, before
    # any model or tool read — an addition is neither dropped nor delivered
    # silently.
    envelope_gate: GateDecision | None = None
    if freeze.envelope_request is not None:
        guarded = guard_visibility_delivery(
            freeze.envelope_request, lambda material_id: material_id
        )
        envelope_gate = guarded.decision
        if guarded.delivery_status != "delivered":
            return _finish(
                freeze,
                decision,
                governed,
                exposure,
                envelope_gate=envelope_gate,
                tool_return_gate=None,
                delivery=ModelDelivery.build(
                    state="blocked",
                    authorization=freeze.authorization,
                    reason=f"final_envelope_gate:{guarded.delivery_status}",
                ),
                review=None,
                no_candidate_reason="final_envelope_gate_blocked",
            )

    if not freeze.authorization.authorized:
        # The honest terminal state: the round was assembled, gated and decided,
        # and then stopped short of a model call that nobody authorized.
        return _finish(
            freeze,
            decision,
            governed,
            exposure,
            envelope_gate=envelope_gate,
            tool_return_gate=None,
            delivery=ModelDelivery.build(
                state="not_run",
                authorization=freeze.authorization,
                reason=freeze.authorization.reason,
            ),
            review=None,
            no_candidate_reason="model_delivery_not_run",
        )

    if model_response is None:
        raise RoundTwoRefusal("an authorized round requires the real controlled model response")

    if not governed.invocations:
        raise RoundTwoRefusal("an authorized round recorded no real engine invocation")
    invocation_id = governed.invocations[-1]
    delivery = ModelDelivery.build(
        state="delivered",
        authorization=freeze.authorization,
        reason="authorized_real_delivery",
        invocation_id=invocation_id,
        response_ref=f"controlled-store:{freeze.identity}",
        raw_response=model_response,
    )
    _append_envelope_delivered(exposure, freeze, decision, delivery)

    tool_return_gate: GateDecision | None = None
    if freeze.tool_return_request is not None:
        returned = guard_visibility_delivery(
            freeze.tool_return_request, lambda material_id: material_id
        )
        tool_return_gate = returned.decision

    review = review_model_response(
        model_response,
        approved_source_ids=decision.request.approved_source_ids,
        permitted_step_ids=_permitted_steps(decision),
        allowed_actions=freeze.allowed_actions,
    )
    candidate_id: str | None = None
    reason = ""
    if review.verdict == "refused":
        reason = "model_response_refused:" + ",".join(review.codes)
    elif review.verdict == "stop":
        reason = "model_proposed_stop"
    elif tool_return_gate is not None and tool_return_gate.status != "allowed":
        reason = f"tool_return_gate:{tool_return_gate.status}"
    else:
        # A new Candidate is an admission, not a side effect of a response: it
        # carries the frozen round identity so the gate can trace it back.
        candidate_id = f"candidate:{freeze.identity}"

    return _finish(
        freeze,
        decision,
        governed,
        exposure,
        envelope_gate=envelope_gate,
        tool_return_gate=tool_return_gate,
        delivery=delivery,
        review=review,
        no_candidate_reason=reason,
        candidate_id=candidate_id,
    )


def _permitted_steps(decision: DecisionOutcome) -> tuple[str, ...]:
    """The next steps round one already published, with their own provenance.

    A model may propose one of these and nothing else, so a "next step" it
    invented has no source and is refused rather than admitted.
    """

    if decision.context is None:
        return ()
    return tuple(
        step.step_id for step in decision.context.context.declaration.candidate_next_steps
    )


def _event(
    freeze: RoundTwoFreeze,
    decision: DecisionOutcome,
    event_type: str,
    *,
    invocation_id: str,
) -> dict[str, object]:
    request = decision.request
    return {
        "schema": EXPOSURE_EVENT_SCHEMA,
        "event_type": event_type,
        "key": request.key.as_dict(),
        "research_action_id": f"a0-round-2:{freeze.identity}",
        "context_identity": decision.context_identity,
        "research_family": request.research_family.as_dict(),
        "policy": {
            "policy_id": request.policy.policy_id,
            "policy_version": request.policy.policy_version,
            "knowledge_cutoff": freeze.knowledge_cutoff,
        },
        "invocation_id": invocation_id,
    }


def _append_context_prepared(
    exposure: ExposureLog,
    freeze: RoundTwoFreeze,
    decision: DecisionOutcome,
) -> None:
    """Record that the Context was assembled — which is true even if nobody read it.

    A retry of the same action finds the record already there and adds nothing,
    so reconciliation never depends on re-preparing anything.
    """

    if exposure.state(decision.request.action_key()) is not None:
        return
    event = _event(freeze, decision, "context_prepared", invocation_id=f"round-2:{freeze.identity}")
    event["context_material_ids"] = list(decision.request.approved_source_ids)
    exposure.append(event)


def _append_envelope_delivered(
    exposure: ExposureLog,
    freeze: RoundTwoFreeze,
    decision: DecisionOutcome,
    delivery: ModelDelivery,
) -> None:
    """Record the controlled reference of what was actually delivered."""

    invocation_id = delivery.invocation_id
    assert invocation_id is not None
    event = _event(freeze, decision, "envelope_delivered", invocation_id=invocation_id)
    event["delivery"] = {
        "envelope_digest": _digest(freeze.as_dict()),
        "envelope_content_ref": delivery.response_ref,
        "provider_request_id": freeze.model_version,
        "template_version": freeze.template_version,
        "tool_input_version": freeze.tool_input_version,
        "receipt_ref": invocation_id,
        "response_ref": delivery.response_ref,
        "added_material_ids": [],
        # Replay reaches the controlled reference, not the payload.
        "replay_coverage": "limited",
    }
    exposure.append(event)


def _finish(
    freeze: RoundTwoFreeze,
    decision: DecisionOutcome,
    governed: GovernedRoundTwoEngine,
    exposure: ExposureLog,
    *,
    envelope_gate: GateDecision | None,
    tool_return_gate: GateDecision | None,
    delivery: ModelDelivery,
    review: ModelReview | None,
    no_candidate_reason: str,
    candidate_id: str | None = None,
) -> RoundTwoOutcome:
    family_id = decision.request.research_family.family_id
    identity = _digest(
        {
            "freeze": freeze.identity,
            "decision": decision.identity,
            "delivery": delivery.as_dict(),
            "review": None if review is None else review.as_dict(),
            "candidate_id": candidate_id,
        }
    )
    return RoundTwoOutcome(
        freeze=freeze,
        decision=decision,
        envelope_gate=envelope_gate,
        tool_return_gate=tool_return_gate,
        delivery=delivery,
        review=review,
        candidate_id=candidate_id,
        no_candidate_reason=no_candidate_reason,
        counters=decision.counters,
        engine_counts=governed.counts(),
        # Usage history is read by family, so it survives across Campaigns.
        exposure_readback=exposure.usage_history(family_id=family_id),
        identity=identity,
    )


# --- shared helpers ----------------------------------------------------------


def _digest(value: object) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RoundTwoRefusal(f"{label} is invalid")
    return value


def _fields_subset(value: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    if set(value) - set(expected):
        raise RoundTwoRefusal(f"{label} fields are invalid")


def _token(value: object, label: str) -> str:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        raise RoundTwoRefusal(f"{label} is invalid")
    return value


def _tokens(value: object, label: str, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RoundTwoRefusal(f"{label} is invalid")
    if not value and not empty:
        raise RoundTwoRefusal(f"{label} is invalid")
    canonical = tuple(sorted(_token(item, label) for item in value))
    if len(canonical) != len(set(canonical)):
        raise RoundTwoRefusal(f"{label} is not canonical")
    return canonical


def _statements(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RoundTwoRefusal(f"{label} is invalid")
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 512:
            raise RoundTwoRefusal(f"{label} is invalid")
    return tuple(value)


def _flag(value: object, label: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise RoundTwoRefusal(f"model response {label} is invalid")
    return value


def _reason(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise AcceptanceFailure(f"{label} is invalid")
    return value
