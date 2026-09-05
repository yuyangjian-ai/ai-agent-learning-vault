// No SDK or network: validate unknown values before they enter the typed runtime.
export const SIMULATED_TOKENS_PER_CALL = 20;
export const SCENARIOS = [
  "success", "schema_error", "unauthorized", "timeout", "loop_limit", "cancelled", "budget_limit",
];

export interface OrderObservation {
  order_id: string;
  status: string;
  updated_at: string;
}
export interface OrderRecord { tenant_id: string; status: string; updated_at: string }
export type Orders = Map<string, OrderRecord>;
export interface ScenarioCase {
  id: string;
  scenario: string;
  tenant_id: string;
  order_id: string;
  schema_variant: string;
  max_model_calls: number;
  max_simulated_tokens: number;
  tool_timeout_ms: number;
  simulated_tool_latency_ms: number;
  cancel_after_model_calls: number | null;
}
export interface Model {
  nextAction(observation: OrderObservation | null, signal?: AbortSignal): Promise<unknown>;
}
export interface OrderTool {
  readonly simulatedLatencyMs: number;
  isAuthorized(tenantId: string, orderId: string): Promise<boolean>;
  lookup(tenantId: string, orderId: string, timeoutMs: number, signal?: AbortSignal): Promise<unknown>;
}
export interface Usage {
  model_calls: number; tokens: number; tool_attempts: number; tool_successes: number; tool_ms: number;
}
export interface TraceEvent { step: number; event: string; [key: string]: unknown }
export interface RunResult {
  status: string;
  final_response: string;
  simulated_usage: Usage;
  trace: TraceEvent[];
  error_code?: string;
}
export interface EvaluationRow {
  id: string; status: string; passed: boolean; checks: Record<string, boolean>; error_code?: string;
}
export interface EvaluationReport {
  dataset_version: string; total: number; passed: number; failed: number;
  scope: string; results: EvaluationRow[];
}

export class InvalidDatasetError extends Error {}
class SchemaError extends Error {}
export class PermissionError extends Error {}
export class SimulatedTimeoutError extends Error {}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function record(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw new Error("Expected an object");
  return value;
}
function text(value: unknown): string {
  if (typeof value !== "string" || value.trim() === "") throw new Error("Expected nonempty text");
  return value;
}
function integer(value: unknown, fallback: number): number {
  if (value === undefined) return fallback;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error("Expected a nonnegative integer");
  }
  return value;
}
function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

export function parseOrders(value: unknown): Orders {
  const result: Orders = new Map();
  for (const [id, raw] of Object.entries(record(value))) {
    const order = record(raw);
    if (!/^ORD-\d{3}$/.test(id) || !exactKeys(order, ["tenant_id", "status", "updated_at"])) {
      throw new Error("Invalid order fixture");
    }
    result.set(id, { tenant_id: text(order.tenant_id), status: text(order.status),
      updated_at: text(order.updated_at) });
  }
  return result;
}

export function parseCase(value: unknown): ScenarioCase {
  const item = record(value);
  const scenario = text(item.scenario);
  if (!SCENARIOS.includes(scenario)) throw new Error("Unknown scenario");
  return {
    id: item.id === undefined ? "case" : text(item.id), scenario,
    tenant_id: text(item.tenant_id), order_id: text(item.order_id),
    schema_variant: item.schema_variant === undefined ? "extra_key" : text(item.schema_variant),
    max_model_calls: integer(item.max_model_calls, 3),
    max_simulated_tokens: integer(item.max_simulated_tokens, 200),
    tool_timeout_ms: integer(item.tool_timeout_ms, 100),
    simulated_tool_latency_ms: integer(item.simulated_tool_latency_ms, 10),
    cancel_after_model_calls: item.cancel_after_model_calls === undefined || item.cancel_after_model_calls === null
      ? null : integer(item.cancel_after_model_calls, 0),
  };
}

export function renderOrderReply(observation: OrderObservation): string {
  // An exact order template, not general-purpose natural-language fact verification.
  return `订单 ${observation.order_id} 当前状态：${observation.status}。数据时间：${observation.updated_at}。`;
}
function parseObservation(value: unknown, orderId: string): OrderObservation | null {
  if (!isRecord(value) || !exactKeys(value, ["order_id", "status", "updated_at"]) ||
      value.order_id !== orderId || typeof value.status !== "string" || !value.status.trim() ||
      typeof value.updated_at !== "string" || !value.updated_at.trim()) return null;
  return { order_id: orderId, status: value.status, updated_at: value.updated_at };
}
type Action = { type: "final"; text: string } |
  { type: "tool_call"; name: "get_order_status"; arguments: { order_id: string } };
