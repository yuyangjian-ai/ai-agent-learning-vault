"""Boundary tests, independent of the table-driven fixture evaluation."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import build_runtime, evaluate, load_fixture  # noqa: E402
import main as lab  # noqa: E402


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.orders = load_fixture("orders.json")
        self.case = {"scenario": "success", "tenant_id": "tenant-a", "order_id": "ORD-001"}

    def test_success_uses_observation_then_final_response(self):
        # Changing the source must change the answer, not just a hardcoded expected fixture.
        self.orders["ORD-001"]["status"] = "仓库复核中"
        runtime = build_runtime(self.case, self.orders)
        result = runtime.run()
        events = [entry["event"] for entry in result["trace"]]
        self.assertEqual(result["status"], "completed")
        self.assertIn("仓库复核中", result["final_response"])
        self.assertEqual(result["simulated_usage"]["model_calls"], 2)
        self.assertLess(events.index("authorization_passed"), events.index("tool_started"))
        self.assertLess(events.index("tool_observation"), len(events) - 1)
        report = evaluate(load_fixture("cases.json"), self.orders)
        self.assertEqual(report["failed"], 1)
        self.assertFalse(report["results"][0]["checks"]["response_contains"])

    def test_tenant_isolation_also_holds_at_tool_boundary(self):
        self.case["order_id"] = "ORD-900"
        runtime = build_runtime(self.case, self.orders)
        result = runtime.run()
        self.assertEqual(result["status"], "denied")
        self.assertEqual(runtime.tool.calls, [])
        self.assertNotIn("待付款", str(result))
        with self.assertRaises(PermissionError):
            runtime.tool.lookup("tenant-a", "ORD-900", 100)
        self.assertEqual(runtime.tool.calls, [])

    def test_invalid_schema_never_reaches_tool(self):
        for variant in ("extra_key", "wrong_type"):
            with self.subTest(variant=variant):
                runtime = build_runtime(
                    {**self.case, "scenario": "schema_error", "schema_variant": variant}, self.orders
                )
                result = runtime.run()
                self.assertEqual(result["status"], "schema_error")
                self.assertEqual(runtime.tool.calls, [])

    def test_same_tenant_order_switch_is_rejected_before_authorization(self):
        runtime = build_runtime(self.case, self.orders)
        self.assertTrue(runtime.tool.is_authorized("tenant-a", "ORD-002"))
        runtime.model.next_action = Mock(return_value={
            "type": "tool_call", "name": "get_order_status", "arguments": {"order_id": "ORD-002"}
        })
        runtime.tool.is_authorized = Mock(side_effect=AssertionError("Authorization must not run"))
        result = runtime.run()
        self.assertEqual(result["status"], "off_target_action")
        self.assertEqual(result["error_code"], "TARGET_MISMATCH")
        runtime.tool.is_authorized.assert_not_called()
        self.assertEqual(runtime.tool.calls, [])
        self.assertEqual(result["simulated_usage"]["tool_attempts"], 0)

    def test_timeout_has_no_successful_observation_or_invented_result(self):
        runtime = build_runtime({**self.case, "simulated_tool_latency_ms": 250}, self.orders)
        result = runtime.run()
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["simulated_usage"]["tool_attempts"], 1)
        self.assertEqual(result["simulated_usage"]["tool_successes"], 0)
        self.assertNotIn("tool_observation", [entry["event"] for entry in result["trace"]])
        self.assertNotIn("待发货", result["final_response"])

    def test_loop_and_budget_bounds_stop_before_extra_work(self):
        for override, status, calls in (
            ({"scenario": "loop_limit", "max_model_calls": 2}, "step_limit", 2),
            ({"max_simulated_tokens": 30}, "budget_limit", 1),
            ({"max_simulated_tokens": 0}, "budget_limit", 0),
        ):
            with self.subTest(override=override):
                result = build_runtime({**self.case, **override}, self.orders).run()
                self.assertEqual(result["status"], status)
                self.assertEqual(result["simulated_usage"]["model_calls"], calls)
                self.assertEqual(result["simulated_usage"]["tool_attempts"], calls)

    def test_cancellation_after_proposal_prevents_tool_execution(self):
        runtime = build_runtime({**self.case, "cancel_after_model_calls": 1}, self.orders)
        result = runtime.run()
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["simulated_usage"]["model_calls"], 1)
        self.assertEqual(runtime.tool.calls, [])

    def test_final_without_tool_observation_cannot_complete(self):
        runtime = build_runtime(self.case, self.orders)
        runtime.model.next_action = Mock(return_value={"type": "final", "text": "订单已退款。"})
        result = runtime.run()
        self.assertEqual(result["status"], "unverified_final")
        self.assertEqual(result["error_code"], "UNVERIFIED_FINAL")
        self.assertEqual(runtime.tool.calls, [])
        self.assertNotIn("已退款", result["final_response"])

    def test_model_cannot_rewrite_stored_evidence_to_validate_false_final(self):
        runtime = build_runtime(self.case, self.orders)

        def contradict(observation):
            if observation is None:
                return {"type": "tool_call", "name": "get_order_status",
                        "arguments": {"order_id": "ORD-001"}}
            observation["status"] = "已退款"
            return {"type": "final", "text": lab.render_order_reply(observation)}

        runtime.model.next_action = Mock(side_effect=contradict)
        result = runtime.run()
        self.assertEqual(result["status"], "unverified_final")
        stored = next(event["result"] for event in result["trace"]
                      if event["event"] == "tool_observation")
        self.assertEqual(stored["status"], "待发货")
        self.assertNotIn("已退款", result["final_response"])

    def test_invalid_tool_observation_cannot_complete(self):
        for invalid in ({}, {"order_id": "ORD-900", "status": "已退款", "updated_at": "today"}):
            with self.subTest(observation=invalid):
                runtime = build_runtime(self.case, self.orders)
                runtime.tool.lookup = Mock(return_value=invalid)
                result = runtime.run()
                self.assertEqual(result["status"], "tool_error")
                self.assertEqual(result["error_code"], "INVALID_OBSERVATION")
                self.assertEqual(result["simulated_usage"]["tool_successes"], 0)

    def test_model_exception_is_classified_without_sensitive_error_text(self):
        runtime = build_runtime(self.case, self.orders)
        runtime.model.next_action = Mock(side_effect=RuntimeError("request token=TEST_SECRET"))
        result = runtime.run()
        self.assertEqual(result["status"], "model_error")
        self.assertEqual(result["error_code"], "MODEL_ERROR")
        self.assertEqual(result["simulated_usage"]["model_calls"], 1)
        self.assertEqual(runtime.tool.calls, [])
        self.assertNotIn("TEST_SECRET", str(result))

    def test_evaluation_retains_failed_case_and_continues_without_error_text(self):
        valid = load_fixture("cases.json")[0]
        cases = [{**valid, "id": "broken-case"}, valid]
        with patch("main.build_runtime", side_effect=[
            RuntimeError("request token=TEST_SECRET"), build_runtime(valid, self.orders)
        ]):
            report = evaluate(cases, self.orders)
        self.assertEqual((report["total"], report["passed"], report["failed"]), (2, 1, 1))
        self.assertEqual(report["results"][0]["error_code"], "CASE_ERROR")
        self.assertTrue(report["results"][1]["passed"])
        self.assertNotIn("TEST_SECRET", str(report))

    def test_empty_dataset_is_rejected_and_cli_returns_nonzero(self):
        with self.assertRaises(ValueError):
            evaluate([], self.orders)
        output = io.StringIO()
        with patch("main.load_fixture", side_effect=[self.orders, []]), \
                patch.object(sys, "argv", ["main.py", "--evaluate"]), redirect_stdout(output):
            exit_code = lab.main()
        self.assertNotEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue())["error_code"], "INVALID_DATASET")


if __name__ == "__main__":
    unittest.main()
