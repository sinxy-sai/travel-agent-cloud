# Agent 与 AI 应用架构

本文档定义 Travel Agent Cloud 的 AI 应用架构和最小可用实现范围。目标是在不堆叠概念和框架的前提下，完整落地 Agent、Skills、Tools、MCP、Context Engineering、Harness Engineering、Loop Engineering 与 RAG。

## 1. 架构审计结论

旧设计将旅行规划拆成十余个 Agent，并为景点、天气、酒店、餐食、路线、预算分别定义 Agent 和 Skill。该设计存在以下问题：

- 多数所谓 Agent 只执行一次固定工具调用，没有独立目标、决策或循环，本质上是 Tool 或 Skill。
- Agent、Skill 与 LangGraph node 的职责重复，调用链过长，增加状态同步、错误处理、测试和追踪成本。
- `critic_agent`、`validator_agent` 和 `budget_agent` 与已有确定性质量规则重叠。能用代码验证的约束不应优先交给 LLM。
- `trip_context_agent` 只是上下文构建步骤，不需要成为 Agent。
- 过早拆出 `travel-research` 微服务会增加部署和通信成本，当前没有独立扩缩容需求。
- 原路线按阶段分别补 Agent、RAG、评测，容易出现各组件都存在但端到端闭环长期不可用。

因此，项目采用“少量 Agent + 粗粒度 Skill + 原子 Tool + 有界工作流”的结构。组件是否命名为 Agent，不取决于业务名词，而取决于它是否需要围绕目标自主选择步骤和工具。

## 2. 目标与原则

AI 应用应生成可执行、可验证、可修订且来源透明的旅行计划，而不只是生成看似合理的文本。

核心原则：

- **真实数据优先**：POI、天气、路线等事实来自工具或知识库，LLM 负责推理和表达。
- **少 Agent**：仅在需要自主决策和多步工具调用时使用 Agent。
- **确定性优先**：结构、预算、数量、坐标和来源覆盖率使用代码校验。
- **有界循环**：失败可重试、质量不足可修订，但必须限制次数和成本。
- **来源透明**：事实携带来源、时间、状态和可信度，不把推测伪装成实时数据。
- **渐进增强**：外部搜索、pgvector 和 LLM Judge 不可用时，核心规划仍可降级运行。

## 3. 总体结构

```text
用户请求
  -> travel-gateway
  -> travel-agent                 会话、摘要、异步任务入口
  -> agent-runtime
       -> Context Builder         构建统一规划上下文
       -> RAG Retriever           检索偏好、目的地知识和优质案例
       -> Research Agent          搜集并验证旅行事实
            -> Research Skill
                 -> Tools
                      -> travel-mcp -> 高德、天气、路线等 API
                      -> Search/Fetch（可选）
       -> Planner Agent           生成或修订结构化行程
            -> Planning Skills
       -> Quality Gate            硬规则、来源和质量检查
       -> 条件修订，最多 2 次
       -> 最终结果
  -> travel-trip                  持久化、版本、导出、SSE
```

服务边界保持不变：用户属于 `travel-auth`，会话属于 `travel-agent`，行程属于 `travel-trip`，Agent 执行属于 `agent-runtime`，外部旅行数据工具属于 `travel-mcp`。

当前不新增 `travel-research` 服务。只有在网页抓取需要独立队列、浏览器池或独立扩缩容时，才将 Research Skill 迁出运行时。

## 4. 两个 Agent

### 4.1 Research Agent

目标是取得规划所需的最小事实集，并判断事实是否足够可信。它可以自主选择 POI、天气、酒店/商圈、餐食和网页搜索工具，但不能生成最终行程、规划路线或写业务数据库。

输入：`ResearchContextView`。

输出：`ResearchBundle`，包含候选事实、来源、获取时间、状态和缺口。

Research Agent 只有在以下场景才需要再次调用工具：

- 关键 POI 名称或坐标无法验证。
- 酒店、餐食或路线候选不足。
- 多个来源冲突或数据已过期。
- 用户约束要求额外资料，例如亲子设施、无障碍或临时开放信息。

### 4.2 Planner Agent

目标是根据用户约束和已验证事实生成完整行程，并根据质量问题进行局部修订。聊天澄清、初次规划、单日重生成和整份行程修订共享同一规划能力，不再创建多个薄 Agent。

