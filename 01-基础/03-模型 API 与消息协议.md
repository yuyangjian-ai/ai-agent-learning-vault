---
tags:
  - concept/api
status: seed
---

# 模型 API 与消息协议

学完本章，你应能画出一次请求与响应、区分文本和工具结果，并让失败落入明确分支。先读 [[01-基础/02-Prompt 与结构化输出]]；第一次掌握调用、校验和超时，接工具时再回看消息往返。

## 一次调用包含什么

- 模型及其支持的采样/推理参数
- 按角色排列的消息，或有明确类型的输入项
- 可选的工具定义和输出 schema
- 请求标识、超时、取消信号

典型消息角色包括 system/developer、user、assistant、tool。角色优先级和具体字段由模型 API 决定，不能假设不同供应商完全一致。

## 响应不是只有一段文字

可以把模型响应想成一个快递箱，里面可能同时有“给人的说明”“交给程序的动作单”和“运费清单”。程序要逐项识别，不能只拿第一件东西当最终答案。

| 内容 | Runtime 的处理 |
| --- | --- |
| 文本/结构化结果 | 等完整结束后进行 schema 与业务校验 |
| 工具调用 | 按调用 ID 收集完整参数，再鉴权和执行 |
| 引用/文件产物 | 保存来源、资源权限与有效期 |
| refusal / incomplete / error | 进入拒答、未完成或错误分支，不强行解析为业务 JSON |
| usage / 结束状态 | 累计预算，确认是否真的完成 |

模型响应 `completed` 只说明这次模型生成结束；如果里面还有待执行的工具调用，整个 Agent 任务仍未完成。

## 后端必须记录

| 字段 | 用途 |
| --- | --- |
| trace/run ID | 串起一次完整运行 |
| 模型与版本 | 复现行为 |
| Prompt 版本 | 对比变更 |
| token/成本 | 容量和预算管理 |
| 延迟与重试 | 定位性能问题 |
| 工具轨迹 | 审计 Agent 行为 |

## 失败不是一种失败

至少区分：网络错误、限流、超时、上下文过长、内容策略拒绝、schema 不合法、工具执行失败。不同错误应有不同重试和降级策略。

## 最小实现检查表

- [ ] 设置连接与整体超时。
- [ ] 只对可恢复错误做有上限的退避重试。
- [ ] 支持取消请求。
- [ ] 不把密钥、完整敏感 Prompt 写入日志。
- [ ] 保存可重放的输入摘要与版本信息。

实践：[[05-项目实战/01-Minimal Chatbot]]

## 消息在一次 Agent 运行中的变化

```text
system/developer: 稳定规则与工具边界
user:             本次目标
assistant:        请求调用 get_order_status
tool:             {"status":"paid","updatedAt":"..."}
assistant:        根据工具结果形成回答
```

工具结果不是新的用户指令，而是一次外部观察。Runtime 必须把调用 ID 与工具结果对应起来，避免并行调用时串错结果。下例使用 Chat Completions 风格的字段名。

> [!example]- 帮助理解：一次 Tool Call 实际跨越两次模型请求
> ```text
> Request 1 messages:
>   user: 查询订单 A123
>
> Response 1:
>   assistant: tool_call(id=tc_1, name=get_order_status, args={A123})
>
> Runtime 执行工具后，Request 2 messages:
>   user: 查询订单 A123
>   assistant: tool_call(id=tc_1, ...)
>   tool: tool_call_id=tc_1, result={status: shipped}
>
> Response 2:
>   assistant: 订单 A123 当前已发货……
> ```
> 工具通常由应用在两次模型请求之间执行。在这种显式消息历史的 API 中，第二次请求既要带回模型原先的调用记录，也要带回 ID 匹配的工具结果。

> [!info] 这不是所有供应商共用的消息格式
> 上例采用常见的 Chat Completions 风格。应用内部可以先归一化成 `ToolRequest{id,name,args}` 和 `ToolResult{id,data,error}`，再由适配层映射。不要把供应商 SDK 对象直接当业务状态。

下面是 OpenAI 两种 API 的字段对照，仅展示关联关系，不是完整请求体：

| 环节 | Chat Completions | Responses |
| --- | --- | --- |
| 模型提出调用 | assistant 的 `tool_calls`，其中有 `id` | `type=function_call` 的输出项，使用 `call_id` |
| 应用返回结果 | `role=tool`，使用 `tool_call_id` | `type=function_call_output`，使用同一 `call_id` |
| 延续上下文 | 显式带回所需消息历史 | 可显式回传所需输出项，或使用 `previous_response_id` |

