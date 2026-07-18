# travel-mcp

`travel-mcp` 是旅行工具微服务，提供 MCP 风格的 HTTP JSON-RPC 接口，供 `agent-runtime` 调用。

## 当前能力

服务在 `/mcp` 暴露 JSON-RPC 接口：

- `tools/list`
- `tools/call`

配置 `AMAP_WEB_SERVICE_KEY` 后，服务会调用高德 Web Service API 获取：

- POI 搜索
- 天气
- 基础步行和驾车路线

如果没有配置高德 key，或者上游调用失败，服务会返回确定性的 fallback 数据，保证本地开发、smoke test 和部署检查仍可运行。

## 工具列表

- `travel.search_attractions`
- `travel.search_hotel`
- `travel.search_meals`
- `travel.plan_routes`
- `travel.get_weather`
- `travel.estimate_budget`

## 数据约束

- 服务本身无状态，不持久化用户数据。
- 工具名称和响应 schema 应保持稳定。
- 不应把 `Amap POI`、`MCP option`、`Stub` 等内部占位名暴露到面向用户的行程里。
- 高德数据可用时，应按类别搜索、过滤无效 POI、去重后再返回给 `agent-runtime`。
- 供应商相关逻辑应留在本服务中，避免泄漏到前端或核心 Agent API。

## 配置

```text
AMAP_WEB_SERVICE_KEY=
AMAP_BASE_URL=https://restapi.amap.com
AMAP_TIMEOUT_SECONDS=8
```

## 本地运行

```powershell
cd services/mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AMAP_WEB_SERVICE_KEY="your-amap-web-service-key"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

容器环境推荐从仓库根目录启动：

```powershell
docker compose up -d --build travel-mcp
```

runtime 调用地址：

```text
FASTMCP_BASE_URL=http://travel-mcp:8100/mcp
```
