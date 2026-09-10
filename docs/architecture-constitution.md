# QuantResearch architecture constitution

`architecture-constitution.v1.json` is the machine-readable authority for QuantResearch
architecture. This document is an explanatory companion; an admission decision must be made
by the validator, not by interpreting this prose.

The only canonical flow is source evidence to an immutable Strategy Package, then Quant
Runtime, Apex Research evidence, and Strategy Reporting. Strategy Workspace is the sole
control-plane owner for immutable packages, requests, lifecycle, records, artifacts, and
lineage. Consumers cross repository boundaries only through listed public seams; SQLite,
runtime directories, artifact paths, locks, and implementation modules are private.

Quant Runtime alone consumes MarketHub data, uses Qlib for discovery, runs formal work in
NautilusTrader, and publishes single-run native metrics. NautilusTrader output is formal
truth. Apex Research orchestrates campaigns and cross-run evidence but never executes an
engine or recreates native metrics. Strategy Reporting is deterministic presentation of
published read models, never a source of evidence or metrics.

An external project is classified as an adapter, internalized idea, benchmark, or rejected
dependency. At adoption time its license and upstream interface are reverified. QuantResearch
ends at `research_qualified` or `retired`: production approval, orders, positions, and live
trading are forbidden.

Every later SPEC supplies the five declarations named by the policy. Validate a proposed
admission record with:

```powershell
python tools/validate_architecture_constitution.py --candidate candidate.json
```
