"""A local page over the same report the CLI prints.

stdlib only, bound to 127.0.0.1: the report names paths and may quote a line
of somebody's diff, so it does not belong on an interface anyone can reach.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .diff import base_label, excluded, read_diff, repo_root, unmatched_patterns
from .report import build

STATIC = Path(__file__).parent / "static"
INDEX = STATIC / "index.html"


def make_handler(root: Path, base: str | None = None, staged: bool = False,
                 exclude: tuple[str, ...] = (), committed: bool = False,
                 paths: tuple[str, ...] = ()):
    def payload() -> dict:
        resolved = base_label(root, base, staged, committed)
        all_files = read_diff(root, base, staged, list(paths) or None,
                              committed=committed)
        files = [file for file in all_files if not excluded(file.path, exclude)]
        return build(files, str(root), resolved, excluded=len(all_files) - len(files),
                     only=tuple(paths))

    class Handler(BaseHTTPRequestHandler):
        server_version = "diffbrief/0.1"

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                try:
                    page = INDEX.read_bytes()
                except OSError:
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                        "error": f"missing {INDEX} — reinstall diffbrief"})
                else:
                    self._send(HTTPStatus.OK, page, "text/html; charset=utf-8")
            elif path == "/api/report":
                try:
                    self._json(HTTPStatus.OK, payload())
                except Exception as error:  # a bad ref must not kill the page
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def _json(self, status: int, body: dict) -> None:
            blob = json.dumps(body, ensure_ascii=False, indent=2).encode()
            self._send(status, blob, "application/json; charset=utf-8")

        def log_message(self, fmt: str, *args) -> None:
            return

    return Handler


def serve(root: Path, base: str | None = None, staged: bool = False,
          host: str = "127.0.0.1", port: int = 8765,
          exclude: tuple[str, ...] = (), committed: bool = False,
          paths: tuple[str, ...] = ()) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port),
                               make_handler(root, base, staged, exclude, committed, paths))


__all__ = ["serve", "make_handler", "INDEX", "repo_root"]
