# services 目录说明

`services` 存放已经拆出或正在拆出的后端微服务。当前迁移采用渐进式门面模式：先让每个领域拥有独立进程、镜像、健康检查、网关路由和 K8s 部署清单，再把真实业务逻辑从 `agent-runtime` 逐步迁入对应服务。

## 当前服务

- `travel-gateway`：前端访问后端的统一入口，负责按路径把请求转发到领域服务。
- `travel-auth`：认证领域门面，当前代理登录、注册、用户资料、密码和 OAuth 相关接口。
- `travel-trip`：行程领域服务，当前已直接处理匿名本地用户的行程历史、编辑、版本、恢复、删除和 Markdown 导出，并承接 `agent-runtime` 生成、AI 修订和单日重生成后的内部保存请求；生成和 AI 修订入口仍代理到 `agent-runtime`。
- `travel-agent`：Agent 领域门面，当前代理聊天、会话和 Agent 状态相关接口。
- `travel-mcp`：真实旅行工具服务，封装高德数据、工具调用和 fallback 行为。
- `common`：跨服务共享 Python 包，只放基础设施工具，不放业务逻辑。

## 代码组织原则

- 每个服务必须能单独构建镜像，并暴露 `/health`。
- 每个服务只拥有自己的业务边界，不直接复制其他服务的业务逻辑。
- 跨服务调用优先走 HTTP + Kubernetes Service DNS，异步任务走 RabbitMQ。
- 公共代码只能放与业务无关的基础能力，例如代理、CORS、配置解析、健康检查和日志工具。
- 新增服务时同步补齐 Dockerfile、README、Compose 配置、K8s 清单和 CI 检查。

## 后续迁移方向

1. 继续稳定 `travel-auth`、`travel-trip`、`travel-agent` 的服务边界。
2. 继续把 `travel-trip` 的登录用户行程持久化和导出元数据迁出 `agent-runtime`。
3. 再迁移 `travel-agent` 的配额、审计、权限和 Agent 请求策略。
4. 最后迁移 `travel-auth` 的用户、会话和 OAuth identity 存储逻辑。
