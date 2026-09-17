"""Deterministic pagination, snapshot integrity and bounded trimming for a Context.

#397 froze a bounded research Context: a declaration, an inclusion / exclusion
manifest, five coverage states and a rebuildable identity.  It deliberately left
one seam open — its readback says so verbatim, ``pagination_owner:
"issue-398"`` — because it takes the *declared* sources on faith.  It proves
which sources a Context relies on; it cannot prove that the store actually
handed them over.

This module closes that seam.  Before anything is read, a ``RetrievalPlan`` is
frozen alongside the #397 declaration: the ordering key, the page size, the page
budget, the record budget, the opening cursor and the trimming policy.  The
pages are then public evidence, replayed rather than re-fetched, and the
retrieval either proves the required scope was fully paged in or it refuses.

Four rules shape everything below.

**The required / optional split is fixed before the pages are looked at.**  The
inner #397 Context is frozen first, and its manifest roles are the only source
of "required".  A source cannot be demoted to optional after a page fails to
deliver it, because by then the roles are already part of a frozen identity.

**Fail closed inside the required scope.**  An invalidated cursor, an
out-of-sequence or unreachable page, a record that appears after the frozen
snapshot, an interrupted page, an unavailable index, an exhausted budget or a
required source the pages never delivered all produce a *refusal*.  None of them
is allowed to quietly shrink the target sample, swap in another source, or
reappear as an optional miss.

**"Not fully read" is never "does not exist."**  A chain that stopped early —
because the page budget ran out, or because the last page never said it was
exhausted — reports ``budget_exhausted``, not ``required_lineage_missing``.  The
genuine-absence state is reachable only from a chain that ran to an explicitly
exhausted page.  For the same reason an empty ``pages`` list is a malformed
declaration rather than a complete-empty result: a database returning no rows is
not a cross-request snapshot contract, and ``complete_empty`` must be earned by
an explicit terminal page.

**Trimming never buys room from a required item.**  The trimming unit stays
#397's: a conclusion together with its required support, counter-evidence and
limitations.  Here the same rule is applied one level down, to retrieved
records: optional records are dropped in frozen order until the record budget
fits, and if the required records alone do not fit, the retrieval refuses
instead of trimming them.

The nine retrieval states are frozen in ``RETRIEVAL_STATE_CONTRACT`` with a
version, and the contract's own digest takes part in the identity, so a renamed
or reordered state is a different Context rather than a silent relabelling.

What this module deliberately does not do: it opens no store, performs no query,
keeps no index, and never re-selects a "latest" result.  Reconstruction replays
the frozen public pages and nothing else.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .research_context import (
    ContextAssemblyFailure,
    ContextDeclaration,
    CoverageState,
    ResearchContext,
    _authorization_status,
    _bounded_int,
    _flag,
    freeze_research_context,
)
from .research_visibility import (
    _SAFE_DIGEST,
    _digest,
    _fields_subset,
    _list,
    _mapping,
    _token,
    evaluate_visibility_request,
)

PAGINATED_DECLARATION_SCHEMA = "quant-research.research-paginated-context-declaration.v1"
PAGINATED_RECORD_SCHEMA = "quant-research.research-paginated-context-record.v1"
PAGINATED_READBACK_SCHEMA = "quant-research.research-paginated-context-readback.v1"

#: The retrieval state contract.  Names are frozen here, not inferred from an
#: example payload, and the version travels with them.
RETRIEVAL_STATE_CONTRACT_ID = "quant-research.research-retrieval-state"
RETRIEVAL_STATE_CONTRACT_VERSION = "v1"

RetrievalState = Literal[
    "complete",
    "complete_empty",
    "optional_scope_not_exhausted",
    "cursor_invalidated",
    "snapshot_contaminated",
    "index_unavailable",
    "retrieval_interrupted",
    "budget_exhausted",
    "required_lineage_missing",
]

#: state -> (category, deliverable, the #397 coverage state it projects onto).
#: ``deliverable`` false means the Context is refused, never downgraded.
RETRIEVAL_STATE_CONTRACT: tuple[tuple[str, str, bool, str], ...] = (
    ("complete", "covered", True, "complete"),
    ("complete_empty", "covered", True, "complete_empty"),
    ("optional_scope_not_exhausted", "bounded", True, "optional_not_exhausted"),
    ("cursor_invalidated", "failure", False, "retrieval_failure"),
    ("snapshot_contaminated", "failure", False, "retrieval_failure"),
    ("index_unavailable", "failure", False, "retrieval_failure"),
    ("retrieval_interrupted", "failure", False, "retrieval_failure"),
    ("budget_exhausted", "failure", False, "required_incomplete"),
    ("required_lineage_missing", "failure", False, "required_incomplete"),
)
RETRIEVAL_STATES: tuple[str, ...] = tuple(state for state, _c, _d, _p in RETRIEVAL_STATE_CONTRACT)
_DELIVERABLE_STATES = frozenset(
    state for state, _c, deliverable, _p in RETRIEVAL_STATE_CONTRACT if deliverable
)
_COVERAGE_PROJECTION: dict[str, str] = {
    state: coverage for state, _c, _d, coverage in RETRIEVAL_STATE_CONTRACT
}
#: Worst first.  The effective coverage is never better than either input.
_COVERAGE_PRECEDENCE: tuple[str, ...] = (
    "retrieval_failure",
    "required_incomplete",
    "complete_empty",
    "optional_not_exhausted",
    "complete",
)


def _state_contract_dict() -> dict[str, object]:
    return {
        "contract_id": RETRIEVAL_STATE_CONTRACT_ID,
        "contract_version": RETRIEVAL_STATE_CONTRACT_VERSION,
        "states": [
            {
                "state": state,
                "category": category,
                "deliverable": deliverable,
                "coverage_projection": coverage,
            }
            for state, category, deliverable, coverage in RETRIEVAL_STATE_CONTRACT
        ],
    }


#: A rename, a reorder or a re-categorisation of any state changes this digest,
#: and the digest is part of every paginated Context identity.
RETRIEVAL_STATE_CONTRACT_DIGEST = _digest(_state_contract_dict())

MAX_PAGE_SIZE = 4096
MAX_PAGE_BUDGET = 4096
MAX_RECORD_BUDGET = 4096

PageStatus = Literal["ok", "interrupted", "index_unavailable"]
RecordDecision = Literal["retrieved", "trimmed", "excluded"]
PaginatedStatus = Literal["bounded", "refused"]

_PAGE_STATUSES = frozenset({"ok", "interrupted", "index_unavailable"})
_RECORD_REASONS = frozenset(
    {
        "declared_and_paged",
        "outside_declared_scope",
        "not_authorized",
        "optional_trimmed_by_policy",
    }
)
_FAILURE_DETAILS = frozenset(
    {
        "conflicting_page_for_cursor",
        "unreachable_page",
        "page_index_out_of_sequence",
        "page_over_declared_size",
        "cursor_cycle",
        "cursor_snapshot_mismatch",
        "cursor_ordering_mismatch",
        "record_ordering_violation",
        "record_after_snapshot_cutoff",
        "page_interrupted",
        "page_index_unavailable",
        "page_budget_exhausted",
        "record_budget_insufficient_for_required",
        "required_records_never_paged",
    }
)

_PAGINATED_FIELDS = frozenset({"schema", "context", "retrieval"})
_RETRIEVAL_FIELDS = frozenset({"plan", "pages"})
_PLAN_FIELDS = frozenset(
    {
        "retrieval_id",
        "ordering_key",
        "trimming_policy",
        "policy_version",
        "page_size",
        "page_budget",
        "record_budget",
        "cursor",
    }
)
_CURSOR_FIELDS = frozenset({"cursor_id", "snapshot_id", "ordering_key", "position", "page_index"})
_PAGE_FIELDS = frozenset(
    {"page_index", "cursor_in", "cursor_out", "status", "exhausted", "records"}
)
_RECORD_FIELDS = frozenset({"source_id", "sort_key", "published_at"})


class RetrievalRefusal(ContextAssemblyFailure):
    """A structurally malformed retrieval declaration.

    As in #397, an honest "the store did not deliver the required scope" is
    *not* an exception: it is a frozen, reconstructable paginated Context whose
    status is ``refused`` with an explicit state and detail list.
    """


@dataclass(frozen=True, slots=True)
class RetrievalCursor:
    cursor_id: str
    snapshot_id: str
    ordering_key: str
    position: str
    page_index: int

    @classmethod
    def parse(cls, value: object) -> RetrievalCursor:
        item = _mapping(value, "retrieval.plan.cursor")
        _fields_subset(item, _CURSOR_FIELDS, "retrieval.plan.cursor")
        index = item.get("page_index")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index <= MAX_PAGE_BUDGET
        ):
            raise RetrievalRefusal("retrieval.plan.cursor.page_index is invalid")
        return cls(
            cursor_id=_token(item.get("cursor_id"), "retrieval.plan.cursor.cursor_id"),
            snapshot_id=_token(item.get("snapshot_id"), "retrieval.plan.cursor.snapshot_id"),
            ordering_key=_token(item.get("ordering_key"), "retrieval.plan.cursor.ordering_key"),
            position=_token(item.get("position"), "retrieval.plan.cursor.position"),
            page_index=index,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "cursor_id": self.cursor_id,
            "snapshot_id": self.snapshot_id,
            "ordering_key": self.ordering_key,
            "position": self.position,
            "page_index": self.page_index,
        }


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    """Everything about *how* the store will be paged, frozen before it is."""

    retrieval_id: str
    ordering_key: str
    trimming_policy: str
    policy_version: str
    page_size: int
    page_budget: int
    record_budget: int
    cursor: RetrievalCursor

    @classmethod
    def parse(cls, value: object) -> RetrievalPlan:
        item = _mapping(value, "retrieval.plan")
        _fields_subset(item, _PLAN_FIELDS, "retrieval.plan")
        return cls(
            retrieval_id=_token(item.get("retrieval_id"), "retrieval.plan.retrieval_id"),
            ordering_key=_token(item.get("ordering_key"), "retrieval.plan.ordering_key"),
            trimming_policy=_token(item.get("trimming_policy"), "retrieval.plan.trimming_policy"),
            policy_version=_token(item.get("policy_version"), "retrieval.plan.policy_version"),
            page_size=_bounded_int(
                item.get("page_size"), "retrieval.plan.page_size", MAX_PAGE_SIZE, default=None
            ),
            page_budget=_bounded_int(
                item.get("page_budget"), "retrieval.plan.page_budget", MAX_PAGE_BUDGET, default=None
            ),
            record_budget=_bounded_int(
                item.get("record_budget"),
                "retrieval.plan.record_budget",
                MAX_RECORD_BUDGET,
                default=None,
            ),
            cursor=RetrievalCursor.parse(item.get("cursor")),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "retrieval_id": self.retrieval_id,
            "ordering_key": self.ordering_key,
            "trimming_policy": self.trimming_policy,
            "policy_version": self.policy_version,
            "page_size": self.page_size,
            "page_budget": self.page_budget,
            "record_budget": self.record_budget,
            "cursor": self.cursor.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class PageRecord:
    source_id: str
    sort_key: str
    published_at: str

    @classmethod
    def parse(cls, value: object, label: str) -> PageRecord:
        item = _mapping(value, label)
        _fields_subset(item, _RECORD_FIELDS, label)
        return cls(
            source_id=_token(item.get("source_id"), f"{label}.source_id"),
            sort_key=_token(item.get("sort_key"), f"{label}.sort_key"),
            published_at=_token(item.get("published_at"), f"{label}.published_at"),
        )

    def order(self) -> tuple[str, str]:
        return (self.sort_key, self.source_id)

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "sort_key": self.sort_key,
            "published_at": self.published_at,
        }


@dataclass(frozen=True, slots=True)
class RetrievalPage:
    """One public page of retrieval evidence, replayed rather than re-fetched."""

    page_index: int
    cursor_in: str
    cursor_out: str
    status: PageStatus
    exhausted: bool
    records: tuple[PageRecord, ...]

    @classmethod
    def parse(cls, value: object, index: int) -> RetrievalPage:
        label = f"retrieval.pages[{index}]"
        item = _mapping(value, label)
        _fields_subset(item, _PAGE_FIELDS, label)
        page_index = item.get("page_index")
        if (
            not isinstance(page_index, int)
            or isinstance(page_index, bool)
            or not 0 <= page_index <= MAX_PAGE_BUDGET
        ):
            raise RetrievalRefusal(f"{label}.page_index is invalid")
        status = _token(item.get("status"), f"{label}.status")
        if status not in _PAGE_STATUSES:
            raise RetrievalRefusal(f"{label}.status is invalid: {status}")
        records = tuple(
            PageRecord.parse(raw, f"{label}.records[{record_index}]")
            for record_index, raw in enumerate(_list(item.get("records", []), f"{label}.records"))
        )
        return cls(
            page_index=page_index,
            cursor_in=_token(item.get("cursor_in"), f"{label}.cursor_in"),
            cursor_out=_token(item.get("cursor_out"), f"{label}.cursor_out"),
            status=status,  # type: ignore[arg-type]
            exhausted=_flag(item.get("exhausted"), f"{label}.exhausted"),
            records=records,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "page_index": self.page_index,
            "cursor_in": self.cursor_in,
            "cursor_out": self.cursor_out,
            "status": self.status,
            "exhausted": self.exhausted,
            "records": [record.as_dict() for record in self.records],
        }

    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RetrievalEntry:
    """One retrieved record and what the frozen policy did with it."""

    source_id: str
    decision: RecordDecision
    reason: str
    role: Literal["required", "optional", "undeclared"]

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "decision": self.decision,
            "reason": self.reason,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    state: RetrievalState
    pages_read: int
    truncated: bool
    manifest: tuple[RetrievalEntry, ...]
    required_unseen: tuple[str, ...]
    optional_unseen: tuple[str, ...]
    trimmed: tuple[str, ...]
    failure_details: tuple[str, ...]

    @property
    def deliverable(self) -> bool:
        return self.state in _DELIVERABLE_STATES

    @property
    def withheld(self) -> bool:
        """Whether the protected side removed anything from the manifest."""

        return any(entry.reason == "not_authorized" for entry in self.manifest)

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "state_contract_id": RETRIEVAL_STATE_CONTRACT_ID,
            "state_contract_version": RETRIEVAL_STATE_CONTRACT_VERSION,
            "deliverable": self.deliverable,
            "pages_read": self.pages_read,
            "truncated": self.truncated,
            "manifest": [entry.as_dict() for entry in self.manifest],
            "required_unseen": list(self.required_unseen),
            "optional_unseen": list(self.optional_unseen),
            "trimmed": list(self.trimmed),
            "failure_details": list(self.failure_details),
            # Completeness is always relative to the declared scope and the
            # frozen snapshot.  No path here ever scans a whole store.
            "declared_scope_only": True,
            "scanned_full_history": False,
        }

    def consumer_dict(self) -> dict[str, object]:
        """The consumer view: no protected-side ids, no protected-side counts."""

        return {
            "state": self.state,
            "state_contract_id": RETRIEVAL_STATE_CONTRACT_ID,
            "state_contract_version": RETRIEVAL_STATE_CONTRACT_VERSION,
            "deliverable": self.deliverable,
            "pages_read": self.pages_read,
            "truncated": self.truncated,
            "manifest": [
                entry.as_dict() for entry in self.manifest if entry.reason != "not_authorized"
            ],
            "withheld": {"present": self.withheld, "reason": "not_authorized"},
            "required_unseen": list(self.required_unseen),
            "optional_unseen": list(self.optional_unseen),
            "trimmed": list(self.trimmed),
            "failure_details": list(self.failure_details),
            "declared_scope_only": True,
            "scanned_full_history": False,
        }


@dataclass(frozen=True, slots=True)
class PaginatedResearchContext:
    """A #397 Context plus the proof that its required scope was actually paged."""

    context: ResearchContext
    plan: RetrievalPlan
    pages: tuple[RetrievalPage, ...]
    chain: tuple[str, ...]
    outcome: RetrievalOutcome
    identity: str

    @property
    def status(self) -> PaginatedStatus:
        return "bounded" if self.outcome.deliverable else "refused"

    @property
    def effective_coverage_state(self) -> CoverageState:
        projected = _COVERAGE_PROJECTION[self.outcome.state]
        inner = self.context.coverage.state
        worse = min(
            (projected, inner),
            key=lambda state: _COVERAGE_PRECEDENCE.index(state),
        )
        return worse  # type: ignore[return-value]

    def public_record(self) -> dict[str, object]:
        """Everything needed to rebuild this Context, and nothing else."""

        return {
            "schema": PAGINATED_RECORD_SCHEMA,
            "paginated_identity": self.identity,
            "declaration": {
                "schema": PAGINATED_DECLARATION_SCHEMA,
                "context": self.context.declaration.as_dict(),
                "retrieval": {
                    "plan": self.plan.as_dict(),
                    "pages": [page.as_dict() for page in self.pages],
                },
            },
        }

    def limitations(self) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = [
            {
                "limitation_id": f"retrieval_state:{self.outcome.state}",
                "provenance": ["retrieval:state-contract"],
                "preconditions": [],
            },
            {
                "limitation_id": f"effective_coverage:{self.effective_coverage_state}",
                "provenance": ["retrieval:coverage"],
                "preconditions": [],
            },
        ]
        for source_id in self.outcome.trimmed:
            entries.append(
                {
                    "limitation_id": f"optional_trimmed:{source_id}",
                    "provenance": ["retrieval:trimming-policy"],
                    "preconditions": [f"budget:{self.plan.trimming_policy}"],
                }
            )
        for source_id in self.outcome.optional_unseen:
            entries.append(
                {
                    "limitation_id": f"optional_not_covered:{source_id}",
                    "provenance": ["retrieval:manifest"],
                    "preconditions": [],
                }
            )
        if self.outcome.withheld:
            entries.append(
                {
                    "limitation_id": "protected_material_withheld",
                    "provenance": ["retrieval:visibility-gate"],
                    "preconditions": [],
                }
            )
        return entries

    def audit_readback(self) -> dict[str, object]:
        """The full readback, protected-side manifest included.

        This is the owner / audit view.  ``deliver_paginated_research_brief``
        never returns it; the consumer gets :meth:`readback`.
        """

        return {
            **self._frame(),
            "retrieval": self.outcome.as_dict(),
            "context": self.context.readback(),
        }

    def readback(self) -> dict[str, object]:
        """The consumer readback.

        A refused retrieval carries its state, its details and its limitations —
        and no brief.  Nothing about the protected side is disclosed beyond the
        single fact that material was withheld, without ids and without counts.
        """

        frame = {
            **self._frame(),
            "retrieval": self.outcome.consumer_dict(),
            "limitations": self.limitations(),
        }
        if not self.outcome.deliverable:
            frame["brief"] = None
            return frame
        frame["brief"] = self.context.brief.as_dict()
        frame["coverage"] = self.context.coverage.as_dict()
        return frame

    def _frame(self) -> dict[str, object]:
        declaration = self.context.declaration
        return {
            "schema": PAGINATED_READBACK_SCHEMA,
            "paginated_identity": self.identity,
            "context_identity": self.context.identity,
            "status": self.status,
            "mode": declaration.mode,
            "purpose": declaration.purpose,
            "query_scope": declaration.query_scope.as_dict(),
            "snapshot": declaration.snapshot.as_dict(),
            "policy": declaration.policy.as_dict(),
            "plan": self.plan.as_dict(),
            "effective_coverage_state": self.effective_coverage_state,
            "state_contract_digest": RETRIEVAL_STATE_CONTRACT_DIGEST,
            # Memory publishes; it never qualifies a research result.
            "grants_eligibility": False,
        }


