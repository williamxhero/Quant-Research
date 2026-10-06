# Manager GUI Reader Guide

This guide describes the read-only Reader surface for the 17 mounted Manager GUI
routes. The Reader is a presentation projection over the public
`ManagerReadModel v0`; it does not create owner facts, rerun research, or change
the source envelope.

## Reading modes

Every route keeps the same URL, language, fixture, source context, and API
contract while switching between three modes:

- **Reader** answers the four questions: what this page is, what is confirmed,
  what is not known, and why the page says that. Claims, gaps, derivation rules,
  source references, as-of values, and snapshot values are visible.
- **Expert** keeps the route's detailed audit view and typed page-specific
  evidence. It is not a second source of truth.
- **Raw** exposes the escaped, read-only `ManagerReadModel v0` JSON. Raw values,
  identifiers, owner text, locators, timestamps, and snapshot tokens are shown
  verbatim and are never translated.

The mode switch is a normal GET link. It preserves `lang`, `fixture`, `scope`,
`root`, repeated `filter` values, `snapshot`/`snapshot_token`, route-local
identifiers, and other opaque context.

## Truth language

Reader vocabulary is intentionally narrower than an outcome vocabulary:

- **Known** is a directly recorded value.
- **Derived** is the named result of a published deterministic rule; it is not
  an owner fact.
- **Interpreted** is a labelled interpretation whose rule and inputs remain
  visible.
- **Missing**, **Blocked**, **Stale**, **Incomparable**, and **Not evaluated**
  remain distinct gaps. None is rewritten as success, failure, zero, or an
  empty conclusion.

A missing owner record renders `无法得出结论` in the Chinese interface and
`No conclusion can be drawn` in the English interface. The Reader never guesses
from an absent record. Owner text and machine/raw values remain verbatim.

## Sample data and owner data

A fixture response carries a visible sample-data banner on the page. The banner
is shell metadata and is never inserted into a real owner-data envelope. A
projection created from an owner provider has no fixture banner and keeps the
owner source references and raw bytes. Synthetic fixture locators are not
presented as owner sources.

The banner is not a conclusion. It tells the reader that the displayed data is
synthetic and must not be treated as connected research data.

## Following evidence

The intended reading loop is:

`Atlas → Research Story → Evidence or status → Source Documents / History → Raw`

The same context can be followed from Strategy, Memory/Failure, Methodology,
Search, Portal, Lineage, and comparison pages. Stable links retain source
references, as-of information, snapshot identity, scope, root identifiers and
filters. Refreshing or bookmarking a link therefore reads the same public
context rather than silently resetting it.

Source links identify a public source scope and locator. They do not open private
storage. The raw drawer and `/api/read-model`/`/api/export` responses remain
language-neutral; changing `lang` changes only UI copy.

## Known limitations

- Reader v1 only presents projections published by the mounted route modules;
  an unpublished projection is labelled as unavailable rather than inferred.
- Fixture coverage is deterministic sample coverage, not a claim that a live
  owner system is connected.
- Graphs are bounded presentations of the already-read envelope. The accessible
  table/inspector is the complete alternative when a graph is unavailable or
  difficult to navigate.
- Pagination and filters are local presentation state over a read envelope;
  they do not submit a cursor mutation or trigger revalidation.
- As-of, snapshot, IDs, locators, owner text, and error reasons may be absent
  or opaque when the source envelope says they are unavailable. The UI does not
  fill them in.
- Reader v1 does not run Runtime, rebuild, revalidation, export publication,
  or any other mutation. Write methods are rejected with `405 Allow: GET, HEAD`.

## Manual accessibility checklist

Run this checklist for every route in both `zh-CN` and `en`, and for Reader,
Expert, and Raw modes:

- [ ] The document has the correct `lang`, a unique page title, one labelled
      main landmark, and a visible skip link.
- [ ] The page heading and route label identify the current route; navigation
      marks the current link with `aria-current="page"`.
- [ ] Reader mode, language, panel, close, export, and search controls are
      reachable with Tab and have visible focus styles.
- [ ] Opening Inspector or the raw/event drawer exposes its labelled region;
      closing it returns focus to the initiating control.
- [ ] Status, empty, partial, blocked, stale, incomparable, and not-evaluated
      states have a text label and are not conveyed by color alone.
- [ ] Every graph has a keyboard-reachable table or inspector alternative with
      column/row headings and the same source/status values.
- [ ] Source links, owner text, machine values, and snapshot references have
      meaningful accessible names and remain readable at CJK and narrow widths.
- [ ] No route contains a mutation form or a write method; GET/HEAD work and
      POST/PUT/PATCH/DELETE return `405 Allow: GET, HEAD`.
- [ ] At 200% zoom and a narrow viewport, text, focus, tables, and route links
      remain usable without losing the source/as-of context.

The automated matrix in `src/manager_gui/test_reader_exit_gate.py` covers all
17 routes × 11 fixture states × 3 modes × 2 locales. The checklist supplements
that matrix with keyboard, screen-reader, zoom, and responsive-layout checks
that require a browser or assistive technology.
