"""Owner-published source corrections, formal currency, and the read-only Reporting projection.

#397 froze a bounded research Context and its deterministic brief; #398 proved
the pages behind it; #399 decided whether the research should happen at all.
All three take the *sources* on faith: a Context says what it read, not whether
what it read is still believed.

This module adds the missing distinction — **what was known then** versus **what
is the current usage status** — and publishes it, read-only and versioned, to
Reporting.

Four rules shape everything below.

**Formal currency belongs to the original owner.**  ``current``,
``revalidation_due``, ``stale``, ``superseded`` and ``invalidated`` are read out
of the owner's published facts; this module never computes one.  A new summary,
explanation or discovery-only review is explicitly *not* new evidence: it is
refused as a currency refresh, because refreshing formal currency requires the
owner's new evidence or decision.  ``CURRENCY_STATE_CONTRACT`` freezes the state
names with a version, and its digest takes part in every identity, so a renamed
state is a different projection rather than a silent relabelling.

**A correction locates potential impact; it never invalidates anything.**  The
walk runs over the *complete, bounded, public* lineage graph.  Precise owner
conditions may narrow the affected scope.  An unknown dependency, an undeclared
node, an incomplete graph or an exhausted budget all yield ``needs_review`` —
never ``invalidated``, and never a blanket invalidation of everything
downstream.  ``invalidates_downstream`` is asserted false on every assessment.

**Hindsight never backfills.**  Every correction and every currency fact carries
two independent times: ``applicable_at`` (when the fact applies to the world)
and ``system_known_at`` (when the system learned it).  A view is read ``as_of``
a knowledge cutoff, which filters on ``system_known_at`` alone, so a historical
reconstruction pinned to an old snapshot cannot see a later correction, and a
later correction can never change the old Context's identity.  Appending a
correction returns a *new* view; the old one is untouched.

**Reporting shows, it does not compute.**  The projection carries the already
published brief fields, the owner's published Genome comparison verbatim, the
owner's currency facts, and #396's real Context / envelope / replay-coverage
linkage.  It recomputes no metric, no independence, no conflict, no eligibility
and no Genome diff, it traverses no private graph, and a digest is never
presented as the delivered content.  Every gap and every candidate step carries
an owner provenance or the explicit token ``unknown``.

Re-delivery checks *current* authorization through the #394/#395 gate.  An old
policy never restores access, a restricted answer leaks no counts and no
reasons, and it does not rewrite the Context it was refused for.

What this module deliberately does not do: it adds no dependency (the lineage
walk is the same bounded explicit-stack DFS #395 and #397 already use, not
NetworkX), it opens no store, it calls no model and runs no backtest, and it
deploys nothing to MLflow — the projection there stays a future one-way,
authorization-filtered view.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .research_context import (
    BRIEF_TEMPLATE_ID,
    ContextAssemblyFailure,
    ResearchContext,
    _bounded_int,
    _flag,
    reconstruct_research_context,
)
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

CurrencyState = Literal[
    "current",
    "revalidation_due",
    "stale",
    "superseded",
    "invalidated",
    "unknown",
]
ImpactState = Literal["potentially_affected", "not_affected", "needs_review"]
CorrectionKind = Literal["data", "implementation", "evidence"]
RefreshBasis = Literal[
    "owner_evidence",
    "owner_decision",
    "summary",
    "explanation",
    "discovery_only_review",
]
ReplayCoverage = Literal["full", "limited", "none"]

CURRENCY_VIEW_SCHEMA = "quant-research.research-source-currency-view.v1"
IMPACT_ASSESSMENT_SCHEMA = "quant-research.research-correction-impact.v1"
CURRENCY_REFRESH_SCHEMA = "quant-research.research-currency-refresh.v1"
REPORTING_DECLARATION_SCHEMA = "quant-research.research-reporting-projection.v1"
REPORTING_RECORD_SCHEMA = "quant-research.research-reporting-projection-record.v1"
REPORTING_READBACK_SCHEMA = "quant-research.research-reporting-readback.v1"

#: The formal currency state contract.  ``usable_as_current_evidence`` is the
#: only derived bit, and it is a *display* rule over the owner's own state, not
#: a judgment about the research.  ``needs_owner_decision`` records that leaving
#: the state requires the owner's new evidence or decision, never a new summary.
CURRENCY_STATE_CONTRACT_ID = "quant-research.research-currency-state"
CURRENCY_STATE_CONTRACT_VERSION = "v1"
CURRENCY_STATE_CONTRACT: tuple[tuple[str, bool, bool], ...] = (
    ("current", True, False),
    ("revalidation_due", True, True),
    ("stale", False, True),
    ("superseded", False, True),
    ("invalidated", False, True),
    ("unknown", False, True),
)
CURRENCY_STATES: tuple[str, ...] = tuple(state for state, _u, _d in CURRENCY_STATE_CONTRACT)
CURRENCY_STATE_CONTRACT_DIGEST = _digest(
    {
        "contract_id": CURRENCY_STATE_CONTRACT_ID,
        "version": CURRENCY_STATE_CONTRACT_VERSION,
        "states": [
            {"state": state, "usable_as_current_evidence": usable, "needs_owner_decision": decision}
            for state, usable, decision in CURRENCY_STATE_CONTRACT
        ],
    }
)
_USABLE_STATES = frozenset(state for state, usable, _d in CURRENCY_STATE_CONTRACT if usable)

IMPACT_STATES: tuple[str, ...] = ("potentially_affected", "not_affected", "needs_review")
#: Only the owner's own new evidence or decision refreshes formal currency.  A
#: summary, an explanation or a discovery-only review is a *reading* of existing
#: material and therefore proves nothing new.
_REFRESHING_BASES = frozenset({"owner_evidence", "owner_decision"})
_NON_REFRESHING_BASES = frozenset({"summary", "explanation", "discovery_only_review"})
_CORRECTION_KINDS = frozenset({"data", "implementation", "evidence"})
_COVERAGES = frozenset({"full", "limited", "none"})

DEFAULT_IMPACT_BUDGET = 256
MAX_IMPACT_BUDGET = 8192

_VIEW_FIELDS = frozenset({"schema", "lineage", "corrections", "currency_facts"})
_GRAPH_FIELDS = frozenset({"complete", "nodes"})
_NODE_FIELDS = frozenset({"statement_id", "record_type", "depends_on", "conditions"})
_EDGE_FIELDS = frozenset({"statement_id", "relationship", "known"})
_CONDITION_FIELDS = frozenset({"known", "values"})
_CORRECTION_FIELDS = frozenset(
    {
        "correction_id",
        "target_statement_id",
        "kind",
        "applicable_at",
        "system_known_at",
        "provenance_ref",
        "precise_conditions",
    }
)
_FACT_FIELDS = frozenset(
    {
        "fact_id",
        "statement_id",
        "state",
        "applicable_at",
        "system_known_at",
        "owner_evidence_ref",
        "provenance_ref",
    }
)
_REFRESH_FIELDS = frozenset(
    {"schema", "statement_id", "basis", "proposed_state", "owner_evidence_ref", "system_known_at"}
)
_REPORTING_FIELDS = frozenset(
    {"schema", "context_record", "currency", "knowledge_cutoff", "correction_id", "exposure"}
)
_EXPOSURE_FIELDS = frozenset(
    {
        "action_key",
        "context_identity",
        "envelope_digest",
        "envelope_content_ref",
        "replay_coverage",
        "provider_request_id",
        "template_version",
        "tool_input_version",
        "receipt_ref",
        "response_ref",
    }
)

#: Carried verbatim into every readback.  These are asserted, not assumed: the
#: projection has no code path that could make any of them true.
REPORTING_GUARANTEES: dict[str, object] = {
    "recomputes_metrics": False,
    "recomputes_independence": False,
    "recomputes_conflicts": False,
    "recomputes_eligibility": False,
    "recomputes_genome_diff": False,
    "traverses_private_graph": False,
    "refreshes_formal_currency": False,
    "grants_eligibility": False,
    "invalidates_downstream": False,
    "scanned_full_history": False,
    "mlflow_deployment": "none",
}


class CurrencyRefusal(ContextAssemblyFailure):
    """A malformed or self-contradictory currency / projection declaration.

    As in #397-#399, an honest "this is only needs_review", "this refresh is not
    owner evidence" or "you are not currently authorized" is *not* an exception.
    Those are public, readable records with an explicit outcome.
    """


class SourceCurrencyReadModel(Protocol):
    """The upstream, owner-published source / correction / currency read model.

    The real read model is owned outside this repository (#392 publishes the
    comparability facts it rests on).  Three capabilities are named separately
    because they answer three different questions and must never be conflated:
    the lineage graph says what *could* be affected, a correction says what the
    owner changed and when the system learned it, and a currency fact says what
    the owner formally believes about one statement right now.
    """

    def lineage(self) -> Mapping[str, object]:
        """The complete bounded public lineage graph, as declared by its owner."""

    def corrections(self) -> Sequence[Mapping[str, object]]:
        """Every published source correction, append-only, newest last."""

    def currency_facts(self) -> Sequence[Mapping[str, object]]:
        """Every published formal-currency fact, append-only, newest last."""


@dataclass(frozen=True, slots=True)
class LineageEdge:
    """One declared dependency hop.  ``known`` false is an *unknown* dependency."""

    statement_id: str
    relationship: str
    known: bool

    @classmethod
    def parse(cls, value: object, label: str) -> LineageEdge:
        item = _mapping(value, label)
        _fields_subset(item, _EDGE_FIELDS, label)
        return cls(
            statement_id=_token(item.get("statement_id"), f"{label}.statement_id"),
            relationship=_token(item.get("relationship"), f"{label}.relationship"),
            known=_flag(item.get("known"), f"{label}.known"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "statement_id": self.statement_id,
            "relationship": self.relationship,
            "known": self.known,
        }

    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class LineageNode:
    """One public statement, its declared dependencies and its applicability conditions."""

    statement_id: str
    record_type: str
    depends_on: tuple[LineageEdge, ...]
    conditions_known: bool
    conditions: tuple[str, ...]

    @classmethod
    def parse(cls, value: object, index: int) -> LineageNode:
        label = f"lineage.nodes[{index}]"
        item = _mapping(value, label)
        _fields_subset(item, _NODE_FIELDS, label)
        edges: dict[str, LineageEdge] = {}
        for edge_index, raw in enumerate(_list(item.get("depends_on", []), f"{label}.depends_on")):
            edge = LineageEdge.parse(raw, f"{label}.depends_on[{edge_index}]")
            # A repeated edge is an allowed-equivalent representation of the same
            # graph, exactly as in #395/#397: deduplicate before anything reads it.
            edges.setdefault(edge.digest(), edge)
        raw_conditions = _mapping(item.get("conditions"), f"{label}.conditions")
        _fields_subset(raw_conditions, _CONDITION_FIELDS, f"{label}.conditions")
        known = _flag(raw_conditions.get("known"), f"{label}.conditions.known")
        values = _tokens(
            raw_conditions.get("values", []), f"{label}.conditions.values", empty=True
        )
        if not known and values:
            raise CurrencyRefusal(f"{label}.conditions cannot be unknown and enumerated")
        return cls(
            statement_id=_token(item.get("statement_id"), f"{label}.statement_id"),
            record_type=_token(item.get("record_type"), f"{label}.record_type"),
            depends_on=tuple(edge for _key, edge in sorted(edges.items())),
            conditions_known=known,
            conditions=values,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "statement_id": self.statement_id,
            "record_type": self.record_type,
            "depends_on": [edge.as_dict() for edge in self.depends_on],
            "conditions": {"known": self.conditions_known, "values": list(self.conditions)},
        }


@dataclass(frozen=True, slots=True)
class PublicLineageGraph:
    """The bounded public lineage graph.  ``complete`` is the owner's own claim."""

    complete: bool
    nodes: tuple[LineageNode, ...]

    @classmethod
    def parse(cls, value: object) -> PublicLineageGraph:
        item = _mapping(value, "lineage")
        _fields_subset(item, _GRAPH_FIELDS, "lineage")
        nodes = tuple(
            LineageNode.parse(raw, index)
            for index, raw in enumerate(_list(item.get("nodes", []), "lineage.nodes"))
        )
        ids = [node.statement_id for node in nodes]
        if len(ids) != len(set(ids)):
            raise CurrencyRefusal("lineage statement ids are not unique")
        return cls(
            complete=_flag(item.get("complete"), "lineage.complete"),
            nodes=tuple(sorted(nodes, key=lambda node: node.statement_id)),
        )

    def as_dict(self) -> dict[str, object]:
        return {"complete": self.complete, "nodes": [node.as_dict() for node in self.nodes]}

    def dependents(self) -> dict[str, tuple[tuple[str, bool], ...]]:
        """Reverse adjacency: statement -> ((dependent_id, edge_known), ...).

        The forward edges are what the owner publishes; impact travels the other
        way.  The reversal is built once, in canonical order, so the traversal
        order is a function of the declared graph alone.
        """

        reverse: dict[str, list[tuple[str, bool]]] = {}
        for node in self.nodes:
            for edge in node.depends_on:
                reverse.setdefault(edge.statement_id, []).append((node.statement_id, edge.known))
        return {key: tuple(sorted(set(value))) for key, value in reverse.items()}

    def undeclared_edge_targets(self) -> tuple[str, ...]:
        declared = {node.statement_id for node in self.nodes}
        missing = {
            edge.statement_id
            for node in self.nodes
            for edge in node.depends_on
            if edge.statement_id not in declared
        }
        return tuple(sorted(missing))


