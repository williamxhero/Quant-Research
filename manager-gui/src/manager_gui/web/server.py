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
from .i18n import DEFAULT_LOCALE, Locale


class ManagerGUIServer(ThreadingHTTPServer):
    """HTTP server carrying the app instance without global mutable state."""

    app: ManagerGUIApp


class _RequestHandler(BaseHTTPRequestHandler):
    server: ManagerGUIServer
    server_version = "ManagerGUI/0.1"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
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
        description="Run the read-only, fixture-backed Manager GUI WebUI shell.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="bind port (default: 8765)")
    parser.add_argument(
        "--fixture",
        choices=[state.value for state in FixtureState],
        default=FixtureState.PARTIAL.value,
        help="fixture availability state (default: partial)",
    )
    parser.add_argument(
        "--lang",
        choices=[locale.value for locale in Locale],
        default=DEFAULT_LOCALE.value,
        help="default UI language (default: zh-CN)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_server(host=args.host, port=args.port, fixture=args.fixture, default_locale=args.lang)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    sys.exit(main())


__all__ = ["ManagerGUIServer", "build_parser", "create_server", "main", "run_server"]
