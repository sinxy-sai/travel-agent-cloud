---
name: travel-research
description: 收集旅行规划所需事实数据，包括景点、天气、住宿、餐食与来源状态。用于 Research Agent 在生成行程前调用旅行工具、FastMCP/高德数据和降级数据，并输出可追踪的 ResearchBundle。
metadata:
  compatibility: agent-runtime Python/FastAPI, LangGraph workflow, FastMCP travel tools
allowed-tools: attractions_for_day weather_for_trip hotel_for_day meals_for_day
---

# Travel Research Skill

## 职责

为 `research_agent` 准备最小可信事实集。该 Skill 只负责研究和校验事实，不生成最终行程，不写数据库，也不做路线和预算汇总。

## 输入

- `TripPlanRequest`
- `TravelToolProvider`
- `LangChainTravelAgentNodeRunner`

## 输出

- `ResearchBundle.attractions_by_day`
- `ResearchBundle.weather_info`
- `ResearchBundle.hotels_by_day`
- `ResearchBundle.meals_by_day`
- `ResearchBundle.trace`

## 来源规则

- LangChain tool-calling 可用且成功时，source 标记为 `langchain:<domain>`。
- LangChain 可用但调用失败时，回退到直接工具调用，并标记 `fallback`。
- LangChain 不可用时，直接工具调用是正常路径，标记 `success`。
- 数据为空时写入 `SkillIssue`，由上游质量门禁决定是否继续、重试或带警告返回。

## 运行代码

执行入口是 `executor.py` 中的 `run_travel_research`。
