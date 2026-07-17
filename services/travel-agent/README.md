# travel-agent

`travel-agent` 是面向用户 Agent 能力的服务入口，负责会话数据边界、同步摘要和 Agent API 门面。

## 当前职责

- 本地处理登录用户和匿名用户的会话列表、详情、重命名、删除。
- 本地读取和生成同步会话摘要。
- 本地创建异步摘要 job，并通过 RabbitMQ 发布 `agent.conversation.summarize.requested`。
- 删除会话前清空相关行程的 `conversation_id`，避免行程和会话之间的外键关系阻塞删除。
- `/api/v1/chat` 通过 runtime internal execution 路径调用 LangGraph/LangChain 执行核心。
- `/api/v1/agent/*` 仍作为 Agent 状态、诊断和工具门面转发到 `agent-runtime`。
- 通过 `/health` 暴露自身数据库和 runtime upstream 状态。

## 仍由 agent-runtime 承担的职责

- LangGraph/LangChain Agent 执行。
- 聊天回复生成。
- 异步摘要 worker 消费。
- 行程生成、行程修订、单日重生成等执行型请求。

## 迁移原则

- `travel-agent` 逐步接管“用户请求入口、会话归属、策略、审计、配额”。
- `agent-runtime` 逐步收缩为“Agent 编排和执行核心”。
- 对外保持 `/api/v1` 兼容，迁移期间由 gateway 和服务内 fallback 保证旧流程可用。

## 本地运行

```powershell
cd services/travel-agent
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
$env:DATABASE_URL="postgresql://travel_agent:travel_agent_dev@localhost:5432/travel_agent_cloud"
$env:AUTH_SECRET_KEY="travel-agent-cloud-local-dev-secret"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8400
```

`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时需要保留 `services/common` 目录。
