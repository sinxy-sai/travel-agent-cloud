# Agent 与 AI 应用架构

本文定义 Travel Agent Cloud 的 AI 应用层设计。目标不是堆叠 Agent 概念，而是在现有微服务架构上落地一个可运行、可验证、可演进的旅行规划 Agent 系统。

## 设计结论

当前采用“少量 Agent + 明确 Skill + 原子 Tool + 有界工作流”的路线。

- 顶层只保留两个 Agent：`research_agent` 和 `planner_agent`。
- 运行时保留四个项目 Skill：`travel_research`、`route_budget`、`itinerary_composition`、`plan_quality`。
- 外部事实数据通过 `travel-mcp` 和 FastMCP 工具服务获取，`agent-runtime` 不直接绑定高德等供应商字段。
- Context Engineering 使用统一 `PlanningContext`，再按节点生成只读上下文视图。
- RAG 先使用 PostgreSQL 结构化知识表，后续再根据收益决定是否接入 `pgvector`。
- Harness Engineering 先覆盖固定 eval cases、trace、schema、来源和质量规则，不引入重型 benchmark 平台。

## 服务边界

```text
frontend
  -> travel-gateway
      -> travel-auth        用户、认证、OAuth、账户数据
      -> travel-agent       会话、聊天、摘要、Agent 状态门面
      -> travel-trip        行程持久化、版本、导出、异步生成
      -> agent-runtime      LangGraph/LangChain 编排与 AI 执行核心
      -> travel-mcp         旅行工具与供应商 API 封装
```

`agent-runtime` 只负责 AI 编排和执行，不再拥有用户、会话、行程持久化边界。

## LangGraph 工作流

主旅行规划流程：

```text
trip_context
  -> retrieve_knowledge
  -> trip_draft
  -> research_agent
  -> route_budget
  -> planner_agent
  -> trip_validation
```

各节点职责：

- `trip_context`：把请求解析为统一 `PlanningContext`。
- `retrieve_knowledge`：从 RAG 检索目的地知识、历史优质案例和规划注意事项。
- `trip_draft`：在 LLM 可用时生成初稿；不可用时允许后续 Skill 继续构造结果。
- `research_agent`：调用 `travel_research` Skill 获取 POI、天气、酒店、餐食等事实。
- `route_budget`：调用 `route_budget` Skill 生成路线和预算。
- `planner_agent`：调用 `itinerary_composition` Skill 组装 `TripPlanResponse`。
- `trip_validation`：调用 `plan_quality` Skill 做 schema、预算、来源和节奏检查，并最多自动修复 2 次。

## Agent

### Research Agent

目标是为规划准备最小可信事实集。它可以选择旅行工具，但不生成最终行程，不写业务数据库。

输出包含：

- 每日候选景点
- 天气信息
- 酒店和餐食候选
- 数据来源与状态
- 缺口和降级原因

### Planner Agent

目标是把用户约束、RAG 结果、研究事实、路线和预算组装为结构化行程。它负责生成、修订和单日重生成的共同规划能力。

Planner Agent 不直接抓网页，不直接持久化数据，也不能把 fallback 或 LLM inferred 内容伪装成实时事实。

## Skills

项目 Skill 位于 `agent-runtime/app/skills/`，它们是项目后端运行时能力，不是 Codex 个人技能，也不是可共享 marketplace skill。

| Skill | 职责 |
| --- | --- |
| `travel_research` | 搜集并整理景点、天气、酒店、餐食事实 |
| `route_budget` | 生成每日路线并估算交通、酒店、餐食、门票预算 |
| `itinerary_composition` | 组装结构化行程，保持输出符合 `TripPlanResponse` |
| `plan_quality` | 执行确定性质量检查并驱动有界修复 |

每个 Skill 需要保持统一契约：

```text
input_schema
output_schema
status: success | partial | fallback | failed
sources[]
issues[]
trace
```

## Tools 与 MCP

Tool 是原子能力，不承担跨步骤决策。当前旅行工具通过 `travel-mcp` 暴露：

- 景点搜索
- 天气查询
- 酒店搜索
- 餐食搜索
- 路线规划
- 预算估算

所有工具结果都需要保留来源状态。工具失败时允许 fallback，但必须在 trace 和 dataSources 中可见。

## Context Engineering

第一版只维护一个 `PlanningContext`：

- 用户请求
- 预算、日期、交通、住宿等约束
- 兴趣和偏好
- 目的地与行程天数
- RAG 检索结果
- 工具事实摘要
- 当前质量报告

注入规则：

- 最多注入 5 条 RAG 命中。
- 长文本必须先摘要再注入。
- 实时天气、路线、营业状态不进 RAG，每次通过工具获取。
- 用户私有记忆必须和公共目的地知识区分。

## RAG 与知识库

RAG 当前最小实现位于 `agent-runtime/app/knowledge.py`。

后端模式：

- `static`：无数据库或依赖不可用时的只读 fallback。
- `postgres`：使用 `agent_knowledge_records` 表进行关键词检索、写入、过期过滤和删除。

运行时接口：

- `GET /api/v1/agent/knowledge`
- `POST /api/v1/agent/knowledge`
- `POST /api/v1/agent/knowledge/seed`
- `DELETE /api/v1/agent/knowledge/{record_id}`

成功生成行程后，runtime 会写入 `itinerary_summary`，有效期 90 天。该写入失败不会让行程生成失败。

## Loop Engineering

质量闭环必须有界：

- 自动修复最多 2 次。
- 补充研究最多 1 次，后续再接入。
- 工具短暂失败最多重试 1 次，后续再细化。
- 达到上限后返回最佳可用结果和明确警告。

优先使用确定性规则检查 schema、天数、每日负载、预算、路线完整性和来源覆盖。LLM Judge 只作为可选增强，不进入默认 CI 门禁。

## Harness Engineering

当前最小 Harness：

- `scripts/smoke-test.ps1` 和 `scripts/smoke-test.sh` 验证服务链路、Agent trace、数据来源、RAG 接口。
- `scripts/ai-eval.py` 离线运行固定用例，默认强制 mock LLM，保证稳定。
- `scripts/ai-eval.py --base-url http://localhost:5173` 可对运行中的 Docker/Gateway 做 HTTP 端到端 eval。
- `scripts/seed-knowledge.py` 可为目的地预置 RAG 知识。

当前不引入 GAIA、AgentBench、WebArena、OSWorld 等通用 Agent benchmark。它们和旅游规划业务目标不完全一致，投入产出比暂时不高。

## 最小技术栈

| 领域 | 当前采用 |
| --- | --- |
| 编排 | LangGraph |
| Agent/工具调用 | LangChain tool-calling |
| Schema | Pydantic |
| 旅行工具 | FastMCP、travel-mcp、高德 Web Service |
| RAG | PostgreSQL，后续可选 pgvector |
| 异步与状态 | PostgreSQL、RabbitMQ、Redis |
| 可观测性 | OpenTelemetry、Prometheus、Grafana、Loki、Tempo |

## 完成标准

AI 应用层阶段性完成需要满足：

- 主流程按 LangGraph 节点运行。
- 两个 Agent 和四个 Skill 的职责清晰。
- 工具来源、fallback 和失败状态可见。
- RAG 支持读取、写入、检索、删除和过期。
- 质量门禁可触发有限自动修复。
- smoke test 和 AI eval 能覆盖端到端结果、trace、质量分和 RAG 状态。
