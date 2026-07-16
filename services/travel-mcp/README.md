# travel-mcp

Local MCP-compatible travel tool server for Agent Runtime development.

This service exposes a minimal JSON-RPC endpoint at `/mcp` with `tools/list`
and `tools/call`. When `AMAP_WEB_SERVICE_KEY` is configured it calls Amap Web
Service APIs for POI search, weather, and basic walking/driving routes. Without
that key, or when an upstream call fails, it returns deterministic fallback
travel data for:

- `travel.search_attractions`
- `travel.search_hotel`
- `travel.search_meals`
- `travel.plan_routes`
- `travel.get_weather`
- `travel.estimate_budget`

The service is intentionally stateless and does not persist user data. Keep the
tool names and response schemas stable while replacing or expanding provider
logic.

POI tools should not leak internal placeholder names such as `Amap POI`,
`MCP option`, or `Stub` into user-facing plans. When live AMap data is available,
the service searches multiple category-specific keywords, filters unrelated POIs,
and deduplicates results before returning them to `agent-runtime`.

Configuration:

```text
AMAP_WEB_SERVICE_KEY=
AMAP_BASE_URL=https://restapi.amap.com
AMAP_TIMEOUT_SECONDS=8
```

Local run:

```powershell
cd services/travel-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AMAP_WEB_SERVICE_KEY="your-amap-web-service-key"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

Agent Runtime config for local host mode:

```text
TRAVEL_TOOL_PROVIDER=fastmcp
FASTMCP_BASE_URL=http://localhost:8100/mcp
```

Agent Runtime config for Docker Compose network mode:

```text
TRAVEL_TOOL_PROVIDER=fastmcp
FASTMCP_BASE_URL=http://travel-mcp:8100/mcp
```