@dataclass(frozen=True, slots=True)
class SourceCorrection:
    """One owner-published correction.

    ``applicable_at`` is when the corrected fact applies to the world;
    ``system_known_at`` is when this system learned it.  They are separate
    fields on purpose: only the second one decides what a knowledge cutoff sees.
    """

    correction_id: str
    target_statement_id: str
    kind: CorrectionKind
    applicable_at: str
    system_known_at: str
    provenance_ref: str
    precise_conditions: tuple[str, ...]

    @classmethod
    def parse(cls, value: object, label: str) -> SourceCorrection:
        item = _mapping(value, label)
        _fields_subset(item, _CORRECTION_FIELDS, label)
        kind = _token(item.get("kind"), f"{label}.kind")
        if kind not in _CORRECTION_KINDS:
            raise CurrencyRefusal(f"{label}.kind is invalid: {kind}")
        return cls(
            correction_id=_token(item.get("correction_id"), f"{label}.correction_id"),
            target_statement_id=_token(
                item.get("target_statement_id"), f"{label}.target_statement_id"
            ),
            kind=kind,  # type: ignore[arg-type]
            applicable_at=_token(item.get("applicable_at"), f"{label}.applicable_at"),
            system_known_at=_token(item.get("system_known_at"), f"{label}.system_known_at"),
            provenance_ref=_token(item.get("provenance_ref"), f"{label}.provenance_ref"),
            precise_conditions=_tokens(
                item.get("precise_conditions", []), f"{label}.precise_conditions", empty=True
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "correction_id": self.correction_id,
            "target_statement_id": self.target_statement_id,
            "kind": self.kind,
            "applicable_at": self.applicable_at,
            "system_known_at": self.system_known_at,
            "provenance_ref": self.provenance_ref,
            "precise_conditions": list(self.precise_conditions),
        }


@dataclass(frozen=True, slots=True)
class CurrencyFact:
    """One owner-published formal-currency fact about one statement."""

    fact_id: str
    statement_id: str
    state: CurrencyState
    applicable_at: str
    system_known_at: str
    owner_evidence_ref: str
    provenance_ref: str

    @classmethod
    def parse(cls, value: object, label: str) -> CurrencyFact:
        item = _mapping(value, label)
        _fields_subset(item, _FACT_FIELDS, label)
        state = _token(item.get("state"), f"{label}.state")
        if state not in CURRENCY_STATES:
            raise CurrencyRefusal(f"{label}.state is invalid: {state}")
        return cls(
            fact_id=_token(item.get("fact_id"), f"{label}.fact_id"),
            statement_id=_token(item.get("statement_id"), f"{label}.statement_id"),
            state=state,  # type: ignore[arg-type]
            applicable_at=_token(item.get("applicable_at"), f"{label}.applicable_at"),
            system_known_at=_token(item.get("system_known_at"), f"{label}.system_known_at"),
            owner_evidence_ref=_token(
                item.get("owner_evidence_ref"), f"{label}.owner_evidence_ref"
            ),
            provenance_ref=_token(item.get("provenance_ref"), f"{label}.provenance_ref"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "fact_id": self.fact_id,
            "statement_id": self.statement_id,
            "state": self.state,
            "applicable_at": self.applicable_at,
            "system_known_at": self.system_known_at,
            "owner_evidence_ref": self.owner_evidence_ref,
            "provenance_ref": self.provenance_ref,
        }


@dataclass(frozen=True, slots=True)
class CurrencyStatus:
    """What Reporting may say about one statement, and where it came from."""

    statement_id: str
    state: CurrencyState
    as_known_at: str | None
    applicable_at: str | None
    owner_evidence_ref: str | None
    provenance: tuple[str, ...]

    @property
    def usable_as_current_evidence(self) -> bool:
        return self.state in _USABLE_STATES

    def as_dict(self) -> dict[str, object]:
        return {
            "statement_id": self.statement_id,
            "state": self.state,
            "as_known_at": self.as_known_at,
            "applicable_at": self.applicable_at,
            "owner_evidence_ref": self.owner_evidence_ref,
            "provenance": list(self.provenance) if self.provenance else ["unknown"],
            "usable_as_current_evidence": self.usable_as_current_evidence,
            "state_contract": CURRENCY_STATE_CONTRACT_ID,
            "state_contract_version": CURRENCY_STATE_CONTRACT_VERSION,
        }


@dataclass(frozen=True, slots=True)
class ImpactAssessment:
    """Where a correction *might* reach, and where the answer is honestly unknown."""

    correction_id: str
    target_statement_id: str
    states: tuple[tuple[str, ImpactState], ...]
    codes: tuple[str, ...]
    graph_complete: bool
    budget: int

    def by_state(self, state: ImpactState) -> tuple[str, ...]:
        return tuple(sorted(name for name, value in self.states if value == state))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": IMPACT_ASSESSMENT_SCHEMA,
            "correction_id": self.correction_id,
            "target_statement_id": self.target_statement_id,
            "potentially_affected": list(self.by_state("potentially_affected")),
            "needs_review": list(self.by_state("needs_review")),
            "not_affected": list(self.by_state("not_affected")),
            "codes": list(self.codes),
            "graph_complete": self.graph_complete,
            "budget": self.budget,
            "traversal": "bounded_explicit_stack_dfs",
            # A correction marks potential impact.  Only the owner's new
            # evidence or decision changes a formal currency state.
            "invalidates_downstream": False,
            "blanket_invalidation": False,
            "refreshes_formal_currency": False,
        }


@dataclass(frozen=True, slots=True)
class CurrencyRefreshOutcome:
    """Whether a proposed refresh is owner evidence, and therefore whether it counts."""

    statement_id: str
    refreshed: bool
    basis: RefreshBasis
    reason: str
    resulting_state: CurrencyState | None

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": CURRENCY_REFRESH_SCHEMA,
            "statement_id": self.statement_id,
            "refreshed": self.refreshed,
            "basis": self.basis,
            "reason": self.reason,
            "resulting_state": self.resulting_state,
            "grants_eligibility": False,
        }


