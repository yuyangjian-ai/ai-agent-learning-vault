"""A deterministic, in-memory Agent runtime teaching lab (Python 3.10+)."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SIMULATED_TOKENS_PER_CALL = 20
SCENARIOS = (
    "success", "schema_error", "unauthorized", "timeout",
    "loop_limit", "cancelled", "budget_limit",
)


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def render_order_reply(observation: dict[str, Any]) -> str:
    """Exact template for this order lab, not general-purpose fact verification."""
    return (
        f"订单 {observation['order_id']} 当前状态：{observation['status']}。"
        f"数据时间：{observation['updated_at']}。"
    )


def valid_order_observation(observation: Any, order_id: str) -> bool:
    return (
        isinstance(observation, dict)
        and set(observation) == {"order_id", "status", "updated_at"}
        and observation["order_id"] == order_id
        and all(isinstance(value, str) and value.strip() for value in observation.values())
    )


@dataclass(frozen=True)
class RuntimeConfig:
    # This identity belongs to the authenticated application context, not the model.
    tenant_id: str
    # The task target is bound by the application before the model proposes actions.
    order_id: str
    max_model_calls: int = 3
    max_simulated_tokens: int = 200
    tool_timeout_ms: int = 100
    cancel_after_model_calls: int | None = None


class FakeModel:
    """Scripted actions, not a language model and not a semantic capability test."""

    def __init__(self, case: dict[str, Any]):
        self.case = case

    def next_action(self, observation: dict[str, Any] | None) -> dict[str, Any]:
        if observation is not None and self.case["scenario"] != "loop_limit":
            return {
                "type": "final",
                "text": render_order_reply(observation),
            }
        arguments: dict[str, Any] = {"order_id": self.case["order_id"]}
        if self.case["scenario"] == "schema_error":
            if self.case.get("schema_variant") == "wrong_type":
                arguments["order_id"] = 123
            else:
                arguments["tenant_id"] = "tenant-b"
        return {"type": "tool_call", "name": "get_order_status", "arguments": arguments}


def validate_tool_call(action: dict[str, Any]) -> str | None:
    """Small explicit schema: one tool, one string argument, no extra fields."""
    if set(action) != {"type", "name", "arguments"}:
        return "工具调用只允许 type、name、arguments 字段"
    if action["name"] != "get_order_status":
        return "未知工具"
    arguments = action["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != {"order_id"}:
        return "arguments 必须且只能包含 order_id"
    order_id = arguments["order_id"]
    if not isinstance(order_id, str) or re.fullmatch(r"ORD-\d{3}", order_id) is None:
        return "order_id 必须是 ORD- 加三位数字的字符串"
    return None


class FakeOrderTool:
    """Read-only synthetic storage; latency is simulated, no sleeping or network."""

    def __init__(self, orders: dict[str, Any], simulated_latency_ms: int = 10):
        self.orders = orders
        self.simulated_latency_ms = simulated_latency_ms
        self.calls: list[str] = []

    def is_authorized(self, tenant_id: str, order_id: str) -> bool:
        order = self.orders.get(order_id)
        return order is not None and order["tenant_id"] == tenant_id

    def lookup(self, tenant_id: str, order_id: str, timeout_ms: int) -> dict[str, Any]:
        # Recheck at the tool boundary; bypassing Runtime must not expose another tenant.
        if not self.is_authorized(tenant_id, order_id):
            raise PermissionError("订单不存在或当前租户无权访问")
        self.calls.append(order_id)
        if self.simulated_latency_ms > timeout_ms:
            raise TimeoutError("模拟工具延迟超过 deadline")
        order = self.orders[order_id]
        return {
            "order_id": order_id,
            "status": order["status"],
            "updated_at": order["updated_at"],
        }


class Runtime:
    def __init__(self, model: FakeModel, tool: FakeOrderTool, config: RuntimeConfig):
        self.model = model
        self.tool = tool
        self.config = config

    def run(self) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        usage = {"model_calls": 0, "tokens": 0, "tool_attempts": 0,
                 "tool_successes": 0, "tool_ms": 0}
        observation = None

        def event(event_name: str, **fields: Any) -> None:
            trace.append({"step": len(trace) + 1, "event": event_name, **fields})

        def finish(status: str, response: str, error_code: str | None = None) -> dict[str, Any]:
            event("run_finished", status=status)
            result = {"status": status, "final_response": response,
                      "simulated_usage": usage, "trace": trace}
            if error_code is not None:
                result["error_code"] = error_code
            return result

        def cancelled() -> bool:
            limit = self.config.cancel_after_model_calls
            return limit is not None and usage["model_calls"] >= limit

        event("run_started", tenant_id=self.config.tenant_id)
        for _ in range(self.config.max_model_calls):
            if cancelled():
                return finish("cancelled", "运行已取消。")
            # FakeModel has a fixed, known charge. Real APIs need reservation and reconciliation.
            if usage["tokens"] + SIMULATED_TOKENS_PER_CALL > self.config.max_simulated_tokens:
                return finish("budget_limit", "模拟 token 预算不足，运行停止。")
            # Count attempted calls, including failures, in this fixed-charge simulation.
            usage["model_calls"] += 1
            usage["tokens"] += SIMULATED_TOKENS_PER_CALL
            try:
                # An adapter must not be able to modify Runtime's stored tool evidence.
                action = self.model.next_action(deepcopy(observation))
            except Exception:
                # Provider exceptions may contain request text or credentials; do not echo them.
                event("model_error", error_code="MODEL_ERROR")
                return finish("model_error", "模型调用失败，运行停止。", "MODEL_ERROR")
            event("model_action", action=action)
            if cancelled():
                return finish("cancelled", "运行已取消，未执行后续动作。")
            if not isinstance(action, dict):
                return finish("schema_error", "模型动作必须是一个对象。")
            if action.get("type") == "final":
                if set(action) != {"type", "text"} or not isinstance(action["text"], str):
                    return finish("schema_error", "最终回复格式不合法。")
                if observation is None:
                    return finish("unverified_final", "尚无成功的订单观察，不能确认订单结果。",
                                  "UNVERIFIED_FINAL")
                expected_reply = render_order_reply(observation)
                if action["text"] != expected_reply:
                    return finish("unverified_final", "最终回复与已读取的订单事实不一致。",
                                  "UNVERIFIED_FINAL")
                return finish("completed", expected_reply)
            if action.get("type") != "tool_call":
                return finish("schema_error", "不支持的模型动作类型。")

            schema_error = validate_tool_call(action)
            if schema_error is not None:
                event("validation_rejected", reason=schema_error)
                return finish("schema_error", f"工具参数不合法：{schema_error}。")
            event("validation_passed")
            order_id = action["arguments"]["order_id"]
            if order_id != self.config.order_id:
                event("target_rejected", error_code="TARGET_MISMATCH")
                return finish("off_target_action", "工具目标与当前任务指定的订单不一致。", "TARGET_MISMATCH")
            if not self.tool.is_authorized(self.config.tenant_id, order_id):
                event("authorization_denied")
                return finish("denied", "订单不存在或当前租户无权访问。")
            event("authorization_passed")
            usage["tool_attempts"] += 1
            usage["tool_ms"] += min(self.tool.simulated_latency_ms, self.config.tool_timeout_ms)
            event("tool_started", name=action["name"], order_id=order_id)
            try:
                observation = self.tool.lookup(
                    self.config.tenant_id, order_id, self.config.tool_timeout_ms
                )
            except TimeoutError:
                event("tool_timeout", timeout_ms=self.config.tool_timeout_ms)
                return finish("timeout", "查询超时，尚未获得订单结果，请稍后重试。")
            except PermissionError:
                event("authorization_denied")
                return finish("denied", "订单不存在或当前租户无权访问。")
            if not valid_order_observation(observation, order_id):
                event("tool_result_rejected", error_code="INVALID_OBSERVATION")
                return finish("tool_error", "订单工具返回的结果格式不合法。", "INVALID_OBSERVATION")
            usage["tool_successes"] += 1
            event("tool_observation", result=observation)
        return finish("step_limit", "已达到模型调用次数上限，运行停止。")


def build_runtime(case: dict[str, Any], orders: dict[str, Any]) -> Runtime:
    return Runtime(
        model=FakeModel(case),
        tool=FakeOrderTool(orders, case.get("simulated_tool_latency_ms", 10)),
        config=RuntimeConfig(
            tenant_id=case["tenant_id"],
            order_id=case["order_id"],
            max_model_calls=case.get("max_model_calls", 3),
            max_simulated_tokens=case.get("max_simulated_tokens", 200),
            tool_timeout_ms=case.get("tool_timeout_ms", 100),
            cancel_after_model_calls=case.get("cancel_after_model_calls"),
        ),
    )


def evaluate(cases: list[dict[str, Any]], orders: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(cases, list) or not cases:
        raise ValueError("评测数据集必须是非空列表")
    results = []
    for index, case in enumerate(cases, start=1):
        case_id = case.get("id", f"case-{index}") if isinstance(case, dict) else f"case-{index}"
        try:
            run = build_runtime(case, orders).run()
            expected = case["expected"]
            checks = {
                "status": run["status"] == expected["status"],
                "tool_attempts": run["simulated_usage"]["tool_attempts"] == expected["tool_attempts"],
                "response_contains": expected["response_contains"] in run["final_response"],
                "bounded_calls": run["simulated_usage"]["model_calls"] <= case.get("max_model_calls", 3),
                "bounded_tokens": run["simulated_usage"]["tokens"] <= case.get("max_simulated_tokens", 200),
            }
            results.append({"id": case_id, "status": run["status"],
                            "passed": all(checks.values()), "checks": checks})
        except Exception:
            # A broken case is a failed row, not permission to skip the rest or print secrets.
            results.append({"id": case_id, "status": "case_error", "passed": False,
                            "error_code": "CASE_ERROR", "checks": {"case_execution": False}})
    passed = sum(result["passed"] for result in results)
    return {"dataset_version": "synthetic-runtime-v1", "total": len(results),
            "passed": passed, "failed": len(results) - passed,
            "scope": "仅评测预设 Runtime 行为及订单模板与观察的一致性，不评测通用事实核查、真实模型能力、token 或性能。",
            "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scenario", choices=SCENARIOS, default="success")
    mode.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    orders = load_fixture("orders.json")
    cases = load_fixture("cases.json")
    if args.evaluate:
        try:
            output = evaluate(cases, orders)
            exit_code = 0 if output["failed"] == 0 else 1
        except ValueError:
            output = {"status": "invalid_dataset", "error_code": "INVALID_DATASET",
                      "message": "评测数据集必须是非空列表。"}
            exit_code = 1
    else:
        case = next(case for case in cases if case["scenario"] == args.scenario)
        output = {"case_id": case["id"], **build_runtime(case, orders).run()}
        exit_code = 0  # A deliberately injected failure is a valid scenario demonstration.
    # Keep Chinese JSON readable when Windows redirects stdout through a UTF-8 terminal.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