输入：`PlannerContextView`、`ResearchBundle`，修订时额外包含 `QualityReport` 或用户反馈。

输出：符合 `TripPlanResponse` 的结构化计划。

Planner Agent 不直接搜索网页，不直接持久化数据，也不能把 `fallback` 或 `llm_inferred` 内容声明为实时事实。

## 5. 四个 Skills

Skill 是可复用、可独立测试的业务能力包。它可以组合多个 Tool 和确定性代码，但自身不拥有长期状态。

| Skill | 职责 | 主要调用方 |
|---|---|---|
| `travel_research` | 搜集 POI、天气、住宿区域、餐食和补充网页资料，并交叉验证 | Research Agent |
| `route_budget` | 根据候选地点生成每日路线，估算交通、住宿、餐食和门票预算 | Planner Agent |
| `itinerary_composition` | 将上下文、研究结果、路线和预算生成或局部修订为结构化行程 | Planner Agent |
| `plan_quality` | 执行硬规则、来源审计和可选主观评分，输出修订问题 | Quality Gate |

以下能力不再单独建 Skill：

- 偏好抽取属于 Context Builder。
- POI 校验、天气风险属于 `travel_research` 内部步骤。
- 来源归因属于所有 Tool/Skill 的统一输出协议。
- 导出属于 `travel-trip` 的领域能力，不属于 Agent Skill。
- 单日重生成和用户修订属于 `itinerary_composition` 的不同操作模式。

每个 Skill 使用统一契约：

```text
name
input_schema
output_schema
status: success | partial | fallback | failed
sources[]
issues[]
trace
```

Skill 第一阶段使用普通 Python 类或函数实现，不引入额外 Skill 框架。建议目录：

```text
agent-runtime/app/skills/
  schemas.py
  travel_research/
    SKILL.md
    executor.py
  route_budget/
    SKILL.md
    executor.py
  itinerary_composition/
    SKILL.md
    executor.py
  plan_quality/
    SKILL.md
    executor.py
```

## 6. Tools 与 MCP

Tool 是单次调用即可描述的原子能力，不承担跨步骤决策。

第一批 Tool：

- `search_poi`
- `get_weather`
- `search_hotel`
- `search_meal`
- `plan_route`
- `estimate_cost`
- `web_search`（可选）
- `fetch_page`（可选）

RAG 检索由 `retrieve_knowledge` 内部适配器在确定性工作流节点中执行，不暴露为 LLM 可自由调用的 Tool，避免模型绕过权限、数量和过期过滤。

`travel-mcp` 是工具服务和协议边界，不是 Agent。高德 Web Service 等供应商 API 由 `travel-mcp` 封装，`agent-runtime` 不直接依赖供应商字段。

所有 Tool 返回统一元数据：

```json
{
  status: success,
  data: {},
  source: {
    provider: amap,
    reference: provider-result-id-or-url,
    retrievedAt: ISO-8601,
    freshness: live
  },
  error: null
}
```

工具失败不能返回伪造的“真实结果”。允许使用静态候选继续规划，但必须标记 `fallback`。

网页研究的最小实现采用 `ddgs` 或 SearXNG 搜索、`httpx` 抓取、`trafilatura` 清洗，以及 LLM + Pydantic 抽取。仅在普通 HTTP 无法取得必要内容时使用 Playwright。ScrapeGraphAI 只作为实验 provider，不作为核心依赖。

## 7. Context Engineering

Context Engineering 负责收集、筛选、压缩和注入信息。第一版只维护一个统一 `PlanningContext`，再生成两个只读视图，避免建立复杂 context 平台。

```text
PlanningContext
  request                 本次明确请求
  constraints             日期、预算、节奏、同行人、交通、特殊限制
  preferences             显式偏好与高置信历史偏好
  conversation_summary    与当前任务相关的短摘要
  retrieved_memories      RAG 检索结果
  research_bundle         工具事实与来源
  current_plan            修订时使用
  quality_report          修订时使用
  locale                  zh-CN | en-US
```

只保留两个 Context View：

- `ResearchContextView`：目的地、日期、兴趣、同行人、特殊限制、已有知识和资料缺口。
- `PlannerContextView`：完整约束、已验证事实、路线预算结果、相关记忆和待修订问题。

上下文规则：

