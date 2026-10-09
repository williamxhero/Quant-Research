from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from ctypes import wintypes
from html import unescape
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

import pytest
from strategy_workspace import WorkspaceClient

from manager_gui.web.navigation import ViewId


@pytest.fixture
def workspace_root(tmp_path):
    root = tmp_path / "isolated-workspace"
    WorkspaceClient(root).init()
    return root


@pytest.fixture
def published_workspace(workspace_root):
    client = WorkspaceClient(workspace_root)
    for record_id, schema in (
        ("w2-study", "apex-research.study-registration.v1"),
        ("w2-evidence", "apex-research.evidence.v1"),
        ("w2-report", "apex-research.study-report-source.v1"),
        ("w2-unmapped", "w2.unmapped.v1"),
    ):
        client.publish_record(
            {
                "record_id": record_id,
                "record_type": schema,
                "payload": {
                    "schema": schema,
                    "title": "W2 published research " + record_id,
                    "body": "Published research rationale " + record_id,
                },
            },
            artifacts=[
                {
                    "source": ("Original supporting text " + record_id).encode(),
                    "media_type": "text/plain",
                    "name": "W2 published source " + record_id,
                }
            ],
        )
    return workspace_root


def inventory(root):
    return sorted(
        (str(path.relative_to(root)), path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
    )


def cli_command(*args):
    executable = Path(sys.executable).with_name("manager-gui-web.exe")
    return [str(executable), "--port", "0", *map(str, args)]


@contextmanager
def cli_server(*args, env=None):
    process = subprocess.Popen(
        cli_command(*args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
    )
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
    try:
        line = lines.get(timeout=30)
        assert line.startswith("Manager GUI listening at "), process.stderr.read()
        yield line.strip().removeprefix("Manager GUI listening at ").rstrip("/")
    finally:
        process.terminate()
        _, stderr = process.communicate(timeout=10)
        assert "W2_WRITE_SENTINEL" not in stderr
        assert "Error in sitecustomize" not in stderr
        if env and "W2_GUARDED_ROOT" in env:
            assert "W2_READONLY_GUARD_READY" in stderr


@pytest.mark.parametrize("method", ["get_registered_package", "query_lineage", "read_artifact"])
@pytest.mark.parametrize("incompatible", [False, True])
def test_workspace_provider_checks_conditional_api_only_when_needed(
    monkeypatch, tmp_path, method, incompatible
):
    import hashlib
    import types

    class PublicError(Exception):
        pass

    class PublicClient:
        runs = [{"run_id": "run-1", "status": "failed", "result": None}]
        records = []

        def __init__(self, root, *, read_only):
            assert read_only is True

        def list_runs(self, *, limit):
            return self.runs[:limit]

        def list_records(self, *, limit):
            return self.records[:limit]

    module = types.ModuleType("strategy_workspace")
    module.WorkspaceClient = PublicClient
    module.WorkspaceError = PublicError
    monkeypatch.setitem(sys.modules, "strategy_workspace", module)

    from manager_gui.workspace import WorkspaceDataProvider, WorkspaceDependencyError

    provider = WorkspaceDataProvider(tmp_path)
    assert provider.read().data["public_input"]["packages"] == []
    if incompatible:
        def wrong_shape(self):
            raise AssertionError("Incompatible method must not execute")

        setattr(PublicClient, method, wrong_shape)
    if method == "get_registered_package":
        PublicClient.runs[0]["request"] = {"strategy_package": {"strategy_id": "missing-api"}}
    else:
        record = {"record_id": "published-1"}
        if method == "query_lineage":
            record["lineage"] = [{"source_kind": "publication", "source_id": "parent-1"}]
        else:
            digest = hashlib.sha256(b"").hexdigest()
            record["artifacts"] = [{
                "sha256": digest,
                "uri": "workspace-artifact://sha256/" + digest,
                "bytes": 0,
            }]
        PublicClient.records = [record]
    with pytest.raises(WorkspaceDependencyError, match=f"WorkspaceClient.{method}"):
        WorkspaceDataProvider(tmp_path)


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


def test_workspace_identity_is_not_fixture_identity_on_any_route(published_workspace):
    workspace_root = published_workspace
    before = inventory(workspace_root)
    with cli_server("--provider", "workspace", "--workspace-root", workspace_root) as base:
        for view in ViewId:
            for mode in ("reader", "expert", "raw"):
                for lang in ("zh-CN", "en"):
                    url = f"{base}/?view={view.value}&mode={mode}&lang={lang}"
                    with urlopen(url, timeout=5) as response:
                        document = response.read().decode("utf-8")
                    for forbidden in (
                        "编造的示例",
                        "fabricated example",
                        "样例数据",
                        "Sample data",
                        "fixture workspace",
                        "fixture-backed",
                        'data-sample-banner="fixture"',
                    ):
                        assert forbidden not in document, (view, mode, lang, forbidden)
                    assert "workspace-view-" in document
        for view in ("atlas", "evidence", "search", "source-documents", "portal"):
            with urlopen(f"{base}/?view={view}&lang=en", timeout=5) as response:
                document = response.read().decode("utf-8")
            assert "W2 published" in document
            assert 'class="source-support"' in document
    assert inventory(workspace_root) == before


@pytest.fixture
def readonly_guard(tmp_path):
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        """
import os
import sys
from pathlib import Path
from strategy_workspace import WorkspaceClient, WorkspaceError

root = Path(os.environ['W2_GUARDED_ROOT']).resolve()
if os.environ.get('W2_FAIL_READ'):
    def failed_read(*args, **kwargs):
        raise WorkspaceError('workspace_read_failed', 'injected public read failure')
    WorkspaceClient.list_records = failed_read
def forbidden(*args, **kwargs):
    print('W2_WRITE_SENTINEL', file=sys.stderr, flush=True)
    raise AssertionError('W2_WRITE_SENTINEL')
for name in ('init', 'register_package', 'inspect_package', 'submit_run',
             'publish_record', 'propose_genome', 'genome_operation', 'doctor',
             'materialize_artifact', 'get_package'):
    if hasattr(WorkspaceClient, name):
        setattr(WorkspaceClient, name, forbidden)

def audit(event, args):
    if event == 'open':
        path, mode, flags = args
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        )
        paths = (path,) if writing else ()
    elif event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.replace'}:
        paths = args[:2] if event in {'os.rename', 'os.replace'} else args[:1]
    else:
        return
    for path in paths:
        if isinstance(path, (str, bytes, os.PathLike)):
            candidate = Path(os.fsdecode(path)).resolve()
            if candidate == root or root in candidate.parents:
                forbidden()
sys.addaudithook(audit)
print('W2_READONLY_GUARD_READY', file=sys.stderr, flush=True)
""",
        encoding="utf-8",
    )
    return {
        "PYTHONPATH": str(guard) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def failed_cli(args, *, env=None):
    result = subprocess.run(
        cli_command(*args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
    )
    assert result.returncode == 2, result.stderr
    assert "Manager GUI listening" not in result.stdout
    assert "Traceback" not in result.stderr
    assert "W2_WRITE_SENTINEL" not in result.stderr
    assert "Error in sitecustomize" not in result.stderr
    if env and "W2_GUARDED_ROOT" in env:
        assert "W2_READONLY_GUARD_READY" in result.stderr
    return result.stderr


@pytest.mark.parametrize(
    ("args", "diagnostic"),
    [
        (("--provider", "invalid"), "invalid choice"),
        (("--provider", "workspace"), "requires --workspace-root"),
        (("--workspace-root", "{root}"), "requires --provider workspace"),
        (("--provider", "fixture", "--workspace-root", "{root}"), "requires --provider workspace"),
        (
            ("--provider", "workspace", "--workspace-root", "{root}", "--fixture", "partial"),
            "--fixture conflicts",
        ),
        (
            ("--provider", "workspace", "--workspace-root", "{root}", "--fixture", "complete"),
            "--fixture conflicts",
        ),
    ],
)
def test_conflicting_or_invalid_cli_configuration_fails_without_writes(
    tmp_path, readonly_guard, args, diagnostic
):
    root = tmp_path / "must-not-exist"
    before = inventory(tmp_path)
    env = {**readonly_guard, "W2_GUARDED_ROOT": str(root)}
    assert diagnostic in failed_cli(
        [str(root) if arg == "{root}" else arg for arg in args], env=env
    )
    assert not root.exists()
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("root_kind", ["missing", "empty-directory", "regular-file"])
def test_invalid_workspace_root_fails_at_public_seam_without_initialization(
    tmp_path, readonly_guard, root_kind
):
    root = tmp_path / "invalid-root"
    if root_kind == "empty-directory":
        root.mkdir()
    elif root_kind == "regular-file":
        root.write_text("not a workspace", encoding="utf-8")
    before = inventory(tmp_path)
    diagnostic = failed_cli(
        ["--provider", "workspace", "--workspace-root", root],
        env={**readonly_guard, "W2_GUARDED_ROOT": str(root)},
    )
    code = "workspace_root_missing" if root_kind == "missing" else "workspace_uninitialized"
    assert f"[{code}]" in diagnostic
    assert inventory(tmp_path) == before


def test_public_workspace_read_failure_exits_instead_of_serving_fixtures(
    workspace_root, readonly_guard
):
    before = inventory(workspace_root)
    diagnostic = failed_cli(
        ["--provider", "workspace", "--workspace-root", workspace_root],
        env={**readonly_guard, "W2_GUARDED_ROOT": str(workspace_root), "W2_FAIL_READ": "1"},
    )
    assert "[workspace_read_failed]" in diagnostic
    assert "injected public read failure" in diagnostic
    assert inventory(workspace_root) == before


@pytest.mark.parametrize("operation", ["initialization", "directory-write"])
def test_readonly_sentinels_are_active(tmp_path, readonly_guard, operation):
    root = tmp_path / "guard-self-test"
    command = (
        "from strategy_workspace import WorkspaceClient; WorkspaceClient(root).init()"
        if operation == "initialization"
        else "root.mkdir()"
    )
    before = inventory(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import os; "
            "root = Path(os.environ['W2_GUARDED_ROOT']); " + command,
        ],
        env={**os.environ, **readonly_guard, "W2_GUARDED_ROOT": str(root)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode != 0
    assert "W2_READONLY_GUARD_READY" in result.stderr
    assert "W2_WRITE_SENTINEL" in result.stderr
    assert not root.exists()
    assert inventory(tmp_path) == before


def test_unreadable_workspace_root_fails_without_writes(workspace_root, readonly_guard):
    before = inventory(workspace_root)
    identity = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    sid = re.search(r"S-1-[0-9-]+", identity).group()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    security.GetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    security.SetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    handle = kernel.CreateFileW(str(workspace_root), 0x60000, 7, None, 3, 0x02000000, None)
    assert handle != ctypes.c_void_p(-1).value
    descriptor, dacl = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        assert (
            security.GetSecurityInfo(
                handle, 1, 4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor)
            )
            == 0
        )
        try:
            subprocess.run(
                ["icacls", str(workspace_root), "/deny", f"*{sid}:(R)"],
                capture_output=True,
                check=True,
            )
            diagnostic = failed_cli(
                ["--provider", "workspace", "--workspace-root", workspace_root],
                env={**readonly_guard, "W2_GUARDED_ROOT": str(workspace_root)},
            )
            assert "[workspace_read_failed]" in diagnostic
        finally:
            assert security.SetSecurityInfo(handle, 1, 4, None, None, dacl, None) == 0
    finally:
        kernel.LocalFree(descriptor)
        kernel.CloseHandle(handle)
    assert inventory(workspace_root) == before


@pytest.mark.parametrize(
    "args", [(), ("--fixture", "complete"), ("--provider", "fixture", "--fixture", "complete")]
)
def test_fixture_cli_keeps_explicit_sample_identity(args):
    with cli_server(*args) as base:
        for lang, identity in (("zh-CN", "样例数据"), ("en", "Sample data")):
            with urlopen(f"{base}/?view=search&lang={lang}", timeout=5) as response:
                document = response.read().decode("utf-8")
            assert identity in document
            assert 'data-sample-banner="fixture"' in document
            assert "workspace-view-" not in document


def test_cli_all_routes_use_workspace_resources_and_never_fallback(workspace_root, readonly_guard):
    schema = "apex-research.study-registration.v1"
    WorkspaceClient(workspace_root).publish_record(
        {
            "record_id": "w2-real-study",
            "record_type": schema,
            "payload": {"schema": schema, "title": "W2 isolated study", "body": "Published intent"},
        }
    )
    before = inventory(workspace_root)
    env = {**readonly_guard, "W2_GUARDED_ROOT": str(workspace_root)}
    supported = {
        "atlas": "records",
        "stories": "intent",
        "evidence": "records",
        "lineage": "nodes",
        "history": "events",
        "source-documents": "documents",
        "search": "records",
        "portal": "reports",
    }
    with cli_server("--provider", "workspace", "--workspace-root", workspace_root, env=env) as base:
        models = {}
        for view in ViewId:
            with urlopen(
                f"{base}/api/read-model?view={view}&fixture=complete", timeout=5
            ) as response:
                model = json.load(response)
            models[view.value] = model
            assert model["snapshot_token"].startswith("workspace-view-")
            if view.value in supported:
                assert supported[view.value] in model["data"]
                assert model["data"]["coverage"]["publications_observed"] == 1
                assert model["data"]["public_input"]["records"][0]["record_id"] == "w2-real-study"
            else:
                assert model["availability"]["status"] == "api_unavailable"
                assert model["data"] == {}
                assert "absence is not confirmed" in model["availability"]["reason"]
            with urlopen(f"{base}/?view={view}&fixture=complete", timeout=5) as response:
                assert 'data-sample-banner="fixture"' not in response.read().decode("utf-8")
            with urlopen(
                f"{base}/api/read-model?view={view}&snapshot_token=unknown", timeout=5
            ) as response:
                drift = json.load(response)
            assert drift["availability"]["status"] == "stale"
            assert drift["data"] == {}
        assert models["memory"] == models["memory-failures"]
    assert inventory(workspace_root) == before


def test_workspace_http_preserves_get_head_export_and_rejects_writes(
    published_workspace, readonly_guard
):
    root = published_workspace
    before = inventory(root)
    env = {**readonly_guard, "W2_GUARDED_ROOT": str(root)}
    with cli_server("--provider", "workspace", "--workspace-root", root, env=env) as base:
        for path in (
            "/?view=atlas",
            "/index.html",
            "/health",
            "/api/read-model?view=atlas",
            "/api/export?view=atlas",
        ):
            with urlopen(base + path, timeout=5) as response:
                body = response.read()
                content_type = response.headers["Content-Type"]
                assert response.headers["Cache-Control"] == "no-store"
            with urlopen(Request(base + path, method="HEAD"), timeout=5) as response:
                assert response.read() == b""
                assert int(response.headers["Content-Length"]) == len(body)
                assert response.headers["Content-Type"] == content_type
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                with pytest.raises(HTTPError) as error:
                    urlopen(Request(base + path, method=method), timeout=5)
                assert error.value.code == 405
                assert error.value.headers["Allow"] == "GET, HEAD"
        with urlopen(base + "/api/read-model?view=atlas", timeout=5) as response:
            model = json.load(response)
        with urlopen(base + "/api/export?view=atlas&lang=en&mode=raw", timeout=5) as response:
            exported = json.load(response)
        assert exported["read_model"] == model
        assert "lang" not in exported["query_params"]
        assert "mode" not in exported["query_params"]
        assert any(error["code"] == "unsupported_record_type" for error in model["errors"])
    assert inventory(root) == before


def test_mode_and_language_links_retain_real_object_and_read_context(published_workspace):
    root = published_workspace
    with cli_server("--provider", "workspace", "--workspace-root", root) as base:
        with urlopen(base + "/api/read-model?view=search", timeout=5) as response:
            token = json.load(response)["snapshot_token"]
        context = (
            "&record_id=w2-study&root=w2-study&scope=owner-scope"
            "&filter=state%3Dknown&filter=type%3Dstudy&opaque_ref=owner-ref&panel=inspector&q=Published"
            f"&snapshot_token={token}"
        )
        for view in ViewId:
            for mode in ("reader", "expert", "raw"):
                for lang in ("zh-CN", "en"):
                    with urlopen(
                        f"{base}/?view={view}&mode={mode}&lang={lang}{context}", timeout=5
                    ) as response:
                        document = response.read().decode("utf-8")
                    links = re.findall(r'class="reader-mode-link"[^>]+href="([^"]+)"', document)
                    links += re.findall(r'hreflang="[^"]+" href="([^"]+)"', document)
                    assert len(links) == 4
                    for link in links:
                        pairs = parse_qsl(urlsplit(unescape(link)).query, keep_blank_values=True)
                        for pair in parse_qsl(context.lstrip("&")):
                            assert pair in pairs, (view, mode, lang, pair)
                        with urlopen(base + unescape(link), timeout=5) as response:
                            assert response.status == 200
                    with urlopen(
                        f"{base}/api/read-model?view={view}{context}", timeout=5
                    ) as response:
                        expected = response.read()
                    with urlopen(
                        f"{base}/api/read-model?view={view}&mode={mode}&lang={lang}{context}",
                        timeout=5,
                    ) as response:
                        assert response.read() == expected


def test_real_originals_containing_sample_words_are_not_rewritten(workspace_root):
    original = "编造的示例 / A fabricated example / Sample data: quoted owner research text."
    schema = "apex-research.study-registration.v1"
    publication = WorkspaceClient(workspace_root).publish_record(
        {
            "record_id": "w2-quoted-original",
            "record_type": schema,
            "payload": {"schema": schema, "title": "Quoted source", "body": original},
        },
        artifacts=[
            {
                "source": original.encode("utf-8"),
                "media_type": "text/plain",
                "name": "Original quote",
            }
        ],
    )
    with cli_server("--provider", "workspace", "--workspace-root", workspace_root) as base:
        for lang in ("zh-CN", "en"):
            with urlopen(f"{base}/?view=atlas&lang={lang}", timeout=5) as response:
                document = response.read().decode("utf-8")
            assert original in document
            assert 'class="source-support"' in document
            assert 'data-sample-banner="fixture"' not in document
        with urlopen(base + "/api/read-model?view=atlas", timeout=5) as response:
            model = json.load(response)
        assert model["data"]["public_input"]["records"][0] == publication
        assert model["data"]["sources"][0]["text"] == original
