"""Frozen, reconstructable bounded research Context and its deterministic brief.

This module completes the Context side of the Research Memory seam that
``research_exposure`` already references by identity.  An exposure event carries
a ``context_identity`` digest; until now that digest was supplied by the caller.
Here the same digest is *derived* from a declaration that is frozen before any
retrieval happens, so the Context that #396 links to is a public, rebuildable
object rather than an opaque hash.

The order is deliberate.  A caller declares the query scope, the required
evidence closure, the optional experience scope, the snapshot, the policy and
brief template, and the budget *first*.  Only then are the declared sources
resolved, admitted or excluded, and only then is a brief assembled.  The
identity binds the sources, the scope, the ordering and trimming rule, the
purpose, and the full inclusion / exclusion manifest, so two Contexts that
included different material can never share an identity.

Three constraints shape everything below.

Nothing is invented.  Every brief field is either generated from an approved
owner fact (which must carry its own provenance) or from a deterministic rule
over the manifest, or it is explicitly ``unknown``.  There is no summariser and
no free text: every value is a safe token or a ``sha256:`` digest.

A conclusion is never delivered alone.  Conclusion, required support, required
counter-evidence and limitations form one assembly unit.  Ranking and the
discussion budget may drop *optional* units; they may never drop the counter-
evidence or the limitations of a unit that is delivered.  When the required
units do not fit, the brief is blocked and handed to #398 rather than trimmed
into a one-sided positive story.

Coverage is honest about what it did not read.  ``complete``,
``complete_empty``, ``optional_not_exhausted``, ``retrieval_failure`` and
``required_incomplete`` are five distinct states, a retrieval failure is never
relabelled as an optional miss, and every readback states
``scanned_full_history: false``.

What this module deliberately does not do: it creates no task, reserves no
budget, invokes no engine, and never turns a component difference into a causal
claim.  Candidate next steps stay suggestions with explicit preconditions.
Pagination and trimming enforcement belong to #398; only the seam is left here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .core import AcceptanceFailure
from .research_visibility import (
    _SAFE_DIGEST,
    _digest,
    _fields_subset,
    _list,
    _mapping,
    _token,
    _tokens,
    evaluate_visibility_request,
)

ContextMode = Literal["current_research", "historical_reconstruction"]
CoverageState = Literal[
    "complete",
    "complete_empty",
    "optional_not_exhausted",
    "retrieval_failure",
    "required_incomplete",
]
BriefStatus = Literal["assembled", "blocked"]
FieldState = Literal["present", "unknown"]
InclusionDecision = Literal["included", "excluded"]
AlignmentState = Literal["aligned", "not_aligned", "unknown"]

CONTEXT_DECLARATION_SCHEMA = "quant-research.research-context-declaration.v1"
CONTEXT_READBACK_SCHEMA = "quant-research.research-context-readback.v1"
CONTEXT_RECORD_SCHEMA = "quant-research.research-context-record.v1"
BRIEF_TEMPLATE_ID = "quant-research.research-brief.v1"

DEFAULT_CLOSURE_BUDGET = 64
MAX_CLOSURE_BUDGET = 4096
MAX_DISCUSSION_BUDGET = 4096

#: The brief template is fixed.  A field is never omitted; it is ``unknown``.
BRIEF_FIELDS: tuple[str, ...] = (
    "current_candidate",
    "current_genome",
    "baseline_condition",
    "comparison_condition",
    "conditional_conclusions",
    "key_disagreements",
    "evidence_gaps",
    "reusable_assets",
    "candidate_next_steps",
    "must_not_claim",
    "coverage_limitations",
)
_OWNER_SCALAR_FIELDS = frozenset(
    {"current_candidate", "current_genome", "baseline_condition", "comparison_condition"}
)
_OWNER_LIST_FIELDS = frozenset({"key_disagreements", "reusable_assets", "must_not_claim"})

_EXCLUSION_REASONS = frozenset(
    {
        "not_approved",
        "not_applicable",
        "not_authorized",
        "retrieval_failure",
        "published_after_snapshot",
        "outside_declared_scope",
    }
)
_BLOCK_REASONS = frozenset(
    {
        "required_closure_incomplete",
        "required_source_retrieval_failure",
        "required_counter_evidence_unavailable",
        "discussion_budget_insufficient_for_required_units",
        "current_authorization_denied",
    }
)
_ALIGNMENTS = frozenset({"aligned", "not_aligned", "unknown"})
_ALIGNMENT_DIMENSIONS: tuple[str, ...] = ("cost", "data", "execution")

_DECLARATION_FIELDS = frozenset(
    {
        "schema",
        "mode",
        "purpose",
        "query_scope",
        "snapshot",
        "policy",
        "budget",
        "required_closure",
        "optional_scope",
        "sources",
        "owner_facts",
        "evidence_gaps",
        "candidate_next_steps",
        "conclusions",
        "genome_compare",
        "visibility_request",
    }
)
_QUERY_SCOPE_FIELDS = frozenset(
    {"campaign_id", "iteration_id", "question_id", "ordering", "trimming"}
)
_SNAPSHOT_FIELDS = frozenset({"snapshot_id", "knowledge_cutoff", "corrections_version"})
_POLICY_FIELDS = frozenset({"policy_id", "policy_version", "template_id", "template_version"})
_BUDGET_FIELDS = frozenset({"discussion_budget", "closure_budget"})
_OPTIONAL_SCOPE_FIELDS = frozenset({"source_ids", "exhausted"})
_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "record_type",
        "approved",
        "applicable",
        "retrieval",
        "published_at",
        "provenance_ref",
        "content_digest",
        "derived_from",
    }
)
_FACT_FIELDS = frozenset({"value", "values", "provenance"})
_GAP_FIELDS = frozenset({"gap_id", "provenance_ref", "preconditions"})
_STEP_FIELDS = frozenset({"step_id", "provenance_ref", "preconditions"})
_CONCLUSION_FIELDS = frozenset(
    {
        "conclusion_id",
        "statement_ref",
        "required_support",
        "required_counter_evidence",
        "limitations",
        "optional",
    }
)
_GENOME_FIELDS = frozenset(
    {
        "semantic_path",
        "change_category",
        "verified_unchanged_scope",
        "alignment",
        "provenance_ref",
    }
)


class ContextAssemblyFailure(AcceptanceFailure):
    """The declared Context could not be frozen into a deliverable brief.

    This is raised only for a malformed or self-contradictory declaration.  An
    honest "cannot deliver" outcome is *not* an exception: it is a frozen
    Context whose brief status is ``blocked`` with explicit reasons, so the
    refusal itself stays a public, reconstructable record.
    """


@dataclass(frozen=True, slots=True)
class QueryScope:
    campaign_id: str
    iteration_id: str
    question_id: str
    ordering: str
    trimming: str

    @classmethod
    def parse(cls, value: object) -> QueryScope:
        item = _mapping(value, "query_scope")
        _fields_subset(item, _QUERY_SCOPE_FIELDS, "query_scope")
        return cls(
            campaign_id=_token(item.get("campaign_id"), "query_scope.campaign_id"),
            iteration_id=_token(item.get("iteration_id"), "query_scope.iteration_id"),
            question_id=_token(item.get("question_id"), "query_scope.question_id"),
            ordering=_token(item.get("ordering"), "query_scope.ordering"),
            trimming=_token(item.get("trimming"), "query_scope.trimming"),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "campaign_id": self.campaign_id,
            "iteration_id": self.iteration_id,
            "question_id": self.question_id,
            "ordering": self.ordering,
            "trimming": self.trimming,
        }


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    snapshot_id: str
    knowledge_cutoff: str
    corrections_version: str

    @classmethod
    def parse(cls, value: object) -> ContextSnapshot:
        item = _mapping(value, "snapshot")
        _fields_subset(item, _SNAPSHOT_FIELDS, "snapshot")
        return cls(
            snapshot_id=_token(item.get("snapshot_id"), "snapshot.snapshot_id"),
            knowledge_cutoff=_token(item.get("knowledge_cutoff"), "snapshot.knowledge_cutoff"),
            corrections_version=_token(
                item.get("corrections_version"), "snapshot.corrections_version"
            ),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "snapshot_id": self.snapshot_id,
            "knowledge_cutoff": self.knowledge_cutoff,
            "corrections_version": self.corrections_version,
        }


@dataclass(frozen=True, slots=True)
class ContextPolicyRef:
    policy_id: str
    policy_version: str
    template_id: str
    template_version: str

    @classmethod
    def parse(cls, value: object) -> ContextPolicyRef:
        item = _mapping(value, "policy")
        _fields_subset(item, _POLICY_FIELDS, "policy")
        template_id = _token(item.get("template_id"), "policy.template_id")
        if template_id != BRIEF_TEMPLATE_ID:
            raise ContextAssemblyFailure(f"policy.template_id is not supported: {template_id}")
        return cls(
            policy_id=_token(item.get("policy_id"), "policy.policy_id"),
            policy_version=_token(item.get("policy_version"), "policy.policy_version"),
            template_id=template_id,
            template_version=_token(item.get("template_version"), "policy.template_version"),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "template_id": self.template_id,
            "template_version": self.template_version,
        }


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """The frozen budget.

    ``closure_budget`` bounds the required-evidence closure walk.
    ``discussion_budget`` bounds how much brief material may be assembled.
    Actual pagination and trimming of an over-budget Context is #398's job; the
    seam here is that an over-budget *required* set blocks rather than trims.
    """

    discussion_budget: int
    closure_budget: int

    @classmethod
    def parse(cls, value: object) -> ContextBudget:
        item = _mapping(value, "budget")
        _fields_subset(item, _BUDGET_FIELDS, "budget")
        return cls(
            discussion_budget=_bounded_int(
                item.get("discussion_budget"),
                "budget.discussion_budget",
                MAX_DISCUSSION_BUDGET,
                default=None,
            ),
            closure_budget=_bounded_int(
                item.get("closure_budget"),
                "budget.closure_budget",
                MAX_CLOSURE_BUDGET,
                default=DEFAULT_CLOSURE_BUDGET,
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "discussion_budget": self.discussion_budget,
            "closure_budget": self.closure_budget,
            # #398 owns pagination/trimming enforcement; this contract only
            # declares the budget and refuses to trim a required unit.
            "pagination_owner": "issue-398",
        }


@dataclass(frozen=True, slots=True)
class SourceEdge:
    source_id: str
    relationship: str

    def as_dict(self) -> dict[str, str]:
        return {"source_id": self.source_id, "relationship": self.relationship}

    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ContextSource:
    """One declared candidate source and the owner facts that decide admission."""

    source_id: str
    record_type: str
    approved: bool
    applicable: bool
    retrieval: Literal["ok", "failed"]
    published_at: str
    provenance_ref: str
    content_digest: str
    derived_from: tuple[SourceEdge, ...]

    @classmethod
    def parse(cls, value: object, index: int) -> ContextSource:
        label = f"sources[{index}]"
        item = _mapping(value, label)
        _fields_subset(item, _SOURCE_FIELDS, label)
        retrieval = _token(item.get("retrieval"), f"{label}.retrieval")
        if retrieval not in {"ok", "failed"}:
            raise ContextAssemblyFailure(f"{label}.retrieval is invalid: {retrieval}")
        digest = item.get("content_digest")
        if not isinstance(digest, str) or _SAFE_DIGEST.fullmatch(digest) is None:
            raise ContextAssemblyFailure(f"{label}.content_digest is invalid")
        edges: dict[str, SourceEdge] = {}
        raw_edges = _list(item.get("derived_from", []), f"{label}.derived_from")
        for edge_index, raw in enumerate(raw_edges):
            edge_label = f"{label}.derived_from[{edge_index}]"
            edge_item = _mapping(raw, edge_label)
            _fields_subset(edge_item, {"source_id", "relationship"}, edge_label)
            edge = SourceEdge(
                source_id=_token(edge_item.get("source_id"), f"{edge_label}.source_id"),
                relationship=_token(edge_item.get("relationship"), f"{edge_label}.relationship"),
            )
            # A repeated edge is an allowed-equivalent representation, not a
            # different graph: deduplicate before anything reads the order.
            edges.setdefault(edge.digest(), edge)
        return cls(
            source_id=_token(item.get("source_id"), f"{label}.source_id"),
            record_type=_token(item.get("record_type"), f"{label}.record_type"),
            approved=_flag(item.get("approved"), f"{label}.approved"),
            applicable=_flag(item.get("applicable"), f"{label}.applicable"),
            retrieval=retrieval,  # type: ignore[arg-type]
            published_at=_token(item.get("published_at"), f"{label}.published_at"),
            provenance_ref=_token(item.get("provenance_ref"), f"{label}.provenance_ref"),
            content_digest=digest,
            derived_from=tuple(edge for _key, edge in sorted(edges.items())),
        )

    def identity(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "record_type": self.record_type,
            "content_digest": self.content_digest,
            "provenance_ref": self.provenance_ref,
            "published_at": self.published_at,
            "derived_from": [edge.as_dict() for edge in self.derived_from],
        }


@dataclass(frozen=True, slots=True)
class OwnerFact:
    """An approved owner fact.  Provenance is mandatory; nothing is inferred."""

    values: tuple[str, ...]
    provenance: tuple[str, ...]
    scalar: bool

    @classmethod
    def parse(cls, value: object, name: str) -> OwnerFact:
        label = f"owner_facts.{name}"
        item = _mapping(value, label)
        _fields_subset(item, _FACT_FIELDS, label)
        has_value = "value" in item
        has_values = "values" in item
        if has_value == has_values:
            raise ContextAssemblyFailure(f"{label} needs exactly one of value/values")
        if has_value:
            values = (_token(item.get("value"), f"{label}.value"),)
        else:
            values = _tokens(item.get("values"), f"{label}.values")
        provenance = _tokens(item.get("provenance"), f"{label}.provenance")
        return cls(values=values, provenance=provenance, scalar=has_value)


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    gap_id: str
    provenance_ref: str
    preconditions: tuple[str, ...]

    @classmethod
    def parse(cls, value: object, index: int) -> EvidenceGap:
        label = f"evidence_gaps[{index}]"
        item = _mapping(value, label)
        _fields_subset(item, _GAP_FIELDS, label)
        return cls(
            gap_id=_token(item.get("gap_id"), f"{label}.gap_id"),
            provenance_ref=_token(item.get("provenance_ref"), f"{label}.provenance_ref"),
            preconditions=_tokens(item.get("preconditions"), f"{label}.preconditions"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "gap_id": self.gap_id,
            "provenance": [self.provenance_ref],
            "preconditions": list(self.preconditions),
        }


@dataclass(frozen=True, slots=True)
class CandidateNextStep:
    """A suggestion only.  It never becomes a task, a budget, or an invocation."""

    step_id: str
    provenance_ref: str
    preconditions: tuple[str, ...]

    @classmethod
    def parse(cls, value: object, index: int) -> CandidateNextStep:
        label = f"candidate_next_steps[{index}]"
        item = _mapping(value, label)
        _fields_subset(item, _STEP_FIELDS, label)
        return cls(
            step_id=_token(item.get("step_id"), f"{label}.step_id"),
            provenance_ref=_token(item.get("provenance_ref"), f"{label}.provenance_ref"),
            preconditions=_tokens(item.get("preconditions"), f"{label}.preconditions"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "provenance": [self.provenance_ref],
            "execution_preconditions": list(self.preconditions),
            "status": "suggestion_pending_approval",
        }


@dataclass(frozen=True, slots=True)
class ConclusionUnit:
    """A conclusion and everything that must ship with it, as one unit."""

    conclusion_id: str
    statement_ref: str
    required_support: tuple[str, ...]
    required_counter_evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    optional: bool

    @classmethod
    def parse(cls, value: object, index: int) -> ConclusionUnit:
        label = f"conclusions[{index}]"
        item = _mapping(value, label)
        _fields_subset(item, _CONCLUSION_FIELDS, label)
        return cls(
            conclusion_id=_token(item.get("conclusion_id"), f"{label}.conclusion_id"),
            statement_ref=_token(item.get("statement_ref"), f"{label}.statement_ref"),
            required_support=_tokens(item.get("required_support"), f"{label}.required_support"),
            required_counter_evidence=_tokens(
                item.get("required_counter_evidence", []),
                f"{label}.required_counter_evidence",
                empty=True,
            ),
            limitations=_tokens(item.get("limitations", []), f"{label}.limitations", empty=True),
            optional=_flag(item.get("optional"), f"{label}.optional"),
        )

    def members(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                set(self.required_support)
                | set(self.required_counter_evidence)
                | set(self.limitations)
            )
        )

    def cost(self) -> int:
        """One slot for the conclusion, one for each thing that must ship with it."""

        return 1 + len(self.members())

    def as_dict(self) -> dict[str, object]:
        return {
            "conclusion_id": self.conclusion_id,
            "statement_ref": self.statement_ref,
            "required_support": list(self.required_support),
            "required_counter_evidence": list(self.required_counter_evidence),
            "limitations": list(self.limitations),
            "optional": self.optional,
        }


@dataclass(frozen=True, slots=True)
class GenomeCompare:
    """Owner-published component comparison.  Nothing here is recomputed."""

    semantic_path: str
    change_category: str
    verified_unchanged_scope: tuple[str, ...]
    alignment: tuple[tuple[str, AlignmentState], ...]
    provenance_ref: str

    @classmethod
    def parse(cls, value: object) -> GenomeCompare | None:
        if value is None:
            return None
        item = _mapping(value, "genome_compare")
        _fields_subset(item, _GENOME_FIELDS, "genome_compare")
        raw = _mapping(item.get("alignment"), "genome_compare.alignment")
        _fields_subset(raw, set(_ALIGNMENT_DIMENSIONS), "genome_compare.alignment")
        alignment: list[tuple[str, AlignmentState]] = []
        for dimension in _ALIGNMENT_DIMENSIONS:
            state = _token(raw.get(dimension), f"genome_compare.alignment.{dimension}")
            if state not in _ALIGNMENTS:
                raise ContextAssemblyFailure(
                    f"genome_compare.alignment.{dimension} is invalid: {state}"
                )
            alignment.append((dimension, state))  # type: ignore[arg-type]
        return cls(
            semantic_path=_token(item.get("semantic_path"), "genome_compare.semantic_path"),
            change_category=_token(item.get("change_category"), "genome_compare.change_category"),
            verified_unchanged_scope=_tokens(
                item.get("verified_unchanged_scope", []),
                "genome_compare.verified_unchanged_scope",
                empty=True,
            ),
            alignment=tuple(alignment),
            provenance_ref=_token(item.get("provenance_ref"), "genome_compare.provenance_ref"),
        )

    def misaligned(self) -> tuple[str, ...]:
        return tuple(dimension for dimension, state in self.alignment if state != "aligned")

    def as_dict(self) -> dict[str, object]:
        return {
            "semantic_path": self.semantic_path,
            "change_category": self.change_category,
            "verified_unchanged_scope": list(self.verified_unchanged_scope),
            "alignment": {dimension: state for dimension, state in self.alignment},
            "provenance_ref": self.provenance_ref,
        }


@dataclass(frozen=True, slots=True)
class ContextDeclaration:
    """Everything declared *before* retrieval, in one frozen object."""

    mode: ContextMode
    purpose: str
    query_scope: QueryScope
    snapshot: ContextSnapshot
    policy: ContextPolicyRef
    budget: ContextBudget
    required_closure: tuple[str, ...]
    optional_scope: tuple[str, ...]
    optional_exhausted: bool
    sources: tuple[ContextSource, ...]
    owner_facts: tuple[tuple[str, OwnerFact], ...]
    evidence_gaps: tuple[EvidenceGap, ...]
    candidate_next_steps: tuple[CandidateNextStep, ...]
    conclusions: tuple[ConclusionUnit, ...]
    genome_compare: GenomeCompare | None
    visibility_request: dict[str, Any] | None

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> ContextDeclaration:
        item = _mapping(value, "context declaration")
        _fields_subset(item, _DECLARATION_FIELDS, "context declaration")
        if item.get("schema") != CONTEXT_DECLARATION_SCHEMA:
            raise ContextAssemblyFailure("context declaration schema is invalid")
        mode = _token(item.get("mode"), "context mode")
        if mode not in {"current_research", "historical_reconstruction"}:
            raise ContextAssemblyFailure(f"context mode is invalid: {mode}")
        sources = tuple(
            ContextSource.parse(raw, index)
            for index, raw in enumerate(_list(item.get("sources"), "sources"))
        )
        ids = [source.source_id for source in sources]
        if len(ids) != len(set(ids)):
            raise ContextAssemblyFailure("context source ids are not unique")
        raw_facts = _mapping(item.get("owner_facts", {}), "owner_facts")
        _fields_subset(raw_facts, _OWNER_SCALAR_FIELDS | _OWNER_LIST_FIELDS, "owner_facts")
        facts: list[tuple[str, OwnerFact]] = []
        for name in sorted(raw_facts):
            fact = OwnerFact.parse(raw_facts[name], name)
            if fact.scalar != (name in _OWNER_SCALAR_FIELDS):
                raise ContextAssemblyFailure(f"owner_facts.{name} has the wrong shape")
            facts.append((name, fact))
        conclusions = tuple(
            ConclusionUnit.parse(raw, index)
            for index, raw in enumerate(_list(item.get("conclusions", []), "conclusions"))
        )
        conclusion_ids = [unit.conclusion_id for unit in conclusions]
        if len(conclusion_ids) != len(set(conclusion_ids)):
            raise ContextAssemblyFailure("conclusion ids are not unique")
        raw_optional = _mapping(item.get("optional_scope"), "optional_scope")
        _fields_subset(raw_optional, _OPTIONAL_SCOPE_FIELDS, "optional_scope")
        required = _tokens(item.get("required_closure", []), "required_closure", empty=True)
        optional = _tokens(
            raw_optional.get("source_ids", []), "optional_scope.source_ids", empty=True
        )
        raw_visibility = item.get("visibility_request")
        return cls(
            mode=mode,  # type: ignore[arg-type]
            purpose=_token(item.get("purpose"), "purpose"),
            query_scope=QueryScope.parse(item.get("query_scope")),
            snapshot=ContextSnapshot.parse(item.get("snapshot")),
            policy=ContextPolicyRef.parse(item.get("policy")),
            budget=ContextBudget.parse(item.get("budget")),
            required_closure=required,
            # A source named in both scopes is required; the optional scope is
            # the remainder.  That keeps the two representations equivalent.
            optional_scope=tuple(name for name in optional if name not in set(required)),
            optional_exhausted=_flag(raw_optional.get("exhausted"), "optional_scope.exhausted"),
            sources=tuple(sorted(sources, key=lambda source: source.source_id)),
            owner_facts=tuple(facts),
            evidence_gaps=tuple(
                sorted(
                    (
                        EvidenceGap.parse(raw, index)
                        for index, raw in enumerate(
                            _list(item.get("evidence_gaps", []), "evidence_gaps")
                        )
                    ),
                    key=lambda gap: gap.gap_id,
                )
            ),
            candidate_next_steps=tuple(
                sorted(
                    (
                        CandidateNextStep.parse(raw, index)
                        for index, raw in enumerate(
                            _list(item.get("candidate_next_steps", []), "candidate_next_steps")
                        )
                    ),
                    key=lambda step: step.step_id,
                )
            ),
            conclusions=tuple(sorted(conclusions, key=lambda unit: unit.conclusion_id)),
            genome_compare=GenomeCompare.parse(item.get("genome_compare")),
            visibility_request=(
                None
                if raw_visibility is None
                else dict(_mapping(raw_visibility, "visibility_request"))
            ),
        )

    def as_dict(self) -> dict[str, object]:
        """The canonical public echo of the declaration.

        This is what ``reconstruct_research_context`` replays.  It is ordered
        and deduplicated, so the record of a Context is enough to rebuild it.
        """

        return {
            "schema": CONTEXT_DECLARATION_SCHEMA,
            "mode": self.mode,
            "purpose": self.purpose,
            "query_scope": self.query_scope.as_dict(),
            "snapshot": self.snapshot.as_dict(),
            "policy": self.policy.as_dict(),
            "budget": {
                "discussion_budget": self.budget.discussion_budget,
                "closure_budget": self.budget.closure_budget,
            },
            "required_closure": list(self.required_closure),
            "optional_scope": {
                "source_ids": list(self.optional_scope),
                "exhausted": self.optional_exhausted,
            },
            "sources": [
                {
                    "source_id": source.source_id,
                    "record_type": source.record_type,
                    "approved": source.approved,
                    "applicable": source.applicable,
                    "retrieval": source.retrieval,
                    "published_at": source.published_at,
                    "provenance_ref": source.provenance_ref,
                    "content_digest": source.content_digest,
                    "derived_from": [edge.as_dict() for edge in source.derived_from],
                }
                for source in self.sources
            ],
            "owner_facts": {
                name: (
                    {"value": fact.values[0], "provenance": list(fact.provenance)}
                    if fact.scalar
                    else {"values": list(fact.values), "provenance": list(fact.provenance)}
                )
                for name, fact in self.owner_facts
            },
            "evidence_gaps": [
                {
                    "gap_id": gap.gap_id,
                    "provenance_ref": gap.provenance_ref,
                    "preconditions": list(gap.preconditions),
                }
                for gap in self.evidence_gaps
            ],
            "candidate_next_steps": [
                {
                    "step_id": step.step_id,
                    "provenance_ref": step.provenance_ref,
                    "preconditions": list(step.preconditions),
                }
                for step in self.candidate_next_steps
            ],
            "conclusions": [unit.as_dict() for unit in self.conclusions],
            "genome_compare": (
                None if self.genome_compare is None else self.genome_compare.as_dict()
            ),
            "visibility_request": self.visibility_request,
        }


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    source_id: str
    decision: InclusionDecision
    reason: str
    role: Literal["required", "optional"]

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "decision": self.decision,
            "reason": self.reason,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class ContextCoverage:
    state: CoverageState
    required_missing: tuple[str, ...]
    optional_uncovered: tuple[str, ...]
    retrieval_failures: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "required_missing": list(self.required_missing),
            "optional_uncovered": list(self.optional_uncovered),
            "retrieval_failures": list(self.retrieval_failures),
            # The declared scope is the only thing completeness ever refers to.
            "declared_scope_only": True,
            "scanned_full_history": False,
        }


@dataclass(frozen=True, slots=True)
class ResearchBrief:
    status: BriefStatus
    block_reasons: tuple[str, ...]
    fields: tuple[tuple[str, dict[str, object]], ...]
    dropped_optional_units: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "template_id": BRIEF_TEMPLATE_ID,
            "status": self.status,
            "block_reasons": list(self.block_reasons),
            "dropped_optional_units": list(self.dropped_optional_units),
            "fields": {name: value for name, value in self.fields},
            # Nothing in this contract acts.  These are asserted, not assumed.
            "creates_tasks": False,
            "reserves_budget": False,
            "invokes_engine": False,
            "grants_eligibility": False,
        }


@dataclass(frozen=True, slots=True)
class ResearchContext:
    """A frozen bounded Context: identity, manifest, coverage and brief."""

    declaration: ContextDeclaration
    identity: str
    manifest: tuple[ManifestEntry, ...]
    coverage: ContextCoverage
    brief: ResearchBrief

    @property
    def included_source_ids(self) -> tuple[str, ...]:
        return tuple(entry.source_id for entry in self.manifest if entry.decision == "included")

    def public_record(self) -> dict[str, object]:
        """Everything needed to rebuild this Context, and nothing else."""

        return {
            "schema": CONTEXT_RECORD_SCHEMA,
            "context_identity": self.identity,
            "declaration": self.declaration.as_dict(),
        }

    def readback(self) -> dict[str, object]:
        return {
            "schema": CONTEXT_READBACK_SCHEMA,
            "context_identity": self.identity,
            "mode": self.declaration.mode,
            "purpose": self.declaration.purpose,
            "query_scope": self.declaration.query_scope.as_dict(),
            "snapshot": self.declaration.snapshot.as_dict(),
            "policy": self.declaration.policy.as_dict(),
            "budget": self.declaration.budget.as_dict(),
            "manifest": [entry.as_dict() for entry in self.manifest],
            "coverage": self.coverage.as_dict(),
            "brief": self.brief.as_dict(),
            # Memory publishes; it never qualifies a research result.
            "grants_eligibility": False,
        }


def freeze_research_context(value: Mapping[str, object]) -> ResearchContext:
    """Freeze a declared bounded Context and assemble its deterministic brief.

    The declaration is parsed and canonicalised first, so input ordering,
    duplicate derivation edges, and a source named in both the required and the
    optional scope all collapse to the same frozen object.  Only then is the
    inclusion / exclusion manifest computed, the required closure walked, and
    the brief assembled.
    """

    declaration = ContextDeclaration.parse(value)
    return _assemble(declaration)


def reconstruct_research_context(record: Mapping[str, object]) -> ResearchContext:
    """Rebuild a Context from its public record alone.

    There is no second store and no cached projection to consult: the record's
    declaration is replayed through exactly the same assembly, and the rebuilt
    identity must equal the recorded one.
    """

    item = _mapping(record, "context record")
    _fields_subset(item, {"schema", "context_identity", "declaration"}, "context record")
    if item.get("schema") != CONTEXT_RECORD_SCHEMA:
        raise ContextAssemblyFailure("context record schema is invalid")
    recorded = item.get("context_identity")
    if not isinstance(recorded, str) or _SAFE_DIGEST.fullmatch(recorded) is None:
        raise ContextAssemblyFailure("context record identity is invalid")
    rebuilt = freeze_research_context(
        _mapping(item.get("declaration"), "context record declaration")
    )
    if rebuilt.identity != recorded:
        raise ContextAssemblyFailure("context record does not reproduce its identity")
    return rebuilt


def deliver_research_brief(
    context: ResearchContext,
    visibility_request: Mapping[str, object],
) -> dict[str, object]:
    """Hand back a frozen brief only under *current* authorization.

    The authorization recorded when the Context was frozen explains what was
    admitted then; it never restores access now.  A currently unauthorized
    reader gets a refusal that leaks neither the brief nor the manifest.
    """

    decision = evaluate_visibility_request(visibility_request)
    if not decision.deliverable:
        return {
            "schema": CONTEXT_READBACK_SCHEMA,
            "delivery": "blocked",
            "reason": "current_authorization_denied",
            "context_identity": None,
            "grants_eligibility": False,
        }
    return {**context.readback(), "delivery": "delivered"}


def _assemble(declaration: ContextDeclaration) -> ResearchContext:
    by_id = {source.source_id: source for source in declaration.sources}
    # The closure is resolved before the manifest, so declaring the roots and
    # declaring every transitive ancestor are equivalent representations.
    closure, closure_missing = _required_closure(declaration, by_id)
    declared_roles = _roles(declaration, closure)
    authorization = _authorization_status(declaration)
    manifest_map: dict[str, ManifestEntry] = {}
    for source_id in sorted(declared_roles):
        role = declared_roles[source_id]
        source = by_id.get(source_id)
        if source is None:
            manifest_map[source_id] = ManifestEntry(
                source_id, "excluded", "outside_declared_scope", role
            )
            continue
        reason = _exclusion_reason(declaration, source, authorization)
        manifest_map[source_id] = ManifestEntry(
            source_id,
            "excluded" if reason is not None else "included",
            reason if reason is not None else "declared_and_approved",
            role,
        )
    # Sources that were declared but belong to neither scope are recorded as
    # excluded too, so the manifest covers every source the Context ever saw.
    for source_id in sorted(by_id):
        if source_id not in manifest_map:
            manifest_map[source_id] = ManifestEntry(
                source_id, "excluded", "outside_declared_scope", "optional"
            )
    included = {
        source_id for source_id, entry in manifest_map.items() if entry.decision == "included"
    }
    required_missing = tuple(sorted(set(closure_missing) | (closure - included)))
    coverage = _coverage(declaration, manifest_map, required_missing, included)
    brief = _brief(declaration, manifest_map, coverage, included)
    identity = _identity(declaration, manifest_map)
    return ResearchContext(
        declaration=declaration,
        identity=identity,
        manifest=tuple(manifest_map[key] for key in sorted(manifest_map)),
        coverage=coverage,
        brief=brief,
    )


def _roles(
    declaration: ContextDeclaration,
    closure: set[str],
) -> dict[str, Literal["required", "optional"]]:
    roles: dict[str, Literal["required", "optional"]] = {}
    for source_id in declaration.optional_scope:
        roles[source_id] = "optional"
    for source_id in sorted(closure):
        roles[source_id] = "required"
    return roles


def _authorization_status(declaration: ContextDeclaration) -> dict[str, str]:
    """Per-source authorization, decided by the #394/#395 gate, never re-decided."""

    if declaration.visibility_request is None:
        return {}
    decision = evaluate_visibility_request(declaration.visibility_request)
    return {material.material_id: material.status for material in decision.materials}


