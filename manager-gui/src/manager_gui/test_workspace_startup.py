from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

import pytest
from strategy_workspace import WorkspaceClient


@pytest.fixture
def workspace_root(tmp_path):
    root = tmp_path / "isolated-workspace"
    WorkspaceClient(root).init()
    return root


def inventory(root):
    return sorted(
        (str(path.relative_to(root)), path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
    )


@contextmanager
def cli_server(*args):
    executable = Path(sys.executable).with_name("manager-gui-web.exe")
    process = subprocess.Popen(
        [str(executable), "--port", "0", *map(str, args)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
    try:
        line = lines.get(timeout=30)
        assert line.startswith("Manager GUI listening at "), process.stderr.read()
        yield line.strip().removeprefix("Manager GUI listening at ").rstrip("/")
    finally:
        process.terminate()
        process.communicate(timeout=10)


def test_cli_workspace_starts_existing_root_without_writes(workspace_root):
    before = inventory(workspace_root)
    with cli_server("--provider", "workspace", "--workspace-root", workspace_root) as base:
        with urlopen(base + "/health", timeout=5) as response:
            assert json.load(response)["read_only"] is True
        with urlopen(base + "/api/read-model?view=atlas", timeout=5) as response:
            model = json.load(response)
            assert model["schema"] == "manager-gui.manager-read-model.v0"
            assert model["snapshot_token"].startswith("workspace-view-")
    assert inventory(workspace_root) == before
