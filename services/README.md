# services 目录说明

`services` 存放已经拆出的后端微服务。当前迁移路线是 Kubernetes 原生 + Python/FastAPI：本地用 Docker Compose 编排，VPS 上用 K3s 编排。每个服务都应能独立构建镜像、暴露 `/health`、拥有自己的配置文件和部署清单。

## 当前服务

- `travel-gateway`：统一入口，按路径把前端请求转发到领域服务，同时保留外部 `/api/v1` 兼容性。
- `travel-auth`：认证和用户领域服务，负责账号、session、profile、邮箱 token、OAuth identity、GitHub OAuth 回调、账户导入导出聚合和导出文件。
- `travel-trip`：行程领域服务，负责行程历史、详情、编辑、版本、恢复、收藏、删除和 Markdown 导出。
- `travel-agent`：Agent 领域入口，负责会话 CRUD、同步摘要、异步摘要 job 生产；聊天和行程执行核心通过内部接口调用 `agent-runtime`。
- `travel-mcp`：旅行工具服务，负责高德数据、工具调用和 fallback。
- `common`：跨服务共享 Python 包，只放代理、CORS、健康检查、通用错误等基础设施能力，不放业务规则。

## 环境变量约定

每个服务都必须有自己的环境变量模板：

- `services/gateway/.env.example`
- `services/auth/.env.example`
- `services/trip/.env.example`
- `services/agent/.env.example`
- `services/mcp/.env.example`

本地开发时，对应的 `.env` 文件也放在各服务目录下，并由 `docker-compose.yml` 的 `env_file` 加载。`.env` 文件不提交到 Git，`.env.example` 才是可提交的模板。

`agent-runtime/.env` 只保留 Agent 编排/执行核心需要的配置，例如 LLM、LangGraph、FastMCP、Redis、RabbitMQ 和内部行程服务地址。认证、用户、账户导入导出、SMTP、OAuth 等新配置应该放在 `services/auth/.env`，不要再继续堆到 `agent-runtime/.env`。

`INTERNAL_SERVICE_TOKEN` 是服务间调用的共享内部 token。所有需要通过 `travel-gateway` 或 internal API 通信的服务必须配置同一个值；本地可以使用开发默认值，VPS/K3s 必须放到 Secret 中。

## 本地和 K3s 的差异

- 本地 Docker Compose：通过每个服务目录下的 `.env` 注入配置，服务名直接使用 Compose DNS，例如 `http://travel-auth:8300`。
- VPS/K3s：同样按服务边界拆配置，但应迁移为 Kubernetes `ConfigMap` 和 `Secret`，服务间地址使用 Kubernetes Service DNS。
- 共享基础设施连接串可以在多个服务中重复出现，但业务配置必须归属到拥有该领域的服务。

## 代码组织原则

- 每个服务只拥有自己的业务边界，不复制其他服务的业务规则。
- 跨服务同步调用优先使用 HTTP + 服务 DNS，异步任务使用 RabbitMQ。
- 新增服务时同步补齐 Dockerfile、README、Compose 配置、`.env.example` 和 K8s 清单。
- `agent-runtime` 不是旧单体服务，而是 Agent 编排/执行核心；用户、行程、会话等数据边界应持续迁出。