def _exclusion_reason(
    declaration: ContextDeclaration,
    source: ContextSource,
    authorization: Mapping[str, str],
) -> str | None:
    # Order matters: a retrieval failure must never be relabelled as a mere
    # applicability or budget miss, so it is checked before the softer reasons.
    if source.retrieval == "failed":
        return "retrieval_failure"
    if not source.approved:
        return "not_approved"
    if not source.applicable:
        return "not_applicable"
    status = authorization.get(source.source_id)
    if status is not None and status != "allowed":
        return "not_authorized"
    if (
        declaration.mode == "historical_reconstruction"
        and source.published_at > declaration.snapshot.knowledge_cutoff
    ):
        # A correction published after the snapshot belongs to current research,
        # not to the historical Context being reconstructed.
        return "published_after_snapshot"
    return None


def _required_closure(
    declaration: ContextDeclaration,
    by_id: Mapping[str, ContextSource],
) -> tuple[set[str], tuple[str, ...]]:
    """Walk the declared required-evidence closure, fail closed.

    The walk is an explicit-stack DFS over canonically ordered edges, bounded by
    the frozen closure budget.  Because the edges are sorted before the walk
    starts, the traversal order is a function of the declared graph alone and
    never of the order the caller happened to list things in.
    """

    closure: set[str] = set()
    missing: set[str] = set()
    visits = 0
    frames: list[list[Any]] = []
    for source_id in declaration.required_closure:
        closure.add(source_id)
        source = by_id.get(source_id)
        if source is None:
            missing.add(source_id)
            continue
        frames.append([source_id, source.derived_from, 0])
    on_path: set[str] = set()
    while frames:
        frame = frames[-1]
        node_id, edges, index = frame
        if index == 0:
            on_path.add(node_id)
        if index >= len(edges):
            frames.pop()
            on_path.discard(node_id)
            continue
        frame[2] = index + 1
        edge = edges[index]
        visits += 1
        if visits > declaration.budget.closure_budget:
            # An exhausted budget is a missing closure, never an empty one.
            missing.add(edge.source_id)
            break
        closure.add(edge.source_id)
        child = by_id.get(edge.source_id)
        if child is None:
            missing.add(edge.source_id)
            continue
        if edge.source_id in on_path:
            continue
        frames.append([child.source_id, child.derived_from, 0])
    return closure, tuple(sorted(missing))


