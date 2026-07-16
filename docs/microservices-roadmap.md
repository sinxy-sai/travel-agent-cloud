# Kubernetes 原生 Python 微服务路线图

本项目后续采用 Kubernetes 原生 + Python/FastAPI 微服务路线。这里的“微服务化”指服务边界、独立部署、服务发现、网关入口、异步消息和可观测性，不要求使用 Spring Boot、Spring Cloud 或 gRPC。

## 当前运行边界

```text
frontend
  -> travel-gateway
      -> travel-auth
      -> travel-trip
      -> travel-agent
      -> agent-runtime
      -> travel-mcp

agent-runtime
  -> PostgreSQL
  -> Redis
  -> RabbitMQ
  -> MinIO
  -> travel-mcp
```

## 当前和规划中的服务

- `travel-gateway`：轻量 FastAPI 网关，作为前端访问后端的统一入口。
- `agent-runtime`：当前承载认证、行程、聊天、导出和 Agent 编排 API。
- `travel-mcp`：旅行工具服务，当前支持高德数据和确定性 fallback。
- `agent-runtime-worker`：消费 RabbitMQ 任务的后台 worker。
- `services/common`：微服务共享 Python 包，存放跨服务基础设施工具，不放业务逻辑。
- `travel-auth`：当前已作为认证 API 门面服务运行，内部暂时代理到 `agent-runtime`，后续迁移真实认证存储逻辑。
- `travel-trip`：当前已开始实迁行程持久化能力。匿名本地用户的行程列表、详情、编辑、版本、恢复、删除和 Markdown 导出由它直接访问 PostgreSQL 处理；`agent-runtime` 生成后的行程也通过它的内部接口保存；AI 修订、单日重生成和登录用户读写路径暂时仍代理到 `agent-runtime`。
- `travel-agent`：当前已作为 Agent API 门面服务运行，内部暂时代理到 `agent-runtime`，后续迁移配额、审计、权限和请求策略。

## Kubernetes 职责

- 服务发现使用 Kubernetes Service DNS，例如 `http://agent-runtime:8000`。
- 公网入口使用 Ingress，并优先路由到 `travel-gateway`。
- 配置通过环境变量注入，敏感信息放在 Kubernetes Secret。
- 异步任务通过 RabbitMQ，不依赖进程内调用。
- 共享基础设施包括 PostgreSQL、Redis、MinIO 和 RabbitMQ。
- 跨服务通用代码放在 `services/common`，业务逻辑仍留在各自服务内。

## 迁移顺序

1. 先让 `travel-gateway` 站到现有 API 前面。
2. 将 `travel-mcp` 作为第一个真实工具微服务运行。
3. 保持 `agent-runtime` 稳定，继续打磨旅行规划行为。
4. 将 `travel-auth` 从代理门面升级为真正拥有用户、会话、邮箱 token 和 OAuth identity 的服务。
5. 将 `travel-trip` 从代理门面升级为真正拥有行程、版本和导出元数据的服务。当前已完成匿名用户读写路径和生成后保存的实迁。
6. 将 `travel-agent` 从代理门面升级为真正承载配额、审计、权限和 Agent 请求策略的服务。

## 暂不做的事

- 暂不迁移到 Spring Cloud。
- 暂不引入服务网格。
- 暂不默认使用 gRPC，除非出现明确的低延迟或双向流式内部调用需求。
- 暂不急着拆分每个服务的独立数据库，先等数据所有权稳定。
