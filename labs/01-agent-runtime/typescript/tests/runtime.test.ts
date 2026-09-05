import assert from "node:assert/strict";
import test from "node:test";
import { loadFixture, runCli } from "../src/main.js";
import { buildRuntime, evaluate, FakeOrderTool, InvalidDatasetError, isRecord,
  parseOrders, PermissionError, renderOrderReply } from "../src/runtime.js";

const baseCase = { scenario: "success", tenant_id: "tenant-a", order_id: "ORD-001" };
async function setup(overrides: Record<string, unknown> = {}) {
  const orders = parseOrders(await loadFixture("orders.json"));
  const runtime = buildRuntime({ ...baseCase, ...overrides }, orders);
  assert.ok(runtime.tool instanceof FakeOrderTool);
  return { orders, runtime, tool: runtime.tool };
}
async function cases(): Promise<unknown[]> {
  const value = await loadFixture("cases.json");
  assert.ok(Array.isArray(value));
  const result: unknown[] = value;
  return result;
}

test("success uses observation then final, and evaluation detects source drift", async () => {
  const { orders, runtime } = await setup();
  const order = orders.get("ORD-001");
  assert.ok(order);
  order.status = "仓库复核中";
  const result = await runtime.run();
  assert.equal(result.status, "completed");
  assert.match(result.final_response, /仓库复核中/);
  assert.equal(result.simulated_usage.model_calls, 2);
  const events = result.trace.map((event) => event.event);
  assert.ok(events.indexOf("authorization_passed") < events.indexOf("tool_started"));
  const report = await evaluate(await cases(), orders);
  assert.equal(report.failed, 1);
  assert.equal(report.results[0]?.checks.response_contains, false);
});

test("tenant isolation also holds at the tool boundary", async () => {
  const { runtime, tool } = await setup({ order_id: "ORD-900" });
  const result = await runtime.run();
  assert.equal(result.status, "denied");
  assert.deepEqual(tool.calls, []);
  assert.doesNotMatch(JSON.stringify(result), /待付款/);
  await assert.rejects(tool.lookup("tenant-a", "ORD-900", 100), PermissionError);
  assert.deepEqual(tool.calls, []);
});

test("invalid schemas never reach the tool", async () => {
  for (const variant of ["extra_key", "wrong_type"]) {
    const { runtime, tool } = await setup({ scenario: "schema_error", schema_variant: variant });
    assert.equal((await runtime.run()).status, "schema_error");
    assert.deepEqual(tool.calls, []);
  }
});

test("same-tenant order switch is rejected before authorization", async () => {
  const { runtime, tool } = await setup();
  assert.equal(await tool.isAuthorized("tenant-a", "ORD-002"), true);
  let authorizationCalls = 0;
  runtime.model = { async nextAction() {
    return { type: "tool_call", name: "get_order_status", arguments: { order_id: "ORD-002" } };
  } };
  tool.isAuthorized = async () => { authorizationCalls++; return true; };
  const result = await runtime.run();
  assert.equal(result.status, "off_target_action");
  assert.equal(result.error_code, "TARGET_MISMATCH");
  assert.equal(authorizationCalls, 0);
  assert.deepEqual(tool.calls, []);
  assert.equal(result.simulated_usage.tool_attempts, 0);
});

test("timeout has no successful observation or invented result", async () => {
  const { runtime } = await setup({ simulated_tool_latency_ms: 250 });
  const result = await runtime.run();
  assert.equal(result.status, "timeout");
  assert.equal(result.simulated_usage.tool_attempts, 1);
  assert.equal(result.simulated_usage.tool_successes, 0);
  assert.equal(result.trace.some((event) => event.event === "tool_observation"), false);
  assert.doesNotMatch(result.final_response, /待发货/);
});

test("loop and budget bounds stop before extra work", async () => {
  const inputs = [
    { options: { scenario: "loop_limit", max_model_calls: 2 }, status: "step_limit", calls: 2 },
    { options: { max_simulated_tokens: 30 }, status: "budget_limit", calls: 1 },
    { options: { max_simulated_tokens: 0 }, status: "budget_limit", calls: 0 },
  ];
  for (const input of inputs) {
    const { runtime } = await setup(input.options);
    const result = await runtime.run();
    assert.equal(result.status, input.status);
    assert.equal(result.simulated_usage.model_calls, input.calls);
    assert.equal(result.simulated_usage.tool_attempts, input.calls);
  }
});