function parseAction(value: unknown): Action {
  if (!isRecord(value)) throw new SchemaError("模型动作必须是一个对象");
  if (value.type === "final") {
    if (!exactKeys(value, ["type", "text"]) || typeof value.text !== "string") {
      throw new SchemaError("最终回复格式不合法");
    }
    return { type: "final", text: value.text };
  }
  if (value.type !== "tool_call") throw new SchemaError("不支持的模型动作类型");
  if (!exactKeys(value, ["type", "name", "arguments"])) {
    throw new SchemaError("工具调用只允许 type、name、arguments 字段");
  }
  if (value.name !== "get_order_status") throw new SchemaError("未知工具");
  if (!isRecord(value.arguments) || !exactKeys(value.arguments, ["order_id"])) {
    throw new SchemaError("arguments 必须且只能包含 order_id");
  }
  const orderId = value.arguments.order_id;
  if (typeof orderId !== "string" || !/^ORD-\d{3}$/.test(orderId)) {
    throw new SchemaError("order_id 必须是 ORD- 加三位数字的字符串");
  }
  return { type: "tool_call", name: "get_order_status", arguments: { order_id: orderId } };
}

export class FakeModel implements Model {
  constructor(private readonly item: ScenarioCase) {}
  async nextAction(observation: OrderObservation | null): Promise<unknown> {
    if (observation && this.item.scenario !== "loop_limit") {
      return { type: "final", text: renderOrderReply(observation) };
    }
    const args: Record<string, unknown> = { order_id: this.item.order_id };
    if (this.item.scenario === "schema_error") {
      if (this.item.schema_variant === "wrong_type") args.order_id = 123;
      else args.tenant_id = "tenant-b";
    }
    return { type: "tool_call", name: "get_order_status", arguments: args };
  }
}

export class FakeOrderTool implements OrderTool {
  readonly calls: string[] = [];
  constructor(private readonly orders: Orders, readonly simulatedLatencyMs = 10) {}
  async isAuthorized(tenantId: string, orderId: string): Promise<boolean> {
    return this.orders.get(orderId)?.tenant_id === tenantId;
  }
  async lookup(tenantId: string, orderId: string, timeoutMs: number, signal?: AbortSignal): Promise<unknown> {
    signal?.throwIfAborted();
    const order = this.orders.get(orderId);
    if (!order || order.tenant_id !== tenantId) throw new PermissionError("Access denied");
    this.calls.push(orderId);
    if (this.simulatedLatencyMs > timeoutMs) throw new SimulatedTimeoutError("Simulated deadline");
    return { order_id: orderId, status: order.status, updated_at: order.updated_at };
  }
}

export class Runtime {
  constructor(public model: Model, public tool: OrderTool, readonly config: ScenarioCase) {}