def freeze_paginated_research_context(
    value: Mapping[str, object],
) -> PaginatedResearchContext:
    """Freeze a #397 Context together with the pagination that produced it.

    The inner Context is frozen *first*.  Its manifest roles are then the frozen
    required / optional split that the page walk is judged against, so no page
    result can change what counts as required.
    """

    item = _mapping(value, "paginated context declaration")
    _fields_subset(item, _PAGINATED_FIELDS, "paginated context declaration")
    if item.get("schema") != PAGINATED_DECLARATION_SCHEMA:
        raise RetrievalRefusal("paginated context declaration schema is invalid")
    context = freeze_research_context(
        _mapping(item.get("context"), "paginated context declaration.context")
    )
    retrieval = _mapping(item.get("retrieval"), "retrieval")
    _fields_subset(retrieval, _RETRIEVAL_FIELDS, "retrieval")
    plan = RetrievalPlan.parse(retrieval.get("plan"))
    raw_pages = _list(retrieval.get("pages"), "retrieval.pages")
    if not raw_pages:
        # A store handing back no rows is not a cross-request snapshot contract.
        # ``complete_empty`` must be earned by an explicit exhausted page.
        raise RetrievalRefusal("retrieval.pages is required")
    pages = tuple(RetrievalPage.parse(raw, index) for index, raw in enumerate(raw_pages))
    _check_plan_against_declaration(plan, context.declaration)
    return _assemble(context, plan, pages)


