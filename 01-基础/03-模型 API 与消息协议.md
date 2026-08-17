---
tags:
  - concept/api
status: seed
---

# 模型 API 与消息协议

## 一次调用包含什么

- 模型与采样参数
- 按角色排列的消息
- 可选的工具定义和输出 schema
- 请求标识、超时、取消信号

典型消息角色包括 system/developer、user、assistant、tool。角色优先级和具体字段由模型 API 决定，不能假设不同供应商完全一致。

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

工具结果不是新的用户指令，而是一次外部观察。Runtime 必须把 `tool_call_id` 与工具结果对应起来，避免并行调用时串错结果。

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
> 工具通常由应用在两次模型请求之间执行。第二次请求既要带回模型原先的调用记录，也要带回 ID 匹配的工具结果。

## 流式响应

流式传输改善首 token 延迟，但给工程带来额外状态：连接可能中途断开、结构化 JSON 在完成前不合法、工具调用参数可能分片到达、用户可能主动取消。

可靠实现通常分成两层：

- 传输层接收事件并维护连接状态。
- 组装层按事件类型累积文本、工具参数、usage 和结束原因。

在拿到明确的完成事件前，不要把半截 JSON 交给业务系统。客户端断开时应传播取消信号，避免后台继续消耗 token。

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
> | JSON 被截断 | `INVALID_MODEL_OUTPUT` | 最多 1 次结构修复 | finish reason、schema 版本 |
> | 客户端取消 | `CANCELLED` | 0 次 | cancel source、供应商请求是否终止 |