- 关键事实标记 `user_input`、`profile`、`conversation_summary`、`trip_history`、`amap`、`web_research`、`llm_inferred` 或 `fallback`。
- 长会话只注入摘要与最近相关消息，不注入完整聊天记录。
- 网页只注入结构化摘要、引用和时间，不注入整页正文。
- 最多注入 5 条 RAG 结果，每条限制长度并要求相关性分数。
- 缺少目的地、日期/天数等关键字段时进入澄清，不允许静默猜测。

## 8. RAG 与记忆

RAG 的目标是复用可靠知识，而不是给项目增加一个向量数据库标签。最小可用 RAG 必须同时包含写入、检索、过滤、引用和过期处理。

### 8.1 三类资料

| 类型 | 内容 | 更新方式 |
|---|---|---|
| 用户记忆 | 稳定偏好、明确禁忌、历史反馈 | 用户确认或多次行为后写入 |
| 目的地知识 | 已验证的目的地摘要、POI 注意事项、季节信息 | Research Skill 写入并设置有效期 |
| 优质案例 | 通过质量门禁且获得正向反馈的行程摘要 | 行程完成或用户收藏后写入 |

用户记忆和知识资料必须分表或使用明确 `record_type`，避免把用户私有数据与公共知识混检。

### 8.2 最小检索流程

```text
请求标准化
  -> 按用户、城市、时间和 record_type 做权限/元数据过滤
  -> 关键词或向量召回
  -> 取前 5 条
  -> 去重和过期过滤
  -> 注入 PlanningContext
  -> 在 trace 中记录命中项
```

第一版可先用现有 PostgreSQL 的结构化查询和全文检索，接口保持 `KnowledgeRetriever`。当资料规模和语义检索收益得到验证后，再启用 `pgvector` 和 embedding，不引入 OpenSearch、Meilisearch 或知识图谱。

RAG 不缓存天气、实时路线和即时营业状态；这些内容每次通过 Tool 获取。所有检索结果保留 `source`、`updated_at`、`expires_at` 和可见范围。

## 9. Loop Engineering

主工作流使用一个有界闭环：

```text
build_context
  -> retrieve_knowledge
  -> research
  -> route_and_budget
  -> draft_plan
  -> validate
       -> 通过：finalize
       -> 可修复：revise_plan -> validate
       -> 资料不足：research（最多补查 1 次）
       -> 不可修复：finalize_with_warnings
```

循环限制：

- 自动修订最多 2 次。
- 补充研究最多 1 次。
- 每类 Tool 使用固定超时和重试次数，默认只重试瞬时错误 1 次。
- 达到限制后返回最佳可用结果和明确警告，不能无限循环。
- 每次循环记录触发原因、修改字段、耗时、token 和工具成本。

质量门禁优先执行硬规则：schema、日期、每日负载、POI 名称/坐标、路线完整性、预算一致性、来源覆盖率。只有“是否符合偏好、节奏是否自然”等主观问题才可调用低频 LLM Judge。

## 10. Harness Engineering

Harness 是保证 Agent 可运行、可测试、可回放的外壳，不再建设独立评测平台。

### 10.1 运行 Harness

复用项目已有能力：异步 job、SSE、超时、错误码、OpenTelemetry trace、Prometheus 指标和结构化日志。额外记录：

- run、node、skill 和 tool 的关联 ID。
- 模型、token、耗时和失败原因。
- Tool 的 success、partial、fallback、failed 状态。
- 每次修订的原因和质量分变化。
- RAG 命中、来源和过期过滤结果。

### 10.2 质量 Harness

维护 6 至 10 个稳定的业务用例，覆盖亲子、低预算、短途、文化、天气风险和中英文输出。执行分为三层：

1. Pydantic schema 校验。
2. 硬规则与来源校验，必须稳定运行，可进入 CI。
3. 可选 LLM Judge，只在本地或离线评测中运行，不阻塞每次提交。

评测命令输出 JSON 报告，至少包含：通过率、硬规则问题、来源覆盖率、fallback 比例、平均修订次数和耗时。保存脱敏后的输入、工具摘要和输出，使同一案例能够重放。

`smoke-test.ps1` 只验证服务链路，AI Eval 只验证规划质量，两者保持独立。当前不引入 GAIA、AgentBench、WebArena 或 OSWorld。

