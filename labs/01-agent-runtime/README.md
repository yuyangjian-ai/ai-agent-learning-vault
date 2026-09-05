# 离线实验：用 TypeScript 看见 Agent Runtime 的完整一圈

预计 20～30 分钟。默认版本使用 **Node.js + TypeScript**；建议 Node.js 24/22 LTS，无需 API Key。首次安装编译工具需要联网；安装后，实验使用 Node 内置模块离线运行，没有第三方运行时依赖。所有订单和身份都是合成数据，工具只读取内存。

先读 [typescript/src/runtime.ts](typescript/src/runtime.ts) 的 `Runtime.run()`，再回看模型接口、`FakeModel` 和 `FakeOrderTool`；命令行入口在 [typescript/src/main.ts](typescript/src/main.ts)。Java 开发者可结合 [[03-工程实践/TypeScript 与 Java 实现对照]]，用熟悉的 Service、DTO 和接口适配器理解同一套职责，不需要先学 Python。

这里的“模型”是一段确定性规则：第一次提出查订单，拿到结果后拼出回复。它不会理解任意自然语言，实验验证的是调用链和程序边界。`simulated_usage.tokens` 和 `simulated_usage.tool_ms` 都是人为设定的教学数字，不是真实模型用量、计费或性能测量。

## 先跑成功场景

在仓库根目录执行：

```powershell
npm --prefix labs/01-agent-runtime/typescript ci --ignore-scripts
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario success
```

输出是 JSON，关键结果如下；完整输出还包含逐步 `trace`：

`start` 会先自动编译；npm 和编译器可能先打印几行命令信息，再输出下面的 JSON。只需要纯 JSON 时，可在构建后运行 `node labs/01-agent-runtime/typescript/dist/src/main.js --scenario success`。

```json
{
  "case_id": "success-pending",
  "status": "completed",
  "final_response": "订单 ORD-001 当前状态：待发货。数据时间：2026-09-01T08:00:00Z。",
  "simulated_usage": {
    "model_calls": 2,
    "tokens": 40,
    "tool_attempts": 1,
    "tool_successes": 1,
    "tool_ms": 10
  }
}
```

为什么查一次订单，却请求两次模型？第一次模型只提出 `get_order_status({"order_id": "ORD-001"})`；Runtime 检查参数和权限，再执行工具；第二次模型看见工具观察结果，才生成最终回复。

在这个订单实验里，`final` 只是模型提出“可以结束”的申请。Runtime 必须已经取得通过鉴权与格式检查的订单观察，并确认回复与“订单号 + 状态 + 数据时间”的固定模板完全一致，才能标记 `completed`。查询前还会检查订单号是否等于本次任务的原始目标；即使另一张订单属于同一租户、有权访问，也不能拿它替代当前目标，偏离目标会返回 `TARGET_MISMATCH`，不执行工具。模型提前回答、改写观察副本或编造其他状态，会得到 `unverified_final`。这是一项范围很窄的确定性校验，不是通用的自然语言事实核查；真实系统不能把“模型说完成了”直接当成业务验收通过。

| 角色 | 类比 | 本实验里的具体职责 |
|---|---|---|
| FakeModel | 提交查询申请的客服 | 提出调用，或根据观察结果回复 |
| Runtime | 审核并调度申请的值班主管 | 参数校验、租户鉴权、结果验收、预算、步数、取消、错误与 trace |
| FakeOrderTool | 订单柜台 | 返回合成订单的状态与数据时间，并在入口再次校验权限 |
| fixtures | 实验用样本箱 | 固定订单、故障开关和期望行为 |

`tenant_id` 来自 Runtime 的可信身份上下文。实验用 fixture 代替登录系统注入它；工具参数只能包含 `order_id`。生产中必须从服务端已验证的身份取得租户，不能直接相信用户或模型自报的租户。

## 一次只打开一个故障开关

```powershell
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario schema_error
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario unauthorized
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario timeout
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario loop_limit
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario cancelled
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario budget_limit
```

| 场景 | 你应看到的现象 | 帮你理解什么 |
|---|---|---|
| `schema_error` | 模型偷偷增加 `tenant_id`，被参数校验拒绝；工具执行 0 次 | 能解析的对象也可能不符合工具契约 |
| `unauthorized` | 参数格式合法，但 ORD-900 属于另一个租户；工具执行 0 次 | 格式合法不代表有权操作 |
| `timeout` | 模拟耗时 250 ms，超过 100 ms 限制；无成功观察结果 | 超时应返回未知/失败，不能编造业务结果 |
| `loop_limit` | 模型重复查单，调用 3 次后停止 | 能调用工具不代表能自主结束，Runtime 要兜底 |
| `cancelled` | 模型已提出调用，但执行前收到模拟取消信号 | 取消检查要放在动作边界，不能只改界面状态 |
| `budget_limit` | 总模拟预算 30，每次模型调用收费 20；查询后无法再调用模型 | 预算不足可能发生在拿到资料之后、生成答案之前 |

这里的超时通过比较预设数字注入，没有启动真正的异步任务或等待 100 ms；取消是预设检查点，不演示如何中断一个正在进行的网络请求。单场景演示即使进入预设失败状态，也以退出码 0 结束；看 JSON 的 `status` 判断业务结果。

## 用固定样本做一次回归评测

```powershell
npm --prefix labs/01-agent-runtime/typescript run evaluate
npm --prefix labs/01-agent-runtime/typescript test
```

