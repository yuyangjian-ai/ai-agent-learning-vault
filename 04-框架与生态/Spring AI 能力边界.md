---
tags:
  - ecosystem/spring-ai
status: seed
---

# Spring AI 能力边界

## 适合覆盖的能力

- 模型客户端与 Prompt 模板
- 结构化输出
- Tool Calling
- Chat Memory 抽象
- RAG、Embedding、VectorStore
- Advisors、可观测性和模型供应商适配

## 仍需业务层负责

- 复杂 [[02-核心机制/07-Agent Loop]] 和状态机
- 工具权限、审批、租户隔离
- 幂等、事务、补偿与失败降级
- 面向业务目标的回归评测集
- 审计、成本预算和生产告警

## 正确定位

Spring AI 更像 Agent 开发工具箱和基础设施层，不是“自动生成完整 Agent”的平台。它能减少模型、RAG 和工具集成的样板代码，但系统是否可靠仍取决于普通软件工程设计。

## 学习建议

先用原生模型 API 完成 [[05-项目实战/01-Minimal Chatbot]]，理解消息与 tool call 的真实数据；再用 Spring AI 重写，对比它抽象了什么、哪些责任仍然存在。

相关：[[04-框架与生态/框架选型]] · [[03-工程实践/Agent 系统架构]]

## Spring AI 的分层理解

| 层次 | 主要抽象 | 用途 |
| --- | --- | --- |
| 模型层 | ChatModel、EmbeddingModel 等 | 对接不同模型能力 |
| 客户端层 | ChatClient | 以 fluent API 组织 Prompt、工具和返回 |
| 增强层 | Advisor | 在调用前后加入 Memory、RAG、工具循环等横切逻辑 |
| 数据层 | Document、VectorStore、ChatMemory | 文档、检索与会话历史 |
| 观测层 | Micrometer observations | 模型、向量和工具调用指标与 trace |

## 结构化输出示例

```java
record TicketDecision(String category, String priority, List<String> evidence) {}

TicketDecision decision = chatClient.prompt()
    .user("Analyze this ticket: ...")
    .call()
    .entity(TicketDecision.class);
```

Spring AI 可以根据目标类型帮助生成格式并转换结果，但官方文档也明确指出，通用 converter 是 best effort；业务代码仍需验证枚举、证据和字段关系。支持原生 structured output 的模型可以使用供应商原生约束，但仍不能跳过业务校验。

## Tool Calling 示例

```java
class OrderTools {
    @Tool(description = "Read the current order status; does not modify the order")
    OrderStatus getOrderStatus(String orderNumber) {
        return orderService.getStatus(orderNumber);
    }
}

String answer = chatClient.prompt()
    .user("Where is order A123?")
    .tools(new OrderTools())
    .call()
    .content();
```

当前官方参考中，`ChatClient` 可以由框架控制工具循环，也提供 Advisor 控制或用户手动控制的方式。需要自定义审批、状态机和中间进度时，不应只依赖默认自动循环。

> [!example]- 帮助理解：`@Tool` 只解决了一部分工作
> 以“取消订单”为例：
>
> | 层次 | 责任 |
> | --- | --- |
> | Spring AI | 把工具描述交给模型、解析调用参数、回填结果 |
> | Web/Runtime | 注入已认证用户、租户、deadline 和 run ID |
> | 业务服务 | 校验订单归属、状态、取消规则、事务和幂等 |
> | 审批层 | 对高风险订单暂停、展示预览并恢复运行 |
>
> 给方法加上 `@Tool` 不会自动获得业务授权，也不会自动提供可恢复状态机。

## RAG 与 Memory

- `QuestionAnswerAdvisor` 适合基础向量问答。
- `RetrievalAugmentationAdvisor` 提供更模块化的 query、retrieval、post-retrieval 和 generation 组合。
- `MessageChatMemoryAdvisor` 将会话历史加入消息。
- `ChatMemoryRepository` 负责存储抽象。

Chat Memory 不等于业务状态，也不等于长期个性化 Memory。订单状态、审批状态和 run checkpoint 仍应由业务数据库管理。

## Advisor 的价值与风险

Advisor 适合封装日志、Memory、RAG、策略等重复模式，但多个 Advisor 的顺序会影响输入和输出。必须测试调用顺序、流式路径、异常传播和敏感内容是否进入 observation。

## 可观测性

Spring AI 基于 Spring 生态的观测能力记录模型和工具相关 observation。工具参数与结果可能敏感，官方默认不会导出完整内容；打开内容采集前必须做安全评审。

## 建议的学习顺序

1. 直接用 `ChatClient` 完成普通调用和 typed result。
2. 增加一个只读 `@Tool`，观察真实 tool-call 循环。
3. 增加 `ChatMemory`，区分对话历史与业务状态。
4. 用 VectorStore + Advisor 完成最小 RAG，并加入元数据过滤。
5. 手动控制一次复杂工具循环，实现审批和 checkpoint。
6. 接入 trace 和固定评测集，再讨论生产化。

> [!warning] 版本提示
> Spring AI API 仍在持续演进。代码落地时以项目锁定版本的 reference 与 upgrade notes 为准，不要直接复制与项目版本不匹配的示例。

## 官方资料

- [Spring AI API 总览](https://docs.spring.io/spring-ai/reference/api/index.html)
- [Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Structured Output Converter](https://docs.spring.io/spring-ai/reference/api/structured-output-converter.html)
- [Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Chat Memory](https://docs.spring.io/spring-ai/reference/api/chat-memory.html)
- [Observability](https://docs.spring.io/spring-ai/reference/observability/index.html)

资料核对日期：2026-07-14。