@dataclass(frozen=True, slots=True)
class SourceCurrencyView:
    """A frozen, canonical read of the owner's public correction / currency facts."""

    lineage: PublicLineageGraph
    corrections: tuple[SourceCorrection, ...]
    currency_facts: tuple[CurrencyFact, ...]

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> SourceCurrencyView:
        item = _mapping(value, "currency view")
        _fields_subset(item, _VIEW_FIELDS, "currency view")
        if item.get("schema") != CURRENCY_VIEW_SCHEMA:
            raise CurrencyRefusal("currency view schema is invalid")
        corrections = tuple(
            SourceCorrection.parse(raw, f"corrections[{index}]")
            for index, raw in enumerate(_list(item.get("corrections", []), "corrections"))
        )
        ids = [item_.correction_id for item_ in corrections]
        if len(ids) != len(set(ids)):
            raise CurrencyRefusal("correction ids are not unique")
        facts = tuple(
            CurrencyFact.parse(raw, f"currency_facts[{index}]")
            for index, raw in enumerate(_list(item.get("currency_facts", []), "currency_facts"))
        )
        fact_ids = [fact.fact_id for fact in facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise CurrencyRefusal("currency fact ids are not unique")
        return cls(
            lineage=PublicLineageGraph.parse(item.get("lineage")),
            corrections=tuple(sorted(corrections, key=lambda entry: entry.correction_id)),
            currency_facts=tuple(sorted(facts, key=lambda fact: fact.fact_id)),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": CURRENCY_VIEW_SCHEMA,
            "lineage": self.lineage.as_dict(),
            "corrections": [entry.as_dict() for entry in self.corrections],
            "currency_facts": [fact.as_dict() for fact in self.currency_facts],
        }

    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_of(self, knowledge_cutoff: str) -> SourceCurrencyView:
        """The view as the system knew it at ``knowledge_cutoff``.

        The filter is on ``system_known_at`` alone.  ``applicable_at`` may be far
        in the past — a correction about 2019 data published today is still
        invisible to a snapshot taken yesterday — which is exactly what stops
        hindsight from backfilling an old knowledge snapshot.
        """

        cutoff = _token(knowledge_cutoff, "knowledge_cutoff")
        return SourceCurrencyView(
            lineage=self.lineage,
            corrections=tuple(
                entry for entry in self.corrections if entry.system_known_at <= cutoff
            ),
            currency_facts=tuple(
                fact for fact in self.currency_facts if fact.system_known_at <= cutoff
            ),
        )

    def append_correction(self, value: Mapping[str, object]) -> SourceCurrencyView:
        """Append one published correction, returning a *new* view.

        The receiver is a frozen dataclass and is never mutated, so a correction
        published today cannot reach into a Context frozen yesterday.
        """

        correction = SourceCorrection.parse(value, "correction")
        existing = {entry.correction_id for entry in self.corrections}
        if correction.correction_id in existing:
            raise CurrencyRefusal(f"correction already published: {correction.correction_id}")
        return SourceCurrencyView(
            lineage=self.lineage,
            corrections=tuple(
                sorted((*self.corrections, correction), key=lambda entry: entry.correction_id)
            ),
            currency_facts=self.currency_facts,
        )

    def correction(self, correction_id: str) -> SourceCorrection:
        for entry in self.corrections:
            if entry.correction_id == correction_id:
                return entry
        raise CurrencyRefusal(f"correction is not published in this view: {correction_id}")

    def status(self, statement_id: str) -> CurrencyStatus:
        """The owner's latest published state for one statement, or ``unknown``.

        "Latest" is by the system-known time and then the fact id, both of which
        are public, so two readers of the same view always agree.
        """

        candidates = [fact for fact in self.currency_facts if fact.statement_id == statement_id]
        if not candidates:
            return CurrencyStatus(
                statement_id=statement_id,
                state="unknown",
                as_known_at=None,
                applicable_at=None,
                owner_evidence_ref=None,
                provenance=(),
            )
        latest = max(candidates, key=lambda fact: (fact.system_known_at, fact.fact_id))
        return CurrencyStatus(
            statement_id=statement_id,
            state=latest.state,
            as_known_at=latest.system_known_at,
            applicable_at=latest.applicable_at,
            owner_evidence_ref=latest.owner_evidence_ref,
            provenance=(latest.provenance_ref,),
        )


def read_source_currency(model: SourceCurrencyReadModel) -> SourceCurrencyView:
    """Consume the upstream read model once, and freeze what it returned.

    Nothing downstream ever calls the seam again: the frozen view is the only
    input to impact assessment and to the Reporting projection, so a projection
    is reproducible from public facts without the upstream service.
    """

    lineage = dict(_mapping(model.lineage(), "read model lineage"))
    corrections = [
        dict(_mapping(item, "read model correction")) for item in model.corrections()
    ]
    facts = [
        dict(_mapping(item, "read model currency fact")) for item in model.currency_facts()
    ]
    return SourceCurrencyView.parse(
        {
            "schema": CURRENCY_VIEW_SCHEMA,
            "lineage": lineage,
            "corrections": corrections,
            "currency_facts": facts,
        }
    )


def assess_correction_impact(
    view: SourceCurrencyView,
    correction_id: str,
    *,
    budget: int | None = None,
) -> ImpactAssessment:
    """Locate what a correction *might* have reached, over the public lineage graph.

    The walk is a bounded explicit-stack DFS over the reversed public edges, the
    same traversal shape #395 and #397 already use — deliberately not NetworkX,
    which #381's shared policy scopes to Apex-internal bounded graph algorithms.

    Three things can narrow or widen the answer, and each is explicit:

    * The owner's *precise conditions* may prove a node out of scope.  A node
      whose declared conditions are disjoint from the correction's conditions is
      ``not_affected``, and impact does not propagate through it.
    * An *unknown* dependency edge, an undeclared node, an incomplete graph or an
      exhausted budget yields ``needs_review``, which then travels downstream.
    * Nothing ever yields ``invalidated``.  Only the owner's new evidence or
      decision changes a formal currency state.
    """

    correction = view.correction(correction_id)
    limit = _bounded_int(
        budget, "impact budget", MAX_IMPACT_BUDGET, default=DEFAULT_IMPACT_BUDGET
    )
    graph = view.lineage
    declared = {node.statement_id: node for node in graph.nodes}
    dependents = graph.dependents()
    codes: set[str] = set()
    states: dict[str, ImpactState] = {}
    if correction.target_statement_id not in declared:
        codes.add("correction_target_not_in_public_lineage")
    undeclared = set(graph.undeclared_edge_targets())
    if undeclared:
        codes.add("lineage_graph_incomplete")
    if not graph.complete:
        codes.add("lineage_graph_not_declared_complete")

    def _resolve(node_id: str, inherited_review: bool) -> ImpactState:
        node = declared.get(node_id)
        if node is None:
            return "needs_review"
        if inherited_review:
            return "needs_review"
        if not correction.precise_conditions:
            return "potentially_affected"
        if not node.conditions_known:
            # The correction is precise, but this statement does not say what it
            # applies to.  That is uncertainty, not exclusion and not invalidity.
            return "needs_review"
        if set(node.conditions) & set(correction.precise_conditions):
            return "potentially_affected"
        return "not_affected"

    # Explicit-stack DFS; each frame is [node_id, review_flag, dependents, index].
    # The correction's own target is what the owner corrected, so it is affected
    # by construction; the precise conditions narrow its *dependents*, not it.
    root = correction.target_statement_id
    states[root] = "needs_review" if root not in declared else "potentially_affected"
    frames: list[list[Any]] = [[root, states[root] == "needs_review", dependents.get(root, ()), 0]]
    visits = 0
    exhausted = False
    while frames:
        frame = frames[-1]
        _node_id, review, edges, index = frame
        if index >= len(edges):
            frames.pop()
            continue
        frame[3] = index + 1
        child_id, edge_known = edges[index]
        visits += 1
        if visits > limit:
            codes.add("impact_budget_exhausted")
            exhausted = True
            break
        child_review = review or not edge_known or child_id not in declared
        if not edge_known:
            codes.add("unknown_dependency")
        resolved = _resolve(child_id, child_review)
        previous = states.get(child_id)
        merged = _merge_impact(previous, resolved)
        if previous == merged and previous is not None:
            # Already settled at least as strongly on another path; a re-walk
            # cannot make the answer weaker, so the subtree is not re-entered.
            continue
        states[child_id] = merged
        if merged == "not_affected":
            # Narrowed out by the owner's precise conditions: impact does not
            # travel through it.  A descendant reachable another way is still
            # reached by that other path.
            continue
        frames.append([child_id, merged == "needs_review", dependents.get(child_id, ()), 0])
    # A declared node the walk never reached is out of the correction's reach on
    # this graph.  That is a statement about the graph, so it only survives while
    # the graph is provably complete and the walk actually finished.
    for node in graph.nodes:
        states.setdefault(node.statement_id, "not_affected")
    if exhausted or not graph.complete or undeclared or root not in declared:
        # The answer cannot be proved negative on a graph that is not provably
        # complete, so "not affected" is downgraded rather than asserted.
        for statement_id, current in list(states.items()):
            if current == "not_affected":
                states[statement_id] = "needs_review"
    return ImpactAssessment(
        correction_id=correction.correction_id,
        target_statement_id=correction.target_statement_id,
        states=tuple(sorted(states.items())),
        codes=tuple(sorted(codes)),
        graph_complete=graph.complete and not undeclared,
        budget=limit,
    )


def _merge_impact(previous: ImpactState | None, resolved: ImpactState) -> ImpactState:
    """Combine two paths' answers.  Uncertainty and impact both win over exclusion."""

    if previous is None:
        return resolved
    order = {"not_affected": 0, "needs_review": 1, "potentially_affected": 2}
    return previous if order[previous] >= order[resolved] else resolved


def refresh_formal_currency(
    view: SourceCurrencyView,
    request: Mapping[str, object],
) -> CurrencyRefreshOutcome:
    """Decide whether a proposed currency refresh is owner evidence.

    A new summary, a new explanation or a discovery-only review re-reads material
    that already exists.  Re-reading is not new evidence, so it never refreshes
    formal currency and never grants eligibility — that is the whole point of
    keeping the basis in the request instead of inferring it from the payload.
    """

    item = _mapping(request, "currency refresh")
    _fields_subset(item, _REFRESH_FIELDS, "currency refresh")
    if item.get("schema") != CURRENCY_REFRESH_SCHEMA:
        raise CurrencyRefusal("currency refresh schema is invalid")
    basis = _token(item.get("basis"), "currency refresh basis")
    if basis not in _REFRESHING_BASES | _NON_REFRESHING_BASES:
        raise CurrencyRefusal(f"currency refresh basis is invalid: {basis}")
    statement_id = _token(item.get("statement_id"), "currency refresh statement_id")
    proposed = _token(item.get("proposed_state"), "currency refresh proposed_state")
    if proposed not in CURRENCY_STATES:
        raise CurrencyRefusal(f"currency refresh proposed_state is invalid: {proposed}")
    raw_evidence = item.get("owner_evidence_ref")
    evidence = None if raw_evidence is None else _token(raw_evidence, "owner_evidence_ref")
    if basis in _NON_REFRESHING_BASES:
        return CurrencyRefreshOutcome(
            statement_id=statement_id,
            refreshed=False,
            basis=basis,  # type: ignore[arg-type]
            reason=f"{basis}_is_not_owner_evidence",
            resulting_state=view.status(statement_id).state,
        )
    if evidence is None:
        return CurrencyRefreshOutcome(
            statement_id=statement_id,
            refreshed=False,
            basis=basis,  # type: ignore[arg-type]
            reason="owner_evidence_ref_missing",
            resulting_state=view.status(statement_id).state,
        )
    return CurrencyRefreshOutcome(
        statement_id=statement_id,
        refreshed=True,
        basis=basis,  # type: ignore[arg-type]
        reason="owner_evidence_published",
        resulting_state=proposed,  # type: ignore[arg-type]
    )


@dataclass(frozen=True, slots=True)
class ExposureLink:
    """#396's real Context / envelope / replay-coverage linkage, carried verbatim."""

    action_key: str
    context_identity: str
    envelope_digest: str
    envelope_content_ref: str | None
    replay_coverage: ReplayCoverage
    provider_request_id: str
    template_version: str
    tool_input_version: str
    receipt_ref: str | None
    response_ref: str | None

    @classmethod
    def parse(cls, value: object) -> ExposureLink | None:
        if value is None:
            return None
        item = _mapping(value, "exposure")
        _fields_subset(item, _EXPOSURE_FIELDS, "exposure")
        coverage = _token(item.get("replay_coverage"), "exposure.replay_coverage")
        if coverage not in _COVERAGES:
            raise CurrencyRefusal(f"exposure.replay_coverage is invalid: {coverage}")
        content_ref = item.get("envelope_content_ref")
        reference = None if content_ref is None else _token(content_ref, "exposure.content_ref")
        if coverage == "full" and reference is None:
            raise CurrencyRefusal("exposure replay_coverage cannot be full without a stored ref")
        if coverage == "none" and reference is not None:
            raise CurrencyRefusal("exposure replay_coverage is inconsistent with a stored ref")
        digest = item.get("envelope_digest")
        if not isinstance(digest, str) or _SAFE_DIGEST.fullmatch(digest) is None:
            raise CurrencyRefusal("exposure.envelope_digest is invalid")
        identity = item.get("context_identity")
        if not isinstance(identity, str) or _SAFE_DIGEST.fullmatch(identity) is None:
            raise CurrencyRefusal("exposure.context_identity is invalid")
        return cls(
            action_key=_token(item.get("action_key"), "exposure.action_key"),
            context_identity=identity,
            envelope_digest=digest,
            envelope_content_ref=reference,
            replay_coverage=coverage,  # type: ignore[arg-type]
            provider_request_id=_token(
                item.get("provider_request_id"), "exposure.provider_request_id"
            ),
            template_version=_token(item.get("template_version"), "exposure.template_version"),
            tool_input_version=_token(
                item.get("tool_input_version"), "exposure.tool_input_version"
            ),
            receipt_ref=_optional(item.get("receipt_ref"), "exposure.receipt_ref"),
            response_ref=_optional(item.get("response_ref"), "exposure.response_ref"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "action_key": self.action_key,
            "context_identity": self.context_identity,
            "envelope_digest": self.envelope_digest,
            "envelope_content_ref": self.envelope_content_ref,
            "replay_coverage": self.replay_coverage,
            "provider_request_id": self.provider_request_id,
            "template_version": self.template_version,
            "tool_input_version": self.tool_input_version,
            "receipt_ref": self.receipt_ref,
            "response_ref": self.response_ref,
        }

    def public_view(self) -> dict[str, object]:
        return {
            **self.as_dict(),
            # A digest names the delivery; it is never the delivered body.
            "full_content_available": self.replay_coverage == "full",
            "digest_is_not_content": True,
        }


@dataclass(frozen=True, slots=True)
class ReportingProjection:
    """A read-only, versioned research brief / status projection for Reporting."""

    context: ResearchContext
    view: SourceCurrencyView
    knowledge_cutoff: str
    correction_id: str | None
    exposure: ExposureLink | None
    identity: str

    def public_record(self) -> dict[str, object]:
        """Everything needed to rebuild this projection, and nothing else."""

        return {
            "schema": REPORTING_RECORD_SCHEMA,
            "projection_identity": self.identity,
            "declaration": {
                "schema": REPORTING_DECLARATION_SCHEMA,
                "context_record": self.context.public_record(),
                "currency": self.view.as_dict(),
                "knowledge_cutoff": self.knowledge_cutoff,
                "correction_id": self.correction_id,
                "exposure": None if self.exposure is None else self.exposure.as_dict(),
            },
        }

    def impact(self) -> ImpactAssessment | None:
        if self.correction_id is None:
            return None
        return assess_correction_impact(self.visible_view(), self.correction_id)

    def visible_view(self) -> SourceCurrencyView:
        return self.view.as_of(self.knowledge_cutoff)

    def statuses(self) -> tuple[CurrencyStatus, ...]:
        visible = self.visible_view()
        return tuple(
            visible.status(source_id) for source_id in self.context.included_source_ids
        )

    def readback(self) -> dict[str, object]:
        """The public Reporting readback.  Display only; nothing here is computed."""

        assessment = self.impact()
        brief = self.context.brief.as_dict()
        fields = dict(self.context.brief.fields)
        statuses = self.statuses()
        return {
            "schema": REPORTING_READBACK_SCHEMA,
            "projection_identity": self.identity,
            "template_id": BRIEF_TEMPLATE_ID,
            "knowledge_cutoff": self.knowledge_cutoff,
            "currency_state_contract": {
                "contract_id": CURRENCY_STATE_CONTRACT_ID,
                "version": CURRENCY_STATE_CONTRACT_VERSION,
                "digest": CURRENCY_STATE_CONTRACT_DIGEST,
                "states": list(CURRENCY_STATES),
            },
            "context": {
                "context_identity": self.context.identity,
                "mode": self.context.declaration.mode,
                "snapshot": self.context.declaration.snapshot.as_dict(),
                "policy": self.context.declaration.policy.as_dict(),
                "coverage": self.context.coverage.as_dict(),
            },
            "published_brief": brief,
            # Component differences come from the owner's already-published
            # comparison, verbatim.  No diff is computed here.
            "genome_compare": (
                None
                if self.context.declaration.genome_compare is None
                else self.context.declaration.genome_compare.as_dict()
            ),
            "source_currency": [status.as_dict() for status in statuses],
            "unusable_as_current_evidence": [
                status.statement_id for status in statuses if not status.usable_as_current_evidence
            ],
            "correction_impact": None if assessment is None else assessment.as_dict(),
            "published_corrections": [
                entry.as_dict() for entry in self.visible_view().corrections
            ],
            "evidence_gaps": _sourced(fields["evidence_gaps"]),
            "candidate_next_steps": _sourced(fields["candidate_next_steps"]),
            "coverage_limitations": _sourced(fields["coverage_limitations"]),
            "exposure": None if self.exposure is None else self.exposure.public_view(),
            "reporting_guarantees": dict(REPORTING_GUARANTEES),
        }


def freeze_reporting_projection(value: Mapping[str, object]) -> ReportingProjection:
    """Freeze a read-only Reporting projection over already-published facts.

    The Context is rebuilt from its own public record rather than handed in as an
    object, so the projection can only ever show a Context that reproduces its
    recorded identity.  The exposure link must name that same identity: a
    projection cannot pair one Context's brief with another delivery's envelope.
    """

    item = _mapping(value, "reporting projection")
    _fields_subset(item, _REPORTING_FIELDS, "reporting projection")
    if item.get("schema") != REPORTING_DECLARATION_SCHEMA:
        raise CurrencyRefusal("reporting projection schema is invalid")
    context = reconstruct_research_context(
        _mapping(item.get("context_record"), "reporting projection context_record")
    )
    view = SourceCurrencyView.parse(
        _mapping(item.get("currency"), "reporting projection currency")
    )
    cutoff = _token(item.get("knowledge_cutoff"), "reporting projection knowledge_cutoff")
    raw_correction = item.get("correction_id")
    correction_id = (
        None if raw_correction is None else _token(raw_correction, "correction_id")
    )
    if correction_id is not None:
        # Referencing a correction the declared cutoff cannot see would be
        # hindsight entering through the back door.
        view.as_of(cutoff).correction(correction_id)
    exposure = ExposureLink.parse(item.get("exposure"))
    if exposure is not None and exposure.context_identity != context.identity:
        raise CurrencyRefusal("exposure link does not name the projected Context")
    identity = _digest(
        {
            "schema": REPORTING_DECLARATION_SCHEMA,
            "currency_state_contract": CURRENCY_STATE_CONTRACT_DIGEST,
            "context_identity": context.identity,
            "currency_digest": view.digest(),
            "knowledge_cutoff": cutoff,
            "correction_id": correction_id,
            "exposure": None if exposure is None else exposure.as_dict(),
        }
    )
    return ReportingProjection(
        context=context,
        view=view,
        knowledge_cutoff=cutoff,
        correction_id=correction_id,
        exposure=exposure,
        identity=identity,
    )


def reconstruct_reporting_projection(record: Mapping[str, object]) -> ReportingProjection:
    """Rebuild a projection from its public record alone.

    There is no display store to consult.  Deleting the projection loses
    nothing: the declaration replays through the same freeze, and the rebuilt
    identity must equal the recorded one.
    """

    item = _mapping(record, "reporting record")
    _fields_subset(item, {"schema", "projection_identity", "declaration"}, "reporting record")
    if item.get("schema") != REPORTING_RECORD_SCHEMA:
        raise CurrencyRefusal("reporting record schema is invalid")
    recorded = item.get("projection_identity")
    if not isinstance(recorded, str) or _SAFE_DIGEST.fullmatch(recorded) is None:
        raise CurrencyRefusal("reporting record identity is invalid")
    rebuilt = freeze_reporting_projection(
        _mapping(item.get("declaration"), "reporting record declaration")
    )
    if rebuilt.identity != recorded:
        raise CurrencyRefusal("reporting record does not reproduce its identity")
    return rebuilt


def deliver_reporting_projection(
    projection: ReportingProjection,
    visibility_request: Mapping[str, object],
) -> dict[str, object]:
    """Hand the projection to Reporting only under *current* authorization.

    The policy recorded when the Context was frozen explains what was admitted
    then; it never restores access now.  A currently unauthorized reader gets a
    fixed refusal that carries no identity, no counts and no per-source reasons,
    and the projection object it was refused for is not touched.
    """

    decision = evaluate_visibility_request(visibility_request)
    if not decision.deliverable:
        return {
            "schema": REPORTING_READBACK_SCHEMA,
            "delivery": "blocked",
            "reason": "current_authorization_denied",
            "projection_identity": None,
            "grants_eligibility": False,
        }
    return {**projection.readback(), "delivery": "delivered"}


def _sourced(field: Mapping[str, object]) -> dict[str, object]:
    """Every entry keeps an owner provenance, or says ``unknown``.  Never neither."""

    entries = field.get("entries")
    if not isinstance(entries, list):
        raise CurrencyRefusal("brief field is malformed")
    sourced: list[dict[str, object]] = []
    for entry in entries:
        item = dict(_mapping(entry, "brief entry"))
        provenance = item.get("provenance")
        if not isinstance(provenance, list) or not provenance:
            item["provenance"] = ["unknown"]
        sourced.append(item)
    return {"state": field.get("state"), "entries": sourced}


def _optional(value: object, label: str) -> str | None:
    return None if value is None else _token(value, label)


__all__ = [
    "CURRENCY_REFRESH_SCHEMA",
    "CURRENCY_STATES",
    "CURRENCY_STATE_CONTRACT",
    "CURRENCY_STATE_CONTRACT_DIGEST",
    "CURRENCY_STATE_CONTRACT_ID",
    "CURRENCY_STATE_CONTRACT_VERSION",
    "CURRENCY_VIEW_SCHEMA",
    "DEFAULT_IMPACT_BUDGET",
    "IMPACT_ASSESSMENT_SCHEMA",
    "IMPACT_STATES",
    "MAX_IMPACT_BUDGET",
    "REPORTING_DECLARATION_SCHEMA",
    "REPORTING_GUARANTEES",
    "REPORTING_READBACK_SCHEMA",
    "REPORTING_RECORD_SCHEMA",
    "CurrencyFact",
    "CurrencyRefreshOutcome",
    "CurrencyRefusal",
    "CurrencyStatus",
    "ExposureLink",
    "ImpactAssessment",
    "LineageEdge",
    "LineageNode",
    "PublicLineageGraph",
    "ReportingProjection",
    "SourceCorrection",
    "SourceCurrencyReadModel",
    "SourceCurrencyView",
    "assess_correction_impact",
    "deliver_reporting_projection",
    "freeze_reporting_projection",
    "read_source_currency",
    "reconstruct_reporting_projection",
    "refresh_formal_currency",
]