def reconstruct_paginated_research_context(
    record: Mapping[str, object],
) -> PaginatedResearchContext:
    """Rebuild a paginated Context from its frozen public record alone.

    Nothing is re-queried and no "latest" result is re-selected: the frozen
    pages in the record are the only retrieval evidence, and the rebuilt
    identity must equal the recorded one.  A record that is missing those frozen
    facts fails loudly rather than being patched with a fresh query.
    """

    item = _mapping(record, "paginated context record")
    _fields_subset(
        item, {"schema", "paginated_identity", "declaration"}, "paginated context record"
    )
    if item.get("schema") != PAGINATED_RECORD_SCHEMA:
        raise RetrievalRefusal("paginated context record schema is invalid")
    recorded = item.get("paginated_identity")
    if not isinstance(recorded, str) or _SAFE_DIGEST.fullmatch(recorded) is None:
        raise RetrievalRefusal("paginated context record identity is invalid")
    rebuilt = freeze_paginated_research_context(
        _mapping(item.get("declaration"), "paginated context record declaration")
    )
    if rebuilt.identity != recorded:
        raise RetrievalRefusal("paginated context record does not reproduce its identity")
    return rebuilt


def deliver_paginated_research_brief(
    context: PaginatedResearchContext,
    visibility_request: Mapping[str, object],
) -> dict[str, object]:
    """Hand back a bounded brief only under *current* authorization.

    Three outcomes stay distinct, and none of them is allowed to impersonate
    another: a current-authorization denial (no identity, no brief, no
    manifest), an honest retrieval refusal (identity and state, but no brief),
    and a delivery (which may still be bounded with declared limitations).
    """

    decision = evaluate_visibility_request(visibility_request)
    if not decision.deliverable:
        return {
            "schema": PAGINATED_READBACK_SCHEMA,
            "delivery": "blocked",
            "reason": "current_authorization_denied",
            "paginated_identity": None,
            "context_identity": None,
            "grants_eligibility": False,
        }
    readback = context.readback()
    if not context.outcome.deliverable:
        return {
            **readback,
            "delivery": "refused",
            "reason": context.outcome.state,
        }
    return {**readback, "delivery": "delivered"}


