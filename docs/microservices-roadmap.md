# Kubernetes 原生 Python 微服务路线图

本项目采用 Kubernetes 原生 + Python/FastAPI 微服务路线。这里的“微服务化”指服务边界、独立镜像、独立健康检查、网关路由、异步消息和可观测性，不要求使用 Spring Boot、Spring Cloud 或 gRPC。

## 当前运行边界

```text
frontend
  -> travel-gateway
      -> travel-auth
      -> travel-trip
      -> travel-agent
      -> travel-mcp
      -> agent-runtime

agent-runtime
  -> PostgreSQL
  -> Redis
  -> RabbitMQ
  -> MinIO
  -> travel-mcp
```

## 当前服务

- `travel-gateway`：前端访问后端的统一入口，按路径转发到领域服务。
- `travel-auth`：用户、认证、profile、安全事件、session、邮箱 token、OAuth identity 和 GitHub OAuth 回调。
- `travel-trip`：行程历史、详情、编辑、版本、恢复、收藏、删除和 Markdown 导出。
- `travel-agent`：会话列表、详情、重命名、删除、同步摘要、异步摘要 job 生产和 Agent API 门面。
- `travel-mcp`：旅行工具服务，封装高德数据、工具调用和 fallback 行为。
- `agent-runtime`：Agent 编排和执行核心，承担 LangGraph/LangChain 执行、聊天回复、行程生成和后台 worker 执行。
- `services/common`：跨服务基础设施工具包，只放代理、CORS、健康检查等非业务逻辑。

## 已完成的实迁

1. `travel-auth` 已接管注册、登录、退出、当前用户、密码修改、session 管理、安全事件、账户删除、邮箱验证 token、密码重置 token、OAuth identity、GitHub OAuth 回调、登录/匿名用户 profile，以及账户导入导出聚合和导出文件。
2. `travel-trip` 已接管登录和匿名用户的行程持久化、版本、恢复、收藏、删除和 Markdown 导出。
3. `travel-agent` 已接管会话 CRUD、同步摘要和异步摘要 job 生产，并在删除会话时维护行程引用一致性。
4. Docker Compose 和 K8s 清单已经包含 `travel-auth`、`travel-trip`、`travel-agent`、`travel-mcp`、`travel-gateway` 等独立服务。

## 当前仍保留在 agent-runtime 的内容

- LangGraph/LangChain Agent 执行。
- 聊天回复生成的执行核心，入口在 `travel-agent`。
- 行程生成、行程修订、单日重生成的执行核心，入口在 `travel-trip`。
- 异步摘要 worker 消费。
- 兼容旧调用的公开 `/api/v1` runtime 路径。

## 后续收敛方向

- 继续收敛 `agent-runtime` 的兼容公开路径，保持新流量优先通过领域服务进入 internal execution。
- 把 Agent 请求策略、配额、审计和权限判断继续增强到 `travel-agent`。
- 等领域边界稳定后，再考虑每个服务独立数据库；当前阶段仍使用共享 PostgreSQL，靠服务代码边界先拆单体。

## 暂不做

- 暂不迁移到 Spring Cloud。
- 暂不引入服务网格。
- 暂不默认使用 gRPC，除非出现明确的低延迟或双向流式内部调用需求。
- 暂不强制每个微服务独立数据库，先稳定服务所有权和 API 边界。
