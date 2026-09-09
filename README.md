# Quant Research workspace

This repository is the lightweight shell for the QuantResearch workspace.
It contains shared navigation, agent configuration, the machine-readable architecture
constitution and admissions, and public-seam acceptance tools that verify contracts across
the independently versioned project repositories without owning their implementation.

Each project directory is an independent Git repository with its own GitHub
remote, history, releases, and commits. This repository neither tracks those
directories nor pins them as submodules.

## Layered acceptance

The `quantresearch-acceptance` package is the single planning and L0-L3 execution seam.
It accepts a strict acceptance-scope v2 document, a fixed-base diff, and `spec` or
`release` phase. The immutable plan records owners, argv tokens, L0-L5 selection,
per-command p95-derived timeouts, markers, source-to-direct-test mappings, source
fingerprints, JUnit/event destinations, and one canonical identity. Unknown fields,
duplicate JSON keys, path traversal, shell strings, ambiguous ownership, unmapped
meaning-bearing paths, and base/fingerprint drift fail closed.

```console
quantresearch-acceptance diff --scope scope.json --repository-root . --owner-root apex-research=../ApexResearch --output fixed-diff.json
quantresearch-acceptance select --scope scope.json --diff fixed-diff.json --phase spec
quantresearch-acceptance execute --scope scope.json --diff fixed-diff.json --phase spec --repository-root . --owner-root apex-research=../ApexResearch
quantresearch-acceptance audit --history durations.json
quantresearch-acceptance migrate --scope docs/architecture-admissions/spec-026a.acceptance-scope.v1.json
```

Ordinary pytest commands exclude `slow`, `oci`, `connected`, and `release`. Tests over
2 seconds and files over 60 seconds must carry `slow` plus a non-empty explanation.
L0-L2 run for every SPEC; L3 is selected only for a public-contract change and builds
and installs the selected wheel set once before two complete pytest replays in the
same no-source environment. L4 runs only at 5-8-SPEC checkpoints or final release;
L5 remains an independent truthful status with no fallback.

The release ledger accepts exactly 32 ordered SPEC evidence references, defaults to
six-SPEC checkpoints, is resumable and idempotent, and rejects replacement evidence.
Review repairs create a fresh fixed-base diff containing only repair-touched paths, so
the same selector reruns only the new impact set. The v1 SPEC-026A scope is retained as
prior machine-readable evidence and can be migrated without dropping its recorded
levels or installed tracers.