评测数据集 `synthetic-runtime-v1` 固定 12 条：4 条成功、2 条 schema 拒绝、2 条无权访问/不存在，以及超时、循环、取消、预算各 1 条。每条检查状态、工具执行次数、回复中的关键内容和预算上界。预期输出 `total: 12, passed: 12, failed: 0`；任意评测失败时命令退出码为 1。某一条执行或校验抛出异常时，评测保留 `CASE_ERROR` 失败行并继续后续样本；空数据集则报 `INVALID_DATASET` 并非零退出，不能产生“0 条全部通过”的结论。

单元测试还覆盖权限、同租户换单、参数、预算/循环、超时、取消、无观察的 final、模型改写证据、非法工具结果、模型异常、单条评测异常隔离以及空数据集退出码。模型调用异常归类为 `status: model_error`、`error_code: MODEL_ERROR`；用户输出和 trace 不包含异常原文，避免把请求或凭据带出来。本实验把失败调用也算作一次调用并计入固定模拟 token，真实计费仍需真实 usage 对账。

这 12 条全部是公开可见的合成回归样本，没有训练集/测试集划分。12/12 只表示这些预设行为符合预期，不能推导真实模型正确率、泛化能力或生产安全性。Runtime 的订单模板验收只检查与已读取数据的一致性，不证明源数据本身正确或仍然最新；评测层的关键字检查也很粗，真实业务还需要结构化断言、引用核对和人工抽查。

可以先改 [fixtures/orders.json](fixtures/orders.json) 中 ORD-001 的状态，再跑成功场景，观察回复跟随工具数据变化；随后恢复该值，否则固定样本的预期答案会使评测失败。这正好说明“数据变了”和“程序回归了”需要分别判断。TypeScript 与可选 Python 版本共用这一份订单和 [cases.json](fixtures/cases.json)，不会各自维护另一套预期。

## TypeScript 里值得特别注意的三处

1. 模型返回值首先是 `unknown`。`as ToolCall`、接口定义和 `tsc` 通过都不代表外部 JSON 已合法，仍需运行时校验并收窄类型。
2. 模型和工具通过 Promise 接口调用。`await` 前后都可能收到取消；终止本地等待不证明外部动作已撤回。这个 fake 实验只模拟受控检查点，真实网络要传递取消信号并核对结果。
3. `tenant_id` 放在可信执行上下文，不放进模型可改写的工具参数。这与你给业务 Service 传递已认证用户是同一种边界。

TypeScript 编译检查程序内部的类型使用；回归测试检查实际输入和运行行为。二者都需要，不是二选一。

## 如何逐步接入真实模型

1. 实现 TypeScript 模型接口，替换 `FakeModel`，将供应商响应校验后归一成 `tool_call` 或 `final`；让适配器保存协议要求的消息历史与工具调用 ID，并回传对应工具结果。Java 实现也是相同的接口替换思路。
2. 保留 Runtime 和工具入口的鉴权、校验及停止条件，并为实际任务定义独立验收。当前是手写的小 schema 和固定订单回复模板；工具复杂后可采用 schema 库，开放式回答也需要独立设计证据与业务验收，不能直接取消 final 检查。
3. 将固定的 20 个模拟 token 改为调用前预算预留、调用后真实 usage 对账；不要把本实验的已知固定费用当成真实模型的费用预测。
4. 将假的延迟与取消开关换成真实 deadline、请求取消和错误分类，补上网络级集成测试。引入真实模型后再增加自然语言测试集、重复运行与人工评测。

实验没有实现持久化、崩溃恢复、流式输出、并发、自动重试或写操作。它也不证明“收到取消就能撤回已经完成的操作”。若下一步添加退款等写工具，需要单独设计审批、幂等和结果对账，不能把这个只读示例直接改名后上线。

## 3 个小练习与参考答案

1. 把 `max_model_calls` 改成 1，成功场景为什么不能生成最终回复？

   示例答案：唯一一次模型调用用来提出查单。工具结果回来了，但没有第二次调用额度，因此进入 `step_limit`；有工具结果与有最终答案是两种状态。

2. 模型把参数改成 `{"order_id":"ORD-900"}`，删掉了多余字段，是否应该允许执行？

   示例答案：schema 校验会通过，但 tenant-a 仍不拥有这张订单，鉴权应拒绝。可运行 `unauthorized` 对照 trace 中的两个检查阶段。

3. 为订单状态“已退货”增加一个成功样本，最少改哪些文件？

   示例答案：在 `orders.json` 增加该订单，在 `cases.json` 增加同租户的成功输入与期望状态/执行次数/回复关键字，再跑 `--evaluate`。此时样本数应变成 13，并给数据集版本与文档说明同步升级。

## 可选：保留的 Python 对照版

原版 [main.py](main.py) 与 [Python 测试](tests/test_runtime.py) 保留，用于语言间对照；不在 TypeScript 学习必做清单中。已有 Python 3.10+ 时可以运行：

```powershell
python labs/01-agent-runtime/main.py --scenario success
python labs/01-agent-runtime/main.py --evaluate
python -m unittest discover -s labs/01-agent-runtime/tests -v
```

Python 版使用同步 fake 接口，TypeScript 版使用 Promise 接口；两者演示同一套固定场景，但都不是通用生产 Runtime。若只学习 Node.js/TypeScript，可以跳过本节。

继续阅读：[Tool Calling](../../02-核心机制/04-Tool%20Calling.md)、[Tool 设计](../../03-工程实践/Tool%20设计.md)、[Agent 评测](../../06-评测安全生产/Agent%20评测.md)。
