#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

from __future__ import annotations

import argparse
import functools
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser


ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"


class NotesHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"", "/"}:
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", "/notes/")
            self.end_headers()
            return
        super().do_GET()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview the generated dist/ directory.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000).")
    parser.add_argument("--open", action="store_true", help="Open the browser automatically.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(NotesHandler, directory=str(DIST_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/notes/"
    print(f"Serving {DIST_DIR} at {url}")
    if args.open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