工具结果必须关联到原调用；手动管理推理模型的上下文时，还要按官方要求保留所需 reasoning items。不要只保存可见文本，丢失其他响应项。[Function Calling 官方说明](https://developers.openai.com/api/docs/guides/function-calling)

## 工具由谁执行

自定义函数通常由应用执行；供应商内置搜索等工具可能在供应商服务中执行；远程 MCP 工具则由对应 Server 执行。配置工具时先确认执行位置、允许访问的数据、谁校验权限、谁记录费用。不能把“应用没调用本地函数”理解成“本次没有外部动作”。

## 推理预算与可见解释

`reasoning effort` 可以理解为给解题过程的计算预算倾向，和回答长短、temperature 都不是一回事；支持的值取决于模型。较高预算可能改善复杂题，也可能增加耗时和费用，应以同一评测集比较。

推理 token 可能计入输出费用与输出上限，即使最后只显示两句话。不要把原始内部思考作为日志或审计依赖；记录输入版本、工具观察、可见结论及验证结果。供应商提供的推理摘要也不等于完整内部过程。[Reasoning 官方说明](https://developers.openai.com/api/docs/guides/reasoning)

> [!example]- 帮助理解：没有最终文字也可能已经产生费用
> 假设任务输出预算耗尽，响应为 `incomplete`，但 usage 已记录输入和推理消耗。程序应累计费用并返回“未完成”，再按剩余预算决定是否重试，不能当作“空响应，免费再来一次”。

供应商保存的 response/conversation 状态用于续接模型上下文；订单、审批、权限撤销和任务完成状态仍放在应用自己的数据库。两类状态不能互相代替。

## 流式响应

流式传输改善首 token 延迟，但给工程带来额外状态：连接可能中途断开、结构化 JSON 在完成前不合法、工具调用参数可能分片到达、用户可能主动取消。

可靠实现通常分成两层：

- 传输层接收事件并维护连接状态。
- 组装层按事件类型累积文本、工具参数、usage 和结束原因。

在拿到明确的完成事件前，不要把半截 JSON 交给业务系统。客户端断开时应传播取消信号，避免后台继续消耗 token。

原生结构化输出也可能遇到拒答或截断。先检查状态和拒答，再解析完整结果；不要把安全拒答当格式错误反复“修复”。[Structured Outputs 官方说明](https://developers.openai.com/api/docs/guides/structured-outputs)

## 超时设计

不要只设置一个“60 秒超时”。至少区分：

| 超时 | 含义 |
| --- | --- |
| connection timeout | 无法建立连接 |
| first-token timeout | 已连接但模型迟迟不开始返回 |
| idle timeout | 流式连接长时间没有新事件 |
| total/run deadline | 整个模型或 Agent 运行的最终期限 |
| tool timeout | 某个外部工具的独立上限 |

所有重试都必须服从最外层 deadline，否则每层重试会把总耗时无限放大。

## 重试矩阵

| 错误 | 通常是否重试 | 注意事项 |
| --- | --- | --- |
| 429/暂时性 5xx | 是 | 指数退避、抖动、尊重服务端提示 |
| 网络瞬断 | 是 | 流式请求需判断是否已产生副作用 |
| 参数/schema 错误 | 否 | 修复客户端或有限纠正模型输出 |
| 内容过长 | 否 | 裁剪/摘要后作为新请求 |
| 鉴权失败 | 否 | 不要靠重试掩盖配置问题 |
| 工具写入超时 | 谨慎 | 先用幂等键查询是否已成功 |

## 供应商适配层

业务代码应依赖自己的最小接口，例如 `generate()`、`stream()`、`embed()`，而不是让所有模块直接依赖某家 SDK。适配层负责消息格式、错误归一化、usage、trace 字段和能力差异。

但不要为了“未来可能换模型”创建覆盖所有厂商特性的巨大抽象。先抽象当前确实需要的共同能力，把工具并行、推理强度等差异保留为显式 capability。

## 安全与隐私

- API key 只由服务端密钥系统管理。
- 日志默认不记录完整 Prompt、工具结果和用户敏感信息。
- 明确供应商的数据保留、训练使用、区域和合规设置。
- 为用户输入和模型输出设置大小上限。
- trace 中保存可定位问题的摘要与哈希，而非无限复制原文。

## 实验任务

为同一个调用模拟限流、超时、JSON 截断和客户端取消，检查系统返回的错误类型、重试次数和 trace 是否符合预期。

> [!example]- 示例答案（参考）
> | 场景 | 对外错误 | 重试 | Trace 关键字段 |
> | --- | --- | --- | --- |
> | 首次 429，随后成功 | 无；最终成功 | 1 次退避 | `attempts=2`、429、等待时间 |
> | 超过 total deadline | `MODEL_TIMEOUT` | 0 或服从剩余预算 | deadline、已耗时、取消结果 |
> | JSON 因输出上限被截断 | `MODEL_INCOMPLETE` | 丢弃半成品，预算允许时最多重新生成 1 次 | finish reason、usage、schema 版本 |
> | 客户端取消 | `CANCELLED` | 0 次 | cancel source、供应商请求是否终止 |

长任务的后台执行、回调和取消竞态见 [[03-工程实践/异步任务与取消]]。本章 API 字段核对日期：2026-09-05；具体模型兼容性以锁定版本为准。
