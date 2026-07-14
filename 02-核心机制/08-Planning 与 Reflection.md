---
tags:
  - concept/planning
status: seed
---

# Planning 与 Reflection

## Planning

Planning 把目标拆成可执行步骤。计划可以由模型生成，但 Runtime 应校验依赖、预算和权限。计划是可修改的工作假设，不是必须照做的真理。

适合先计划的任务：步骤多、有依赖、工具昂贵或风险高。简单问答不需要额外规划，否则只会增加延迟。

## Reflection

Reflection 让系统检查当前结果是否满足明确标准，再决定修正或结束。它应基于证据和 rubric，而不是笼统问“你觉得答案好吗”。

## 常见模式

- Plan → Execute → Re-plan：执行后根据新信息调整计划。
- Draft → Critique → Revise：生成、按标准检查、修订。
- Generate → Verify：用独立工具或规则验证关键事实。

## 防止无限循环

- 每种动作限制次数。
- 只有发现新的具体问题时才允许修订。
- 记录已尝试方案，检测重复。
- 达到预算后输出部分结果和阻塞原因。

## 何时不用

能用确定性代码、单次工具调用或固定 [[03-工程实践/Workflow 与 Agent|Workflow]] 完成时，不要引入自由规划。

## 一个可执行计划的 schema

```yaml
goal: 找出服务启动失败的根因
steps:
  - id: s1
    action: search_logs
    inputs: {query: "ERROR"}
    depends_on: []
    success: 找到至少一个带时间和组件名的错误
  - id: s2
    action: inspect_config
    inputs: {componentFrom: s1}
    depends_on: [s1]
    success: 确认运行值与期望值是否一致
limits:
  max_steps: 6
  deadline_seconds: 120
```

好计划包含可观察的成功条件和依赖，不应写“深入分析”“解决问题”这类无法执行和验收的步骤。

## 什么时候重新规划

只有发生以下变化时才值得 re-plan：关键假设被证伪、工具返回新约束、步骤不可执行、用户目标改变、预算不足。每完成一步都重新生成整份计划会增加漂移和成本。

## Reflection 的 rubric

以代码解释任务为例，rubric 可以是：

- 结论是否引用真实文件和行号？
- 是否区分确认事实与推测？
- 是否回答了用户的具体问题？
- 是否遗漏异常路径或配置入口？

检查器返回结构化缺陷：`criterion`、`evidence`、`severity`、`suggested_action`。只有严重且可修复的缺陷才进入修订。

## 独立验证优于自我认同

同一个模型评价自己的答案可能重复原来的偏差。能用确定性工具验证时，优先使用编译器、schema、数据库查询、单元测试或引用检查。模型评审适合判断语义完整性，但仍需具体标准。

## 计划失败的常见模式

- 过度分解：每一步都需要一次模型调用。
- 假计划：列了步骤，但执行时完全不参考。
- 计划与权限脱节：包含当前用户不能执行的动作。
- 把猜测当依赖输出：后续步骤建立在未验证事实之上。
- 没有停止标准：反复“再检查一次”。

## 练习

为“分析一个陌生代码仓库的登录流程”分别设计固定 Workflow 和动态 Planning 方案，比较在哪些节点真正需要模型决定下一步。
