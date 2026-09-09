# ruff: noqa: E402
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantresearch_acceptance import (
    AcceptanceFailure,
    AcceptanceSelector,
    AcceptanceSession,
    ArtifactCache,
    PlanRunner,
)
from tools.test_acceptance_runner import BuilderSpy, InstallerSpy, ProcessSpy
from tools.test_acceptance_selector import diff_literal, scope_literal


class ProofSpy:
    def __init__(self) -> None:
        self.proofs: list[tuple[str, str, str, tuple[str, ...]]] = []

    def prove(self, proof: object) -> None:
        self.proofs.append(
            (
                proof.owner,
                proof.fixed_sha,
                proof.source_fingerprint,
                proof.import_names,
            )
        )


class AcceptanceCacheFixtureContractTests(unittest.TestCase):
    def test_unchanged_owners_receive_only_fixed_sha_fingerprint_and_import_smoke(self) -> None:
        plan = AcceptanceSelector().select(scope_literal(), diff_literal(), phase="spec")
        proofs = ProofSpy()

        PlanRunner(
            ProcessSpy(),
            BuilderSpy(),
            InstallerSpy(),
            unchanged_prover=proofs,
        ).run(plan)

        self.assertEqual(len(proofs.proofs), 4)
        self.assertEqual(
            {item[0] for item in proofs.proofs},
            {
                "apex-research",
                "quant-runtime",
                "strategy-reporting",
                "strategy-workspace",
            },
        )
        self.assertTrue(all(item[2].startswith("sha256:") for item in proofs.proofs))
        self.assertEqual({step.owner for step in plan.steps}, {"quant-research"})

    def test_wheel_cache_is_immutable_and_keyed_by_fixed_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = ArtifactCache(Path(temporary))
            key = cache.key(
                owner="quant-research",
                fixed_sha="1" * 40,
                source_fingerprint="sha256:" + "2" * 64,
                build_argv=("uv", "build"),
            )
            self.assertEqual(len(key), 64)
            stored = cache.store(
                key, b"wheel-v1", filename="quantresearch_acceptance-1-py3-none-any.whl"
            )
            self.assertEqual(cache.lookup(key), stored)
            self.assertEqual(stored.name, "quantresearch_acceptance-1-py3-none-any.whl")
            self.assertEqual(stored.parent.name, key)
            self.assertEqual(stored.read_bytes(), b"wheel-v1")
            self.assertEqual(
                cache.store(
                    key,
                    b"wheel-v1",
                    filename="quantresearch_acceptance-1-py3-none-any.whl",
                ),
                stored,
            )
            with self.assertRaises(AcceptanceFailure):
                cache.store(
                    key,
                    b"wheel-v2",
                    filename="quantresearch_acceptance-1-py3-none-any.whl",
                )
            with self.assertRaises(AcceptanceFailure):
                cache.store(key, b"wheel-v1", filename="renamed-1-py3-none-any.whl")
            self.assertIsNone(
                cache.lookup(
                    cache.key(
                        owner="quant-research",
                        fixed_sha="1" * 40,
                        source_fingerprint="sha256:" + "3" * 64,
                        build_argv=("uv", "build"),
                    )
                )
            )

    def test_session_workspace_initializes_once_and_sqlite_rolls_back_namespaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session = AcceptanceSession(Path(temporary))
            self.assertIs(session.workspace, session.workspace)
            self.assertEqual(session.initialization_count, 1)
            alpha = session.namespace("alpha")
            beta = session.namespace("beta")
            self.assertNotEqual(alpha, beta)

            with session.sqlite.transaction("ticket_294") as connection:
                connection.execute("CREATE TABLE evidence (value TEXT)")
                connection.execute("INSERT INTO evidence VALUES ('private')")
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM evidence").fetchone()[0], 1
                )
            with session.sqlite.transaction("ticket_295") as connection:
                tables = connection.execute(
                    "SELECT count(*) FROM sqlite_master WHERE name = 'evidence'"
                ).fetchone()[0]
                self.assertEqual(tables, 0)
            self.assertEqual(session.sqlite.initialization_count, 1)
            session.close()


if __name__ == "__main__":
    unittest.main()