def _coverage(
    declaration: ContextDeclaration,
    manifest: Mapping[str, ManifestEntry],
    required_missing: tuple[str, ...],
    included: set[str],
) -> ContextCoverage:
    failures = tuple(
        sorted(
            source_id
            for source_id, entry in manifest.items()
            if entry.reason == "retrieval_failure"
        )
    )
    uncovered = tuple(
        sorted(
            source_id
            for source_id in declaration.optional_scope
            if source_id not in included
        )
    )
    if failures:
        state: CoverageState = "retrieval_failure"
    elif required_missing:
        state = "required_incomplete"
    elif not declaration.required_closure and not included:
        # The declared scope was resolved in full and matched nothing.  That is
        # a complete result, and it is not the same thing as a failed retrieval.
        state = "complete_empty"
    elif uncovered or not declaration.optional_exhausted:
        state = "optional_not_exhausted"
    else:
        state = "complete"
    return ContextCoverage(
        state=state,
        required_missing=required_missing,
        optional_uncovered=uncovered,
        retrieval_failures=failures,
    )


def _brief(
    declaration: ContextDeclaration,
    manifest: Mapping[str, ManifestEntry],
    coverage: ContextCoverage,
    included: set[str],
) -> ResearchBrief:
    facts = dict(declaration.owner_facts)
    block_reasons: set[str] = set()
    if coverage.state == "required_incomplete":
        block_reasons.add("required_closure_incomplete")
    if coverage.state == "retrieval_failure":
        required_failed = any(
            entry.reason == "retrieval_failure" and entry.role == "required"
            for entry in manifest.values()
        )
        block_reasons.add(
            "required_source_retrieval_failure"
            if required_failed
            else "required_closure_incomplete"
        )
    units, dropped, unit_blocks = _assemble_units(declaration, included)
    block_reasons.update(unit_blocks)
    limitations = _coverage_limitations(declaration, manifest, coverage)
    gaps = _evidence_gaps(declaration)
    fields: list[tuple[str, dict[str, object]]] = []
    for name in BRIEF_FIELDS:
        if name in _OWNER_SCALAR_FIELDS:
            fields.append((name, _scalar_field(facts.get(name))))
        elif name == "conditional_conclusions":
            fields.append((name, _unit_field(units)))
        elif name == "evidence_gaps":
            fields.append((name, _entry_field(gaps)))
        elif name == "candidate_next_steps":
            steps = [step.as_dict() for step in declaration.candidate_next_steps]
            fields.append((name, _entry_field(steps)))
        elif name == "must_not_claim":
            fields.append((name, _must_not_claim(declaration, facts.get(name))))
        elif name == "coverage_limitations":
            fields.append((name, _entry_field(limitations)))
        else:
            fields.append((name, _list_field(facts.get(name))))
    return ResearchBrief(
        status="blocked" if block_reasons else "assembled",
        block_reasons=tuple(sorted(block_reasons)),
        fields=tuple(fields),
        dropped_optional_units=dropped,
    )


