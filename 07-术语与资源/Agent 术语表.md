---
tags:
  - glossary
---

# Agent 术语表

| 术语 | 通俗解释 | 深入阅读 |
| --- | --- | --- |
| LLM | 根据上下文生成 token 的模型 | [[01-基础/01-LLM 基础]] |
| Prompt | 交给模型的任务契约和上下文 | [[01-基础/02-Prompt 与结构化输出]] |
| Structured Output | 按 schema 返回可被程序消费的数据 | [[01-基础/02-Prompt 与结构化输出]] |
| Tool Calling | 模型提出工具请求，由 Runtime 执行 | [[02-核心机制/04-Tool Calling]] |
| RAG | 检索外部证据后再生成回答 | [[02-核心机制/05-RAG]] |
| Embedding | 把内容映射为便于相似度计算的向量 | [[02-核心机制/05-RAG]] |
| Memory | 保存和读取后续决策需要的状态 | [[02-核心机制/06-Memory]] |
| Agent Loop | 决策、执行、观察、再决策的循环 | [[02-核心机制/07-Agent Loop]] |
| Planning | 把目标拆成步骤并动态调整 | [[02-核心机制/08-Planning 与 Reflection]] |
| Reflection | 按标准检查并修订结果 | [[02-核心机制/08-Planning 与 Reflection]] |
| Workflow | 主要由代码预定义的执行路径 | [[03-工程实践/Workflow 与 Agent]] |
| Multi-Agent | 由编排层协调多个角色化执行单元 | [[02-核心机制/09-Multi-Agent]] |
| MCP | AI 应用发现和调用外部能力的协议 | [[04-框架与生态/MCP 概览]] |
| Trace | 一次 run 内各步骤的关联轨迹 | [[06-评测安全生产/可观测性与生产化]] |
| Eval | 用固定样本和标准比较系统质量 | [[06-评测安全生产/Agent 评测]] |
| State | 当前 run 的确定性业务和执行状态 | [[03-工程实践/状态、事件与持久化]] |
| Checkpoint | 可暂停、恢复的状态快照 | [[03-工程实践/状态、事件与持久化]] |
| Idempotency | 同一业务意图重复执行仍只产生一次效果 | [[03-工程实践/错误恢复与幂等]] |
| HITL | 在审批、补充信息或接管点引入人工 | [[03-工程实践/Human-in-the-loop]] |
| Model Gateway | 统一模型能力、路由、错误和 usage 的边界 | [[03-工程实践/模型网关与路由]] |
| Prompt Injection | 不可信文本诱导模型违反原有规则 | [[06-评测安全生产/Prompt Injection 攻防]] |
| Reranker | 对检索候选进行更精细的相关性重排 | [[02-核心机制/05-RAG]] |
| Recall@k | 正确证据是否出现在前 k 个检索结果中 | [[06-评测安全生产/Agent 评测]] |
| SLO | 对服务质量目标的明确承诺 | [[06-评测安全生产/可观测性与生产化]] |
