"""Immutable Research Exposure lifecycle events for Research Memory.

An exposure action moves through ``prepared`` -> ``delivered`` /
``delivery_uncertain`` -> ``completed``.  Events are append-only: a later event
never rewrites an earlier fact, and no event ever moves an action back towards
"unseen".  The log records only what is observable -- a Context identity, the
controlled reference or digest of the envelope that was actually delivered, the
provider request identity, template and tool-input versions, receipt and
response references, and the downstream Candidate / selection decisions that
actually used the material.

Three things this module deliberately does not do.  It does not claim that a
receipt proves the model cognised the content; it only records that a receipt
was observed.  It does not treat a local transaction, checkpoint, or request
timeout as proof that an external consumer did not receive the request -- those
resolve to ``delivery_uncertain`` and are reconciled against public events or
real receipts rather than by blind resend.  And it never grants research
eligibility: a usage history is published for the originating statistical owner,
who remains the only party that decides multiplicity, independence, or
qualification.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from .core import AcceptanceFailure
from .research_visibility import (
    _SAFE_DIGEST,
    VisibilityRequest,
    _digest,
    _fields_subset,
    _mapping,
    _token,
    _tokens,
    evaluate_visibility_request,
)

ExposureState = Literal["prepared", "delivered", "delivery_uncertain", "completed"]
ExposureEventType = Literal[
    "context_prepared",
    "envelope_delivered",
    "delivery_uncertain",
    "completion_linked",
]
ReplayCoverage = Literal["full", "limited", "none"]
UncertaintyReason = Literal[
    "receipt_lost",
    "request_timeout",
    "process_interrupted",
    "persistence_failure",
]
DeliveryObservation = Literal["local_checkpoint", "public_event", "real_receipt"]
TransportKind = Literal["offline_stand_in", "real_process"]
ReconstructionScope = Literal["full", "limited", "denied"]
ContextExposure = Literal["unseen", "prepared", "uncertain", "exposed"]

EXPOSURE_EVENT_SCHEMA = "quant-research.research-exposure-event.v1"
EXPOSURE_READBACK_SCHEMA = "quant-research.research-exposure-readback.v1"
EXPOSURE_USAGE_SCHEMA = "quant-research.research-exposure-usage.v1"

_EVENT_TYPES: frozenset[str] = frozenset(
    {"context_prepared", "envelope_delivered", "delivery_uncertain", "completion_linked"}
)
# An absent action is keyed by "" so the transition table stays a plain mapping.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "": frozenset({"context_prepared"}),
    "prepared": frozenset({"envelope_delivered", "delivery_uncertain"}),
    # Uncertainty is only ever resolved forwards, and only against a real
    # receipt or a public completion result -- never by assuming non-exposure.
    "delivery_uncertain": frozenset({"envelope_delivered", "completion_linked"}),
    # A confirmed delivery is never re-confirmed and never returns to uncertain.
    "delivered": frozenset({"completion_linked"}),
    "completed": frozenset(),
}
_STATE_FOR_EVENT: dict[str, ExposureState] = {
    "context_prepared": "prepared",
    "envelope_delivered": "delivered",
    "delivery_uncertain": "delivery_uncertain",
    "completion_linked": "completed",
}
_EXPOSED_STATES: frozenset[str] = frozenset({"delivered", "completed"})

_KEY_FIELDS = frozenset({"campaign_id", "iteration_id", "consumer", "action", "idempotency_key"})
_FAMILY_FIELDS = frozenset({"family_id", "test_family", "prior_result_ids"})
_POLICY_FIELDS = frozenset({"policy_id", "policy_version", "knowledge_cutoff"})
_DELIVERY_FIELDS = frozenset(
    {
        "envelope_digest",
        "envelope_content_ref",
        "provider_request_id",
        "template_version",
        "tool_input_version",
        "receipt_ref",
        "response_ref",
        "added_material_ids",
        "replay_coverage",
    }
)
_UNCERTAINTY_FIELDS = frozenset({"reason", "observation", "transport"})
_COMPLETION_FIELDS = frozenset(
    {"result_ref", "candidate_ids", "selection_decision_ids", "confirmed_by"}
)
_EVENT_FIELDS = frozenset(
    {
        "schema",
        "event_type",
        "key",
        "research_action_id",
        "context_identity",
        "research_family",
        "policy",
        "invocation_id",
        "context_material_ids",
        "delivery",
        "visibility_request",
        "uncertainty",
        "completion",
    }
)
_UNCERTAINTY_REASONS = frozenset(
    {"receipt_lost", "request_timeout", "process_interrupted", "persistence_failure"}
)
_OBSERVATIONS = frozenset({"local_checkpoint", "public_event", "real_receipt"})
_TRANSPORTS = frozenset({"offline_stand_in", "real_process"})
_COVERAGES = frozenset({"full", "limited", "none"})
_CONFIRMATIONS = frozenset({"real_receipt", "public_event", "completion_result"})


class ExposurePersistenceFailure(AcceptanceFailure):
    """The exposure event could not be durably appended.

    The exposure status is never rolled back to "unseen" because of this: an
    append that fails after an external fact has occurred leaves the action in
    ``delivery_uncertain``.
    """


@dataclass(frozen=True, slots=True)
class ExposureKey:
    campaign_id: str
    iteration_id: str
    consumer: str
    action: str
    idempotency_key: str

    @classmethod
    def parse(cls, value: object) -> ExposureKey:
        item = _mapping(value, "exposure key")
        _fields_subset(item, _KEY_FIELDS, "exposure key")
        return cls(
            campaign_id=_token(item.get("campaign_id"), "exposure key campaign_id"),
            iteration_id=_token(item.get("iteration_id"), "exposure key iteration_id"),
            consumer=_token(item.get("consumer"), "exposure key consumer"),
            action=_token(item.get("action"), "exposure key action"),
            idempotency_key=_token(item.get("idempotency_key"), "exposure key idempotency_key"),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "campaign_id": self.campaign_id,
            "iteration_id": self.iteration_id,
            "consumer": self.consumer,
            "action": self.action,
            "idempotency_key": self.idempotency_key,
        }

    def action_key(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ResearchFamilyRef:
    """The originating research / statistical-test family and the results read."""

    family_id: str
    test_family: str
    prior_result_ids: tuple[str, ...]

    @classmethod
    def parse(cls, value: object) -> ResearchFamilyRef:
        item = _mapping(value, "research_family")
        _fields_subset(item, _FAMILY_FIELDS, "research_family")
        return cls(
            family_id=_token(item.get("family_id"), "research_family.family_id"),
            test_family=_token(item.get("test_family"), "research_family.test_family"),
            prior_result_ids=_tokens(
                item.get("prior_result_ids", []),
                "research_family.prior_result_ids",
                empty=True,
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "family_id": self.family_id,
            "test_family": self.test_family,
            "prior_result_ids": list(self.prior_result_ids),
        }


@dataclass(frozen=True, slots=True)
class ExposurePolicyRef:
    policy_id: str
    policy_version: str
    knowledge_cutoff: str

    @classmethod
    def parse(cls, value: object) -> ExposurePolicyRef:
        item = _mapping(value, "policy")
        _fields_subset(item, _POLICY_FIELDS, "policy")
        return cls(
            policy_id=_token(item.get("policy_id"), "policy.policy_id"),
            policy_version=_token(item.get("policy_version"), "policy.policy_version"),
            knowledge_cutoff=_token(item.get("knowledge_cutoff"), "policy.knowledge_cutoff"),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "knowledge_cutoff": self.knowledge_cutoff,
        }


@dataclass(frozen=True, slots=True)
class DeliveryBinding:
    """What was actually delivered, bound separately from the Context draft."""

    envelope_digest: str
    envelope_content_ref: str | None
    provider_request_id: str
    template_version: str
    tool_input_version: str
    receipt_ref: str | None
    response_ref: str | None
    added_material_ids: tuple[str, ...]
    replay_coverage: ReplayCoverage

    @classmethod
    def parse(cls, value: object) -> DeliveryBinding:
        item = _mapping(value, "delivery")
        _fields_subset(item, _DELIVERY_FIELDS, "delivery")
        coverage = _token(item.get("replay_coverage"), "delivery.replay_coverage")
        if coverage not in _COVERAGES:
            raise AcceptanceFailure(f"delivery.replay_coverage is invalid: {coverage}")
        content_ref = _optional_token(item.get("envelope_content_ref"), "delivery.content_ref")
        # A digest is an identity, never the body.  Full replay coverage may only
        # be declared when an approved store actually holds the envelope.
        if coverage == "full" and content_ref is None:
            raise AcceptanceFailure(
                "delivery.replay_coverage cannot be full without a stored envelope reference"
            )
        if coverage == "none" and content_ref is not None:
            raise AcceptanceFailure("delivery.replay_coverage is inconsistent with a stored ref")
        return cls(
            envelope_digest=_digest_field(item.get("envelope_digest"), "delivery.envelope_digest"),
            envelope_content_ref=content_ref,
            provider_request_id=_token(
                item.get("provider_request_id"), "delivery.provider_request_id"
            ),
            template_version=_token(item.get("template_version"), "delivery.template_version"),
            tool_input_version=_token(
                item.get("tool_input_version"), "delivery.tool_input_version"
            ),
            receipt_ref=_optional_token(item.get("receipt_ref"), "delivery.receipt_ref"),
            response_ref=_optional_token(item.get("response_ref"), "delivery.response_ref"),
            added_material_ids=_tokens(
                item.get("added_material_ids", []),
                "delivery.added_material_ids",
                empty=True,
            ),
            replay_coverage=coverage,  # type: ignore[arg-type]
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "envelope_digest": self.envelope_digest,
            "envelope_content_ref": self.envelope_content_ref,
            "provider_request_id": self.provider_request_id,
            "template_version": self.template_version,
            "tool_input_version": self.tool_input_version,
            "receipt_ref": self.receipt_ref,
            "response_ref": self.response_ref,
            "added_material_ids": list(self.added_material_ids),
            "replay_coverage": self.replay_coverage,
        }


@dataclass(frozen=True, slots=True)
class DeliveryUncertainty:
    reason: UncertaintyReason
    observation: DeliveryObservation
    transport: TransportKind

    @classmethod
    def parse(cls, value: object) -> DeliveryUncertainty:
        item = _mapping(value, "uncertainty")
        _fields_subset(item, _UNCERTAINTY_FIELDS, "uncertainty")
        reason = _token(item.get("reason"), "uncertainty.reason")
        if reason not in _UNCERTAINTY_REASONS:
            raise AcceptanceFailure(f"uncertainty.reason is invalid: {reason}")
        observation = _token(item.get("observation"), "uncertainty.observation")
        if observation not in _OBSERVATIONS:
            raise AcceptanceFailure(f"uncertainty.observation is invalid: {observation}")
        transport = _token(item.get("transport"), "uncertainty.transport")
        if transport not in _TRANSPORTS:
            raise AcceptanceFailure(f"uncertainty.transport is invalid: {transport}")
        return cls(
            reason=reason,  # type: ignore[arg-type]
            observation=observation,  # type: ignore[arg-type]
            transport=transport,  # type: ignore[arg-type]
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "reason": self.reason,
            "observation": self.observation,
            "transport": self.transport,
        }


@dataclass(frozen=True, slots=True)
class CompletionLink:
    """The completion result and the downstream usage that actually consumed it."""

    result_ref: str
    candidate_ids: tuple[str, ...]
    selection_decision_ids: tuple[str, ...]
    confirmed_by: Literal["real_receipt", "public_event", "completion_result"]

    @classmethod
    def parse(cls, value: object) -> CompletionLink:
        item = _mapping(value, "completion")
        _fields_subset(item, _COMPLETION_FIELDS, "completion")
        confirmed = _token(item.get("confirmed_by"), "completion.confirmed_by")
        if confirmed not in _CONFIRMATIONS:
            raise AcceptanceFailure(f"completion.confirmed_by is invalid: {confirmed}")
        return cls(
            result_ref=_token(item.get("result_ref"), "completion.result_ref"),
            candidate_ids=_tokens(
                item.get("candidate_ids", []), "completion.candidate_ids", empty=True
            ),
            selection_decision_ids=_tokens(
                item.get("selection_decision_ids", []),
                "completion.selection_decision_ids",
                empty=True,
            ),
            confirmed_by=confirmed,  # type: ignore[arg-type]
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "result_ref": self.result_ref,
            "candidate_ids": list(self.candidate_ids),
            "selection_decision_ids": list(self.selection_decision_ids),
            "confirmed_by": self.confirmed_by,
        }


@dataclass(frozen=True, slots=True)
class ExposureEvent:
    """One immutable append-only exposure fact."""

    event_type: ExposureEventType
    key: ExposureKey
    research_action_id: str
    context_identity: str
    research_family: ResearchFamilyRef
    policy: ExposurePolicyRef
    invocation_id: str
    context_material_ids: tuple[str, ...]
    delivery: DeliveryBinding | None
    uncertainty: DeliveryUncertainty | None
    completion: CompletionLink | None
    gate_identity: str | None
    input_digest: str
    sequence: int
    persisted: bool

    @property
    def action_key(self) -> str:
        return self.key.action_key()

    def binding(self) -> tuple[str, str, tuple[object, ...], tuple[str, ...]]:
        return (
            self.research_action_id,
            self.context_identity,
            (self.research_family.family_id, self.research_family.test_family),
            (self.policy.policy_id, self.policy.policy_version),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": EXPOSURE_EVENT_SCHEMA,
            "event_type": self.event_type,
            "sequence": self.sequence,
            "action_key": self.action_key,
            "key": self.key.as_dict(),
            "research_action_id": self.research_action_id,
            "context_identity": self.context_identity,
            "research_family": self.research_family.as_dict(),
            "policy": self.policy.as_dict(),
            "invocation_id": self.invocation_id,
            "context_material_ids": list(self.context_material_ids),
            "delivery": None if self.delivery is None else self.delivery.as_dict(),
            "uncertainty": None if self.uncertainty is None else self.uncertainty.as_dict(),
            "completion": None if self.completion is None else self.completion.as_dict(),
            "gate_identity": self.gate_identity,
            "input_digest": self.input_digest,
            "persisted": self.persisted,
        }


@dataclass(frozen=True, slots=True)
class ExposureReplay:
    """The result of asking for historical content back, under current authority."""

    action_key: str
    reconstruction: ReconstructionScope
    declared_coverage: ReplayCoverage | None
    payload_present: bool
    context_identity: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "action_key": self.action_key,
            "reconstruction": self.reconstruction,
            "declared_coverage": self.declared_coverage,
            "payload_present": self.payload_present,
            "context_identity": self.context_identity,
        }


class _ActionRecord:
    __slots__ = ("events", "events_by_type", "state")

    def __init__(self) -> None:
        self.events: list[ExposureEvent] = []
        self.events_by_type: dict[str, ExposureEvent] = {}
        self.state: ExposureState | None = None


class ExposureLog:
    """An append-only Research Exposure log with canonical public readback."""

    def __init__(self, sink: Callable[[dict[str, object]], None] | None = None) -> None:
        self._sink = sink
        self._actions: dict[str, _ActionRecord] = {}
        self._sequence = 0
        self._torn_tail = False

    @property
    def torn_tail(self) -> bool:
        """True when a reload found an incomplete trailing record."""

        return self._torn_tail

    @property
    def action_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._actions))

    def append(self, value: Mapping[str, object]) -> ExposureEvent:
        event = _parse_event(value)
        action = self._actions.get(event.action_key)
        existing = None if action is None else action.events_by_type.get(event.event_type)
        if existing is not None:
            if existing.input_digest == event.input_digest:
                # Same action key and same frozen input: recover the existing
                # event.  A duplicate callback never confirms a delivery twice.
                return existing
            raise AcceptanceFailure(
                f"exposure idempotency conflict for {event.event_type}: input differs"
            )
        current = "" if action is None or action.state is None else action.state
        if event.event_type not in _ALLOWED_TRANSITIONS[current]:
            raise AcceptanceFailure(
                f"exposure transition is not allowed: {current or 'absent'} -> {event.event_type}"
            )
        self._check_binding(event, action)
        gate_identity = self._check_visibility(event)
        if (
            event.event_type == "envelope_delivered"
            and current == "delivery_uncertain"
            and (event.delivery is None or event.delivery.receipt_ref is None)
        ):
            raise AcceptanceFailure(
                "reconciling an uncertain delivery requires a real receipt reference"
            )
        record = replace(event, gate_identity=gate_identity, sequence=self._sequence)
        self._commit(record)
        return record

    def state(self, action_key: str) -> ExposureState | None:
        action = self._actions.get(action_key)
        return None if action is None else action.state

    def events(self, action_key: str) -> tuple[ExposureEvent, ...]:
        action = self._actions.get(action_key)
        return () if action is None else tuple(action.events)

    def readback(self, action_key: str) -> dict[str, object]:
        """Canonical public readback for one exposure action."""

        action = self._actions.get(action_key)
        if action is None or not action.events:
            return {
                "schema": EXPOSURE_READBACK_SCHEMA,
                "action_key": action_key,
                "state": None,
                "events": [],
            }
        first = action.events[0]
        delivered = action.events_by_type.get("envelope_delivered")
        uncertain = action.events_by_type.get("delivery_uncertain")
        completed = action.events_by_type.get("completion_linked")
        confirmed_by: str | None = None
        if completed is not None and completed.completion is not None:
            confirmed_by = completed.completion.confirmed_by
        elif delivered is not None and delivered.delivery is not None:
            confirmed_by = (
                "real_receipt" if delivered.delivery.receipt_ref is not None else "public_event"
            )
        return {
            "schema": EXPOSURE_READBACK_SCHEMA,
            "action_key": action_key,
            "state": action.state,
            "key": first.key.as_dict(),
            "research_action_id": first.research_action_id,
            "context_identity": first.context_identity,
            "research_family": first.research_family.as_dict(),
            "policy": first.policy.as_dict(),
            "invocations": sorted({event.invocation_id for event in action.events}),
            "invocation_count": len({event.invocation_id for event in action.events}),
            "state_trajectory": [event.event_type for event in action.events],
            "replay_coverage": (
                None
                if delivered is None or delivered.delivery is None
                else delivered.delivery.replay_coverage
            ),
            "delivery_confirmed_by": confirmed_by,
            "uncertainty": (
                None
                if uncertain is None or uncertain.uncertainty is None
                else uncertain.uncertainty.as_dict()
            ),
            "resend_allowed": False,
            "grants_eligibility": False,
            "events": [event.as_dict() for event in action.events],
        }

    def research_action_readback(self, research_action_id: str) -> dict[str, object]:
        """Every exposure action -- Context draft and each tool turn -- for one research action."""

        keys = sorted(
            {
                event.action_key
                for action in self._actions.values()
                for event in action.events
                if event.research_action_id == research_action_id
            }
        )
        return {
            "schema": EXPOSURE_READBACK_SCHEMA,
            "research_action_id": research_action_id,
            "actions": [self.readback(key) for key in keys],
            "grants_eligibility": False,
        }

    def context_exposure(self, context_identity: str) -> ContextExposure:
        """The most exposed status ever recorded for one Context identity.

        This spans Campaigns and Iterations on purpose.  Starting a new Campaign,
        renaming one, or confirming a new task never returns a Context to
        ``unseen``.
        """

        status: ContextExposure = "unseen"
        for action in self._actions.values():
            for event in action.events:
                if event.context_identity != context_identity:
                    continue
                if action.state in _EXPOSED_STATES:
                    return "exposed"
                if action.state == "delivery_uncertain":
                    status = "uncertain"
                elif status == "unseen":
                    status = "prepared"
        return status

    def usage_history(
        self,
        *,
        family_id: str | None = None,
        context_identity: str | None = None,
    ) -> dict[str, object]:
        """Published source-and-usage relations for the originating statistical owner."""

        entries: list[dict[str, object]] = []
        for key in sorted(self._actions):
            action = self._actions[key]
            if not action.events:
                continue
            first = action.events[0]
            if family_id is not None and first.research_family.family_id != family_id:
                continue
            if context_identity is not None and first.context_identity != context_identity:
                continue
            completion = action.events_by_type.get("completion_linked")
            link = None if completion is None else completion.completion
            entries.append(
                {
                    "action_key": key,
                    "campaign_id": first.key.campaign_id,
                    "iteration_id": first.key.iteration_id,
                    "research_action_id": first.research_action_id,
                    "context_identity": first.context_identity,
                    "research_family": first.research_family.as_dict(),
                    "state": action.state,
                    "candidate_ids": [] if link is None else list(link.candidate_ids),
                    "selection_decision_ids": (
                        [] if link is None else list(link.selection_decision_ids)
                    ),
                }
            )
        return {
            "schema": EXPOSURE_USAGE_SCHEMA,
            "entries": entries,
            # Memory publishes relations only.  Multiplicity, independence and
            # qualification stay with the originating statistical owner.
            "grants_eligibility": False,
        }

    def export(self) -> list[dict[str, object]]:
        records = [event for action in self._actions.values() for event in action.events]
        return [event.as_dict() for event in sorted(records, key=lambda event: event.sequence)]

    @classmethod
    def load(
        cls,
        path: Path,
        sink: Callable[[dict[str, object]], None] | None = None,
    ) -> ExposureLog:
        """Rebuild a log from its append-only file, conservatively.

        A trailing record that was not completely written is dropped, because it
        was never durable.  An action left at ``prepared`` by a torn tail becomes
        ``delivery_uncertain``: the local write failing proves nothing about
        whether the external consumer received the request.
        """

        log = cls(sink)
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
        torn = bool(lines) and not lines[-1].endswith("\n")
        for line in lines[: len(lines) - 1] if torn else lines:
            body = line.strip()
            if not body:
                continue
            log._replay_line(body)
        if torn:
            log._torn_tail = True
            log._promote_prepared_to_uncertain()
        return log

    def _replay_line(self, body: str) -> None:
        try:
            raw = json.loads(body)
        except json.JSONDecodeError as error:
            raise AcceptanceFailure("exposure log record is not canonical") from error
        item = _mapping(raw, "exposure log record")
        event = _parse_event({name: value for name, value in item.items() if name in _EVENT_FIELDS})
        gate_identity = item.get("gate_identity")
        if gate_identity is not None:
            gate_identity = _digest_field(gate_identity, "exposure log record gate_identity")
        sequence = item.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise AcceptanceFailure("exposure log record sequence is invalid")
        self._register(replace(event, gate_identity=gate_identity, sequence=sequence))
        self._sequence = max(self._sequence, sequence + 1)

    def _promote_prepared_to_uncertain(self) -> None:
        for action in self._actions.values():
            if action.state != "prepared":
                continue
            last = action.events[-1]
            uncertainty = DeliveryUncertainty(
                reason="process_interrupted",
                observation="local_checkpoint",
                transport="real_process",
            )
            event = replace(
                last,
                event_type="delivery_uncertain",
                delivery=None,
                uncertainty=uncertainty,
                completion=None,
                gate_identity=None,
                input_digest=_digest(
                    {"recovered_from": last.input_digest, "uncertainty": uncertainty.as_dict()}
                ),
                sequence=self._sequence,
                persisted=False,
            )
            self._sequence += 1
            self._register(event)

    def _check_binding(self, event: ExposureEvent, action: _ActionRecord | None) -> None:
        if action is not None and action.events:
            if action.events[0].binding() != event.binding():
                raise AcceptanceFailure("exposure action binding drifted")
            return
        for other in self._actions.values():
            if not other.events:
                continue
            first = other.events[0]
            if first.research_action_id != event.research_action_id:
                continue
            if (first.context_identity, first.research_family.family_id) != (
                event.context_identity,
                event.research_family.family_id,
            ):
                raise AcceptanceFailure("research action binding drifted")

    def _check_visibility(self, event: ExposureEvent) -> str | None:
        if event.event_type != "envelope_delivered" or event.delivery is None:
            return None
        added = set(event.delivery.added_material_ids)
        if not added:
            return None
        if event.gate_identity is None:
            raise AcceptanceFailure(
                "delivered material added after Context assembly needs a visibility request"
            )
        return event.gate_identity

    def _commit(self, record: ExposureEvent) -> None:
        if self._sink is not None:
            try:
                self._sink(record.as_dict())
            except Exception as error:
                # The append was not durable.  If the event reports an external
                # fact, the honest recovery state is uncertainty, not "unseen".
                if record.event_type in {"envelope_delivered", "delivery_uncertain"}:
                    self._register_persistence_uncertainty(record)
                raise ExposurePersistenceFailure(
                    "exposure event could not be durably appended"
                ) from error
        self._register(record)
        self._sequence = max(self._sequence, record.sequence + 1)

    def _register_persistence_uncertainty(self, record: ExposureEvent) -> None:
        action = self._actions.get(record.action_key)
        if action is not None and action.state in _EXPOSED_STATES:
            return
        uncertainty = DeliveryUncertainty(
            reason="persistence_failure",
            observation="local_checkpoint",
            transport=(
                record.uncertainty.transport if record.uncertainty is not None else "real_process"
            ),
        )
        marker = replace(
            record,
            event_type="delivery_uncertain",
            delivery=None,
            uncertainty=uncertainty,
            completion=None,
            gate_identity=None,
            input_digest=_digest(
                {"recovered_from": record.input_digest, "uncertainty": uncertainty.as_dict()}
            ),
            sequence=self._sequence,
            persisted=False,
        )
        self._sequence += 1
        self._register(marker)

    def _register(self, record: ExposureEvent) -> None:
        action = self._actions.setdefault(record.action_key, _ActionRecord())
        action.events.append(record)
        action.events_by_type[record.event_type] = record
        action.state = _STATE_FOR_EVENT[record.event_type]


def append_exposure_event(
    log: ExposureLog,
    value: Mapping[str, object],
) -> ExposureEvent:
    return log.append(value)


def replay_exposure_delivery(
    log: ExposureLog,
    action_key: str,
    visibility_request: Mapping[str, object],
    load_envelope: Callable[[str], object] | None = None,
) -> tuple[ExposureReplay, object | None]:
    """Hand back historical content only under *current* authorization.

    The historical decision recorded at delivery time explains what happened
    then; it never restores access now.  When the approved store does not hold
    the envelope, only a limited reconstruction is declared -- the digest is not
    the body, and the model is never re-invoked to manufacture the missing
    evidence after the fact.
    """

    action_events = log.events(action_key)
    delivered = next(
        (event for event in action_events if event.event_type == "envelope_delivered"), None
    )
    context_identity = action_events[0].context_identity if action_events else None
    decision = evaluate_visibility_request(visibility_request)
    if not decision.deliverable:
        return (
            ExposureReplay(
                action_key=action_key,
                reconstruction="denied",
                declared_coverage=None,
                payload_present=False,
                context_identity=None,
            ),
            None,
        )
    if delivered is None or delivered.delivery is None:
        return (
            ExposureReplay(
                action_key=action_key,
                reconstruction="limited",
                declared_coverage=None,
                payload_present=False,
                context_identity=context_identity,
            ),
            None,
        )
    coverage = delivered.delivery.replay_coverage
    reference = delivered.delivery.envelope_content_ref
    if coverage != "full" or reference is None or load_envelope is None:
        return (
            ExposureReplay(
                action_key=action_key,
                reconstruction="limited",
                declared_coverage=coverage,
                payload_present=False,
                context_identity=context_identity,
            ),
            None,
        )
    return (
        ExposureReplay(
            action_key=action_key,
            reconstruction="full",
            declared_coverage=coverage,
            payload_present=True,
            context_identity=context_identity,
        ),
        load_envelope(reference),
    )


def _parse_event(value: Mapping[str, object]) -> ExposureEvent:
    item = _mapping(value, "exposure event")
    _fields_subset(item, _EVENT_FIELDS, "exposure event")
    if item.get("schema") != EXPOSURE_EVENT_SCHEMA:
        raise AcceptanceFailure("exposure event schema is invalid")
    event_type = _token(item.get("event_type"), "exposure event_type")
    if event_type not in _EVENT_TYPES:
        raise AcceptanceFailure(f"exposure event_type is invalid: {event_type}")
    key = ExposureKey.parse(item.get("key"))
    delivery = None if item.get("delivery") is None else DeliveryBinding.parse(item.get("delivery"))
    uncertainty = (
        None if item.get("uncertainty") is None else DeliveryUncertainty.parse(item["uncertainty"])
    )
    completion = (
        None if item.get("completion") is None else CompletionLink.parse(item["completion"])
    )
    _require_event_shape(event_type, delivery, uncertainty, completion)
    gate_identity = _gate_identity(item, delivery)
    event = ExposureEvent(
        event_type=event_type,  # type: ignore[arg-type]
        key=key,
        research_action_id=_token(item.get("research_action_id"), "exposure research_action_id"),
        context_identity=_digest_field(item.get("context_identity"), "exposure context_identity"),
        research_family=ResearchFamilyRef.parse(item.get("research_family")),
        policy=ExposurePolicyRef.parse(item.get("policy")),
        invocation_id=_token(item.get("invocation_id"), "exposure invocation_id"),
        context_material_ids=_tokens(
            item.get("context_material_ids", []), "exposure context_material_ids", empty=True
        ),
        delivery=delivery,
        uncertainty=uncertainty,
        completion=completion,
        gate_identity=gate_identity,
        input_digest="",
        sequence=-1,
        persisted=True,
    )
    return replace(event, input_digest=_input_digest(event))


def _require_event_shape(
    event_type: str,
    delivery: DeliveryBinding | None,
    uncertainty: DeliveryUncertainty | None,
    completion: CompletionLink | None,
) -> None:
    present = {
        "delivery": delivery is not None,
        "uncertainty": uncertainty is not None,
        "completion": completion is not None,
    }
    required = {
        "context_prepared": set(),
        "envelope_delivered": {"delivery"},
        "delivery_uncertain": {"uncertainty"},
        "completion_linked": {"completion"},
    }[event_type]
    for name, is_present in present.items():
        if (name in required) != is_present:
            raise AcceptanceFailure(f"exposure event {event_type} body is invalid")


def _gate_identity(item: Mapping[str, object], delivery: DeliveryBinding | None) -> str | None:
    raw = item.get("visibility_request")
    if raw is None:
        return None
    if delivery is None:
        raise AcceptanceFailure("visibility request belongs to a delivery event")
    # Material added after Context assembly is re-checked against the #394/#395
    # gate here; a blocked or unknown addition is never recorded as delivered.
    decision = evaluate_visibility_request(_mapping(raw, "visibility_request"))
    if not decision.deliverable:
        raise AcceptanceFailure("delivered material was not cleared by the visibility gate")
    if decision.safety_audit.get("status") not in {"clear", "not_applicable"}:
        raise AcceptanceFailure("delivered envelope addition was not cleared by the safety audit")
    request = VisibilityRequest.parse(_mapping(raw, "visibility_request"))
    cleared = {material.material_id for material in request.materials}
    missing = sorted(set(delivery.added_material_ids) - cleared)
    if missing:
        raise AcceptanceFailure(f"delivered additions were not gated: {','.join(missing)}")
    return decision.request_identity


def _input_digest(event: ExposureEvent) -> str:
    return _digest(
        {
            "event_type": event.event_type,
            "key": event.key.as_dict(),
            "research_action_id": event.research_action_id,
            "context_identity": event.context_identity,
            "research_family": event.research_family.as_dict(),
            "policy": event.policy.as_dict(),
            "invocation_id": event.invocation_id,
            "context_material_ids": list(event.context_material_ids),
            "delivery": None if event.delivery is None else event.delivery.as_dict(),
            "uncertainty": None if event.uncertainty is None else event.uncertainty.as_dict(),
            "completion": None if event.completion is None else event.completion.as_dict(),
        }
    )


def _digest_field(value: object, label: str) -> str:
    if not isinstance(value, str) or _SAFE_DIGEST.fullmatch(value) is None:
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _optional_token(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _token(value, label)


__all__ = [
    "EXPOSURE_EVENT_SCHEMA",
    "EXPOSURE_READBACK_SCHEMA",
    "EXPOSURE_USAGE_SCHEMA",
    "CompletionLink",
    "DeliveryBinding",
    "DeliveryUncertainty",
    "ExposureEvent",
    "ExposureKey",
    "ExposureLog",
    "ExposurePersistenceFailure",
    "ExposurePolicyRef",
    "ExposureReplay",
    "ResearchFamilyRef",
    "append_exposure_event",
    "replay_exposure_delivery",
]