def _assemble_units(
    declaration: ContextDeclaration,
    included: set[str],
) -> tuple[tuple[ConclusionUnit, ...], tuple[str, ...], set[str]]:
    """Assemble whole units, then fit them to the budget from the optional end.

    A unit whose required support, required counter-evidence or limitations are
    not all available is never delivered as a bare conclusion: it blocks.  When
    the budget cannot hold every unit, optional discussion units are dropped
    first, in reverse canonical order.  If the required units still do not fit,
    the brief blocks and hands the trimming decision to #398 -- it never keeps
    the conclusion and drops the counter-evidence.
    """

    blocks: set[str] = set()
    available: list[ConclusionUnit] = []
    for unit in declaration.conclusions:
        if set(unit.members()) <= included:
            available.append(unit)
            continue
        if not unit.optional:
            blocks.add("required_counter_evidence_unavailable")
        # An optional unit that cannot be assembled in full is simply not
        # discussed.  It is never degraded to a conclusion without its evidence.
    required_units = [unit for unit in available if not unit.optional]
    optional_units = [unit for unit in available if unit.optional]
    budget = declaration.budget.discussion_budget
    required_cost = sum(unit.cost() for unit in required_units)
    if required_cost > budget:
        blocks.add("discussion_budget_insufficient_for_required_units")
        return (), tuple(sorted(unit.conclusion_id for unit in optional_units)), blocks
    kept: list[ConclusionUnit] = list(required_units)
    dropped: list[str] = []
    spend = required_cost
    for unit in optional_units:
        if spend + unit.cost() <= budget:
            kept.append(unit)
            spend += unit.cost()
        else:
            dropped.append(unit.conclusion_id)
    return (
        tuple(sorted(kept, key=lambda unit: unit.conclusion_id)),
        tuple(sorted(dropped)),
        blocks,
    )


