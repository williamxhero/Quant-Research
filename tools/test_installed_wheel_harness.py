from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools" / "installed_wheel_harness.py"
SPEC = importlib.util.spec_from_file_location("installed_wheel_harness", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


class InstalledWheelHarnessTests(unittest.TestCase):
    def test_timeout_kills_descendants_even_after_process_leader_exits(self) -> None:
        child = "import time; time.sleep(5)"
        parent = (
            "import subprocess, sys; "
            f"subprocess.Popen([sys.executable, '-c', {child!r}])"
        )
        started = time.monotonic()

        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(
            harness.InstalledWheelFailure
        ):
            harness.run_command(
                [sys.executable, "-c", parent],
                cwd=Path(temporary),
                environment=dict(os.environ),
                timeout_seconds=1,
            )

        self.assertLess(time.monotonic() - started, 4)

    def test_unchanged_source_check_rejects_untracked_build_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "package"
            (repository / "src" / "package").mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=repository, check=True
            )
            tracked = repository / "src" / "package" / "__init__.py"
            tracked.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "src/package/__init__.py"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=repository, check=True)
            baseline = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (repository / "src" / "package" / "injected.py").write_text(
                "VALUE = 2\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                harness.InstalledWheelFailure, "untracked production source"
            ):
                harness.verify_unchanged_sources(
                    root,
                    {"package": baseline},
                    dict(os.environ),
                )


if __name__ == "__main__":
    unittest.main()
