# #394 Research Memory visibility gate evidence

## Scope

This evidence covers the QuantResearch acceptance seam for #394 (RM-V1B.1), under
the constraints in #394, parent SPEC #384, and the R2 policy in #381. It uses only
synthetic test identities and payloads; it does not read or transmit a real holdout.
The implementation is local and deterministic, with a metadata decision before the
payload loader is invoked.

## Delivered contract

- `quantresearch_acceptance.research_visibility` defines versioned request and
  decision schemas, immutable logical scope/time range records, current consumer
  grants, frozen research policy, lineage metadata, and historical context identity.
- Scope matching uses logical dataset, universe, time range, and sample role. Display
  name, campaign, and dataset version are not authorization keys.
- Every supported delivery stage is evaluated, including initial read, ranking,
  embedding, summary, planning, research model, final envelope, tool return, and
  historical redelivery.
- Strict incomplete metadata is `restricted`; audit-only incomplete metadata is
  `unknown` and never deliverable. Current authorization and frozen research policy
  remain separate sanitized decision dimensions.
- The required protection-closure fields `derived_from`, `allowed_purposes`, and
  `required_capabilities` distinguish missing metadata from an explicitly empty
  value; omission cannot silently open a material.
- `guard_visibility_delivery` invokes the material loader only after an `allowed`
  decision. Revoked current authorization therefore cannot replay an old context.

## Verification

Commands run from the QuantResearch worktree:

```text
python -m pytest -q src/quantresearch_acceptance/_research_visibility_test.py
18 passed

ruff check src/quantresearch_acceptance
All checks passed!

python -m compileall -q src
success

git diff --check
success

uv build --wheel --out-dir dist/issue-394
success

uv build --wheel --no-sources --offline --out-dir dist/issue-394-revised-offline
success
```

The no-source wheel replay installed the wheel into an isolated temporary
`site-packages` directory and ran the 18 visibility tests plus the existing
installed acceptance tests: `23 passed`. The import path resolved to
the installed wheel and the source checkout was absent from the replay working
directory. The final offline-built wheel SHA-256 was
`E3D30C2049009B63334FE1A3A1B5BD1AE7DEDC5167C2CD74804BD6D7FCE50102`.

The ordinary full repository pytest command was attempted. Collection stops at the
pre-existing SPEC-027 installed tracer because this machine does not have the four
external owner wheels (`apex_research`, `quant_runtime`, `strategy_reporting`, and
`strategy_workspace`). That environment limitation is not counted as #394 evidence;
the focused source and installed/no-source tests above are the applicable result.

## Acceptance conclusion

The local #394 gate behavior is verified for the covered A0-P01/L02 slice. This is
engineering and acceptance-seam evidence only. It does not claim a connected E02
model run, real holdout access, research qualification, or profitability.