def _check_plan_against_declaration(plan: RetrievalPlan, declaration: ContextDeclaration) -> None:
    """The plan may not disagree with the Context it pages for."""

    if plan.ordering_key != declaration.query_scope.ordering:
        raise RetrievalRefusal("retrieval.plan.ordering_key contradicts query_scope.ordering")
    if plan.trimming_policy != declaration.query_scope.trimming:
        raise RetrievalRefusal("retrieval.plan.trimming_policy contradicts query_scope.trimming")


def _assemble(
    context: ResearchContext,
    plan: RetrievalPlan,
    supplied: tuple[RetrievalPage, ...],
) -> PaginatedResearchContext:
    # Roles are read off the already-frozen inner Context, before any page is
    # looked at.  This is what makes post-hoc reclassification impossible.
    required_ids = {entry.source_id for entry in context.manifest if entry.role == "required"}
    optional_ids = {
        entry.source_id for entry in context.manifest if entry.role == "optional"
    } - required_ids

    unique = _deduplicate(supplied)
    details: set[str] = set()
    if plan.cursor.snapshot_id != context.declaration.snapshot.snapshot_id:
        # A cursor opened against another snapshot describes another store
        # state; resuming from it would silently mix two source populations.
        details.add("cursor_snapshot_mismatch")
    by_cursor = _index_by_cursor(unique, details)
    chain = _walk(plan, by_cursor, unique, details)
    records, ordering_ok = _records_in_order(chain, details)
    _check_snapshot_fence(records, context.declaration, details)

    authorization = _authorization_status(context.declaration)
    manifest, retrieved_required, retrieved_optional, budget_ok = _record_manifest(
        records, required_ids, optional_ids, authorization, plan, details
    )
    required_unseen = tuple(sorted(required_ids - retrieved_required))
    optional_unseen = tuple(sorted(optional_ids - retrieved_optional))
    trimmed = tuple(
        sorted(entry.source_id for entry in manifest if entry.decision == "trimmed")
    )
    truncated = not (chain and chain[-1].status == "ok" and chain[-1].exhausted)
    if truncated and len(chain) >= plan.page_budget:
        details.add("page_budget_exhausted")
    state = _state(
        chain=chain,
        details=details,
        ordering_ok=ordering_ok,
        budget_ok=budget_ok,
        truncated=truncated,
        required_unseen=required_unseen,
        optional_unseen=optional_unseen,
        trimmed=trimmed,
        records=records,
        required_ids=required_ids,
        optional_ids=optional_ids,
    )
    if state == "required_lineage_missing":
        details.add("required_records_never_paged")
    outcome = RetrievalOutcome(
        state=state,
        pages_read=len(chain),
        truncated=truncated,
        manifest=manifest,
        required_unseen=required_unseen,
        optional_unseen=optional_unseen,
        trimmed=trimmed,
        failure_details=tuple(sorted(details)),
    )
    identity = _identity(context, plan, unique, chain, outcome)
    return PaginatedResearchContext(
        context=context,
        plan=plan,
        pages=unique,
        chain=tuple(page.cursor_in for page in chain),
        outcome=outcome,
        identity=identity,
    )


