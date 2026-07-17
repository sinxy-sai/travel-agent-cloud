# travel-auth

`travel-auth` 是认证与用户领域服务。

## 当前职责

- 处理注册、登录、退出登录、当前用户读取和当前用户显示名更新。
- 处理密码修改、密码重置 token、邮箱验证 token。
- 处理当前 session 列表、单个 session 撤销和其他 session 批量撤销。
- 处理登录用户和匿名本地用户的 `GET/PATCH /api/v1/me/profile`。
- 记录和查询安全事件。
- 管理 OAuth identity 列表、解绑，以及 GitHub OAuth start/callback。
- 删除当前账户。
- 对账户导入导出、导出文件和匿名数据导入路径执行认证与邮箱验证策略，再转发到迁移期聚合实现。
- 通过 `/health` 暴露自身、数据库和上游 runtime 状态。

## 仍在迁移中的职责

- 账户导入导出的真实聚合逻辑仍回落到 `agent-runtime`，后续应改为由 `travel-auth` 调用 `travel-agent`、`travel-trip` 和对象存储完成。
- SMTP 真发送还未在 `travel-auth` 内实现，目前 `EMAIL_PROVIDER=mock` 时会返回 dev token。

## 本地运行

```powershell
cd services/travel-auth
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:DATABASE_URL="postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud"
$env:AUTH_SECRET_KEY="travel-agent-cloud-local-dev-secret"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8300
```

GitHub OAuth 需要额外配置：

```powershell
$env:GITHUB_OAUTH_CLIENT_ID="..."
$env:GITHUB_OAUTH_CLIENT_SECRET="..."
$env:GITHUB_OAUTH_REDIRECT_URI="http://localhost:5173/api/v1/auth/oauth/github/callback"
```

`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时需要保留 `services/common` 目录。
