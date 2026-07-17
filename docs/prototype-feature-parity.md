# 原型功能对齐

参考原型：

```text
Hello-Agents/hello-agents-main/code/chapter13/helloagents-trip-planner
```

本项目应先保留原型面向用户的旅行规划能力，再逐步演进为云原生产品。

## 迁移形态

原型是两层应用：Vue 前端 + 以 `MultiAgentTripPlanner` 为核心的 FastAPI 后端。核心流程是：

1. 景点 Agent 调用高德文本搜索。
2. 天气 Agent 调用高德天气。
3. 酒店 Agent 调用高德文本搜索。
4. Planner Agent 将工具结果整合为结构化行程 JSON。

Travel Agent Cloud 保留相同的用户侧行为，但映射到可部署架构：

| 原型概念 | Travel Agent Cloud 对应实现 |
| --- | --- |
| 景点、天气、酒店、规划等 `SimpleAgent` | LangGraph 节点：`attraction_agent`、`weather_agent`、`hotel_agent`、`meal_agent`、`route_agent`、`budget_agent`、`planner_agent` |
| 包装 `amap-mcp-server` 的 `MCPTool` | `services/mcp` MCP 兼容工具服务 |
| Planner prompt 整合文本工具结果 | `agent-runtime` 整合结构化工具 payload，可在节点内部使用 LangChain tool-calling |
| 前端 sessionStorage 状态 | PostgreSQL 持久化会话、行程、版本、导出、任务和用户账号 |
| 单后端进程 | frontend、travel-gateway、agent-runtime、worker、PostgreSQL、Redis、RabbitMQ、MinIO、travel-mcp |

这意味着我们要复刻原型的产品行为和有价值的 prompt 思路，但不直接复制 `helloagent` 框架或它的持久化模型。

## 需要保留的原型能力

| 模块 | 原型行为 | 当前状态 |
| --- | --- | --- |
| 行程输入 | 目的地、开始日期、结束日期、自动计算天数 | 已支持目的地、日期、天数、交通、住宿、兴趣和自由文本 |
| 偏好 | 交通、住宿、旅行风格、额外要求 | 已支持 |
| 生成进度 | 生成时展示景点、天气、酒店、行程等步骤 | 已支持 job polling、SSE 进度和 fallback |
| Agent 规划 | 多 Agent：景点、天气、酒店、最终规划 | 已通过 LangGraph 节点和 FastMCP 工具支持 |
| 地图工具 | 高德 MCP 工具查询 POI、天气、路线 | 已接入 `travel-mcp` 和高德 Web Service |
| 结果概览 | 概览、日期范围、建议、预算 | 已支持 |
| 预算 | 景点、酒店、餐食、交通和总价 | 已支持 |
| 每日行程 | 每日描述、交通、住宿、景点、酒店、餐食、路线 | 已支持，并带数据来源徽标 |
| 景点详情 | 名称、地址、时长、描述、评分、门票、图片 | 已支持，高德图片可用时展示 |
| 酒店详情 | 名称、地址、类型、价格范围、评分、距离 | 已支持 |
| 天气 | 日夜天气、温度、风向风力 | 已支持 |
| 地图视图 | 景点 marker 和路线 polyline | 已支持高德 SDK 预览和 schematic fallback |
| 编辑 | 编辑行程、移动/删除景点、保存/取消 | 已支持行程、每日、酒店、景点、餐食、天气和路线编辑 |
| 导出 | 图片和 PDF 导出 | 已支持 Markdown、PNG 和 PDF |

## 推荐实现顺序

1. 将数据来源透明度从模块徽标细化到单个失败来源的重试动作。
2. 用浏览器验证 Docker Compose、本地 Vite 代理和生产 Ingress 下的 SSE 进度。
3. 验证长行程、中文文本、高德数据、fallback 地图和远程 POI 图片下的 PNG/PDF 导出。
4. 持续增强 FastMCP 工具覆盖范围，并把供应商细节留在工具层。
5. 将原型中有效的 planner prompt 思路迁移到 LangGraph `planner_agent`，同时保持 API 契约稳定。

## 不直接复制的部分

- 不复制原型只依赖 sessionStorage 的持久化方式。
- 不把原始工具调用 payload 暴露给前端。
- 不让公共 API 绑定高德供应商命名，供应商细节留在工具层。