def _deduplicate(pages: tuple[RetrievalPage, ...]) -> tuple[RetrievalPage, ...]:
    """An exactly repeated page is an allowed-equivalent representation.

    Two deliveries of the same page collapse to one; a page that *differs* is a
    different page and is kept, so the conflict is caught rather than hidden.
    """

    unique: dict[str, RetrievalPage] = {}
    for page in pages:
        unique.setdefault(page.digest(), page)
    return tuple(page for _digest_key, page in sorted(unique.items()))


def _index_by_cursor(
    pages: tuple[RetrievalPage, ...],
    details: set[str],
) -> dict[str, RetrievalPage]:
    by_cursor: dict[str, RetrievalPage] = {}
    for page in pages:
        existing = by_cursor.get(page.cursor_in)
        if existing is not None and existing.digest() != page.digest():
            # The same cursor handed back two different pages: the ordering
            # moved underneath us, so the whole chain is untrustworthy.
            details.add("conflicting_page_for_cursor")
            continue
        by_cursor[page.cursor_in] = page
    return by_cursor


def _walk(
    plan: RetrievalPlan,
    by_cursor: Mapping[str, RetrievalPage],
    supplied: tuple[RetrievalPage, ...],
    details: set[str],
) -> tuple[RetrievalPage, ...]:
    """Rebuild the page chain from the opening cursor, bounded by the budget.

    Input order is irrelevant: the chain is a function of the cursors alone, so
    shuffling the supplied pages cannot change the result.
    """

    reachable = _reachable_cursors(plan, by_cursor, details)
    for page in supplied:
        if page.cursor_in not in reachable:
            details.add("unreachable_page")
    chain: list[RetrievalPage] = []
    cursor = plan.cursor.cursor_id
    expected = plan.cursor.page_index
    seen: set[str] = set()
    while cursor in by_cursor and len(chain) < plan.page_budget:
        if cursor in seen:
            break
        seen.add(cursor)
        page = by_cursor[cursor]
        if page.page_index != expected:
            details.add("page_index_out_of_sequence")
        if len(page.records) > plan.page_size:
            details.add("page_over_declared_size")
        chain.append(page)
        if page.status == "interrupted":
            details.add("page_interrupted")
            break
        if page.status == "index_unavailable":
            details.add("page_index_unavailable")
            break
        if page.exhausted:
            break
        cursor = page.cursor_out
        expected += 1
    return tuple(chain)


