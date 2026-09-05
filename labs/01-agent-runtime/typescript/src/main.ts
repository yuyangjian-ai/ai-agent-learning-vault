import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { buildRuntime, evaluate, InvalidDatasetError, isRecord, parseOrders, SCENARIOS } from "./runtime.js";

type FixtureName = "orders.json" | "cases.json";
type FixtureLoader = (name: FixtureName) => Promise<unknown>;
export async function loadFixture(name: FixtureName): Promise<unknown> {
  // Compiled entry: typescript/dist/src/main.js -> the shared lab fixtures directory.
  const source = await readFile(new URL(`../../../fixtures/${name}`, import.meta.url), "utf8");
  const parsed: unknown = JSON.parse(source);
  return parsed;
}

export async function runCli(args: readonly string[], load: FixtureLoader = loadFixture):
Promise<{ exitCode: number; output: unknown }> {
  const evaluating = args.length === 1 && args[0] === "--evaluate";
  const scenario = args.length === 0 ? "success" : args[1];
  if (!evaluating && !(args.length === 0 ||
      (args.length === 2 && args[0] === "--scenario" && typeof scenario === "string" && SCENARIOS.includes(scenario)))) {
    return { exitCode: 2, output: { error_code: "INVALID_ARGUMENTS", message: "使用 --evaluate 或 --scenario 场景名。" } };
  }
  try {
    const orders = parseOrders(await load("orders.json"));
    const cases = await load("cases.json");
    if (evaluating) {
      const report = await evaluate(cases, orders);
      return { exitCode: report.failed === 0 ? 0 : 1, output: report };
    }
    if (!Array.isArray(cases)) throw new InvalidDatasetError("Invalid cases");
    const inputs: unknown[] = cases;
    const selected = inputs.find((item) => isRecord(item) && item.scenario === scenario);
    if (!isRecord(selected) || typeof selected.id !== "string") throw new InvalidDatasetError("Missing scenario");
    return { exitCode: 0, output: { case_id: selected.id, ...await buildRuntime(selected, orders).run() } };
  } catch (error: unknown) {
    const code = error instanceof InvalidDatasetError ? "INVALID_DATASET" : "FIXTURE_ERROR";
    return { exitCode: 1, output: { error_code: code, message: "实验数据无法运行，请检查本地 fixtures。" } };
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const result = await runCli(process.argv.slice(2));
  process.stdout.write(`${JSON.stringify(result.output, null, 2)}\n`);
  process.exitCode = result.exitCode;
}
