#!/usr/bin/env python3
"""Local-only AXM snapshot server for capability and AI-native user-facing testing.

Serves one already materialized snapshot from 127.0.0.1 and exposes a tiny local control API:
- POST /api/command       enqueue an AI input sequence for the open capability lab
- GET  /api/next-command pop the next sequence
- POST /api/evidence      persist exact snapshot-bound user-facing evidence
- POST /api/command-result record command completion metadata

The server never executes source-module CLI commands. Browser-facing code executes only because
the user/AI loads a captured module page in the test surface.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import re
import threading
from typing import Any
import urllib.parse
import webbrowser

MAX_JSON_BYTES = 25 * 1024 * 1024
MAX_CANVAS_BYTES = 12 * 1024 * 1024
SUPPORTED_ACTIONS = {
    "tap_key", "key_down", "key_up", "type_text", "wait", "click",
    "click_selector", "focus_selector", "reload", "snapshot",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    return text[:80] or "surface"


def validate_command(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("command body must be a JSON object")
    actions = payload.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("command.actions must be a non-empty array")
    if len(actions) > 500:
        raise ValueError("command contains too many actions")
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"action {index} must be an object")
        kind = str(action.get("type") or "")
        if kind not in SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported action type: {kind}")
    surface = payload.get("surface")
    if surface is not None and not isinstance(surface, str):
        raise ValueError("surface must be a string when supplied")
    return {"surface": surface, "actions": actions, "label": payload.get("label")}


def decode_canvas_data_url(data_url: str) -> bytes:
    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        raise ValueError("only PNG data URLs are accepted for canvas evidence")
    raw = base64.b64decode(data_url[len(prefix):], validate=True)
    if len(raw) > MAX_CANVAS_BYTES:
        raise ValueError("canvas PNG exceeds evidence size limit")
    return raw


def persist_evidence(snapshot: Path, payload: dict[str, Any], sequence: int) -> dict[str, Any]:
    root = snapshot / "evidence" / "user-facing"
    root.mkdir(parents=True, exist_ok=True)
    surface = safe_name(str(payload.get("surface") or payload.get("module") or "surface"))
    stem = f"{sequence:06d}_{surface}"
    record = json.loads(json.dumps(payload))
    record.setdefault("server_record", {})
    record["server_record"].update({
        "recorded_at_utc": utc_now(),
        "sequence": sequence,
        "snapshot_relative_evidence_root": "evidence/user-facing",
    })

    saved_canvases: list[dict[str, Any]] = []
    canvases = record.get("canvases")
    if isinstance(canvases, list):
        for index, canvas in enumerate(canvases):
            if not isinstance(canvas, dict):
                continue
            data_url = canvas.pop("data_url", None)
            if not data_url:
                continue
            try:
                raw = decode_canvas_data_url(str(data_url))
                filename = f"{stem}_canvas_{index}.png"
                path = root / filename
                path.write_bytes(raw)
                digest = hashlib.sha256(raw).hexdigest()
                canvas.update({
                    "capture_path": f"evidence/user-facing/{filename}",
                    "sha256": digest,
                    "bytes": len(raw),
                    "server_persisted": True,
                })
                saved_canvases.append({"path": canvas["capture_path"], "sha256": digest, "bytes": len(raw)})
            except Exception as exc:
                canvas.update({"server_persisted": False, "server_error": str(exc)})

    json_path = root / f"{stem}.json"
    json_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "sequence": sequence,
        "recorded_at_utc": record["server_record"]["recorded_at_utc"],
        "module": record.get("module"),
        "surface": record.get("surface"),
        "label": record.get("label"),
        "record": f"evidence/user-facing/{json_path.name}",
        "canvas_captures": saved_canvases,
    }
    with (root / "INDEX.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, sort_keys=True) + "\n")
    return summary


class ServerState:
    def __init__(self, snapshot: Path):
        self.snapshot = snapshot
        self.commands: queue.Queue[dict[str, Any]] = queue.Queue()
        self.lock = threading.Lock()
        self.command_sequence = 0
        self.evidence_sequence = 0
        self.result_sequence = 0

    def next_command_id(self) -> int:
        with self.lock:
            self.command_sequence += 1
            return self.command_sequence

    def next_evidence_id(self) -> int:
        with self.lock:
            self.evidence_sequence += 1
            return self.evidence_sequence

    def next_result_id(self) -> int:
        with self.lock:
            self.result_sequence += 1
            return self.result_sequence


class SnapshotHandler(SimpleHTTPRequestHandler):
    server_version = "AXMMonolithLocal/0.3"

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any):
        super().__init__(*args, directory=directory, **kwargs)

    @property
    def state(self) -> ServerState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > MAX_JSON_BYTES:
            raise ValueError("invalid or excessive JSON body size")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            self._json({
                "ok": True,
                "local_only": True,
                "snapshot": str(self.state.snapshot),
                "queued_commands": self.state.commands.qsize(),
                "truth_boundary": "server provides local transport and evidence persistence; it does not make synthetic events trusted browser input",
            })
            return
        if parsed.path == "/api/next-command":
            try:
                item = self.state.commands.get_nowait()
            except queue.Empty:
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            self._json(item)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/command":
                command = validate_command(payload)
                command.update({"id": self.state.next_command_id(), "queued_at_utc": utc_now()})
                self.state.commands.put(command)
                self._json({"accepted": True, "command": command}, status=202)
                return
            if parsed.path == "/api/evidence":
                if not isinstance(payload, dict):
                    raise ValueError("evidence body must be an object")
                summary = persist_evidence(self.state.snapshot, payload, self.state.next_evidence_id())
                self._json({"saved": True, **summary}, status=201)
                return
            if parsed.path == "/api/command-result":
                if not isinstance(payload, dict):
                    raise ValueError("command result must be an object")
                root = self.state.snapshot / "evidence" / "user-facing"
                root.mkdir(parents=True, exist_ok=True)
                payload = {**payload, "server_recorded_at_utc": utc_now(), "sequence": self.state.next_result_id()}
                with (root / "COMMAND_RESULTS.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, sort_keys=True) + "\n")
                self._json({"saved": True})
                return
            self._json({"error": "unknown API path"}, status=404)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json({"error": str(exc)}, status=400)


def serve(snapshot: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    snapshot = snapshot.resolve()
    if not (snapshot / "OPEN_ME.html").exists():
        raise ValueError(f"snapshot has no OPEN_ME.html: {snapshot}")
    state = ServerState(snapshot)

    def handler(*args: Any, **kwargs: Any) -> SnapshotHandler:
        return SnapshotHandler(*args, directory=str(snapshot), **kwargs)

    server = ThreadingHTTPServer((host, port), handler)
    server.state = state  # type: ignore[attr-defined]
    url = f"http://{host}:{server.server_port}/OPEN_ME.html"
    print(f"AXM capability lab: {url}")
    print(f"Snapshot: {snapshot}")
    print("AI command endpoint: POST /api/command")
    print("Evidence is written only inside snapshot/evidence/user-facing/.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local AXM capability lab.")
    finally:
        server.server_close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Serve one AXM monolith snapshot for local user-facing/AI testing")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true", dest="open_browser")
    return p


def main() -> int:
    args = parser().parse_args()
    serve(args.snapshot, port=args.port, open_browser=args.open_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