def _reachable_cursors(
    plan: RetrievalPlan,
    by_cursor: Mapping[str, RetrievalPage],
    details: set[str],
) -> set[str]:
    if plan.cursor.ordering_key != plan.ordering_key:
        details.add("cursor_ordering_mismatch")
    reachable: set[str] = set()
    cursor = plan.cursor.cursor_id
    while cursor in by_cursor and cursor not in reachable:
        reachable.add(cursor)
        cursor = by_cursor[cursor].cursor_out
    if cursor in reachable:
        details.add("cursor_cycle")
    return reachable


def _records_in_order(
    chain: tuple[RetrievalPage, ...],
    details: set[str],
) -> tuple[tuple[PageRecord, ...], bool]:
    """Concatenate the chain and check the frozen ordering holds across it.

    A record that repeats or goes backwards means pages overlapped or shifted;
    either way the cursor no longer describes a stable position.
    """

    records: list[PageRecord] = []
    ordered = True
    previous: tuple[str, str] | None = None
    for page in chain:
        for record in page.records:
            key = record.order()
            if previous is not None and key <= previous:
                details.add("record_ordering_violation")
                ordered = False
            previous = key
            records.append(record)
    return tuple(records), ordered


def _check_snapshot_fence(
    records: tuple[PageRecord, ...],
    declaration: ContextDeclaration,
    details: set[str],
) -> None:
    """A record published after the frozen cutoff is contamination, not a miss.

    It is never silently dropped: dropping it would shrink the target sample
    without saying so, and keeping it would break the snapshot contract.  So the
    retrieval refuses.
    """

    cutoff = declaration.snapshot.knowledge_cutoff
    if any(record.published_at > cutoff for record in records):
        details.add("record_after_snapshot_cutoff")