def _evidence_gaps(declaration: ContextDeclaration) -> list[dict[str, object]]:
    """Comparison gaps come first, then the owner's declared gaps."""

    gaps: list[dict[str, object]] = []
    compare = declaration.genome_compare
    if compare is not None:
        for dimension in compare.misaligned():
            gaps.append(
                {
                    "gap_id": f"comparison_gap:{dimension}",
                    "provenance": [compare.provenance_ref],
                    "preconditions": [f"align:{dimension}"],
                }
            )
    gaps.extend(gap.as_dict() for gap in declaration.evidence_gaps)
    return gaps


def _coverage_limitations(
    declaration: ContextDeclaration,
    manifest: Mapping[str, ManifestEntry],
    coverage: ContextCoverage,
) -> list[dict[str, object]]:
    limitations: list[dict[str, object]] = [
        {
            "limitation_id": f"coverage_state:{coverage.state}",
            "provenance": ["context:coverage"],
            "preconditions": [],
        }
    ]
    compare = declaration.genome_compare
    if compare is not None:
        for dimension in compare.misaligned():
            limitations.append(
                {
                    "limitation_id": f"comparability_limited:{dimension}",
                    "provenance": [compare.provenance_ref],
                    "preconditions": [f"align:{dimension}"],
                }
            )
        for scope in compare.verified_unchanged_scope:
            # A single-component difference does not make everything else equal;
            # what the owner verified as unchanged is carried through verbatim.
            limitations.append(
                {
                    "limitation_id": f"verified_unchanged:{scope}",
                    "provenance": [compare.provenance_ref],
                    "preconditions": [],
                }
            )
        limitations.append(
            {
                "limitation_id": f"changed_component:{compare.semantic_path}",
                "provenance": [compare.provenance_ref],
                "preconditions": [],
            }
        )
    excluded_reasons = {
        entry.reason for entry in manifest.values() if entry.decision == "excluded"
    }
    for reason in sorted(excluded_reasons):
        limitations.append(
            {
                "limitation_id": f"excluded:{reason}",
                "provenance": ["context:manifest"],
                "preconditions": [],
            }
        )
    return limitations


