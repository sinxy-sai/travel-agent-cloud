# Agent 与 AI 应用架构设计

本文档是 Travel Agent Cloud 的 Agent/AI 应用层设计基准。后续开发以本文档为准，除非产品方向或技术路线发生明确变化，不再频繁重写。

## 1. 目标

本项目的 AI 应用目标是：在现有云原生全栈与微服务基础上，快速做出一个可用、可部署、可持续增强的旅行规划 Agent。

第一阶段优先级：

1. 用户能提交目的地、天数、预算、兴趣、日期、交通、住宿和偏好。
2. Agent 能完成资料研究、路线预算、行程生成和质量检查。
3. 结果必须是结构化行程，能保存、修订、导出、单日重生成。
4. 高德/FastMCP、网页或内置研究、知识库上下文都能进入规划。
5. Agent 内部只保留基础 trace 方便排错，不继续建设复杂观测指标平台。

暂不追求：

- 通用 Agent benchmark 平台。
- 复杂 Agent 指标、Grafana 细粒度业务看板。
- 知识库运营后台。
- 无限制 ReAct 循环。

## 2. 总体路线

当前采用 **Plan-and-Execute + Bounded Reflection**。

```text
用户请求
  -> Context Engineering
  -> 轻量知识库/RAG 检索
  -> Research Agent
       -> travel_research Skill
       -> FastMCP/高德工具
       -> Web/SearXNG 或内置目的地研究笔记
  -> Planner Agent
       -> route_budget Skill
       -> itinerary_composition Skill
       -> LLM 规划器可选增强
  -> Quality Gate
       -> plan_quality Skill
       -> 不合格时最多自动修复 1 次
  -> TripPlanResponse
```

这不是完整 ReAct。当前不让模型在 Thought/Action/Observation 中无限自主探索，因为这会增加不确定性和成本。第一阶段只做明确工作流：先研究，再规划，再检查，最多修一次。

## 3. 服务边界

```text
frontend
  -> travel-gateway
      -> travel-auth        用户、认证、OAuth、账户数据
      -> travel-agent       会话、聊天、摘要、Agent 状态门面
      -> travel-trip        行程持久化、版本、导出、异步生成
      -> agent-runtime      Agent 编排、LLM、Skills、Context、轻量知识库
      -> travel-mcp         高德/FastMCP 工具服务
```

`agent-runtime` 是 Agent 执行核心，但不拥有用户、会话、行程持久化边界。

## 4. Agent 结构

第一阶段只保留两个有效 Agent。

### 4.1 Research Agent

职责：准备规划所需事实和背景。

输入：

- `PlanningContext`
- 知识库命中
- 用户请求

调用：

- `travel_research` Skill
- FastMCP/高德工具：景点、天气、酒店、餐食
- 可选 Web/SearXNG 搜索
- 无搜索服务时使用内置目的地研究笔记

输出：

- 每日景点候选
- 天气
- 酒店
- 餐食
- 研究笔记
- 来源与问题

Research Agent 不生成最终行程，不写业务库。

### 4.2 Planner Agent

职责：把研究结果变成可用行程。

输入：

- `PlanningContext`
- 知识库命中
- Research Agent 输出
- route/budget 输出
- 可选 LLM 草稿

调用：

- `route_budget` Skill
- `itinerary_composition` Skill
- 可选 LLM 规划器，用研究结果生成更自然的每日安排
- `plan_quality` Skill

输出：

- `TripPlanResponse`
- 每日主题、早中晚安排、景点、餐食、酒店、路线、预算、天气、建议

Planner Agent 不直接搜索网页，不直接持久化数据。

## 5. Skills

这里的 Skill 是项目运行时能力，不是 Codex Skill，也不是可共享插件。目录固定在：

```text
agent-runtime/app/skills/
```

第一阶段保留四个 Skill。

| Skill | 作用 |
| --- | --- |
| `travel_research` | 整合高德/FastMCP、网页或内置研究、基础事实 |
| `route_budget` | 生成路线和预算 |
| `itinerary_composition` | 组装最终结构化行程 |
| `plan_quality` | 质量检查与一次自动修复 |

