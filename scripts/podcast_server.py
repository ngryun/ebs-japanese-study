#!/usr/bin/env python3
"""Serve the private podcast feed with HEAD and byte-range support."""

from __future__ import annotations

import mimetypes
import os
import posixpath
import re
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
DEFAULT_SITE_ROOT = Path.home() / "Library/Application Support/EBSPrivatePodcast/site"
SITE_ROOT = Path(os.environ.get("PODCAST_SITE_ROOT", str(DEFAULT_SITE_ROOT))).expanduser().resolve()
HOST = os.environ.get("PODCAST_BIND_HOST", "0.0.0.0")
PORT = int(os.environ.get("PODCAST_PORT", "8081"))
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


def content_type_for(target: Path) -> str:
    # macOS maps .m4a to audio/mp4a-latm, while podcast feeds and clients
    # expect an MPEG-4 container to be served as audio/mp4.
    if target.suffix.lower() == ".m4a":
        return "audio/mp4"
    return mimetypes.guess_type(str(target))[0] or "application/octet-stream"


class PodcastHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._serve(send_body=True)

    def do_HEAD(self) -> None:
        self._serve(send_body=False)

    def _serve(self, send_body: bool) -> None:
        target = self._resolve_path()
        if target is None or not target.is_file():
            self.send_error(404, "File not found")
            return

        total_size = target.stat().st_size
        start = 0
        end = total_size - 1
        status = 200

        range_header = self.headers.get("Range")
        if range_header:
            match = RANGE_RE.fullmatch(range_header.strip())
            if not match:
                self._send_range_not_satisfiable(total_size)
                return

            start_text, end_text = match.groups()
            if start_text == "" and end_text == "":
                self._send_range_not_satisfiable(total_size)
                return

            if start_text == "":
                suffix_length = int(end_text)
                if suffix_length <= 0:
                    self._send_range_not_satisfiable(total_size)
                    return
                start = max(total_size - suffix_length, 0)
            else:
                start = int(start_text)
                if end_text:
                    end = int(end_text)

            if start >= total_size or end < start:
                self._send_range_not_satisfiable(total_size)
                return

            end = min(end, total_size - 1)
            status = 206

        content_length = end - start + 1
        content_type = content_type_for(target)

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", formatdate(target.stat().st_mtime, usegmt=True))
        self.send_header("Cache-Control", "no-cache")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_size}")
        self.end_headers()

        if not send_body:
            return

        with target.open("rb") as handle:
            handle.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = handle.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _resolve_path(self) -> Path | None:
        raw_path = urlsplit(self.path).path
        normalized = posixpath.normpath(unquote(raw_path))
        parts = [part for part in normalized.split("/") if part not in ("", ".", "..")]
        candidate = SITE_ROOT.joinpath(*parts) if parts else SITE_ROOT / "index.html"
        try:
            resolved = candidate.resolve(strict=True)
            if resolved.is_dir():
                resolved = (resolved / "index.html").resolve(strict=True)
        except FileNotFoundError:
            return None

        if SITE_ROOT == resolved or SITE_ROOT in resolved.parents:
            return resolved
        return None

    def _send_range_not_satisfiable(self, total_size: int) -> None:
        self.send_response(416)
        self.send_header("Content-Range", f"bytes */{total_size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format_str: str, *args) -> None:
        super().log_message(format_str, *args)


def main() -> None:
    SITE_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), PodcastHandler)
    print(f"Serving private podcast on http://{HOST}:{PORT} from {SITE_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