  async run(signal?: AbortSignal): Promise<RunResult> {
    const trace: TraceEvent[] = [];
    const usage: Usage = { model_calls: 0, tokens: 0, tool_attempts: 0, tool_successes: 0, tool_ms: 0 };
    let observation: OrderObservation | null = null;
    const event = (name: string, fields: Record<string, unknown> = {}): void => {
      trace.push({ step: trace.length + 1, event: name, ...fields });
    };
    const finish = (status: string, response: string, errorCode?: string): RunResult => {
      event("run_finished", { status });
      return { status, final_response: response, simulated_usage: usage, trace,
        ...(errorCode ? { error_code: errorCode } : {}) };
    };
    const cancelled = (): boolean => signal?.aborted === true ||
      (this.config.cancel_after_model_calls !== null && usage.model_calls >= this.config.cancel_after_model_calls);
    event("run_started", { tenant_id: this.config.tenant_id });
    for (let step = 0; step < this.config.max_model_calls; step++) {
      if (cancelled()) return finish("cancelled", "运行已取消。");
      if (usage.tokens + SIMULATED_TOKENS_PER_CALL > this.config.max_simulated_tokens) {
        return finish("budget_limit", "模拟 token 预算不足，运行停止。");
      }
      usage.model_calls++;
      usage.tokens += SIMULATED_TOKENS_PER_CALL;
      let rawAction: unknown;
      try {
        rawAction = await this.model.nextAction(observation ? { ...observation } : null, signal);
      } catch {
        if (cancelled()) return finish("cancelled", "运行已取消。");
        event("model_error", { error_code: "MODEL_ERROR" });
        return finish("model_error", "模型调用失败，运行停止。", "MODEL_ERROR");
      }
      if (cancelled()) return finish("cancelled", "运行已取消，未执行后续动作。");
      let action: Action;
      try { action = parseAction(rawAction); }
      catch (error: unknown) {
        const reason = error instanceof SchemaError ? error.message : "模型动作格式不合法";
        event("validation_rejected", { reason });
        return finish("schema_error", `工具参数不合法：${reason}。`);
      }
      event("model_action", { action });
      if (action.type === "final") {
        if (!observation) return finish("unverified_final", "尚无成功的订单观察，不能确认订单结果。", "UNVERIFIED_FINAL");
        const expected = renderOrderReply(observation);
        if (action.text !== expected) return finish("unverified_final", "最终回复与已读取的订单事实不一致。", "UNVERIFIED_FINAL");
        return finish("completed", expected);
      }
      event("validation_passed");
      const orderId = action.arguments.order_id;
      // Tenant access alone does not authorize changing the target of this task.
      if (orderId !== this.config.order_id) {
        event("target_rejected", { error_code: "TARGET_MISMATCH" });
        return finish("off_target_action", "工具目标与当前任务指定的订单不一致。", "TARGET_MISMATCH");
      }
      try {
        const authorized = await this.tool.isAuthorized(this.config.tenant_id, orderId);
        if (cancelled()) return finish("cancelled", "运行已取消，未执行后续动作。");
        if (!authorized) {
          event("authorization_denied");
          return finish("denied", "订单不存在或当前租户无权访问。");
        }
        event("authorization_passed");
        usage.tool_attempts++;
        usage.tool_ms += Math.min(this.tool.simulatedLatencyMs, this.config.tool_timeout_ms);
        event("tool_started", { name: action.name, order_id: orderId });
        const rawObservation = await this.tool.lookup(this.config.tenant_id, orderId, this.config.tool_timeout_ms, signal);
        const parsed = parseObservation(rawObservation, orderId);
        if (!parsed) {
          event("tool_result_rejected", { error_code: "INVALID_OBSERVATION" });
          return finish("tool_error", "订单工具返回的结果格式不合法。", "INVALID_OBSERVATION");
        }
        observation = parsed;
        usage.tool_successes++;
        event("tool_observation", { result: { ...observation } });
        // A completed tool result remains observable even when cancellation arrives meanwhile.
        if (cancelled()) return finish("cancelled", "运行已取消，不再执行后续动作。");
      } catch (error: unknown) {
        if (cancelled()) return finish("cancelled", "运行已取消。");
        if (error instanceof PermissionError) return finish("denied", "订单不存在或当前租户无权访问。");
        if (error instanceof SimulatedTimeoutError) {
          event("tool_timeout", { timeout_ms: this.config.tool_timeout_ms });
          return finish("timeout", "查询超时，尚未获得订单结果，请稍后重试。");
        }
        return finish("tool_error", "工具调用失败，运行停止。", "TOOL_ERROR");
      }
    }
    return finish("step_limit", "已达到模型调用次数上限，运行停止。");
  }
}

export function buildRuntime(rawCase: unknown, orders: Orders): Runtime {
  const item = parseCase(rawCase);
  return new Runtime(new FakeModel(item), new FakeOrderTool(orders, item.simulated_tool_latency_ms), item);
}

export async function evaluate(rawCases: unknown, orders: Orders): Promise<EvaluationReport> {
  if (!Array.isArray(rawCases) || rawCases.length === 0) throw new InvalidDatasetError("Empty dataset");
  // Array.isArray narrows only to an array; each element is still explicitly unknown here.
  const inputs: unknown[] = rawCases;
  const results: EvaluationRow[] = [];
  for (const [index, rawCase] of inputs.entries()) {
    const id = isRecord(rawCase) && typeof rawCase.id === "string" ? rawCase.id : `case-${index + 1}`;
    try {
      const item = parseCase(rawCase);
      const expected = record(record(rawCase).expected);
      const expectedStatus = text(expected.status);
      const expectedAttempts = integer(expected.tool_attempts, -1);
      const responseContains = text(expected.response_contains);
      if (expectedAttempts < 0) throw new Error("Missing expectation");
      const run = await buildRuntime(rawCase, orders).run();
      const checks = {
        status: run.status === expectedStatus,
        tool_attempts: run.simulated_usage.tool_attempts === expectedAttempts,
        response_contains: run.final_response.includes(responseContains),
        bounded_calls: run.simulated_usage.model_calls <= item.max_model_calls,
        bounded_tokens: run.simulated_usage.tokens <= item.max_simulated_tokens,
      };
      results.push({ id, status: run.status, passed: Object.values(checks).every(Boolean), checks });
    } catch {
      results.push({ id, status: "case_error", passed: false, error_code: "CASE_ERROR",
        checks: { case_execution: false } });
    }
  }
  const passed = results.filter((row) => row.passed).length;
  return { dataset_version: "synthetic-runtime-v1", total: results.length, passed,
    failed: results.length - passed,
    scope: "仅评测预设 Runtime 行为及订单模板与观察的一致性，不评测通用事实核查、真实模型能力、token 或性能。",
    results };
}
