# travel-auth

`travel-auth` 是 Python/FastAPI 认证与用户领域服务。

当前阶段它已经作为独立服务运行，并开始从纯代理门面进入渐进实迁：匿名本地用户的 `profile` 读写由 `travel-auth` 直接访问 PostgreSQL 处理；登录、注册、OAuth、会话、导入导出等高风险认证和账户数据接口暂时继续代理到 `agent-runtime`。

## 当前职责

- 承接 `travel-gateway` 转发过来的认证与用户 API。
- 对带合法 `X-User-Id` 的匿名本地用户，直接处理 `GET/PATCH /api/v1/me/profile`。
- 代理 `/api/v1/auth/*`、登录用户 profile、账户导入导出和其他 `/api/v1/me/*` 到 `agent-runtime`。
- 通过 `/health` 暴露自身、数据库和上游 runtime 状态。
- 通过 `X-Travel-Service-Boundary: travel-auth` 标记内部服务边界，便于日志和排查。

## 未来职责

- 注册、登录、退出登录、邮箱验证、找回密码和 OAuth 回调。
- 完整拥有用户资料、用户基础信息和账户数据导入导出边界。
- JWT 或 Session 签发与校验。
- 必要时使用 Redis 做登录限流和会话状态。
- 通过 RabbitMQ 发布用户生命周期事件。

## 迁移原则

- 保持现有 `agent-runtime` API 契约稳定。
- 通过 `travel-gateway` 按接口逐步迁移。
- 不让密码、会话逻辑在两个运行服务里长期重复存在。

## 本地运行

```powershell
cd services/travel-auth
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:DATABASE_URL="postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8300
```

`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时要保持 `services/common` 目录存在。
