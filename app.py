"""
Airgap.AI — circuit breaker / firewall for autonomous AI agents.

A stateless policy service: it scores a single proposed agent action against
safety rules and returns ALLOW / APPROVE / BLOCK *before* the action executes.
No state is stored between requests — the caller supplies running session
context with every call.

Built to the airgap.plain spec.
"""

import json
from flask import Flask, request, jsonify
from flask_cors import CORS

# --------------------------------------------------------------------------
# Policy limits — tune these.
# --------------------------------------------------------------------------
TOKEN_LIMIT = 50000
API_LIMIT = 100
LOOP_THRESHOLD = 5

# Supporting policy data (kept beside the limits for the same reason).
DESTRUCTIVE_TYPES = {"FS_WRITE", "FS_DELETE", "DB_WRITE", "EXEC", "DB_QUERY"}
PROD_MARKERS = ("prod", "production", "_prod")
DESTRUCTIVE_PATTERNS = ("drop ", "delete from", "truncate", "rm -rf", "overwrite", "format ")
DENYLIST = ("billing_prod", "secrets", "payments_prod")

app = Flask(__name__)
CORS(app)  # allow a browser frontend from any origin to call this service


# --------------------------------------------------------------------------
# Request parsing — tolerant of two body shapes:
#   nested:  {"action": {...}, "context": {...}}
#   flat:    {"type": ..., "target": ..., "tokensSpent": ..., ...}
# --------------------------------------------------------------------------
def parse_request(data):
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


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# The policy engine. Rules are checked top to bottom; the first match wins.
# --------------------------------------------------------------------------
def evaluate(action, context):
    a_type = str(action.get("type", "")).upper()
    raw_target = action.get("target", "")
    target = str(raw_target).lower()
    payload_json = json.dumps(action.get("payload", {})).lower()
    tokens = _int(action.get("tokens", 0))

    tokens_spent = _int(context.get("tokensSpent", 0))
    api_calls = _int(context.get("apiCalls", 0))
    recent = context.get("recentTargets", []) or []

    # Rule 1 — destructive command on production (or destructive payload pattern).
    destructive_type = a_type in DESTRUCTIVE_TYPES
    hits_prod = any(marker in target for marker in PROD_MARKERS)
    bad_pattern = any(pat in payload_json for pat in DESTRUCTIVE_PATTERNS)
    if (destructive_type and hits_prod) or bad_pattern:
        return {
            "verdict": "BLOCK",
            "reason": "Destructive command pattern detected on production target.",
            "tags": ["High impact", "Requires auth", "Irreversible"],
            "hi": True,
        }

    # Rule 2 — loop / runaway agent.
    if sum(1 for t in recent if t == raw_target) >= LOOP_THRESHOLD:
        return {
            "verdict": "BLOCK",
            "reason": "Repeated call loop detected - possible runaway agent.",
            "tags": ["Cost risk", "Loop pattern"],
            "hi": True,
        }

    # Rule 3 — token budget.
    if tokens_spent + tokens > TOKEN_LIMIT:
        return {
            "verdict": "APPROVE",
            "reason": "Token budget threshold exceeded - confirm before continuing.",
            "tags": ["Budget", "Cost risk"],
            "hi": False,
        }

    # Rule 4 — API budget.
    if api_calls + 1 > API_LIMIT:
        return {
            "verdict": "APPROVE",
            "reason": "API request budget exceeded - confirm before continuing.",
            "tags": ["Budget"],
            "hi": False,
        }

    # Rule 5 — protected resource deny-list.
    if any(d in target for d in DENYLIST):
        return {
            "verdict": "BLOCK",
            "reason": "Target is on the protected resource deny-list.",
            "tags": ["Restricted", "Requires auth"],
            "hi": True,
        }

    # Rule 6 — default allow.
    return {"verdict": "ALLOW", "reason": "Within policy.", "tags": [], "hi": False}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.get("/")
def health():
    return jsonify({"status": "ok", "service": "airgap"}), 200


@app.post("/evaluate")
def evaluate_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Invalid or empty JSON body."}), 400

    action, context = parse_request(data)
    if not isinstance(action, dict) or "type" not in action:
        return jsonify({"error": "Body must contain an action with a 'type' field."}), 400

    return jsonify(evaluate(action, context)), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
