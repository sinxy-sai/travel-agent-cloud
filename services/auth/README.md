# travel-auth

`travel-auth` 是认证与用户领域服务，负责账号、session、profile、邮箱 token、OAuth identity、GitHub OAuth、账户导入导出和导出文件。

## 当前职责

- 处理注册、登录、退出登录和当前用户读取。
- 更新当前用户显示名。
- 处理密码修改、密码重置 token 和邮箱验证 token。
- 管理当前 session、单个 session 撤销和其他 session 批量撤销。
- 处理登录用户和匿名本地用户的 `GET/PATCH /api/v1/me/profile`。
- 记录和查询安全事件。
- 管理 OAuth identity 列表、解绑，以及 GitHub OAuth start/callback。
- 删除当前账号。
- 聚合账户导入导出数据，管理导出文件。
- 根据 `EMAIL_PROVIDER` 使用 mock 或 SMTP 发送认证邮件。
- 通过 `/health` 暴露自身、数据库、对象存储和上游 runtime 状态。

## 不负责的能力

- 会话、聊天历史和摘要任务：属于 `services/agent`。
- 行程持久化、版本和导出：属于 `services/trip`。
- Agent 执行、LLM 和旅行工具编排：属于 `agent-runtime`。

## 环境变量

本地配置文件放在 `services/auth/.env`，模板为 `services/auth/.env.example`。

常用变量：

- `DATABASE_URL`：PostgreSQL 连接串。
- `AUTH_SECRET_KEY`：session/JWT 签名密钥，必须和需要识别用户上下文的服务保持一致。
- `AUTH_TOKEN_TTL_SECONDS`：访问 token 有效期。
- `AUTH_COOKIE_SECURE`：是否使用 Secure cookie，纯 HTTP 本地环境应为 `false`。
- `EMAIL_PROVIDER`：`mock` 或 `smtp`。
- `EMAIL_FROM`：发件人地址。
- `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`：SMTP 发送配置。
- `GITHUB_OAUTH_CLIENT_ID`、`GITHUB_OAUTH_CLIENT_SECRET`、`GITHUB_OAUTH_REDIRECT_URI`：GitHub OAuth 配置。
- `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET`：账户导出文件存储配置。
- `INTERNAL_SERVICE_TOKEN`：服务间 internal API token。

## 本地运行

```powershell
cd services/auth
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:DATABASE_URL="postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud"
$env:AUTH_SECRET_KEY="travel-agent-cloud-local-dev-secret"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8300
```

容器环境推荐从仓库根目录启动：

```powershell
docker compose up -d --build travel-auth
```
