"""#429 SG-V1D: the staged Genome/Package flow, proved through public contract only.

Scope boundary -- read this before trusting anything below
----------------------------------------------------------
The Strategy Genome *product* (#411/#402 and the nine closed children #414-#422,
#427, #428) lives in a **separate repository**, ``williamxhero/StrategyWorkspace``,
and ships as the ``strategy_workspace`` wheel alongside ``apex_research``,
``quant_runtime`` and ``strategy_reporting``.  None of that source is owned here
and none of it is imported here.  ``_spec027_installed_test.py`` is the module
that exercises those wheels directly, and it fails in this environment for the
honest reason that the wheels are not installed in it.

What *is* owned here is the acceptance layer.  So this module states the
Genome flow's **public contract** -- the stage order, the identity algebra, the
verification binding, the fail-closed consumption rules, the replay discipline
and the compatibility table -- as executable code over #437-shaped synthetic
fixtures, exactly as #394-#408 did for the Research Memory family.  Every claim
it makes is a claim about the contract, never about StrategyWorkspace's
implementation of it.  Owner-side facts that only StrategyWorkspace can measure
(#419's concurrency/crash and 256 KiB p95 numbers, #422's independent
behavioural conformance) are **cited** in :data:`CITED_OWNER_EVIDENCE` and are
deliberately *not* re-derived; a citation is labelled as such in the readback so
no consumer can mistake it for something this repository measured.

Five rules shape the code.

**Preparation is not export.**  :data:`STAGE_PREREQUISITES` is the whole
argument: ``independent_conformance`` depends on ``package_preparation`` and
never on ``owner_publication`` or ``formal_package_export``.  The graph is
checked to be acyclic, so "publish before you may verify" is not merely absent,
it is unrepresentable.

**An identity carries its kind.**  :func:`identity_of` digests the kind together
with the content, so a Candidate, a Genome, a Package, a request, a run and an
event can never collide even when their payloads are byte-identical.  Genome
identity is taken over *canonical content only*, which is why a second attempt
with new provenance keeps the identity while the provenance stays separate.

**Content addressing is append-only and acyclic.**  :class:`ContentAddressStore`
refuses to re-bind an identity to different bytes, refuses a reference to
something not already stored (so a cycle or a self-reference cannot be built),
and refuses to let a new attempt clear a tombstone.

**Verification is reused only on an exact binding.**  The validator, suite,
comparator, environment, dependency lock, configuration and policy are one
frozen :class:`ConformanceBinding`.  An exact repeat reuses the existing
evidence and performs no sandbox work; any change revalidates through the same
governed path.  ``contract_valid``, ``behavior_conformant``, ``published`` and
``research_qualified`` are four independent flags and this module never derives
one from another.

**Failure is closed and named.**  :data:`CONSUMPTION_REFUSALS` enumerates every
way the formal path says no, and each one is a distinct reason.  Historical
readability, execution eligibility and current permission to re-deliver are
three separate booleans on the outcome, never one.

What this module deliberately does not do: it imports no wheel, adds no
dependency, opens no network or subprocess, reads no private storage, and
reimplements no recovery -- A0-E03/H02 is #408's ``research_recovery`` and is
referenced rather than duplicated.  Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from .core import AcceptanceFailure

GENOME_FLOW_SCHEMA = "quantresearch.research.genome_flow/v1"
GENOME_RECORD_SCHEMA = "quantresearch.research.genome_record/v1"
GENOME_MATRIX_SCHEMA = "quantresearch.research.genome_matrix/v1"

#: The public major this acceptance layer speaks.  A record declaring anything
#: else is handled by :data:`LEGACY_ADAPTERS` or refused -- never guessed at.
CURRENT_MAJOR = 1


class GenomeRefusal(AcceptanceFailure):
    """The Genome contract was asked for something it does not allow.

    As in #397-#408, an honest "this cannot enter the formal path" is *not* an
    exception: it is a :class:`ConsumptionOutcome` with a named refusal reason,
    so the fail-closed decision stays publicly readable.  This exception is for
    malformed or self-contradictory declarations only.
    """


# --- 1. the golden stages ----------------------------------------------------

#: The ticket's golden flow, in the order it is stated.
GOLDEN_STAGES: tuple[str, ...] = (
    "candidate_ir",
    "genome_proposal",
    "contract_gate",
    "reference_gate",
    "semantic_gate",
    "package_preparation",
    "independent_conformance",
    "owner_publication",
    "formal_package_export",
    "runtime_request",
    "runtime_run",
    "reporting_readback",
)

#: What each stage actually needs before it may start.  This is the module's
#: central claim and the reason the ticket's "no circular publish-before-verify"
#: requirement is checkable rather than asserted: ``independent_conformance``
#: names ``package_preparation`` and nothing downstream of it.
STAGE_PREREQUISITES: Mapping[str, tuple[str, ...]] = {
    "candidate_ir": (),
    "genome_proposal": ("candidate_ir",),
    "contract_gate": ("genome_proposal",),
    "reference_gate": ("contract_gate",),
    "semantic_gate": ("reference_gate",),
    "package_preparation": ("semantic_gate",),
    "independent_conformance": ("package_preparation",),
    "owner_publication": ("independent_conformance",),
    "formal_package_export": ("owner_publication",),
    "runtime_request": ("formal_package_export",),
    "runtime_run": ("runtime_request",),
    "reporting_readback": ("runtime_run",),
}

#: The three gates, in their fixed order.  A later gate never runs before an
#: earlier one, and a gate result is never inferred from a neighbour's.
ORDERED_GATES: tuple[str, ...] = ("contract_gate", "reference_gate", "semantic_gate")


def stage_cycles() -> tuple[str, ...]:
    """Stage ids that can reach themselves through :data:`STAGE_PREREQUISITES`.

    Returns nothing today.  The function exists so that a future edit that makes
    verification depend on publication is reported here rather than shipped.
    """

    offenders: list[str] = []
    for start in STAGE_PREREQUISITES:
        seen: set[str] = set()
        pending = list(STAGE_PREREQUISITES[start])
        while pending:
            node = pending.pop()
            if node == start:
                offenders.append(start)
                break
            if node in seen:
                continue
            seen.add(node)
            pending.extend(STAGE_PREREQUISITES.get(node, ()))
    return tuple(sorted(set(offenders)))


# --- 2. identity -------------------------------------------------------------

IdentityKind = Literal["candidate", "genome", "package", "request", "run", "event"]

IDENTITY_KINDS: tuple[str, ...] = ("candidate", "genome", "package", "request", "run", "event")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def canonical_digest(value: Mapping[str, object]) -> str:
    """The canonical digest of one public payload."""

    return _digest(_canonical(value))


def identity_of(kind: str, content: Mapping[str, object]) -> str:
    """``<kind>:sha256:<hex>`` over the *kind together with* the content.

    Digesting the kind is what keeps a Candidate, a Genome, a Package, a
    request, a run and an event distinct even when their payloads are identical
    bytes.  It also means an identity cannot be re-labelled as another kind
    without changing the digest.
    """

    if kind not in IDENTITY_KINDS:
        raise GenomeRefusal(f"{kind} is not a declared identity kind")
    return f"{kind}:" + _digest(_canonical({"kind": kind, "content": dict(content)}))


def identity_kind(identity: str) -> str:
    kind, _, rest = identity.partition(":")
    if kind not in IDENTITY_KINDS or not rest.startswith("sha256:"):
        raise GenomeRefusal(f"{identity} is not a well-formed Genome-family identity")
    return kind


# --- 3. the content-addressed store -----------------------------------------

RecordState = Literal["prepared", "registered", "validated", "published", "rejected", "tombstoned"]

RECORD_STATES: tuple[str, ...] = (
    "prepared",
    "registered",
    "validated",
    "published",
    "rejected",
    "tombstoned",
)

#: Only these two may be consumed by the ordinary formal path.  ``prepared`` and
#: ``registered`` are deliberately absent: preparation is not export.
FORMALLY_CONSUMABLE: frozenset[str] = frozenset({"validated", "published"})


@dataclass(frozen=True, slots=True)
class Provenance:
    """Who proposed this content, when, and under which attempt.

    Kept strictly *outside* the digested content.  Two attempts that propose the
    same canonical Genome keep one Genome identity and two provenances; that is
    the ticket's "same canonical content retains Genome identity across
    attempts / provenance-only changes".
    """

    attempt_id: str
    proposer: str
    recorded_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "proposer": self.proposer,
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True, slots=True)
class GenomeRecord:
    """One content-addressed object in the Genome family."""

    kind: str
    identity: str
    content: Mapping[str, object]
    references: tuple[str, ...]
    state: RecordState
    major: int
    provenances: tuple[Provenance, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": GENOME_RECORD_SCHEMA,
            "kind": self.kind,
            "identity": self.identity,
            "content": dict(self.content),
            "references": list(self.references),
            "state": self.state,
            "major": self.major,
            "provenances": [item.as_dict() for item in self.provenances],
        }


@dataclass(slots=True)
class ContentAddressStore:
    """An append-only public store: no re-binding, no cycles, no tombstone reset.

    The store holds *public* records only.  It has no engine, no retrieval
    callable and no fallback source, so nothing here can spend a backtest, a
    model call or a budget to fill a gap.
    """

    _records: dict[str, GenomeRecord] = field(default_factory=dict)
    _tombstones: set[str] = field(default_factory=set)

    def register(
        self,
        kind: str,
        content: Mapping[str, object],
        *,
        references: Iterable[str] = (),
        state: RecordState = "registered",
        major: int = CURRENT_MAJOR,
        provenance: Provenance | None = None,
    ) -> GenomeRecord:
        """Store one record, or attach a new provenance to an identical one."""

        if state not in RECORD_STATES:
            raise GenomeRefusal(f"{state} is not a declared record state")
        refs = tuple(references)
        identity = identity_of(kind, content)

        # No cycle and no self-reference: a reference must already be in the
        # store, and a record cannot be in the store before it is registered.
        for ref in refs:
            if ref == identity:
                raise GenomeRefusal("a record may not reference itself")
            if ref not in self._records:
                raise GenomeRefusal(f"{ref} is referenced before it exists")

        # A new attempt never clears a tombstone.
        if identity in self._tombstones:
            raise GenomeRefusal(f"{identity} is tombstoned and cannot be revived")

        existing = self._records.get(identity)
        if existing is None:
            self._records[identity] = GenomeRecord(
                kind=kind,
                identity=identity,
                content=dict(content),
                references=refs,
                state=state,
                major=major,
                provenances=() if provenance is None else (provenance,),
            )
            return self._records[identity]

        # Same identity: the bytes must be the same bytes.  This is the
        # "different bytes cannot take over a hash" rule, stated where it is
        # enforced rather than where it is tested.
        if _canonical(dict(existing.content)) != _canonical(dict(content)):
            raise GenomeRefusal(f"{identity} already holds different content")
        if existing.references != refs or existing.major != major:
            raise GenomeRefusal(f"{identity} already holds a different reference set or major")

        if provenance is not None and provenance not in existing.provenances:
            self._records[identity] = GenomeRecord(
                kind=existing.kind,
                identity=existing.identity,
                content=existing.content,
                references=existing.references,
                state=existing.state,
                major=existing.major,
                provenances=(*existing.provenances, provenance),
            )
        return self._records[identity]

    def advance(self, identity: str, state: RecordState) -> GenomeRecord:
        """Move one record to a new state, never backwards out of a terminal one."""

        record = self._records.get(identity)
        if record is None:
            raise GenomeRefusal(f"{identity} is not in the store")
        if state not in RECORD_STATES:
            raise GenomeRefusal(f"{state} is not a declared record state")
        if record.state in ("rejected", "tombstoned"):
            raise GenomeRefusal(f"{identity} is {record.state} and is terminal")
        if state == "tombstoned":
            self._tombstones.add(identity)
        self._records[identity] = GenomeRecord(
            kind=record.kind,
            identity=record.identity,
            content=record.content,
            references=record.references,
            state=state,
            major=record.major,
            provenances=record.provenances,
        )
        return self._records[identity]

    def get(self, identity: str) -> GenomeRecord | None:
        return self._records.get(identity)

    def identities(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def tombstoned(self) -> tuple[str, ...]:
        return tuple(sorted(self._tombstones))

    def reference_cycles(self) -> tuple[str, ...]:
        """Identities reachable from themselves.  Empty by construction."""

        offenders: list[str] = []
        for start in self._records:
            seen: set[str] = set()
            pending = list(self._records[start].references)
            while pending:
                node = pending.pop()
                if node == start:
                    offenders.append(start)
                    break
                if node in seen:
                    continue
                seen.add(node)
                record = self._records.get(node)
                if record is not None:
                    pending.extend(record.references)
        return tuple(sorted(set(offenders)))


# --- 4. verification ---------------------------------------------------------

#: Everything a conformance claim is bound to.  Changing any one of them makes
#: the existing evidence stale; none of them may be dropped from the binding.
BINDING_FIELDS: tuple[str, ...] = (
    "validator_id",
    "suite_id",
    "comparator_id",
    "environment_id",
    "dependency_lock",
    "configuration_id",
    "policy_id",
)


@dataclass(frozen=True, slots=True)
class ConformanceBinding:
    """The declared validator / suite / comparator / environment / deps / config / policy."""

    validator_id: str
    suite_id: str
    comparator_id: str
    environment_id: str
    dependency_lock: str
    configuration_id: str
    policy_id: str

    def as_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in BINDING_FIELDS}

    def identity(self) -> str:
        return canonical_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ConformanceEvidence:
    """Independent evidence for exact bytes under one exact binding."""

    package_identity: str
    content_digest: str
    binding_identity: str
    conformant: bool
    evidence_ref: str
    reused: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "package_identity": self.package_identity,
            "content_digest": self.content_digest,
            "binding_identity": self.binding_identity,
            "conformant": self.conformant,
            "evidence_ref": self.evidence_ref,
            "reused": self.reused,
            # Stated by the seam, so "no redundant sandbox work" is a fact in
            # the readback rather than a claim in a comment.
            "independent_of_producer": True,
        }


@dataclass(slots=True)
class VerificationLedger:
    """Exact reuse, or revalidation through the same governed path.

    ``sandbox_invocations`` is the counter the ticket asks for.  A second
    request with the same bytes and the same binding must not increment it; any
    change to either must.
    """

    sandbox_invocations: int = 0
    _evidence: dict[tuple[str, str], ConformanceEvidence] = field(default_factory=dict)

    def verify(
        self,
        record: GenomeRecord,
        binding: ConformanceBinding,
        *,
        conformant: bool = True,
    ) -> ConformanceEvidence:
        content_digest = canonical_digest(dict(record.content))
        key = (content_digest, binding.identity())
        cached = self._evidence.get(key)
        if cached is not None:
            return ConformanceEvidence(
                package_identity=cached.package_identity,
                content_digest=cached.content_digest,
                binding_identity=cached.binding_identity,
                conformant=cached.conformant,
                evidence_ref=cached.evidence_ref,
                reused=True,
            )
        self.sandbox_invocations += 1
        evidence = ConformanceEvidence(
            package_identity=record.identity,
            content_digest=content_digest,
            binding_identity=binding.identity(),
            conformant=conformant,
            evidence_ref=_digest(_canonical([content_digest, binding.identity()])),
            reused=False,
        )
        self._evidence[key] = evidence
        return evidence

    def evidence_for(
        self, record: GenomeRecord, binding: ConformanceBinding
    ) -> ConformanceEvidence | None:
        return self._evidence.get((canonical_digest(dict(record.content)), binding.identity()))


@dataclass(frozen=True, slots=True)
class QualificationFlags:
    """Four independent facts that this module never derives from one another.

    "the contract parsed", "the behaviour matched", "the owner published it" and
    "a researcher may cite it as qualified evidence" are separate claims with
    separate owners.  Conflating any two of them is the failure mode the ticket
    names, so they are stored as four booleans with no implication between them.
    """

    contract_valid: bool
    behavior_conformant: bool
    published: bool
    research_qualified: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "contract_valid": self.contract_valid,
            "behavior_conformant": self.behavior_conformant,
            "published": self.published,
            "research_qualified": self.research_qualified,
        }


# --- 5. consumption ----------------------------------------------------------

#: Every named way the formal path says no.  Each is distinct; none of them is
#: an exception and none of them leaks the content it refused.
CONSUMPTION_REFUSALS: tuple[str, ...] = (
    "not_formally_consumable",
    "rejected",
    "tombstoned",
    "unknown_major",
    "identity_mismatch",
    "facts_missing",
    "authorization_revoked",
    "sandbox_only_grant",
    "binding_stale",
    "not_conformant",
)

GRANT_SCOPES: tuple[str, ...] = ("sandbox", "formal")


@dataclass(frozen=True, slots=True)
class ConsumptionOutcome:
    """Whether one package may enter one formal run, and on what grounds."""

    admitted: bool
    refusal: str | None
    package_identity: str | None
    historically_readable: bool
    execution_eligible: bool
    redelivery_permitted: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": GENOME_FLOW_SCHEMA,
            "admitted": self.admitted,
            "refusal": self.refusal,
            "package_identity": self.package_identity,
            # Three separate facts.  Being able to read that something happened
            # is not being allowed to run it, and neither is being allowed to
            # hand its content back out today.
            "historically_readable": self.historically_readable,
            "execution_eligible": self.execution_eligible,
            "redelivery_permitted": self.redelivery_permitted,
        }


def consume_for_formal_run(
    store: ContentAddressStore,
    declared_identity: str,
    *,
    grant_scope: str,
    authorization_current: bool,
    declared_major: int = CURRENT_MAJOR,
    binding: ConformanceBinding | None = None,
    ledger: VerificationLedger | None = None,
) -> ConsumptionOutcome:
    """The ordinary formal path's single entry point.  It fails closed.

    Checks run in a fixed order so a refusal reason is deterministic, and a
    refused outcome publishes no content, no count and no lineage -- only the
    identity the caller already named, and only when that identity exists.
    """

    if grant_scope not in GRANT_SCOPES:
        raise GenomeRefusal(f"{grant_scope} is not a declared grant scope")

    record = store.get(declared_identity)
    if record is None:
        return _refused("facts_missing", None, historically_readable=False)
    if identity_kind(declared_identity) != "package":
        return _refused("identity_mismatch", None, historically_readable=False)
    if record.identity != identity_of(record.kind, record.content):
        return _refused("identity_mismatch", None, historically_readable=False)

    # Past this point the record exists, so it is historically readable; that
    # says nothing about running it or re-delivering it.
    if record.state == "tombstoned":
        return _refused("tombstoned", declared_identity)
    if record.state == "rejected":
        return _refused("rejected", declared_identity)
    if not authorization_current:
        return _refused("authorization_revoked", declared_identity)
    if record.major != declared_major or record.major != CURRENT_MAJOR:
        return _refused("unknown_major", declared_identity)
    if grant_scope != "formal":
        return _refused("sandbox_only_grant", declared_identity)
    if record.state not in FORMALLY_CONSUMABLE:
        return _refused("not_formally_consumable", declared_identity)

    if binding is not None:
        evidence = None if ledger is None else ledger.evidence_for(record, binding)
        if evidence is None:
            return _refused("binding_stale", declared_identity, redelivery_permitted=True)
        if not evidence.conformant:
            return _refused("not_conformant", declared_identity, redelivery_permitted=True)

    return ConsumptionOutcome(
        admitted=True,
        refusal=None,
        package_identity=declared_identity,
        historically_readable=True,
        execution_eligible=True,
        redelivery_permitted=True,
    )


def _refused(
    reason: str,
    identity: str | None,
    *,
    historically_readable: bool = True,
    redelivery_permitted: bool = False,
) -> ConsumptionOutcome:
    if reason not in CONSUMPTION_REFUSALS:
        raise GenomeRefusal(f"{reason} is not a declared refusal")
    return ConsumptionOutcome(
        admitted=False,
        refusal=reason,
        package_identity=identity,
        historically_readable=historically_readable,
        execution_eligible=False,
        redelivery_permitted=redelivery_permitted,
    )


# --- 6. compatibility --------------------------------------------------------

CompareResult = Literal["equal", "different", "incomparable"]

#: Legacy majors this layer speaks, each through an explicitly *named* adapter.
#: An unnamed major is refused; there is no silent fallback and no "try the
#: newest adapter and hope".
LEGACY_ADAPTERS: Mapping[int, str] = {0: "strategy-genome.legacy-v0-adapter"}

#: The documented behaviour of every compatibility case the ticket enumerates.
COMPATIBILITY_MATRIX: Mapping[str, str] = {
    "current_major": "parsed and compared directly",
    "named_legacy_adapter": "parsed through the named adapter; the adapter name is published",
    "unsupported_major": "refused as unknown_major; never guessed and never silently upgraded",
    "unsupported_kind": "refused; an unknown kind is not coerced to a known one",
    "redacted_compare": "incomparable; a redacted field is never treated as absent or as equal",
    "incompatible_compare": "incomparable; two different majors are never reported as different",
}


def adapter_for(major: int) -> str:
    """The named adapter for one major, or a refusal.  Never a silent fallback."""

    if major == CURRENT_MAJOR:
        return "current"
    name = LEGACY_ADAPTERS.get(major)
    if name is None:
        raise GenomeRefusal(f"major {major} has no named adapter")
    return name


def compare_packages(left: GenomeRecord, right: GenomeRecord) -> CompareResult:
    """``equal`` / ``different`` / ``incomparable``, and never a guess.

    Two records of different majors, or either one carrying a redacted field,
    are ``incomparable``.  Reporting them as ``different`` would invite a
    consumer to read a redaction as a change.
    """

    if left.kind != right.kind:
        return "incomparable"
    if left.major != right.major:
        return "incomparable"
    if _is_redacted(left.content) or _is_redacted(right.content):
        return "incomparable"
    if _canonical(dict(left.content)) == _canonical(dict(right.content)):
        return "equal"
    return "different"


def _is_redacted(content: Mapping[str, object]) -> bool:
    return any(value == "<redacted>" for value in content.values())


# --- 7. the golden flow ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GoldenFlowOutcome:
    """One complete public pass, with every identity and every counter."""

    stages: tuple[str, ...]
    identities: Mapping[str, str]
    flags: QualificationFlags
    sandbox_invocations: int
    adapter: str

    def readback(self) -> dict[str, object]:
        return {
            "schema": GENOME_FLOW_SCHEMA,
            "stages": list(self.stages),
            "identities": dict(self.identities),
            "flags": self.flags.as_dict(),
            "sandbox_invocations": self.sandbox_invocations,
            "adapter": self.adapter,
            # The claims this module exists to make, stated by the seam.
            "used_private_storage": False,
            "used_source_import": False,
            "used_silent_fallback": False,
            "second_dsl_introduced": False,
            "new_backtests": 0,
            "model_invocations": 0,
            "budget_reservations": 0,
        }


def run_golden_flow(
    store: ContentAddressStore,
    ledger: VerificationLedger,
    *,
    candidate_ir: Mapping[str, object],
    genome_content: Mapping[str, object],
    package_content: Mapping[str, object],
    binding: ConformanceBinding,
    provenance: Provenance,
    research_qualified: bool = False,
    major: int = CURRENT_MAJOR,
) -> GoldenFlowOutcome:
    """Walk :data:`GOLDEN_STAGES` once, in order, over public records only.

    ``candidate_ir`` is the *existing* typed intake: it is stored verbatim as
    the Candidate's content and every later stage references it, so no second
    DSL is introduced and the source relation survives to the readback.
    """

    adapter = adapter_for(major)
    stages: list[str] = []

    candidate = store.register("candidate", candidate_ir, major=major, provenance=provenance)
    stages.append("candidate_ir")

    genome = store.register(
        "genome",
        genome_content,
        references=(candidate.identity,),
        major=major,
        provenance=provenance,
    )
    stages.append("genome_proposal")

    # The three gates, in their fixed order.  Each is an independent pass over
    # the already-stored public record; none infers another's result.
    for gate in ORDERED_GATES:
        _run_gate(gate, genome)
        stages.append(gate)

    package = store.register(
        "package",
        package_content,
        references=(genome.identity,),
        state="prepared",
        major=major,
        provenance=provenance,
    )
    stages.append("package_preparation")

    # Verification runs against a *prepared* package.  Nothing above required
    # publication first, which is the non-circularity the ticket asks for.
    evidence = ledger.verify(package, binding)
    stages.append("independent_conformance")

    store.advance(package.identity, "validated")
    published = store.advance(package.identity, "published")
    stages.append("owner_publication")

    stages.append("formal_package_export")

    request = store.register(
        "request",
        {"package": published.identity, "purpose": "formal_run"},
        references=(published.identity,),
        major=major,
        provenance=provenance,
    )
    stages.append("runtime_request")

    run = store.register(
        "run",
        {"request": request.identity},
        references=(request.identity,),
        major=major,
        provenance=provenance,
    )
    stages.append("runtime_run")

    event = store.register(
        "event",
        {"run": run.identity, "kind": "reporting_readback"},
        references=(run.identity,),
        major=major,
        provenance=provenance,
    )
    stages.append("reporting_readback")

    return GoldenFlowOutcome(
        stages=tuple(stages),
        identities={
            "candidate": candidate.identity,
            "genome": genome.identity,
            "package": published.identity,
            "request": request.identity,
            "run": run.identity,
            "event": event.identity,
        },
        flags=QualificationFlags(
            contract_valid=True,
            behavior_conformant=evidence.conformant,
            published=published.state == "published",
            # Never inferred.  A qualified research claim is the statistical
            # owner's decision, and this flow does not make it.
            research_qualified=research_qualified,
        ),
        sandbox_invocations=ledger.sandbox_invocations,
        adapter=adapter,
    )


def _run_gate(gate: str, record: GenomeRecord) -> None:
    """One independent gate pass over a public record.

    Each gate reads a different property on purpose, so a passing contract gate
    can never stand in for a passing semantic gate.
    """

    if gate == "contract_gate":
        if record.identity != identity_of(record.kind, record.content):
            raise GenomeRefusal("contract gate: the record does not reproduce its identity")
    elif gate == "reference_gate":
        if not record.references:
            raise GenomeRefusal("reference gate: a Genome must cite its Candidate")
    elif gate == "semantic_gate":
        if not record.content:
            raise GenomeRefusal("semantic gate: an empty Genome has no semantics")
    else:  # pragma: no cover - guarded by ORDERED_GATES
        raise GenomeRefusal(f"{gate} is not a declared gate")


# --- 8. replay ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReplayOutcome:
    """Rebuilding frozen identities from public facts alone."""

    rebuilt: tuple[str, ...]
    unavailable: tuple[str, ...]
    coverage: Literal["complete", "limited"]

    def as_dict(self) -> dict[str, object]:
        return {
            "rebuilt": list(self.rebuilt),
            "unavailable": list(self.unavailable),
            "coverage": self.coverage,
            "new_backtests": 0,
            "model_invocations": 0,
            "budget_reservations": 0,
            "used_fixture_substitute": False,
        }


def replay_from_public_facts(
    facts: Iterable[Mapping[str, object]], expected: Iterable[str]
) -> ReplayOutcome:
    """Recompute each expected identity from its frozen public record.

    There is no store, no engine and no loader parameter, so this seam has
    nothing to spend and nothing to fall back to.  An expected identity whose
    fact is absent is reported ``unavailable`` and the coverage drops to
    ``limited``: a missing payload is never papered over with a substitute.
    """

    rebuilt: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        kind = fact.get("kind")
        content = fact.get("content")
        if not isinstance(kind, str) or not isinstance(content, Mapping):
            raise GenomeRefusal("a public fact must carry a kind and a content mapping")
        identity = identity_of(kind, content)
        declared = fact.get("identity")
        if isinstance(declared, str) and declared != identity:
            raise GenomeRefusal(f"{declared} does not reproduce from its own content")
        seen.add(identity)
        rebuilt.append(identity)
    wanted = tuple(expected)
    unavailable = tuple(sorted(item for item in wanted if item not in seen))
    return ReplayOutcome(
        rebuilt=tuple(sorted(item for item in rebuilt if item in set(wanted))),
        unavailable=unavailable,
        coverage="complete" if not unavailable else "limited",
    )


# --- 9. the rollup -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TestRef:
    module: str
    test: str

    def as_dict(self) -> dict[str, object]:
        return {"module": self.module, "test": self.test}


EvidenceClass = Literal["proven_in_this_repo", "cited_from_owner_ticket", "pending_real_asset"]


@dataclass(frozen=True, slots=True)
class GenomeAcceptanceItem:
    item_id: str
    requirement: str
    owner_issue: str
    evidence_class: EvidenceClass
    status: Literal["executed", "not_run"]
    evidence: tuple[TestRef, ...]
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "requirement": self.requirement,
            "owner_issue": self.owner_issue,
            "evidence_class": self.evidence_class,
            "status": self.status,
            "evidence": [ref.as_dict() for ref in self.evidence],
            "note": self.note,
        }


_SGF = "_research_genome_flow_test"
_DEC = "_research_decision_test"
_REC = "_research_recovery_test"
_MTX = "_research_ac_matrix_test"
_CTX = "_research_context_test"


def _refs(module: str, *tests: str) -> tuple[TestRef, ...]:
    return tuple(TestRef(module, test) for test in tests)


#: Facts only StrategyWorkspace can measure.  Cited verbatim by ticket, never
#: re-derived here: re-measuring them would need that repository's code, which
#: this repository does not own and must not modify.
CITED_OWNER_EVIDENCE: Mapping[str, str] = {
    "#419": "real concurrency and crash evidence, and the 256 KiB p95 <= 250 ms local "
    "get/contract-validate/compare target; measured by the owner in StrategyWorkspace and "
    "cited here, NOT re-measured in Quant-Research",
    "#422": "independent behavioural conformance evidence; owned and executed by "
    "StrategyWorkspace's own suite and cited here, NOT re-run in Quant-Research",
    "#427/#428": "Package export and Runtime/Reporting binding, closed without waiting on "
    "#441; their component acceptance is the owner's and is referenced, not repeated",
}

GENOME_ACCEPTANCE_ITEMS: tuple[GenomeAcceptanceItem, ...] = (
    GenomeAcceptanceItem(
        item_id="SG-AC01",
        requirement="the full public golden flow preserves every separate identity and source "
        "relation, using the existing typed IR rather than a second DSL",
        owner_issue="#414/#415/#420",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=_refs(
            _SGF,
            "test_the_golden_flow_runs_every_stage_in_order_and_keeps_six_identities",
            "test_the_candidate_ir_is_stored_verbatim_and_no_second_dsl_appears",
            "test_identical_payloads_of_different_kinds_never_share_an_identity",
        ),
    ),
    GenomeAcceptanceItem(
        item_id="SG-AC02",
        requirement="installed/no-source positive and negative behaviour: documented "
        "compatibility, equal/different/incomparable and rejection/tombstone/current-permission, "
        "with no private read",
        owner_issue="#421/#427",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=_refs(
            _SGF,
            "test_every_compatibility_case_keeps_its_documented_behaviour",
            "test_an_unsupported_major_has_no_adapter_and_no_silent_fallback",
            "test_the_genome_seam_imports_no_owner_wheel_and_no_private_storage",
        ),
        note="the strategy_workspace / apex_research wheels are NOT installed in this "
        "environment, so _spec027_installed_test.py and _a0_installed_test.py's tracer fail "
        "by design; this item proves the contract shape, not the wheel",
    ),
    GenomeAcceptanceItem(
        item_id="SG-AC03",
        requirement="preparation-only content cannot run formally; exact valid verification is "
        "reused without redundant sandbox work; changed or stale bindings cannot complete export",
        owner_issue="#418/#422",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=_refs(
            _SGF,
            "test_a_prepared_package_cannot_enter_the_formal_path",
            "test_an_exact_repeat_reuses_verification_and_runs_no_new_sandbox_work",
            "test_any_binding_change_revalidates_instead_of_reusing",
            "test_a_stale_binding_cannot_complete_a_formal_consumption",
        ),
    ),
    GenomeAcceptanceItem(
        item_id="SG-AC04",
        requirement="identity/idempotency: same-content stability, distinct attempt provenance, "
        "same-key/different-input rejection, no hash hijack, no tombstone bypass, no cycles",
        owner_issue="#415/#419",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=_refs(
            _SGF,
            "test_a_second_attempt_keeps_the_genome_identity_and_adds_its_provenance",
            "test_different_bytes_can_never_take_over_an_existing_identity",
            "test_a_new_attempt_cannot_clear_a_tombstone",
            "test_content_addressing_admits_no_self_reference_and_no_cycle",
        ),
    ),
    GenomeAcceptanceItem(
        item_id="SG-AC05",
        requirement="U1-U6 and the retry / run-reuse / new-research distinction publish their "
        "branches and metrics; a matching Genome alone never blocks legitimate replication",
        owner_issue="#381/#399/#404",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=(
            *_refs(
                _SGF,
                "test_the_u1_u6_scenarios_are_referenced_from_the_research_memory_evidence",
                "test_a_matching_genome_alone_neither_blocks_nor_establishes_equivalence",
            ),
            *_refs(
                _DEC,
                "test_a_legitimate_new_sample_is_not_blocked_by_a_matching_genome",
                "test_a_genome_match_alone_is_not_a_run_match",
                "test_a_new_statistical_protocol_attaches_to_the_run_and_still_judges_afresh",
                "test_a0_u1_u3_miscall_run_reuse_and_external_call_counts",
            ),
            *_refs(_MTX, "test_u6_rebuild_after_deletion_costs_no_run_llm_call_or_budget"),
        ),
        note="#399/#401/#404/#408 established U1-U6; referenced here per the ticket's "
        "instruction to reference rather than re-derive",
    ),
    GenomeAcceptanceItem(
        item_id="SG-AC06",
        requirement="historical/current views, current authorization, delivery coverage and "
        "zero-call replay after cache deletion have public readback proof",
        owner_issue="#401/#408",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=(
            *_refs(
                _SGF,
                "test_replay_rebuilds_frozen_identities_with_zero_run_call_and_budget",
                "test_an_unavailable_payload_replays_as_limited_and_is_never_substituted",
                "test_historical_readability_is_not_eligibility_is_not_redelivery",
            ),
            *_refs(
                _REC,
                "test_ac1_deleting_every_projection_on_disk_still_recovers_identity_and_boundary",
                "test_ac1_a_recovery_publishes_zero_run_model_and_budget_counts",
                "test_u6_a_fresh_python_process_recovers_the_same_identity",
            ),
        ),
        note="#408's research_recovery owns the real on-disk deletion/restart slice and is "
        "referenced, not reimplemented",
    ),
    GenomeAcceptanceItem(
        item_id="SG-AC07",
        requirement="exact commands, environment/dependency locks, owner boundaries and "
        "executed/not_run status are published; conformance, performance, concurrency and "
        "end-to-end results stay separate and are never inferred from unit tests",
        owner_issue="#419/#422/#429",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=_refs(
            _SGF,
            "test_the_owner_measured_evidence_is_cited_and_never_claimed_as_re_measured",
            "test_the_seam_adds_no_dependency_and_needs_no_optional_service",
            "test_the_rollup_never_counts_a_not_run_item_as_passed",
        ),
    ),
)


A0_GENOME_ITEMS: tuple[GenomeAcceptanceItem, ...] = (
    GenomeAcceptanceItem(
        item_id="A0-G04/V02",
        requirement="the exact Candidate/Genome/Package/request/event identities and valid "
        "conformance bindings survive the A0 public flow; preparation-only, mismatched or "
        "revoked inputs cannot be consumed; permitted reuse avoids redundant verification",
        owner_issue="#437/#438/#439",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=_refs(
            _SGF,
            "test_a0_g04_v02_the_a0_flow_keeps_its_identities_and_refuses_the_bad_inputs",
            "test_an_exact_repeat_reuses_verification_and_runs_no_new_sandbox_work",
        ),
        note="#437-shaped synthetic fixtures, test-only; the A0 wheel is not installed here",
    ),
    GenomeAcceptanceItem(
        item_id="A0-E01",
        requirement="a real V0/V1 normal research round runs end to end on real data",
        owner_issue="#441",
        evidence_class="pending_real_asset",
        status="not_run",
        evidence=_refs(_SGF, "test_a0_e01_e02_report_not_run_and_are_never_substituted"),
        note="#441 landed no commit in this repository and published no round-one asset; "
        "A0-ROUND-1 is still pending in docs/research/a0/a0_delivery_index.json. The listed "
        "test proves the not_run status is reported honestly; it is NOT evidence the "
        "criterion is met, and no synthetic fixture substitutes for it.",
    ),
    GenomeAcceptanceItem(
        item_id="A0-E02",
        requirement="the second round really reads the first round's assets through an "
        "authorized model request, response, Context, Exposure and decision",
        owner_issue="#442",
        evidence_class="pending_real_asset",
        status="not_run",
        evidence=_refs(_SGF, "test_a0_e01_e02_report_not_run_and_are_never_substituted"),
        note="#442 confirmed no owner-authorized ResearchEnginePort configuration exists. "
        "Unchanged by this ticket; reported pending, never mocked.",
    ),
    GenomeAcceptanceItem(
        item_id="A0-E03/H02",
        requirement="installed/no-source environment and frozen owner artifacts give declared "
        "double replay/readback and zero-new-call history reconstruction",
        owner_issue="#408",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=(
            *_refs(
                _REC,
                "test_u6_a_fresh_python_process_recovers_the_same_identity",
                "test_ac4_a_digest_without_a_body_replays_only_as_limited",
                "test_a0_h02_the_real_asset_slice_is_pending_and_never_mocked",
            ),
            *_refs(_SGF, "test_replay_rebuilds_frozen_identities_with_zero_run_call_and_budget"),
        ),
        note="the ticket instructs referencing #408's exact evidence rather than "
        "reimplementing recovery; the installed-wheel half stays not_run because the "
        "strategy_workspace wheel is absent from this environment",
    ),
    GenomeAcceptanceItem(
        item_id="A0-Q02",
        requirement="independent A0 oracles detect the declared identity/time/binding "
        "mutations, and a small non-CPA regression shows no strategy-name special route",
        owner_issue="#437",
        evidence_class="proven_in_this_repo",
        status="executed",
        evidence=_refs(
            _SGF,
            "test_a0_q02_an_independent_oracle_catches_identity_time_and_binding_mutations",
            "test_a0_q02_no_production_module_branches_on_a_strategy_name",
        ),
    ),
)


def not_run_items() -> tuple[GenomeAcceptanceItem, ...]:
    """The items whose real status is ``not_run``, kept apart from the passes."""

    return tuple(
        item
        for item in (*GENOME_ACCEPTANCE_ITEMS, *A0_GENOME_ITEMS)
        if item.status == "not_run"
    )


def genome_matrix_readback() -> dict[str, object]:
    """The whole #429 rollup as one deterministic public record."""

    pending = not_run_items()
    return {
        "schema": GENOME_MATRIX_SCHEMA,
        "owner_repository": "williamxhero/StrategyWorkspace",
        "acceptance_repository": "williamxhero/Quant-Research",
        "owner_boundary": "the Genome product source is owned by StrategyWorkspace and is "
        "neither imported nor modified here; this repository owns only the acceptance layer",
        "installed_wheels_present": False,
        "cited_owner_evidence": dict(CITED_OWNER_EVIDENCE),
        "golden_stages": list(GOLDEN_STAGES),
        "stage_cycles": list(stage_cycles()),
        "compatibility_matrix": dict(COMPATIBILITY_MATRIX),
        "consumption_refusals": list(CONSUMPTION_REFUSALS),
        "acceptance_items": [item.as_dict() for item in GENOME_ACCEPTANCE_ITEMS],
        "a0_items": [item.as_dict() for item in A0_GENOME_ITEMS],
        "not_run_item_ids": [item.item_id for item in pending],
        "passed_item_ids": [
            item.item_id
            for item in (*GENOME_ACCEPTANCE_ITEMS, *A0_GENOME_ITEMS)
            if item.status == "executed"
        ],
        "sign_off": "partial",
        "sign_off_reason": "the contract, identity, fail-closed, reuse and replay layer is "
        "complete and executed in this repository; the installed-wheel half is not_run because "
        "no owner wheel is installed here; A0-E01 and A0-E02 have no real asset and stay "
        "pending; #419 and #422 are cited owner evidence and were not re-measured",
    }


