from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from agent.service import assistant_answer as agent_assistant_answer
from app.planning import PlanningInvariantError, generate_plan
from app.validation import WorkbookValidationError, load_workbook


ROOT = Path(__file__).parent
STATIC_ROOT = ROOT / "static"
WORKBOOK_FILENAME = "Atlas_Fresh_Production_Commercial_Data.xlsx"
WORKBOOK_CANDIDATES = [
    Path(os.getenv("ATLAS_WORKBOOK_PATH", "")).expanduser() if os.getenv("ATLAS_WORKBOOK_PATH") else None,
    ROOT / "data" / WORKBOOK_FILENAME,
    ROOT / "public" / WORKBOOK_FILENAME,
    ROOT / WORKBOOK_FILENAME,
]

STATE = {
    "workbook": None,
    "plan": None,
    "validation_errors": [],
    "last_status": "EMPTY",
}


def to_jsonable(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


def resolve_workbook_path() -> Path:
    for candidate in WORKBOOK_CANDIDATES:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate
    searched = ", ".join(str(path) for path in WORKBOOK_CANDIDATES if path)
    raise FileNotFoundError(f"Workbook not found. Searched: {searched}")


def load_default_workbook():
    workbook = load_workbook(resolve_workbook_path())
    STATE["workbook"] = workbook
    STATE["plan"] = None
    STATE["validation_errors"] = []
    STATE["last_status"] = "DATA_VALIDATED"
    return workbook


def calculate_plan():
    workbook = STATE["workbook"] or load_default_workbook()
    plan = generate_plan(workbook)
    STATE["plan"] = plan
    STATE["last_status"] = "PLAN_CALCULATED"
    return plan


def assistant_answer(question: str):
    plan = STATE["plan"] or calculate_plan()
    return agent_assistant_answer(question, plan)



class AtlasHandler(BaseHTTPRequestHandler):
    server_version = "AtlasFresh/1.0"
    # Declare HTTP/1.1 support so the proxy can reuse keep-alive connections
    # instead of receiving ECONNRESET when Python closes the socket after each
    # HTTP/1.0 response.
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            workbook_path = resolve_workbook_path()
            self.send_json(200, {"ok": True, "status": STATE["last_status"], "workbook": workbook_path.name})
            return
        if parsed.path == "/api/plan":
            if STATE["plan"] is None:
                self.send_json(404, {"ok": False, "error": "empty_state", "message": "No calculated plan is available."})
                return
            self.send_json(200, {"ok": True, "plan": to_jsonable(STATE["plan"])})
            return
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/data/load":
            try:
                workbook = load_default_workbook()
            except WorkbookValidationError as exc:
                STATE["last_status"] = "VALIDATION_FAILED"
                STATE["validation_errors"] = exc.errors
                self.send_json(422, {"ok": False, "status": "Data validation failed", "errors": to_jsonable(exc.errors)})
                return
            except Exception as exc:
                STATE["last_status"] = "SERVER_ERROR"
                self.send_json(500, {"ok": False, "error": "server_error", "message": str(exc)})
                return
            self.send_json(200, {"ok": True, "status": "DATA_VALIDATED", "farms_count": len(workbook.farms), "clients_count": len(workbook.clients)})
            return

        if parsed.path == "/api/plan":
            try:
                plan = calculate_plan()
            except WorkbookValidationError as exc:
                STATE["last_status"] = "VALIDATION_FAILED"
                self.send_json(422, {"ok": False, "status": "Data validation failed", "errors": to_jsonable(exc.errors)})
                return
            except PlanningInvariantError as exc:
                STATE["last_status"] = "SERVER_ERROR"
                self.send_json(500, {"ok": False, "error": "planning_invariant_failed", "message": str(exc)})
                return
            except Exception as exc:
                STATE["last_status"] = "SERVER_ERROR"
                self.send_json(500, {"ok": False, "error": "server_error", "message": str(exc)})
                return
            self.send_json(200, {"ok": True, "plan": to_jsonable(plan)})
            return

        if parsed.path == "/api/assistant":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self.send_json(400, {"ok": False, "error": "bad_json", "message": "Invalid JSON request."})
                return
            try:
                status, body = assistant_answer(str(payload.get("question", "")))
            except Exception as exc:
                self.send_json(500, {"ok": False, "error": "server_error", "message": str(exc)})
                return
            self.send_json(status, body)
            return

        self.send_json(404, {"ok": False, "error": "not_found"})

    def serve_static(self, path: str):
        if path in ("", "/"):
            target = STATIC_ROOT / "index.html"
        else:
            target = (STATIC_ROOT / path.lstrip("/")).resolve()
            if not str(target).startswith(str(STATIC_ROOT.resolve())):
                self.send_json(403, {"ok": False, "error": "forbidden"})
                return
        if not target.exists() or not target.is_file():
            self.send_json(404, {"ok": False, "error": "not_found"})
            return
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }
        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_json(self, status: int, payload: dict):
        content = json.dumps(to_jsonable(payload), separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):  # noqa: A002
        print(f"{self.address_string()} - {format % args}")


class AtlasFreshServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that silently drops client-disconnect errors.

    BrokenPipeError / ConnectionResetError are normal network events (proxy
    retries, tab reloads, keep-alive races).  Printing a full traceback for
    every such event is noise; genuine server-side errors are still reported.
    """

    def handle_error(self, request, client_address):
        exc_type = sys.exc_info()[0]
        if exc_type is not None and issubclass(exc_type, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def main():
    port = int(os.getenv("PORT", "8080"))
    server = AtlasFreshServer(("127.0.0.1", port), AtlasHandler)
    print(f"Atlas Fresh Daily Export Planner running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