def _record_manifest(
    records: tuple[PageRecord, ...],
    required_ids: set[str],
    optional_ids: set[str],
    authorization: Mapping[str, str],
    plan: RetrievalPlan,
    details: set[str],
) -> tuple[tuple[RetrievalEntry, ...], set[str], set[str], bool]:
    """Apply the pre-declared trimming policy to the retrieved records.

    Required records are admitted first and are never candidates for trimming.
    Optional records are then admitted in the frozen ordering until the record
    budget is spent.  If the required records alone do not fit, the retrieval
    refuses rather than trimming one of them or calling it optional.
    """

    entries: dict[str, RetrievalEntry] = {}
    retrieved_required: set[str] = set()
    retrieved_optional: set[str] = set()
    optional_in_order: list[str] = []
    for record in records:
        source_id = record.source_id
        if source_id in entries:
            continue
        status = authorization.get(source_id)
        if status is not None and status != "allowed":
            role: Literal["required", "optional", "undeclared"] = (
                "required" if source_id in required_ids else "optional"
            )
            entries[source_id] = RetrievalEntry(source_id, "excluded", "not_authorized", role)
            continue
        if source_id in required_ids:
            entries[source_id] = RetrievalEntry(
                source_id, "retrieved", "declared_and_paged", "required"
            )
            retrieved_required.add(source_id)
            continue
        if source_id in optional_ids:
            optional_in_order.append(source_id)
            continue
        entries[source_id] = RetrievalEntry(
            source_id, "excluded", "outside_declared_scope", "undeclared"
        )
    budget_ok = len(retrieved_required) <= plan.record_budget
    if not budget_ok:
        details.add("record_budget_insufficient_for_required")
    spend = len(retrieved_required)
    for source_id in optional_in_order:
        if budget_ok and spend < plan.record_budget:
            entries[source_id] = RetrievalEntry(
                source_id, "retrieved", "declared_and_paged", "optional"
            )
            retrieved_optional.add(source_id)
            spend += 1
        else:
            entries[source_id] = RetrievalEntry(
                source_id, "trimmed", "optional_trimmed_by_policy", "optional"
            )
    return (
        tuple(entries[key] for key in sorted(entries)),
        retrieved_required,
        retrieved_optional,
        budget_ok,
    )


