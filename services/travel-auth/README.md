# travel-auth

`travel-auth` 是 Python/FastAPI 认证门面服务。

当前阶段它已经作为独立服务运行，但内部仍以门面方式代理到 `agent-runtime` 的认证和用户数据接口。这样可以先建立服务边界、镜像、健康检查、网关路由和 K3s 部署形态，再逐步迁移真实认证存储逻辑。

## 当前职责

- 承接 `travel-gateway` 转发过来的认证 API。
- 代理 `/api/v1/auth/*` 和 `/api/v1/me/*` 到 `agent-runtime`。
- 通过 `/health` 暴露自身和 upstream 状态。
- 通过 `X-Travel-Service-Boundary: travel-auth` 标记内部服务边界，便于后续日志和排查。

## 未来职责

- 注册、登录、退出登录、邮箱验证、找回密码和 OAuth 回调。
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
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8300
```

`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时要保持 `services/common` 目录存在。
