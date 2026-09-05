---
aliases:
  - HITL
tags:
  - engineering/approval
  - security
status: seed
---

# Human-in-the-loop

## 人工介入不只是“弹一个确认框”

Human-in-the-loop 包含三类能力：

1. **审批**：对高风险动作 approve/edit/reject。
2. **补充信息**：Agent 缺少必要事实时暂停并提问。
3. **接管**：自动流程无法可靠继续时，把完整上下文交给人工处理。

## 审批请求必须包含

- 动作名称和业务影响
- 真实、规范化的参数
- 目标资源当前版本
- 触发原因和来源证据
- 费用或不可逆影响
- 过期时间
- 批准后是否立即执行

用户确认的是具体 action hash，不是自然语言“可以”。任何参数变化都使旧批准失效。

> [!example]- 帮助理解：用户实际批准的是什么
> ```yaml
> action: refund_payment
> subject: user-17
> tenant: shop-A
> resource: payment-P2
> resourceVersion: 7
> normalizedArgs: {amount: 88, currency: CNY}
> evidenceRefs: [payment-query-72, policy-v3-sec4.2]
> actionHash: sha256:example
> expiresAt: 2026-08-17T11:00:00+08:00
> ```
> 用户看到版本 7 的退款预览并批准；如果执行前资源已变成版本 8，旧 action hash 就不能继续使用。系统应重新查询、生成新预览并再次确认。

## 暂停与恢复

审批可能几小时后才完成，所以运行状态必须持久化。恢复时重新验证：用户权限是否仍存在、资源版本是否变化、确认是否过期、系统策略是否升级。

## Edit 的边界

允许用户修改动作参数时，修改后的参数需要重新经过 schema、业务校验和策略评估。不能把编辑内容直接绕过 Agent Runtime 发给工具。

## 何时强制介入

- 删除、支付、退款、发送外部消息等不可逆动作
- 模型置信不足且错误代价高
- 规则冲突或关键证据互相矛盾
- 访问敏感数据或跨权限边界
- 达到自动尝试上限

## 体验指标

除了自动化率，还要看：审批等待时间、无效审批率、用户拒绝原因、修改参数比例、人工接管后的解决率。目标不是消灭人工，而是把人工放在最有价值的决策点。

## 章节练习

审批页显示“退还 P2 的 88 元”，用户批准后修改为退还 P1 的 880 元。能否复用原批准？如果批准后权限被撤销呢？

> [!example]- 示例答案（参考）
> 不能。目标或金额变化会改变待批准动作，必须重新校验并展示新预览；原批准不能移用。即使参数不变，执行前发现用户权限已撤销，也应拒绝执行并记录原因。审批表达意愿，授权决定能不能做，二者缺一不可。

相关：[[06-评测安全生产/安全与权限]] · [[03-工程实践/状态、事件与持久化]] · [[03-工程实践/身份、凭据与委托授权]]

## 来源

- [LangChain JavaScript/TypeScript Human-in-the-loop 中间件](https://docs.langchain.com/oss/javascript/langchain/human-in-the-loop)（核对日期：2026-09-05；框架恢复语义另见 [[04-框架与生态/LangGraph 概览]]）