统一输出最小契约：

```text
status: success | partial | fallback | failed
sources[]
issues[]
structured_result
```

第一阶段不引入复杂 Skill 沙箱。当前 Skill 只调用项目内受控工具和 HTTP 客户端，不执行用户代码。

## 6. Tools 与 MCP

工具层由 `travel-mcp` 封装，`agent-runtime` 不直接依赖高德字段。

核心工具：

- 景点搜索
- 天气查询
- 酒店搜索
- 餐食搜索
- 路线规划
- 预算估算

网页研究工具：

- 优先使用 `SEARXNG_BASE_URL` 的 JSON 搜索。
- 未配置 SearXNG 时使用内置目的地研究笔记。
- 第一阶段不引入 Playwright 浏览器池。
- ScrapeGraphAI、DeepAgents 暂不作为核心依赖；只有当它们明显减少实现复杂度时再接入。

## 7. Context Engineering

第一阶段实现基础 Context Engineering，不建设复杂上下文平台。

核心对象：

- `PlanningContext`
- `ResearchContextView`
- `PlannerContextView`

`PlanningContext` 包含：

- 目的地
- 天数
- 预算
- 日期窗口
- 交通
- 住宿
- 兴趣
- 偏好
- 风格标签
- 额外约束
- 知识库命中

规则：

- 各节点不重复解析用户原始请求。
- Research Agent 使用 `ResearchContextView`。
- Planner Agent 使用 `PlannerContextView`。
- 长文本和网页内容必须摘要后进入上下文。
- 知识库命中最多注入 5 条。
- 规划器必须优先消费结构化工具结果，再用研究笔记补充背景。

## 8. RAG 与知识库

知识库需要保留，但第一阶段保持轻量。

用途：

- 目的地规划注意事项。
- 历史优质行程摘要。
- 可复用用户偏好，后续再细化权限。

后端：

- 默认静态知识 fallback。
- 配置 `DATABASE_URL` 且 `RAG_ENABLED=true` 时使用 PostgreSQL。
- 后续需要语义检索时再加 `pgvector`。

不做：

- 不做复杂知识库后台。
- 不做知识图谱。
- 不缓存实时天气、实时路线和营业状态。

## 9. Loop Engineering

当前 loop：

```text
plan
  -> quality_check
  -> 如果通过：返回
  -> 如果可修复：自动修复 1 次
  -> 再次检查
  -> 返回最佳结果
```

约束：

- 自动修复最多 1 次。
- 不做无限 reflection。
- 不做多轮 ReAct。
- 不合格但可用时返回结果，并通过基础 trace 标记问题。

## 10. Harness Engineering

第一阶段只保留最小 Harness：

- `scripts/smoke-test.ps1`：验证服务链路和关键 API。
- `scripts/smoke-test.sh`：Linux/K3s 环境验证。
- `scripts/ai-eval.py`：固定用例，验证行程是否结构完整。

不引入 GAIA、AgentBench、WebArena、OSWorld。它们和当前旅行规划产品目标不完全一致，会拖慢落地速度。

## 11. 最小可用完成标准

本阶段完成标准：

- LangGraph 主链路可运行。
- Research Agent 能同时使用旅行工具和研究笔记。
- Planner Agent 能消费研究、路线、预算、知识上下文，生成结构化可保存行程。
- Quality Gate 能检查并最多修复一次。
- 知识库能作为上下文进入规划，但不是主流程阻塞项。
- smoke test 通过。
- 本地 Docker 和 VPS/K3s 均可部署。

## 12. 后续增强

在第一阶段可用后，再考虑：

- 接入 SearXNG 服务。
- 增加网页 fetch/clean/extract。
- 引入 pgvector。
- 引入更强的 tool-calling agent。
- 尝试 DeepAgents、ScrapeGraphAI 或 Playwright。
- 对特定城市沉淀高质量知识库。
