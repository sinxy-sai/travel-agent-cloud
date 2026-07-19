---
name: route-budget
description: 基于已研究出的景点和住宿候选，生成每日路线并估算行程预算。用于 LangGraph workflow 在 Research Agent 之后、Planner Agent 之前补齐路线与预算事实。
metadata:
  compatibility: agent-runtime Python/FastAPI, LangGraph workflow, FastMCP travel tools
allowed-tools: routes_for_day estimate_budget
---

# Route Budget Skill

## 职责

将 `travel_research` 产出的候选地点转成可用于规划的路线和预算事实。该 Skill 不负责搜索 POI、住宿或餐食，也不生成最终行程文案。

## 输入

- `TripPlanRequest`
- `dict[int, list[Attraction]]`
- `dict[int, Hotel]`
- `TravelToolProvider`
- `LangChainTravelAgentNodeRunner`

## 输出

- `RouteBudgetBundle.routes_by_day`
- `RouteBudgetBundle.budget`
- `RouteBudgetBundle.trace`

## 来源规则

- LangChain tool-calling 可用且成功时，source 标记为 `langchain:<domain>`。
- LangChain 可用但调用失败时，回退到直接工具调用，并标记 `fallback`。
- LangChain 不可用时，直接工具调用是正常路径，标记 `success`。
- 缺少某天路线或预算时写入 `SkillIssue`，由质量门禁判断是否修订。

## 运行代码

执行入口是 `executor.py` 中的 `run_route_budget`。
