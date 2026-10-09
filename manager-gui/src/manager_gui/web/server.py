"""Dependency-free local HTTP server for the Manager GUI shell."""

from __future__ import annotations

import argparse
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from ..fixtures import FixtureState
from ..models import MANAGER_READ_MODEL_SCHEMA
from ..provider import ManagerDataProvider
from .app import ManagerGUIApp
from .i18n import DEFAULT_LOCALE, Locale, Translator


class ManagerGUIServer(ThreadingHTTPServer):
    """HTTP server carrying the app instance without global mutable state."""

    app: ManagerGUIApp


class _RequestHandler(BaseHTTPRequestHandler):
    server: ManagerGUIServer
    server_version = "ManagerGUI/0.1"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            if self.server.app.request_state(self.path).context_value("ui_reader") == "1":
                self._send_text(
                    self.server.app.render_reader_json(self.path),
                    "application/json; charset=utf-8",
                )
                return
            self._send_text(self.server.app.render(self.path), "text/html; charset=utf-8")
            return
        if path == "/api/read-model":
            self._send_text(
                self.server.app.render_json(self.path),
                "application/json; charset=utf-8",
            )
            return
        if path == "/api/export":
            self._send_text(
                self.server.app.render_export(self.path),
                "application/json; charset=utf-8",
            )
            return
        if path == "/health":
            self._send_text(
                f'{{"status":"ok","read_only":true,"schema":"{MANAGER_READ_MODEL_SCHEMA}"}}',
                "application/json; charset=utf-8",
            )
            return
        self.send_error(404, "Not found")

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            if self.server.app.request_state(self.path).context_value("ui_reader") == "1":
                self._send_text(
                    self.server.app.render_reader_json(self.path),
                    "application/json; charset=utf-8",
                    head_only=True,
                )
                return
            self._send_text(
                self.server.app.render(self.path),
                "text/html; charset=utf-8",
                head_only=True,
            )
            return
        if path == "/api/read-model":
            self._send_text(
                self.server.app.render_json(self.path),
                "application/json; charset=utf-8",
                head_only=True,
            )
            return
        if path == "/api/export":
            self._send_text(
                self.server.app.render_export(self.path),
                "application/json; charset=utf-8",
                head_only=True,
            )
            return
        if path == "/health":
            self._send_text(
                f'{{"status":"ok","read_only":true,"schema":"{MANAGER_READ_MODEL_SCHEMA}"}}',
                "application/json; charset=utf-8",
                head_only=True,
            )
            return
        self.send_error(404, "Not found")

    def _reject_mutation(self) -> None:
        """Keep every HTTP mutation verb outside the read-only server surface."""

        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        self._reject_mutation()

    def do_PUT(self) -> None:
        self._reject_mutation()

    def do_PATCH(self) -> None:
        self._reject_mutation()

    def do_DELETE(self) -> None:
        self._reject_mutation()

    def _send_text(self, body: str, content_type: str, *, head_only: bool = False) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        """Keep fixture smoke tests quiet while retaining opt-in server logging."""

        del format, args


def create_server(
    *,
    app: ManagerGUIApp | None = None,
    provider: ManagerDataProvider | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    fixture: FixtureState | str = FixtureState.PARTIAL,
    default_locale: Locale | str = DEFAULT_LOCALE,
) -> ManagerGUIServer:
    """Create (but do not start) a local server for tests or embedding."""

    if app is not None and provider is not None:
        raise ValueError("pass app or provider, not both")
    selected_app = app or ManagerGUIApp(
        provider,
        default_fixture=fixture,
        default_locale=default_locale,
    )
    server = ManagerGUIServer((host, port), _RequestHandler)
    server.app = selected_app
    return server


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    fixture: FixtureState | str = FixtureState.PARTIAL,
    provider: ManagerDataProvider | None = None,
    default_locale: Locale | str = DEFAULT_LOCALE,
) -> None:
    """Serve until interrupted, with no mutation endpoint exposed."""

    server = create_server(
        host=host,
        port=port,
        fixture=fixture,
        provider=provider,
        default_locale=default_locale,
    )
    print(f"Manager GUI listening at http://{host}:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manager-gui-web",
        description="Run the read-only Manager GUI with fixture or Workspace data.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="bind port (default: 8765)")
    parser.add_argument(
        "--provider",
        choices=["fixture", "workspace"],
        default="fixture",
        help="data provider (default: fixture); workspace requires --workspace-root",
    )
    parser.add_argument(
        "--workspace-root",
        help="existing Workspace root; only valid with --provider workspace",
    )
    parser.add_argument(
        "--fixture",
        choices=[state.value for state in FixtureState],
        default=None,
        help="fixture availability state (default: partial); invalid with workspace provider",
    )
    parser.add_argument(
        "--lang",
        choices=[locale.value for locale in Locale],
        default=DEFAULT_LOCALE.value,
        help="default UI language (default: zh-CN)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    provider = None
    if args.provider == "workspace":
        if args.fixture is not None:
            parser.error("--fixture conflicts with --provider workspace")
        if not args.workspace_root:
            parser.error("--provider workspace requires --workspace-root")
        try:
            from strategy_workspace import WorkspaceError
        except ImportError as exc:
            parser.error(f"Workspace provider dependency unavailable: {exc}")
        from ..workspace import RetryingWorkspaceDataProvider

        try:
            provider = RetryingWorkspaceDataProvider(args.workspace_root)
        except WorkspaceError as exc:
            friendly = Translator(args.lang).t("workspace.startup_failed")
            parser.error(f"{friendly} Workspace provider startup failed [{exc.code}]: {exc}")
        except (OSError, ValueError) as exc:
            friendly = Translator(args.lang).t("workspace.startup_failed")
            parser.error(f"{friendly} Workspace provider startup failed: {exc}")
    elif args.workspace_root is not None:
        parser.error("--workspace-root requires --provider workspace")
    run_server(
        host=args.host,
        port=args.port,
        fixture=args.fixture or FixtureState.PARTIAL,
        provider=provider,
        default_locale=args.lang,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    sys.exit(main())


__all__ = ["ManagerGUIServer", "build_parser", "create_server", "main", "run_server"]
