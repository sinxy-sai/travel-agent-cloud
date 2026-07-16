# travel-trip

`travel-trip` 是 Python/FastAPI 行程管理服务。

当前阶段它已经从纯代理门面进入渐进实迁：匿名本地用户的行程列表、详情、编辑、版本、恢复、删除和 Markdown 导出由 `travel-trip` 直接访问 PostgreSQL 处理；`agent-runtime` 生成、AI 修订或单日重生成行程内容后，也会通过 `travel-trip` 的内部接口保存结果。仍依赖 Agent 执行能力的行程生成、异步生成、AI 修订和单日重生成入口暂时继续代理到 `agent-runtime`。

## 当前职责

- 承接 `travel-gateway` 转发过来的行程 API。
- 对带合法 `X-User-Id` 的匿名本地用户，直接处理行程历史、详情、编辑、版本、恢复、删除和 Markdown 导出。
- 通过 `POST /internal/v1/trip-plans` 承接 `agent-runtime` 的生成后保存请求。
- 通过 `PATCH /internal/v1/trip-plans/{tripPlanId}` 承接 `agent-runtime` 的 AI 修订和单日重生成保存请求。
- 对登录 cookie 用户或数据库未配置场景，继续代理到 `agent-runtime`，避免在认证服务实迁前复制 token 校验逻辑。
- 对行程生成、异步任务、AI 修订和单日重生成入口，继续代理到 `agent-runtime`。
- 通过 `/health` 暴露自身、数据库和 upstream 状态。
- 通过 `X-Travel-Service-Boundary: travel-trip` 标记内部服务边界，便于后续日志和排查。

## 未来职责

- 完整接管行程 CRUD、历史版本、版本恢复、收藏和搜索。
- 接管登录用户的行程读写，但认证身份仍应来自 `travel-auth` 或网关传递的可信用户上下文。
- 导出文件元数据和文件归属校验。
- 使用 PostgreSQL 作为权威数据源。
- 使用 MinIO 保存 Markdown、图片和 PDF 等导出文件。
- 通过 RabbitMQ 发布 `trip.plan.created`、`trip.plan.updated`、`trip.plan.export.requested` 等事件。

## 迁移原则

- 先保持 `travel-gateway` 作为公共入口。
- `agent-runtime` 只负责生成、修订和重生成行程内容；行程记录保存、版本和导出逐步收敛到 `travel-trip`。
- 拆分后，Agent 规划只通过内部 HTTP API 访问行程服务。

## 本地运行

```powershell
cd services/travel-trip
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:DATABASE_URL="postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8200
```

`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时要保持 `services/common` 目录存在。
