# AI Agent 学习知识库

一套面向开发者的中文 AI Agent 系统学习教程，采用 Obsidian Markdown 组织。

内容从 LLM、Prompt 和模型 API 开始，逐步覆盖 Tool Calling、RAG、Memory、Agent Loop、Planning、Multi-Agent、Context Engineering、MCP、评测、安全和生产化。默认实战采用 **Node.js + TypeScript**，配套 **Java/Spring** 实现对照；不需要先学 Python 或机器学习数学。

## 开始学习

- [从这里开始](00-首页/从这里开始.md)：前置知识、环境准备、第一条运行轨迹和排错
- [知识库首页](00-首页/AI%20Agent%20学习知识库.md)：完整导航
- [贯穿案例：重复扣款工单](00-首页/贯穿案例：重复扣款工单.md)
- [8 周学习路线](00-首页/学习路线.md)
- [知识地图](00-首页/知识地图.md)
- [项目实战总览](05-项目实战/项目总览.md)
- [Agent 术语表](07-术语与资源/Agent%20术语表.md)
- [常见困惑与排错](07-术语与资源/常见困惑与排错.md)
- [TypeScript 与 Java 实现对照](03-工程实践/TypeScript%20与%20Java%20实现对照.md)

## 先跑一个不花钱的实验

在仓库根目录执行。建议使用 Node.js 24 或 22 LTS 与 npm；无需 API Key。首次安装需要联网下载锁定的 TypeScript 编译工具，安装后实验运行不联网：

```powershell
npm --prefix labs/01-agent-runtime/typescript ci --ignore-scripts
npm --prefix labs/01-agent-runtime/typescript run start -- --scenario success
npm --prefix labs/01-agent-runtime/typescript run evaluate
```

它用假模型和合成订单演示工具调用、租户隔离、超时、预算和取消。`12/12` 只表示固定 Runtime 回归通过，不代表真实模型能力；不会退款或发送消息。[实验说明](labs/01-agent-runtime/README.md) 提供预期输出、代码阅读顺序和简短练习答案。原 Python 版本保留为可选对照，不是学习前置。

## 目录

```text
00-首页/           导航、路线与知识地图
01-基础/           LLM、Prompt、模型 API、Embedding
02-核心机制/       Tool Calling、RAG、Memory、Agent Loop、Planning、Multi-Agent
03-工程实践/       架构、上下文、工具、状态、幂等、审批、身份授权、异步任务、模型网关
04-框架与生态/     Spring AI、LangGraph、MCP、多模态与 Computer Use
05-项目实战/       Chatbot、Mini Agent CLI、RAG 助手、客服工单 Agent
06-评测安全生产/   评测、指标手算、安全、Prompt Injection、可观测性、成本性能
07-术语与资源/     术语、常见困惑与排错、问题清单、官方资料与论文
08-学习记录/       学习看板与日记
99-模板/           概念、实验和每日学习模板
labs/              TypeScript 离线实验（无第三方运行时依赖），另保留 Python 对照
scripts/           文档维护用的链接、标题和代码围栏检查及测试
.github/workflows/  文档与实验的自动校验
```

## 推荐学习方式

1. 看贯穿案例，再按照 [8 周学习路线](00-首页/学习路线.md) 阅读核心讲义。
2. 每阶段先达到项目的“基础通过”，再做“标准完成”；“生产加餐”按需深入，不要求八周全部完成。
3. 将失败样本沉淀到评测集，不只记录成功案例。
4. 使用 Obsidian 打开仓库，以获得双向链接、知识图谱和模板体验。

## 这套教程怎样帮助理解

- 用同一条“疑似重复扣款”工单串联概念，而不是每章重新换业务。
- 难点配类比、输入输出、失败分支和可折叠的简短示例答案。
- 四个渐进项目共用明确的数据契约，并标注样本量、验收分母和安全边界。
- 讲义代码块标明伪代码或协议示意；`labs/` 才是仓库内可直接运行的实现。框架章节需读者按锁定版本接入，仓库不包含四个项目的完整生产实现。

## 本地验证

完成上面的依赖安装后，验证 TypeScript 实验：

```powershell
npm --prefix labs/01-agent-runtime/typescript test
npm --prefix labs/01-agent-runtime/typescript run evaluate
```

维护文档时可另外使用 Python 3.10+ 运行 `python scripts/check_docs.py` 和 `python -m unittest discover -s scripts/tests -v`；不想安装 Python 的学习者可让 GitHub Actions 执行这部分。它检查本地 Wiki/Markdown 链接、目标标题和代码围栏，不联网检查外部网址，也不替代内容正确性审阅。

## 注意

框架 API 会持续演进。相关笔记标注了资料核对日期；实际编码时请以项目锁定版本的官方文档为准。教程中的订单、金额、错误与评测数字若标注为示例或合成数据，不是线上系统的实测结论。
