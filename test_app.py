"""Unit tests for the Airgap policy service.

Covers every acceptance test in airgap.plain, plus rule-ordering and
edge cases. Run from the project root:  python -m unittest discover
"""

import json
import unittest

from app import app, evaluate, TOKEN_LIMIT, API_LIMIT, LOOP_THRESHOLD


class HealthCheckTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_returns_200_and_ok(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")
        self.assertEqual(resp.get_json()["service"], "airgap")


def _post(client, action, context=None):
    body = {"action": action, "context": context or {}}
    return client.post("/evaluate", data=json.dumps(body),
                       content_type="application/json")


class EvaluateAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    # Rule 1
    def test_exec_on_production_blocks(self):
        resp = _post(self.client, {"type": "EXEC", "target": "db-production"})
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["verdict"], "BLOCK")
        self.assertTrue(body["hi"])

    def test_destructive_payload_blocks(self):
        resp = _post(self.client, {
            "type": "API_CALL", "target": "analytics",
            "payload": {"sql": "drop table users"},
        })
        body = resp.get_json()
        self.assertEqual(body["verdict"], "BLOCK")
        self.assertTrue(body["hi"])

    # Rule 2
    def test_loop_blocks_and_tags_loop_pattern(self):
        tgt = "payments-api/charge"
        resp = _post(self.client,
                     {"type": "API_CALL", "target": tgt},
                     {"recentTargets": [tgt] * LOOP_THRESHOLD})
        body = resp.get_json()
        self.assertEqual(body["verdict"], "BLOCK")
        self.assertIn("Loop pattern", body["tags"])

    # Rule 3
    def test_token_budget_requires_approval(self):
        resp = _post(self.client,
                     {"type": "LLM_CALL", "target": "summariser", "tokens": 1000},
                     {"tokensSpent": 49500})
        body = resp.get_json()
        self.assertEqual(body["verdict"], "APPROVE")
        self.assertFalse(body["hi"])

    # Rule 4
    def test_api_budget_requires_approval(self):
        resp = _post(self.client,
                     {"type": "API_CALL", "target": "pricing-svc"},
                     {"apiCalls": API_LIMIT})
        self.assertEqual(resp.get_json()["verdict"], "APPROVE")

    # Rule 5
    def test_denylist_blocks(self):
        resp = _post(self.client, {"type": "API_CALL", "target": "secrets-store"})
        body = resp.get_json()
        self.assertEqual(body["verdict"], "BLOCK")
        self.assertIn("Restricted", body["tags"])

    # Rule 6
    def test_benign_action_allows_with_empty_tags(self):
        resp = _post(self.client,
                     {"type": "DB_QUERY", "target": "analytics_read", "tokens": 120},
                     {"tokensSpent": 200, "apiCalls": 3, "recentTargets": []})
        body = resp.get_json()
        self.assertEqual(body["verdict"], "ALLOW")
        self.assertEqual(body["tags"], [])

    # Malformed body
    def test_empty_body_returns_400(self):
        resp = self.client.post("/evaluate", data="", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_malformed_json_returns_400_and_does_not_crash(self):
        resp = self.client.post("/evaluate", data="{not json",
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        # service still alive afterwards
        self.assertEqual(self.client.get("/").status_code, 200)


class RuleOrderingTests(unittest.TestCase):
    """Rules are checked top-to-bottom; first match wins."""

    def test_destructive_beats_loop(self):
        # Prod-destructive AND looping -> Rule 1 (BLOCK destructive) wins.
        v = evaluate(
            {"type": "DB_WRITE", "target": "orders_prod"},
            {"recentTargets": ["orders_prod"] * LOOP_THRESHOLD},
        )
        self.assertEqual(v["reason"],
                         "Destructive command pattern detected on production target.")

    def test_loop_beats_token_budget(self):
        # Looping AND over token budget -> Rule 2 (loop) wins over Rule 3.
        v = evaluate(
            {"type": "API_CALL", "target": "loop-tgt", "tokens": 999999},
            {"tokensSpent": TOKEN_LIMIT, "recentTargets": ["loop-tgt"] * LOOP_THRESHOLD},
        )
        self.assertEqual(v["verdict"], "BLOCK")
        self.assertIn("Loop pattern", v["tags"])

    def test_db_query_read_on_prod_is_destructive_type(self):
        # DB_QUERY is treated as destructive per spec when target hits prod.
        v = evaluate({"type": "DB_QUERY", "target": "users_production"}, {})
        self.assertEqual(v["verdict"], "BLOCK")

    def test_loop_threshold_boundary(self):
        tgt = "x"
        below = evaluate({"type": "API_CALL", "target": tgt},
                         {"recentTargets": [tgt] * (LOOP_THRESHOLD - 1)})
        at = evaluate({"type": "API_CALL", "target": tgt},
                      {"recentTargets": [tgt] * LOOP_THRESHOLD})
        self.assertEqual(below["verdict"], "ALLOW")
        self.assertEqual(at["verdict"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
