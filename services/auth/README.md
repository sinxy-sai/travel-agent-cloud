# travel-auth

`travel-auth` 是认证与用户领域服务�?
## 当前职责

- 处理注册、登录、退出登录、当前用户读取和当前用户显示名更新�?- 处理密码修改、密码重�?token、邮箱验�?token�?- 处理当前 session 列表、单�?session 撤销和其�?session 批量撤销�?- 处理登录用户和匿名本地用户的 `GET/PATCH /api/v1/me/profile`�?- 记录和查询安全事件�?- 管理 OAuth identity 列表、解绑，以及 GitHub OAuth start/callback�?- 删除当前账户�?- 直接处理账户导入导出、导出文件和匿名数据导入聚合�?- 根据 `EMAIL_PROVIDER` 使用 mock �?SMTP 发送认证邮件�?- 通过 `/health` 暴露自身、数据库、对象存储和上游 runtime 状态�?
## 环境变量

本服务的本地配置放在 `services/auth/.env`，模板为 `services/auth/.env.example`�?
常用配置�?
- `DATABASE_URL`：PostgreSQL 连接串�?- `AUTH_SECRET_KEY`：session/JWT 签名密钥，必须和需要识别用户上下文的服务保持一致�?- `EMAIL_PROVIDER`：`mock` �?`smtp`�?- `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`：SMTP 发送配置�?- `GITHUB_OAUTH_CLIENT_ID`、`GITHUB_OAUTH_CLIENT_SECRET`、`GITHUB_OAUTH_REDIRECT_URI`：GitHub OAuth 配置�?- `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET`：账户导出文件存储配置�?
## 本地运行

```powershell
cd services/auth
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8300
```

如果不用 Docker Compose，需要自己把 `.env` 中的容器内地址改成本机地址，例如把 `postgres:5432` 改成 `localhost:5432`，把 `minio:9000` 改成 `localhost:9000`�?
`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时需要保�?`services/common` 目录�?