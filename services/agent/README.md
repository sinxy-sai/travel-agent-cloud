# travel-agent

`travel-agent` 是面向用户 Agent 能力的服务入口，负责会话数据边界、聊天入口、同步摘要和异步摘要任务。

它不直接实现 LangGraph/LangChain 推理。需要生成聊天回复时，本服务会通过 internal API 调用 `agent-runtime`。

## 当前职责

- 处理登录用户和匿名本地用户的会话列表、详情、重命名和删除。
- 保存用户消息和助手回复。
- 处理 `POST /api/v1/chat`，并把实际回复生成委托给 `agent-runtime`。
- 生成同步会话摘要。
- 创建异步摘要 job，并通过 RabbitMQ 发布 `agent.conversation.summarize.requested`。
- 提供 `python -m app.worker_main` worker，消费摘要任务并更新任务状态。
- 删除会话前清空相关行程的 `conversation_id`，避免行程和会话关系阻塞删除。
- 转发 `/api/v1/agent/*` 到 `agent-runtime`，用于 Agent 状态、诊断和工具目录。
- 通过 `/health` 暴露自身数据库、消息队列和 runtime upstream 状态。

## 不负责的能力

- 认证、注册、邮箱验证、OAuth 和账户导入导出：属于 `services/auth`。
- 行程持久化、版本、收藏、删除和导出：属于 `services/trip`。
- LangGraph/LangChain、LLM 和工具编排：属于 `agent-runtime`。

## 环境变量

本地配置文件放在 `services/agent/.env`，模板为 `services/agent/.env.example`。

常用变量：

- `AGENT_RUNTIME_URL`：runtime 内部地址。
- `DATABASE_URL`：PostgreSQL 连接串。
- `MESSAGE_QUEUE_URL`：RabbitMQ 连接串。
- `AUTH_SECRET_KEY`：用户 token 校验密钥，必须和 `services/auth` 保持一致。
- `INTERNAL_SERVICE_TOKEN`：服务间 internal API token。
- `RPC_TIMEOUT_SECONDS`：消息队列和内部调用超时。

## 本地运行

```powershell
cd services/agent
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:DATABASE_URL="postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud"
$env:MESSAGE_QUEUE_URL="amqp://travel_agent:travel_agent_dev@localhost:5672/"
$env:AUTH_SECRET_KEY="travel-agent-cloud-local-dev-secret"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8400
```

启动摘要 worker：

```powershell
cd services/agent
.\.venv\Scripts\python -m app.worker_main
```

容器环境推荐从仓库根目录通过 Docker Compose 启动：

```powershell
docker compose --profile worker up -d --build travel-agent travel-agent-worker
```
