---
name: plan-quality
description: 对 TripPlanResponse 执行确定性质量门禁，检查 schema、天数、路线、天气、预算、建议和偏好字段，并在安全范围内修复缺失字段。
metadata:
  compatibility: agent-runtime Python/FastAPI, LangGraph workflow
allowed-tools: weather_for_trip estimate_budget hotel_for_day attractions_for_day routes_for_day
---

# Plan Quality Skill

## 职责

在返回用户前验证候选行程是否完整、结构稳定、可解释。该 Skill 优先使用确定性规则，不默认调用 LLM Judge。

## 输入

- `TripPlanResponse`
- `TripPlanRequest`
- `TravelToolProvider`
- `TravelPlanningContext`

## 输出

- 修复后的 `TripPlanResponse`
- `TripPlanQualityReport`

## 规则

- 可确定修复的缺失字段直接修复。
- 不可确定修复的问题保留在 quality report。
- 修复动作必须进入 trace，避免用户误以为初始生成天然完整。

## 运行代码

执行入口是 `executor.py` 中的 `run_plan_quality`。

