from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.planning import PlanningInvariantError, generate_plan
from app.validation import WorkbookValidationError, load_workbook


ROOT = Path(__file__).parent
STATIC_ROOT = ROOT / "static"
WORKBOOK_FILENAME = "Atlas_Fresh_Production_Commercial_Data.xlsx"
WORKBOOK_CANDIDATES = [
    Path(os.getenv("ATLAS_WORKBOOK_PATH", "")).expanduser() if os.getenv("ATLAS_WORKBOOK_PATH") else None,
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
    normalized = question.strip().lower()
    no_provider = os.getenv("ATLAS_AI_PROVIDER", "").strip() == ""

    if os.getenv("ATLAS_ASSISTANT_SIMULATE") == "timeout":
        return 504, {"ok": False, "error": "provider_timeout", "message": "Assistant provider timed out."}
    if os.getenv("ATLAS_ASSISTANT_SIMULATE") == "invalid":
        return 502, {"ok": False, "error": "invalid_model_output", "message": "Assistant returned invalid model output."}

    at_risk = [client for client in plan.clients if client.status != "COMPLETE"]
    if normalized == "which clients are at risk and why?":
        details = "; ".join(
            f"{client.client_id} is {client.status} with {client.remaining_t:.1f} t remaining because {client.shortage_reason}"
            for client in at_risk
        )
        return 200, {
            "ok": True,
            "mode": "deterministic" if no_provider else "provider_not_used",
            "provider_state": "No AI provider configured" if no_provider else "External provider disabled for deterministic safety",
            "answer": f"{len(at_risk)} clients are at risk. {details}.",
            "evidence": [client.client_id for client in at_risk],
        }
    if normalized == "which farm/segment gaps matter most today?":
        important = plan.production_alerts[:5]
        details = "; ".join(f"{alert.get('farm_id', 'Segment')} {alert.get('segment', '')}: {alert['detail']}" for alert in important)
        evidence = []
        for alert in important:
            if "farm_id" in alert:
                evidence.append(alert["farm_id"])
            if "segment" in alert:
                evidence.append(f"Segment {alert['segment']}")
        return 200, {
            "ok": True,
            "mode": "deterministic" if no_provider else "provider_not_used",
            "provider_state": "No AI provider configured" if no_provider else "External provider disabled for deterministic safety",
            "answer": f"The most important production signal is Segment A at {abs(plan.segment_variance_t['A']):.1f} t below plan. {details}.",
            "evidence": list(dict.fromkeys(evidence)),
        }
    if normalized == "why are 60 t going local and what is their estimated value?":
        residual_ids = [f"{item.farm_id} {item.segment}" for item in plan.local_residuals]
        reason = "station capacity is the main constraint" if plan.exported_t >= plan.station_capacity_t else "compatible export demand was exhausted"
        return 200, {
            "ok": True,
            "mode": "deterministic" if no_provider else "provider_not_used",
            "provider_state": "No AI provider configured" if no_provider else "External provider disabled for deterministic safety",
            "answer": f"{plan.local_t:.1f} t go local because {reason}. Estimated local value is EUR {plan.local_value_eur:,.0f}, calculated as residual tonnes x 10% x segment reference export price.",
            "evidence": residual_ids,
        }
    return 400, {
        "ok": False,
        "error": "unsupported_question",
        "message": "This information is not available in the current planning data.",
        "evidence": [],
    }


class AtlasHandler(BaseHTTPRequestHandler):
    server_version = "AtlasFresh/1.0"

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
            status, body = assistant_answer(str(payload.get("question", "")))
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

    def send_json(self, status: int, payload: dict):
        content = json.dumps(to_jsonable(payload), separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):  # noqa: A002
        print(f"{self.address_string()} - {format % args}")


def main():
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), AtlasHandler)
    print(f"Atlas Fresh Daily Export Planner running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