__all__ = [
    "A0_GENOME_ITEMS",
    "BINDING_FIELDS",
    "CITED_OWNER_EVIDENCE",
    "COMPATIBILITY_MATRIX",
    "CONSUMPTION_REFUSALS",
    "CURRENT_MAJOR",
    "FORMALLY_CONSUMABLE",
    "GENOME_ACCEPTANCE_ITEMS",
    "GENOME_FLOW_SCHEMA",
    "GENOME_MATRIX_SCHEMA",
    "GENOME_RECORD_SCHEMA",
    "GOLDEN_STAGES",
    "GRANT_SCOPES",
    "IDENTITY_KINDS",
    "LEGACY_ADAPTERS",
    "ORDERED_GATES",
    "RECORD_STATES",
    "STAGE_PREREQUISITES",
    "CompareResult",
    "ConformanceBinding",
    "ConformanceEvidence",
    "ConsumptionOutcome",
    "ContentAddressStore",
    "EvidenceClass",
    "GenomeAcceptanceItem",
    "GenomeRecord",
    "GenomeRefusal",
    "GoldenFlowOutcome",
    "IdentityKind",
    "Provenance",
    "QualificationFlags",
    "RecordState",
    "ReplayOutcome",
    "TestRef",
    "VerificationLedger",
    "adapter_for",
    "canonical_digest",
    "compare_packages",
    "consume_for_formal_run",
    "genome_matrix_readback",
    "identity_kind",
    "identity_of",
    "not_run_items",
    "replay_from_public_facts",
    "run_golden_flow",
    "stage_cycles",
]