当前最小 eval harness 位于 `scripts/ai-eval.py`。它使用离线 `MockTravelToolProvider` 运行固定案例，输出 JSON 报告，用于快速验证 schema、天数、RAG 检索节点、路线、预算、trace 和质量分数。该脚本不是 smoke test，也不依赖真实 LLM 或高德服务。

`KnowledgeRetriever` 位于 `agent-runtime/app/knowledge.py`。当前实现已经支持两种后端：没有 `DATABASE_URL` 或依赖不可用时使用确定性 `static` fallback；配置 `DATABASE_URL` 后使用 PostgreSQL 表 `agent_knowledge_records` 做关键词检索，并在成功生成行程后写入 90 天有效期的 `itinerary_summary`。后续可以把 PostgreSQL 关键词检索替换或增强为 pgvector，但对 LangGraph 节点和 PlanningContext 注入契约保持不变。

本地宿主机验证 Postgres RAG 时，如果 `agent-runtime/.env` 使用 Compose 内部主机名 `postgres`，脚本会自动降级为 `static`，避免 Windows DNS 等待。可使用宿主机映射端口显式覆盖：

```powershell
.\agent-runtime\.venv\Scripts\python.exe scripts\seed-knowledge.py --database-url "postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud" Chengdu Shanghai
.\agent-runtime\.venv\Scripts\python.exe scripts\ai-eval.py --database-url "postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud" --require-rag-backend postgres
```

## 11. 数据来源与降级

结果按领域返回 `live | cached | inferred | fallback | failed`：

```text
attractions
weather
hotels
meals
routes
budget
research
```

`live` 和 `cached` 必须有 provider 与时间；`inferred` 必须明确表示由模型推断；`fallback` 必须说明替代来源；`failed` 必须保留错误摘要。计划可以在非关键数据缺失时继续生成，但关键 POI 无法验证或结构校验失败时不得伪装成成功。

## 12. 最小技术栈

| 领域 | 采用 | 暂不采用 |
|---|---|---|
| 编排 | LangGraph | 自研工作流框架 |
| Agent/模型适配 | LangChain、OpenAI-compatible provider | 每个能力一个 AgentExecutor |
| Schema | Pydantic | 自由格式 JSON 拼接 |
| 旅行工具 | FastMCP、travel-mcp、高德 | runtime 直连供应商 |
| 网页研究 | ddgs/SearXNG、httpx、trafilatura；必要时 Playwright | 默认 ScrapeGraphAI |
| RAG | PostgreSQL，后续按需 pgvector | OpenSearch、Neo4j、Meilisearch |
| 状态与任务 | PostgreSQL、Redis、RabbitMQ | 新增 Agent 状态基础设施 |
| 可观测性 | OpenTelemetry、Prometheus、Grafana、Loki、Tempo | 独立 Agent 观测平台 |

## 13. 完成标准与实施顺序

AI 应用部分只有同时满足以下条件才算完成：

- 两个 Agent 通过 LangGraph 主流程运行，职责和输入输出明确。
- 四个 Skill 有 Pydantic 契约、状态、来源和单元测试。
- 真实旅行 Tool 通过 `travel-mcp` 调用，失败可见且可降级。
- `PlanningContext` 和两个 Context View 已接入，不再由各节点重复解析请求。
- RAG 能写入、检索、过滤、引用和过期，关闭向量能力时仍可运行。
- 质量门禁能触发最多两次自动修订，并可返回带警告的最佳结果。
- 固定 Eval Cases 可重复执行并输出机器可读报告。
- trace 能关联 Agent、Skill、Tool、RAG 和修订循环。

建议按以下四个短迭代完成，每个迭代都保持现有 API 和 smoke test 可用：

1. **收敛工作流**：将六个数据 Agent node 合并为 Research Agent，将生成和修订统一为 Planner Agent，保留已有工具实现。
2. **统一契约**：落地四个 Skills、`PlanningContext`、Context View、来源与 trace schema。
3. **接入最小 RAG 与闭环**：先用 PostgreSQL 检索，接入有界 validate/revise 流程。
4. **补齐 Harness**：加入固定案例、硬规则评测、重放和可选 LLM Judge。

后续动态提醒、实时开放时间监控、浏览器池、独立 Research 服务和知识图谱都不属于当前 AI 应用完工的必要条件。