def _must_not_claim(declaration: ContextDeclaration, fact: OwnerFact | None) -> dict[str, object]:
    claims: list[str] = ["full_history_scanned", "research_eligibility"]
    compare = declaration.genome_compare
    if compare is not None and compare.misaligned():
        claims.append("causal_improvement")
    provenance = ["context:rule"]
    if fact is not None:
        claims.extend(fact.values)
        provenance.extend(fact.provenance)
    return {
        "state": "present",
        "values": sorted(set(claims)),
        "provenance": sorted(set(provenance)),
    }


def _scalar_field(fact: OwnerFact | None) -> dict[str, object]:
    if fact is None:
        return {"state": "unknown", "value": None, "provenance": []}
    return {"state": "present", "value": fact.values[0], "provenance": list(fact.provenance)}


def _list_field(fact: OwnerFact | None) -> dict[str, object]:
    if fact is None:
        return {"state": "unknown", "values": [], "provenance": []}
    return {"state": "present", "values": list(fact.values), "provenance": list(fact.provenance)}


def _entry_field(entries: list[dict[str, object]]) -> dict[str, object]:
    if not entries:
        return {"state": "unknown", "entries": []}
    return {"state": "present", "entries": entries}


def _unit_field(units: tuple[ConclusionUnit, ...]) -> dict[str, object]:
    if not units:
        return {"state": "unknown", "entries": []}
    return {"state": "present", "entries": [unit.as_dict() for unit in units]}


