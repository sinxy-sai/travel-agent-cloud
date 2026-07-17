# services 目录说明

`services` 存放已经拆出或正在拆出的后端微服务。当前迁移采用渐进式方式：先让每个领域拥有独立进程、镜像、健康检查、网关路由和 K8s 清单，再把真实业务逻辑从 `agent-runtime` 逐步迁入对应服务。

## 当前服务

- `travel-gateway`：统一入口，负责把前端请求按路径转发到领域服务。
- `travel-auth`：认证和用户领域服务，负责账户、session、安全事件、profile、邮箱 token、OAuth identity 和 GitHub OAuth 回调。
- `travel-trip`：行程领域服务，负责行程历史、详情、编辑、版本、恢复、收藏、删除和 Markdown 导出。
- `travel-agent`：Agent 领域入口，负责会话 CRUD 和同步摘要；聊天执行与异步摘要任务仍由 `agent-runtime` 处理。
- `travel-mcp`：旅行工具服务，负责高德数据、工具调用和 fallback。
- `common`：跨服务共享 Python 包，只放基础设施工具，不放业务逻辑。

## 代码组织原则

- 每个服务必须能单独构建镜像，并暴露 `/health`。
- 每个服务只拥有自己的业务边界，不把其他服务的业务规则复制进来。
- 跨服务同步调用优先使用 HTTP + Kubernetes Service DNS，异步任务使用 RabbitMQ。
- 公共代码只能放与业务无关的基础能力，例如代理、CORS、健康检查和通用错误处理。
- 新增服务时同步补齐 Dockerfile、README、Compose 配置和 K8s 清单。

## 迁移提醒

`agent-runtime` 不是立刻删除的旧服务。它会逐步收缩成 Agent 编排/执行核心，在迁移期间继续承担 LangGraph/LangChain 执行、异步 worker 和部分 fallback。
