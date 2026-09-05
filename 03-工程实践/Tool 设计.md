---
tags:
  - engineering/tools
status: seed
---

# Tool 设计

## 设计目标

工具接口要让模型容易选对，也要让执行层容易限制、测试和审计。

## Schema 示例

```json
{
  "name": "get_order_status",
  "description": "按订单号读取当前订单状态；不修改订单",
  "parameters": {
    "type": "object",
    "properties": {
      "orderNumber": { "type": "string" }
    },
    "required": ["orderNumber"],
    "additionalProperties": false
  }
}
```

## 原则

- 名称使用业务动作，不暴露底层实现细节。
- 描述明确“何时用、何时不用、是否修改数据”。
- 参数数量少、类型强、默认值少。
- 返回 `status/data/error/meta` 等稳定结构。
- 错误告诉模型下一步能做什么，但不泄露内部堆栈。
- 写操作支持幂等键；不可逆动作采用预览/确认两阶段。

## 测试维度

1. schema 单元测试；2. 权限测试；3. 超时与重试；4. 重复调用；5. 大结果裁剪；6. 恶意参数；7. 模型是否能根据描述选对工具。

## 反模式

- 万能 `execute(command)` 或 `request(url)`。
- 把认证交给模型传参。
- 工具失败后返回自然语言“好像不行”。
- 把数据库异常原样塞回模型上下文。

> [!example]- 帮助理解：订单业务中为什么不宜直接暴露 `request(url)`
> 用户说“查一下订单 A123”。如果只给模型一个 `request(url, method, body)`，模型还要自己拼域名、路径、租户参数和认证头；它既可能写错，也可能尝试访问本不该开放的地址。
>
> | 设计 | 模型负责 | Runtime/工具能稳定保证 |
> | --- | --- | --- |
> | `request(url, ...)` | URL、方法、参数甚至认证形式 | 几乎只能做网络层限制 |
> | `get_order_status(orderNumber)` | 订单号 | 固定目标服务、只读语义、租户注入、资源鉴权、超时和审计 |
>
> 窄工具不是“少写几个参数”这么简单，而是把安全边界从 Prompt 搬回确定性代码。底层仍可调用 HTTP，但模型不需要也不应该看见那层自由度。

相关：[[02-核心机制/04-Tool Calling]] · [[06-评测安全生产/安全与权限]] · [[03-工程实践/身份、凭据与委托授权]]

## 工具粒度

太粗的工具如 `manage_customer()` 权限难控、参数复杂；太细的工具会让模型需要很多步骤。合适粒度通常对应一个清晰业务能力，并拥有独立的权限和成功语义。

判断问题：这个动作能否独立授权、独立测试、独立重试、独立审计？如果答案不同，可能应该拆分工具。

## 读写分离

```text
search_orders(criteria)     # 只读、可重复
get_order(orderId)          # 只读、精确
prepare_order_update(...)   # 生成预览，不写入
confirm_order_update(token) # 使用确认令牌写入
```

搜索工具返回候选 ID，精确读取工具返回当前版本；写操作带 `expectedVersion` 防止用户确认期间资源已被其他人修改。

## 身份与权限传递

用户身份、租户、scope 不应出现在模型可自由填写的参数里，而应由 Runtime 的执行上下文注入：

```text
execute(toolCall, ExecutionContext {
  authenticatedUser,
  tenant,
  grantedScopes,
  runId,
  deadline
})
```

模型只提供业务参数。工具内部仍要做资源级鉴权，例如用户有 `orders:read` 不代表能读取其他租户订单。

## 结果大小设计

工具不是给人展示完整报表的接口。提供：分页、字段投影、最大行数、结果摘要和原始资源引用。超过上限时明确返回 `truncated: true` 与下一页游标，避免模型误以为结果完整。

## 幂等与并发

- 读取天然可重试，但要考虑数据在两次读取间变化。
- 创建动作使用客户端幂等键。
- 更新动作使用版本号/ETag 做乐观锁。
- 删除或发送动作应提供确认和明确的不可逆提示。
- 工具超时不等于动作失败，先查询实际结果。

详见 [[03-工程实践/错误恢复与幂等]]。

## Tool Contract 测试

```text
Given 当前用户只能访问 tenant-A
When 模型请求 get_order(order from tenant-B)
Then 工具返回 FORBIDDEN，且响应不泄露订单是否存在
```

测试不应依赖模型。先把工具当普通后端 API 做单元与集成测试，再用模型评测“是否能选对工具”。

## 工具版本变更

新增可选字段通常兼容；删除字段、改变枚举语义、改变副作用则需要新版本。恢复旧 run 时必须使用兼容的工具契约，不能让暂停中的任务自动切到不兼容 schema。

## 练习

为“查询库存并创建补货单”设计工具集。明确哪些字段由模型提供、哪些由执行上下文注入、如何确认、如何避免重复创建。

> [!example]- 示例答案（参考）
> - `search_inventory(skuOrName)`：只读搜索，返回 SKU 候选。
> - `get_inventory(sku, warehouseId)`：只读，返回现存量、在途量、数据版本和观察时间。
> - `prepare_replenishment(sku, warehouseId, quantity, expectedVersion)`：生成供应商、数量、预计金额和 action hash，不写入。
> - `confirm_replenishment(confirmToken)`：创建补货单并返回 order ID。
>
> 模型只提供 SKU 候选、仓库和建议数量；Runtime 注入用户、租户、scope、run ID、deadline 和幂等键。确认令牌绑定预览参数；相同业务意图使用相同幂等键，超时后先查询创建结果。
