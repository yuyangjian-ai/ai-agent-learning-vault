# TypeScript 运行版

这个版本与上一层 Python 实验共用 `../fixtures/` 中的 12 条合成样本。运行逻辑使用 Node.js 的 Promise、`async/await` 和 `AbortSignal`，没有运行时依赖、真实模型调用或网络工具。初次安装只下载 TypeScript 编译器及 Node 类型定义；安装后实验可离线运行。

在仓库根目录执行：

```powershell
npm --prefix labs/01-agent-runtime/typescript ci --ignore-scripts
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario success
npm --prefix labs/01-agent-runtime/typescript run evaluate
npm --prefix labs/01-agent-runtime/typescript test
```

`start`、`evaluate` 和 `test` 都自动编译，无需手工运行 `tsc`。单独检查类型可执行 `npm --prefix labs/01-agent-runtime/typescript run typecheck`。需要 Node.js 20 或更高版本；具体推荐版本与实验说明见[上层说明](../README.md)。

| 阅读位置 | 先看什么 |
| --- | --- |
| `src/runtime.ts` 的 `Model` / `OrderTool` | Promise 只描述异步接口，不等于任务已完成 |
| `Runtime.run()` | 模型提出动作、Runtime 校验授权、工具观察、最终验收 |
| `parseAction()` / `parseObservation()` | TypeScript 类型会被擦除，外部 `unknown` 仍需要运行时校验 |
| `src/main.ts` | 读取共用 JSON fixtures、CLI 参数与退出码 |
| `tests/runtime.test.ts` | 13 个边界测试，覆盖与 Python 版相同的行为 |

成功场景应输出 `status: completed`、2 次模型调用和 1 次工具读取；评测应得到 `total: 12, passed: 12, failed: 0`。替换 `--scenario success` 为 `schema_error`、`unauthorized`、`timeout`、`loop_limit`、`cancelled` 或 `budget_limit`，可观察不同停止原因。

模型输出、工具返回与 JSON 文件入口均先按 `unknown` 处理，再逐层检查字段、类型与额外参数。工具目标必须等于应用预先绑定的 `config.order_id`；即使另一订单属于同一租户，模型自行换单也会在鉴权前收到 `off_target_action` / `TARGET_MISMATCH`，不执行工具。`final` 必须有成功的授权订单观察，并与固定订单模板一致；复制给模型的观察不能修改 Runtime 保存的证据。这种核对只适用于本实验的固定订单输出，不是通用事实核查。

模型异常归类为 `MODEL_ERROR`，不输出可能含凭据的异常原文。单条评测异常保留 `CASE_ERROR` 行并继续；空样本返回 `INVALID_DATASET` 与非零退出码。预设单场景故障仍以退出码 0 表示演示正常运行，查看 JSON `status` 判断业务结果。

`AbortSignal` 在模型前后、鉴权后和工具动作边界检查，适配器也能接收它。已经完成的工具观察会保留，但不再继续后续动作。取消不能强制撤回外部副作用，也不会强制终止一个忽略 signal 且始终不返回的 Promise；接真实 SDK 时还需接入它自己的 deadline 和取消机制。

`simulated_usage.tokens` 与 `tool_ms` 都是教学设定；超时通过比较预设延迟注入，没有真正等待、联网或测量模型性能。12/12 是公开合成回归样本的结果，不代表真实模型正确率。练习、完整限制与接入真实模型的步骤见[上层实验说明](../README.md)。
