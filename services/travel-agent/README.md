# travel-agent

`travel-agent` 是规划中的 Python/FastAPI Agent 门面服务，目前还不是运行中的服务。LangGraph/LangChain 执行逻辑当前仍在 `agent-runtime` 中。

## 未来职责

- 作为用户侧 Agent 请求的门面入口。
- 在进入执行引擎前做配额、审计、权限和用户归属校验。
- 调用 `agent-runtime` 执行 LangGraph/LangChain 工作流。
- 行程服务拆分后，调用 `travel-trip` 读取或写入行程元数据。
- 将非阻塞 Agent 任务发布到 RabbitMQ。

## 迁移原则

- 在旅行规划行为稳定前，先让 `agent-runtime` 保持执行引擎角色。
- 当配额、审计、权限策略明显变复杂后，再引入独立 `travel-agent` 服务。
