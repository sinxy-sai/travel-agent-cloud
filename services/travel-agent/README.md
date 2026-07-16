# travel-agent

`travel-agent` 是 Python/FastAPI Agent 门面服务。

当前阶段它已经作为独立服务运行，但内部仍以门面方式代理到 `agent-runtime` 的聊天、会话和 Agent 状态接口。这样可以先建立服务边界、镜像、健康检查、网关路由和 K3s 部署形态，再逐步迁移配额、审计、权限策略和真实 Agent 门面逻辑。

## 当前职责

- 承接 `travel-gateway` 转发过来的 Agent API。
- 代理 `/api/v1/chat`、`/api/v1/agent/*` 和 `/api/v1/conversations/*` 到 `agent-runtime`。
- 通过 `/health` 暴露自身和 upstream 状态。
- 通过 `X-Travel-Service-Boundary: travel-agent` 标记内部服务边界，便于后续日志和排查。

## 未来职责

- 作为用户侧 Agent 请求的门面入口。
- 在进入执行引擎前做配额、审计、权限和用户归属校验。
- 调用 `agent-runtime` 执行 LangGraph/LangChain 工作流。
- 调用 `travel-trip` 读取或写入行程元数据。
- 将非阻塞 Agent 任务发布到 RabbitMQ。

## 迁移原则

- 在旅行规划行为稳定前，先让 `agent-runtime` 保持执行引擎角色。
- 当配额、审计、权限策略明显变复杂后，再把这些逻辑迁入独立 `travel-agent` 服务。
- 不把 LangGraph/LangChain 的执行细节泄漏到 gateway 或前端。

## 本地运行

```powershell
cd services/travel-agent
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:AGENT_RUNTIME_URL="http://localhost:8000"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8400
```

`requirements.txt` 会以 editable 方式安装 `../common`，因此本地运行时要保持 `services/common` 目录存在。
