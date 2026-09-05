from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools" / "installed_wheel_harness.py"
SPEC = importlib.util.spec_from_file_location("installed_wheel_harness", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


class InstalledWheelHarnessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows Job cleanup contract")
    def test_resume_failure_closes_job_and_reaps_suspended_process(self) -> None:
        process = mock.Mock()
        process.communicate.return_value = ("", "")
        with (
            mock.patch.object(harness.subprocess, "Popen", return_value=process),
            mock.patch.object(harness, "_assign_windows_kill_job", return_value=123),
            mock.patch.object(
                harness,
                "_resume_windows_process",
                side_effect=harness.InstalledWheelFailure("resume failed"),
            ),
            mock.patch.object(harness, "_close_windows_handle") as close_handle,
            self.assertRaisesRegex(harness.InstalledWheelFailure, "resume failed"),
        ):
            harness.run_command(
                ["python", "-c", "pass"],
                cwd=Path.cwd(),
                environment=dict(os.environ),
                timeout_seconds=1,
            )

        close_handle.assert_called_once_with(123)
        process.communicate.assert_called_once_with(timeout=10)

    def test_timeout_kills_descendants_even_after_process_leader_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            pid_path = temporary_path / "child.pid"
            child = "import time; time.sleep(30)"
            parent = (
                "import pathlib, subprocess, sys; "
                f"child=subprocess.Popen([sys.executable, '-c', {child!r}]); "
                f"pathlib.Path({str(pid_path)!r}).write_text(str(child.pid))"
            )
            started = time.monotonic()

            with self.assertRaises(harness.InstalledWheelFailure):
                harness.run_command(
                    [sys.executable, "-c", parent],
                    cwd=temporary_path,
                    environment=dict(os.environ),
                    timeout_seconds=1,
                )

            self.assertLess(time.monotonic() - started, 4)
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            with self.assertRaises(OSError):
                os.kill(child_pid, 0)

    def test_unchanged_source_check_rejects_ignored_build_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, repository, baseline = self._source_repository(Path(temporary))
            (repository / ".gitignore").write_text(
                "src/package/ignored.py\n", encoding="utf-8"
            )
            subprocess.run(["git", "add", ".gitignore"], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-m", "ignore"], cwd=repository, check=True
            )
            baseline = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (repository / "src" / "package" / "ignored.py").write_text(
                "VALUE = 3\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                harness.InstalledWheelFailure, "untracked production source"
            ):
                harness.verify_unchanged_sources(
                    root,
                    {"package": baseline},
                    dict(os.environ),
                )

    @staticmethod
    def _source_repository(root: Path) -> tuple[Path, Path, str]:
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
        subprocess.run(
            ["git", "add", "src/package/__init__.py"], cwd=repository, check=True
        )
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=repository, check=True)
        baseline = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return root, repository, baseline

    def test_unchanged_source_check_rejects_untracked_build_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, repository, baseline = self._source_repository(Path(temporary))
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

    def test_source_build_inputs_rejects_links_that_escape_the_source_tree(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "package"
            source = repository / "src" / "package"
            external = root / "external.py"
            source.mkdir(parents=True)
            external.write_text("VALUE = 42\n", encoding="utf-8")
            linked = source / "injected.py"
            try:
                linked.symlink_to(external)
            except OSError as exc:
                self.skipTest(f"file symlinks unavailable: {exc}")

            with self.assertRaisesRegex(
                harness.InstalledWheelFailure, "symbolic link or junction"
            ):
                harness._source_build_inputs(repository)

    def test_source_build_inputs_rejects_a_linked_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "package"
            external = root / "external-source"
            external.mkdir()
            repository.mkdir()
            try:
                (repository / "src").symlink_to(external, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")

            with self.assertRaisesRegex(
                harness.InstalledWheelFailure,
                "source root is a symbolic link or junction",
            ):
                harness._source_build_inputs(repository)


if __name__ == "__main__":
    unittest.main()
