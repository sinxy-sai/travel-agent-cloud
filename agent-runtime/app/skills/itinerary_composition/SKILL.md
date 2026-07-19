---
name: itinerary-composition
description: 将 PlanningContext、研究结果、路线预算结果和 LLM 草稿整合为 TripPlanResponse。用于 Planner Agent 生成结构化行程、保留用户约束并补齐每日酒店、景点、餐食、路线、天气和预算。
metadata:
  compatibility: agent-runtime Python/FastAPI, LangGraph workflow
allowed-tools: none
---

# Itinerary Composition Skill

## 职责

把上游已收集的事实和草稿计划组合为最终候选行程。该 Skill 不直接调用外部旅行工具，不搜索网页，不持久化数据。

## 输入

- `TripPlanRequest`
- `TravelPlanningContext`
- 可选 `TripPlanResponse` 草稿
- `attractions_by_day`
- `weather_info`
- `hotels_by_day`
- `meals_by_day`
- `routes_by_day`
- `budget`

## 输出

- `TripPlanResponse`

## 规则

- 优先使用工具返回的结构化事实。
- LLM 草稿只作为文案、主题和缺省字段来源。
- 缺少草稿时仍能基于工具事实生成可用结构。
- 不把 fallback 或 inferred 内容伪装成 live 数据。

## 运行代码

执行入口是 `executor.py` 中的 `compose_trip_plan`。