def _state(
    *,
    chain: tuple[RetrievalPage, ...],
    details: set[str],
    ordering_ok: bool,
    budget_ok: bool,
    truncated: bool,
    required_unseen: tuple[str, ...],
    optional_unseen: tuple[str, ...],
    trimmed: tuple[str, ...],
    records: tuple[PageRecord, ...],
    required_ids: set[str],
    optional_ids: set[str],
) -> RetrievalState:
    """Decide the retrieval state under a single, fixed precedence.

    Structural distrust comes first (a broken cursor makes every later question
    unanswerable), then the snapshot contract, then store availability, then the
    budget, and only last can a state describe genuine absence.
    """

    structural = {
        "conflicting_page_for_cursor",
        "unreachable_page",
        "page_index_out_of_sequence",
        "page_over_declared_size",
        "cursor_cycle",
        "cursor_snapshot_mismatch",
        "cursor_ordering_mismatch",
        "record_ordering_violation",
    }
    if details & structural or not ordering_ok:
        return "cursor_invalidated"
    if "record_after_snapshot_cutoff" in details:
        return "snapshot_contaminated"
    if "page_index_unavailable" in details:
        return "index_unavailable"
    if "page_interrupted" in details:
        return "retrieval_interrupted"
    if not budget_ok:
        return "budget_exhausted"
    if required_unseen:
        # A chain that never finished cannot say a record does not exist.  Only
        # an explicitly exhausted chain may report genuine absence.
        return "budget_exhausted" if truncated else "required_lineage_missing"
    if truncated or trimmed or optional_unseen:
        return "optional_scope_not_exhausted"
    if not records and not required_ids and not optional_ids:
        # The declared scope was paged to exhaustion and matched nothing.
        return "complete_empty"
    return "complete"


def _identity(
    context: ResearchContext,
    plan: RetrievalPlan,
    supplied: tuple[RetrievalPage, ...],
    chain: tuple[RetrievalPage, ...],
    outcome: RetrievalOutcome,
) -> str:
    """The paginated Context identity.

    It binds the inner #397 identity — which already carries the snapshot, the
    query scope, the ordering and trimming rule, the policy version and the full
    inclusion / exclusion manifest — to the frozen retrieval plan, the canonical
    set of supplied pages, the chain that was actually walked, the retrieval
    state contract, and the full retrieval manifest, protected-side entries
    included.  Two retrievals that admitted, trimmed or withheld different
    material therefore cannot share an identity, while reordering or repeating
    the same pages cannot change one.
    """

    return _digest(
        {
            "schema": PAGINATED_DECLARATION_SCHEMA,
            "context_identity": context.identity,
            "plan": plan.as_dict(),
            "state_contract": RETRIEVAL_STATE_CONTRACT_DIGEST,
            # Canonical (digest-sorted) so input order and repetition drop out.
            "supplied_pages": [page.digest() for page in supplied],
            "chain": [page.digest() for page in chain],
            "outcome": outcome.as_dict(),
        }
    )


__all__ = [
    "MAX_PAGE_BUDGET",
    "MAX_PAGE_SIZE",
    "MAX_RECORD_BUDGET",
    "PAGINATED_DECLARATION_SCHEMA",
    "PAGINATED_READBACK_SCHEMA",
    "PAGINATED_RECORD_SCHEMA",
    "RETRIEVAL_STATES",
    "RETRIEVAL_STATE_CONTRACT",
    "RETRIEVAL_STATE_CONTRACT_DIGEST",
    "RETRIEVAL_STATE_CONTRACT_ID",
    "RETRIEVAL_STATE_CONTRACT_VERSION",
    "PageRecord",
    "PaginatedResearchContext",
    "RetrievalCursor",
    "RetrievalEntry",
    "RetrievalOutcome",
    "RetrievalPage",
    "RetrievalPlan",
    "RetrievalRefusal",
    "deliver_paginated_research_brief",
    "freeze_paginated_research_context",
    "reconstruct_paginated_research_context",
]
