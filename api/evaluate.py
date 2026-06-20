"""Airgap.AI policy engine as a Vercel Python serverless function.

Stateless: scores one proposed agent action against safety rules and returns
ALLOW / APPROVE / BLOCK. Pure standard library — no dependencies, so the build
cannot fail on packages. Served by Vercel at /api/evaluate.
"""

import json
from http.server import BaseHTTPRequestHandler

# ---- Policy limits (tune here) ----
TOKEN_LIMIT = 50000
API_LIMIT = 100
LOOP_THRESHOLD = 5

DESTRUCTIVE_TYPES = {"FS_WRITE", "FS_DELETE", "DB_WRITE", "EXEC", "DB_QUERY"}
PROD_MARKERS = ("prod", "production", "_prod")
DESTRUCTIVE_PATTERNS = ("drop ", "delete from", "truncate", "rm -rf", "overwrite", "format ")
DENYLIST = ("billing_prod", "secrets", "payments_prod")


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_request(data):
    """Accept nested {action, context} or a flat body."""
    if isinstance(data.get("action"), dict):
        action = data["action"]
        context = data["context"] if isinstance(data.get("context"), dict) else {}
    else:
        action = data
        context = data["context"] if isinstance(data.get("context"), dict) else {
            "tokensSpent": data.get("tokensSpent", 0),
            "apiCalls": data.get("apiCalls", 0),
            "recentTargets": data.get("recentTargets", []),
        }
    return action, context


def evaluate(action, context):
    a_type = str(action.get("type", "")).upper()
    raw_target = action.get("target", "")
    target = str(raw_target).lower()
    payload_json = json.dumps(action.get("payload", {})).lower()
    tokens = _int(action.get("tokens", 0))

    tokens_spent = _int(context.get("tokensSpent", 0))
    api_calls = _int(context.get("apiCalls", 0))
    recent = context.get("recentTargets", []) or []

    # Rule 1 — destructive on prod / destructive payload pattern
    destructive_type = a_type in DESTRUCTIVE_TYPES
    hits_prod = any(m in target for m in PROD_MARKERS)
    bad_pattern = any(p in payload_json for p in DESTRUCTIVE_PATTERNS)
    if (destructive_type and hits_prod) or bad_pattern:
        return {"verdict": "BLOCK",
                "reason": "Destructive command pattern detected on production target.",
                "tags": ["High impact", "Requires auth", "Irreversible"], "hi": True}

    # Rule 2 — loop / runaway
    if sum(1 for t in recent if t == raw_target) >= LOOP_THRESHOLD:
        return {"verdict": "BLOCK",
                "reason": "Repeated call loop detected - possible runaway agent.",
                "tags": ["Cost risk", "Loop pattern"], "hi": True}

    # Rule 3 — token budget
    if tokens_spent + tokens > TOKEN_LIMIT:
        return {"verdict": "APPROVE",
                "reason": "Token budget threshold exceeded - confirm before continuing.",
                "tags": ["Budget", "Cost risk"], "hi": False}

    # Rule 4 — API budget
    if api_calls + 1 > API_LIMIT:
        return {"verdict": "APPROVE",
                "reason": "API request budget exceeded - confirm before continuing.",
                "tags": ["Budget"], "hi": False}

    # Rule 5 — deny-list
    if any(d in target for d in DENYLIST):
        return {"verdict": "BLOCK",
                "reason": "Target is on the protected resource deny-list.",
                "tags": ["Restricted", "Requires auth"], "hi": True}

    # Rule 6 — default allow
    return {"verdict": "ALLOW", "reason": "Within policy.", "tags": [], "hi": False}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        if body is not None:
            self.wfile.write(json.dumps(body).encode("utf-8"))

    def do_OPTIONS(self):
        self._send(204, None)

    def do_GET(self):
        # health check / connection ping
        self._send(200, {"status": "ok", "service": "airgap"})

    def do_POST(self):
        try:
            length = int(self.headers.get("content-length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            data = json.loads(raw or b"{}")
        except Exception:
            return self._send(400, {"error": "Invalid or empty JSON body."})

        if not isinstance(data, dict) or not data:
            return self._send(400, {"error": "Invalid or empty JSON body."})

        action, context = parse_request(data)
        if not isinstance(action, dict) or "type" not in action:
            return self._send(400, {"error": "Body must contain an action with a 'type' field."})

        self._send(200, evaluate(action, context))
