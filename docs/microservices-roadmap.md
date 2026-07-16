# Kubernetes 原生 Python 微服务路线图

本项目后续采用 Kubernetes 原生 + Python/FastAPI 微服务路线。这里的“微服务化”指服务边界、独立部署、服务发现、网关入口、异步消息和可观测性，不要求使用 Spring Boot、Spring Cloud 或 gRPC。

## 当前运行边界

```text
frontend
  -> travel-gateway
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
- `travel-auth`：规划中的认证服务，等认证边界稳定后再拆。
- `travel-trip`：规划中的行程管理服务，等行程和导出模型稳定后再拆。
- `travel-agent`：规划中的 Agent 门面服务，用于配额、审计、权限和请求策略。

## Kubernetes 职责

- 服务发现使用 Kubernetes Service DNS，例如 `http://agent-runtime:8000`。
- 公网入口使用 Ingress，并优先路由到 `travel-gateway`。
- 配置通过环境变量注入，敏感信息放在 Kubernetes Secret。
- 异步任务通过 RabbitMQ，不依赖进程内调用。
- 共享基础设施包括 PostgreSQL、Redis、MinIO 和 RabbitMQ。

## 迁移顺序

1. 先让 `travel-gateway` 站到现有 API 前面。
2. 将 `travel-mcp` 作为第一个真实工具微服务运行。
3. 保持 `agent-runtime` 稳定，继续打磨旅行规划行为。
4. 认证流程稳定后再拆出 `travel-auth`。
5. 行程、版本、导出模型稳定后再拆出 `travel-trip`。
6. 当配额、审计、权限策略变复杂后，再加入 `travel-agent`。

## 暂不做的事

- 暂不迁移到 Spring Cloud。
- 暂不引入服务网格。
- 暂不默认使用 gRPC，除非出现明确的低延迟或双向流式内部调用需求。
- 暂不急着拆分每个服务的独立数据库，先等数据所有权稳定。
