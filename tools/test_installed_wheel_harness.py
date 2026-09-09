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
    def test_installed_pytest_preserves_snapshot_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            isolated = Path(temporary)
            snapshot = isolated / "snapshot"
            snapshot.mkdir()
            test_file = snapshot / "test_fixture.py"
            test_file.write_text("def test_passes():\n    assert True\n", encoding="utf-8")

            harness.run_installed_pytest(
                Path(sys.executable),
                (test_file,),
                (),
                (),
                cwd=isolated,
                environment=harness.sanitized_environment(),
                timeout_seconds=30,
            )

            self.assertEqual(
                sorted(path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*")),
                ["test_fixture.py"],
            )
            self.assertEqual(
                test_file.read_text(encoding="utf-8"),
                "def test_passes():\n    assert True\n",
            )

    def test_sanitized_environment_removes_pytest_and_source_injection(self) -> None:
        environment = harness.sanitized_environment(
            {
                "PYTHONPATH": "source",
                "PYTEST_ADDOPTS": "--ignore=tests",
                "PYTEST_PLUGINS": "injected",
                "UV_WORKING_DIR": "elsewhere",
                "UV_PROJECT": "other-project",
                "UV_NO_SYNC": "1",
                "UV_PROJECT_ENVIRONMENT": "other-venv",
                "UV_CACHE_DIR": "poisoned-cache",
                "UV_INDEX_URL": "https://example.invalid/simple",
                "HATCH_BUILD_NO_HOOKS": "1",
                "HATCH_BUILD_HOOKS_ONLY": "1",
                "SOURCE_DATE_EPOCH": "1",
                "VIRTUAL_ENV": "caller-venv",
                "GIT_DIR": "elsewhere/.git",
                "GIT_WORK_TREE": "elsewhere",
                "GIT_INDEX_FILE": "elsewhere/index",
                "KEEP": "yes",
            }
        )

        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("PYTEST_ADDOPTS", environment)
        self.assertNotIn("PYTEST_PLUGINS", environment)
        self.assertNotIn("UV_WORKING_DIR", environment)
        self.assertNotIn("UV_PROJECT", environment)
        self.assertNotIn("UV_NO_SYNC", environment)
        self.assertNotIn("UV_PROJECT_ENVIRONMENT", environment)
        self.assertFalse(any(name.startswith("UV_") for name in environment))
        self.assertNotIn("VIRTUAL_ENV", environment)
        self.assertFalse(any(name.startswith("GIT_") for name in environment))
        self.assertFalse(any(name.startswith("HATCH_") for name in environment))
        self.assertNotIn("SOURCE_DATE_EPOCH", environment)
        self.assertEqual(environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["KEEP"], "yes")

    def test_run_command_wraps_process_launch_failures(self) -> None:
        with (
            mock.patch.object(
                harness.subprocess, "Popen", side_effect=OSError("missing executable")
            ),
            self.assertRaisesRegex(harness.InstalledWheelFailure, "command could not start"),
        ):
            harness.run_command(
                ["missing-command"],
                cwd=Path.cwd(),
                environment=dict(os.environ),
                timeout_seconds=1,
            )

    def test_source_visibility_detects_paths_below_or_above_source_root(self) -> None:
        source = Path("C:/workspace/package/src").resolve()

        self.assertTrue(harness.path_exposes_source(source, source / "package"))
        self.assertTrue(harness.path_exposes_source(source, source.parent))
        self.assertFalse(harness.path_exposes_source(source, Path("C:/venv").resolve()))

    def test_verify_source_topology_covers_changed_owner_without_git_baseline(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "package"
            source = repository / "src" / "package"
            source.mkdir(parents=True)
            (source / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")

            topology = harness.verify_source_topology(repository)

            self.assertEqual(topology["source_files"], ["src/package/__init__.py"])
            self.assertEqual(len(topology["source_fingerprint"]), 64)

    def test_verify_source_topology_attests_a_non_package_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "quant-research"
            tools = repository / "tools"
            tools.mkdir(parents=True)
            (tools / "tracer.py").write_text("VALUE = 1\n", encoding="utf-8")
            (repository / "说明.md").write_text("验收\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
            subprocess.run(["git", "add", "tools/tracer.py", "说明.md"], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-m", "root"],
                cwd=repository,
                check=True,
                capture_output=True,
            )

            topology = harness.verify_source_topology(repository, dict(os.environ))

            self.assertEqual(topology["source_files"], ["tools/tracer.py", "说明.md"])
            self.assertEqual(len(topology["source_fingerprint"]), 64)

    def test_source_topology_includes_declared_force_includes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            (repository / "src/package").mkdir(parents=True)
            (repository / "strategies").mkdir()
            (repository / "build_backend").mkdir()
            (repository / "licenses").mkdir()
            (repository / "hooks").mkdir()
            (repository / "assets").mkdir()
            (repository / "src/package/__init__.py").write_text("", encoding="utf-8")
            (repository / "strategies/example.py").write_text("VALUE = 1\n", encoding="utf-8")
            (repository / "README.md").write_text("package\n", encoding="utf-8")
            (repository / "licenses/LICENSE.txt").write_text("license\n", encoding="utf-8")
            (repository / "hooks/build.py").write_text("", encoding="utf-8")
            (repository / "assets/data.json").write_text("{}\n", encoding="utf-8")
            (repository / "pyproject.toml").write_text(
                "[build-system]\nbackend-path=['build_backend']\n"
                "[project]\nname='package'\nversion='1.0'\n"
                "readme={file='README.md'}\nlicense={file='licenses/LICENSE.txt'}\n"
                "[tool.hatch.build]\nartifacts=['assets/*.json']\n"
                "[tool.hatch.build.force-include]\n'assets'='package/assets'\n"
                "[tool.hatch.build.hooks.custom]\npath='hooks/build.py'\n"
                "[tool.hatch.build.targets.wheel]\npackages=['src/package']\n"
                "[tool.hatch.build.targets.wheel.force-include]\n"
                "'strategies'='package/strategies'\n",
                encoding="utf-8",
            )

            topology = harness.verify_source_topology(repository)

            self.assertIn("strategies/example.py", topology["source_files"])
            self.assertIn("pyproject.toml", topology["source_files"])
            self.assertIn("README.md", topology["source_files"])
            self.assertIn("licenses/LICENSE.txt", topology["source_files"])
            self.assertIn("hooks/build.py", topology["source_files"])
            self.assertIn("assets/data.json", topology["source_files"])

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

    def test_posix_cleanup_does_not_kill_a_reused_pid(self) -> None:
        process = mock.Mock(pid=100)
        with (
            mock.patch.object(harness.os, "name", "posix"),
            mock.patch.object(harness.os, "killpg", create=True),
            mock.patch.object(harness.os, "kill") as kill,
            mock.patch.object(harness.signal, "SIGKILL", 9, create=True),
            mock.patch.object(
                harness,
                "_posix_process_map",
                return_value={200: (1, 22), 201: (1, 33)},
            ),
            mock.patch.object(harness, "_kill_owned_subreaper_children"),
        ):
            harness._terminate_process_tree(
                process,
                job_handle=None,
                descendant_pids={200: 11, 201: 33},
                process_start_time=44,
            )

        kill.assert_called_once_with(201, 9)

    def test_posix_cleanup_reaps_only_newly_adopted_subreaper_children(self) -> None:
        parent = os.getpid()
        process_map = {
            200: (parent, 11),
            201: (parent, 22),
        }
        with (
            mock.patch.object(harness.os, "name", "posix"),
            mock.patch.object(harness.os, "kill") as kill,
            mock.patch.object(harness.os, "WNOHANG", 1, create=True),
            mock.patch.object(harness.signal, "SIGKILL", 9, create=True),
            mock.patch.object(harness, "_posix_process_map", side_effect=[process_map, {}]),
            mock.patch.object(harness, "_kill_posix_identity") as kill_identity,
            mock.patch.object(harness.os, "waitpid"),
        ):
            harness._kill_owned_subreaper_children({}, {200: 11})

        kill.assert_not_called()
        kill_identity.assert_called_once_with(201, 22)

    def test_posix_cleanup_fails_closed_when_an_owned_child_survives(self) -> None:
        parent = os.getpid()
        process_map = {201: (parent, 22)}
        with (
            mock.patch.object(harness.os, "name", "posix"),
            mock.patch.object(harness, "_posix_process_map", return_value=process_map),
            mock.patch.object(harness, "_kill_posix_identity"),
            mock.patch.object(harness.os, "waitpid"),
            mock.patch.object(harness.os, "WNOHANG", 1, create=True),
            mock.patch.object(harness.time, "monotonic", side_effect=[0.0, 0.0, 2.0]),
            mock.patch.object(harness.time, "sleep"),
            self.assertRaisesRegex(harness.InstalledWheelFailure, "survived bounded cleanup"),
        ):
            harness._kill_owned_subreaper_children({}, {}, timeout_seconds=1.0)

    def test_source_topology_attests_tests_and_rejects_a_dirty_test(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _root, repository, _baseline = self._source_repository(Path(temporary))
            test_file = repository / "tests/test_acceptance.py"
            test_file.parent.mkdir()
            test_file.write_text("def test_acceptance(): pass\n", encoding="utf-8")
            subprocess.run(["git", "add", "tests/test_acceptance.py"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-m", "tests"], cwd=repository, check=True)

            topology = harness.verify_source_topology(repository, dict(os.environ))
            self.assertIn("tests/test_acceptance.py", topology["source_files"])
            test_file.write_text("def test_acceptance(): assert False\n", encoding="utf-8")
            with self.assertRaises(harness.InstalledWheelFailure):
                harness.verify_source_topology(repository, dict(os.environ))

    def test_repository_validation_rejects_a_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _root, repository, _baseline = self._source_repository(Path(temporary))
            nested = repository / "src/package"
            with self.assertRaisesRegex(harness.InstalledWheelFailure, "exact Git work-tree root"):
                harness._validated_repository_path(nested, require_git=True)

    def test_snapshot_repository_copies_only_the_attested_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, repository, _baseline = self._source_repository(Path(temporary))
            destination = root / "snapshot"
            harness.snapshot_repository(repository, destination, ["src/package/__init__.py"])

            self.assertEqual(
                (destination / "src/package/__init__.py").read_text(encoding="utf-8"),
                "VALUE = 1\n",
            )
            self.assertFalse((destination / ".git").exists())

    def test_unchanged_source_check_rejects_ignored_build_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, repository, baseline = self._source_repository(Path(temporary))
            (repository / ".gitignore").write_text("src/package/ignored.py\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-m", "ignore"], cwd=repository, check=True)
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
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
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

    def test_source_topology_rejects_dirty_owner_build_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _root, repository, _baseline = self._source_repository(Path(temporary))
            (repository / "src/package/__init__.py").write_text("VALUE = 9\n", encoding="utf-8")

            with self.assertRaises(harness.InstalledWheelFailure):
                harness.verify_source_topology(repository, dict(os.environ))

    def test_source_topology_requires_git_when_attesting_an_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            (repository / "src/package").mkdir(parents=True)
            (repository / "src/package/__init__.py").write_text("", encoding="utf-8")

            with self.assertRaises(harness.InstalledWheelFailure):
                harness.verify_source_topology(repository, dict(os.environ))

    def test_source_topology_rejects_skip_worktree_build_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _root, repository, _baseline = self._source_repository(Path(temporary))
            subprocess.run(
                ["git", "update-index", "--skip-worktree", "src/package/__init__.py"],
                cwd=repository,
                check=True,
            )
            (repository / "src/package/__init__.py").unlink()

            with self.assertRaisesRegex(harness.InstalledWheelFailure, "unsafe Git index flags"):
                harness.verify_source_topology(repository, dict(os.environ))

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

            with self.assertRaisesRegex(harness.InstalledWheelFailure, "symbolic link or junction"):
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

    def test_source_build_inputs_mocked_link_detection_is_platform_independent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            source = repository / "src/package"
            source.mkdir(parents=True)
            injected = source / "injected.py"
            injected.write_text("VALUE = 1\n", encoding="utf-8")
            original = Path.is_symlink

            with (
                mock.patch.object(
                    Path,
                    "is_symlink",
                    autospec=True,
                    side_effect=lambda path: path == injected or original(path),
                ),
                self.assertRaisesRegex(harness.InstalledWheelFailure, "symbolic link or junction"),
            ):
                harness._source_build_inputs(repository)


if __name__ == "__main__":
    unittest.main()