test("fixture cancellation and AbortSignal stop before tool execution", async () => {
  const uncancelled = await setup({ cancel_after_model_calls: null });
  assert.equal((await uncancelled.runtime.run()).status, "completed");
  const { runtime, tool } = await setup({ cancel_after_model_calls: 1 });
  assert.equal((await runtime.run()).status, "cancelled");
  assert.deepEqual(tool.calls, []);
  const next = await setup();
  const controller = new AbortController();
  next.runtime.model = { async nextAction() {
    controller.abort();
    return { type: "tool_call", name: "get_order_status", arguments: { order_id: "ORD-001" } };
  } };
  assert.equal((await next.runtime.run(controller.signal)).status, "cancelled");
  assert.deepEqual(next.tool.calls, []);
});

test("final without a tool observation cannot complete", async () => {
  const { runtime, tool } = await setup();
  runtime.model = { async nextAction() { return { type: "final", text: "订单已退款。" }; } };
  const result = await runtime.run();
  assert.equal(result.status, "unverified_final");
  assert.equal(result.error_code, "UNVERIFIED_FINAL");
  assert.deepEqual(tool.calls, []);
  assert.doesNotMatch(result.final_response, /已退款/);
});

test("model cannot rewrite stored evidence to validate a false final", async () => {
  const { runtime } = await setup();
  runtime.model = { async nextAction(observation) {
    if (!observation) return { type: "tool_call", name: "get_order_status", arguments: { order_id: "ORD-001" } };
    observation.status = "已退款";
    return { type: "final", text: renderOrderReply(observation) };
  } };
  const result = await runtime.run();
  assert.equal(result.status, "unverified_final");
  const stored = result.trace.find((event) => event.event === "tool_observation")?.result;
  assert.ok(isRecord(stored));
  assert.equal(stored.status, "待发货");
  assert.doesNotMatch(result.final_response, /已退款/);
});

test("invalid tool observations cannot complete", async () => {
  for (const invalid of [{}, { order_id: "ORD-900", status: "已退款", updated_at: "today" }]) {
    const { runtime } = await setup();
    runtime.tool.lookup = async () => invalid;
    const result = await runtime.run();
    assert.equal(result.status, "tool_error");
    assert.equal(result.error_code, "INVALID_OBSERVATION");
    assert.equal(result.simulated_usage.tool_successes, 0);
  }
});

test("model exception is classified without sensitive error text", async () => {
  const { runtime, tool } = await setup();
  runtime.model = { async nextAction() { throw new Error("request token=TEST_SECRET"); } };
  const result = await runtime.run();
  assert.equal(result.status, "model_error");
  assert.equal(result.error_code, "MODEL_ERROR");
  assert.equal(result.simulated_usage.model_calls, 1);
  assert.deepEqual(tool.calls, []);
  assert.doesNotMatch(JSON.stringify(result), /TEST_SECRET/);
});

test("evaluation retains a failed case and continues without error text", async () => {
  const { orders } = await setup();
  const valid = (await cases())[0];
  assert.ok(isRecord(valid));
  const report = await evaluate([{ ...valid, id: "broken-case", order_id: { token: "TEST_SECRET" } }, valid], orders);
  assert.deepEqual([report.total, report.passed, report.failed], [2, 1, 1]);
  assert.equal(report.results[0]?.error_code, "CASE_ERROR");
  assert.equal(report.results[1]?.passed, true);
  assert.doesNotMatch(JSON.stringify(report), /TEST_SECRET/);
});

test("empty dataset is rejected and CLI returns nonzero", async () => {
  const { orders } = await setup();
  await assert.rejects(evaluate([], orders), InvalidDatasetError);
  const result = await runCli(["--evaluate"], async (name) => name === "orders.json" ? loadFixture(name) : []);
  assert.notEqual(result.exitCode, 0);
  assert.ok(isRecord(result.output));
  assert.equal(result.output.error_code, "INVALID_DATASET");
});