def _identity(declaration: ContextDeclaration, manifest: Mapping[str, ManifestEntry]) -> str:
    """The Context identity.

    It binds the snapshot, the query scope, the policy and template version, the
    purpose, the ordering and trimming rule, the identity of every declared
    source, and the full inclusion / exclusion manifest.  Two Contexts that
    admitted different material therefore cannot collide, and nothing that only
    affects traversal order enters the digest.
    """

    return _digest(
        {
            "schema": CONTEXT_DECLARATION_SCHEMA,
            "mode": declaration.mode,
            "purpose": declaration.purpose,
            "query_scope": declaration.query_scope.as_dict(),
            "snapshot": declaration.snapshot.as_dict(),
            "policy": declaration.policy.as_dict(),
            "budget": {
                "discussion_budget": declaration.budget.discussion_budget,
                "closure_budget": declaration.budget.closure_budget,
            },
            "optional_exhausted": declaration.optional_exhausted,
            "sources": [source.identity() for source in declaration.sources],
            # The manifest already states, per source, whether it was required
            # or optional and whether it was included, so the declared roots do
            # not enter the digest: naming a closure by its roots and naming it
            # by every member are the same Context.
            "manifest": [manifest[key].as_dict() for key in sorted(manifest)],
        }
    )


def _flag(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContextAssemblyFailure(f"{label} is invalid")
    return value


def _bounded_int(value: object, label: str, maximum: int, *, default: int | None) -> int:
    if value is None:
        if default is None:
            raise ContextAssemblyFailure(f"{label} is required")
        return default
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        raise ContextAssemblyFailure(f"{label} is invalid")
    return value


__all__ = [
    "BRIEF_FIELDS",
    "BRIEF_TEMPLATE_ID",
    "CONTEXT_DECLARATION_SCHEMA",
    "CONTEXT_READBACK_SCHEMA",
    "CONTEXT_RECORD_SCHEMA",
    "DEFAULT_CLOSURE_BUDGET",
    "MAX_CLOSURE_BUDGET",
    "CandidateNextStep",
    "ConclusionUnit",
    "ContextAssemblyFailure",
    "ContextBudget",
    "ContextCoverage",
    "ContextDeclaration",
    "ContextPolicyRef",
    "ContextSnapshot",
    "ContextSource",
    "EvidenceGap",
    "GenomeCompare",
    "ManifestEntry",
    "OwnerFact",
    "QueryScope",
    "ResearchBrief",
    "ResearchContext",
    "SourceEdge",
    "deliver_research_brief",
    "freeze_research_context",
    "reconstruct_research_context",
]
