<div align="center">

# Travel Agent Cloud

**面向旅行规划场景的 AI Agent 云原生全栈应用**

[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=111)](frontend)
[![Vite](https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white)](frontend)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](frontend)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](services)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](services)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Workflow-1C3C3C)](agent-runtime)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](docker-compose.yml)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-FF6600?logo=rabbitmq&logoColor=white)](docker-compose.yml)
[![K3s](https://img.shields.io/badge/K3s-Kubernetes-FFC61C?logo=kubernetes&logoColor=111)](deploy/k8s/README.md)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)

</div>

---

## 项目简介

Travel Agent Cloud 是一个面向旅行规划场景的 AI Agent 产品。项目以 `Hello-Agents/hello-agents-main/code/chapter13/helloagents-trip-planner` 的核心用户体验为原型，扩展为可本地联调、可部署到 VPS/K3s 的微服务系统。

当前版本已经完成从早期单体后端到 Python/FastAPI 微服务架构的迁移。`agent-runtime` 只负责 Agent 编排与执行；认证、行程、会话、工具和网关能力已经拆分到独立服务。

## 项目特性

- **多轮旅行规划对话**：支持围绕目的地、时间、预算、兴趣和偏好进行连续对话。
- **多 Agent 行程生成**：使用 LangGraph/LangChain 组织景点、天气、酒店、餐食、路线、预算和规划节点。
- **真实旅行工具接入**：通过 FastMCP 风格工具服务接入高德 Web Service，支持 POI、天气、路线和预算数据。
- **行程全生命周期管理**：支持保存、编辑、版本历史、版本恢复、收藏、删除和导出。
- **异步生成进度**：行程生成支持 job polling 和 SSE 事件流，前端可展示生成进度。
- **数据来源透明度**：行程模块可标记 live、fallback、failed 等数据来源状态。
- **用户系统**：支持注册、登录、退出、邮箱验证、找回密码、GitHub OAuth、profile 和账户数据导入导出。
- **会话系统**：支持聊天历史、会话列表、重命名、删除、同步摘要和异步摘要 worker。
- **导出能力**：支持 Markdown、PNG 和 PDF 导出。
- **云原生部署**：支持 Docker Compose 本地联调和 K3s/VPS 自动部署。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React、Vite、TypeScript、Tailwind CSS、Ant Design、TanStack Query、zustand |
| API 服务 | Python、FastAPI、Pydantic、SQLAlchemy、httpx |
| Agent 执行 | LangGraph、LangChain、OpenAI-compatible LLM API |
| 工具服务 | FastAPI、MCP 风格 HTTP JSON-RPC、高德 Web Service |
| 数据存储 | PostgreSQL、MinIO |
| 异步与缓存 | RabbitMQ、Redis |
| 本地编排 | Docker Compose |
| 生产部署 | K3s、Kubernetes、Ingress |
| CI/CD | GitHub Actions、Docker Hub、GHCR |

## 架构概览

```text
Browser
  -> frontend
      -> travel-gateway
          -> travel-auth
          -> travel-trip
              -> agent-runtime
                  -> travel-mcp
          -> travel-agent
              -> agent-runtime

travel-agent-worker
  -> RabbitMQ
  -> PostgreSQL

travel-auth / travel-trip / travel-agent
  -> PostgreSQL

travel-auth
  -> MinIO
```

设计原则：

- 前端和外部客户端只访问 `travel-gateway`。
- `agent-runtime` 只提供内部执行能力，不直接保存用户、会话或行程数据。
- 领域服务负责自己的用户侧 API 和数据边界。
- 在 4C/4G/40G VPS 资源约束下，各服务共享 PostgreSQL、RabbitMQ、Redis 和 MinIO 基础设施。

> [!NOTE]
> `agent-runtime` 不是旧单体后端。它只负责 Agent 编排和执行，不再保存用户、会话或行程数据；前端和外部客户端应统一通过 `travel-gateway` 访问后端。

## 服务边界

| 服务 | 路径 | 端口 | 职责 |
| --- | --- | --- | --- |
| Gateway | `services/gateway` | `8080` | 统一 API 入口、路由转发、`/health` 聚合、内部 token 注入 |
| Auth | `services/auth` | `8300` | 用户、认证、session、profile、邮箱 token、GitHub OAuth、账户导入导出 |
| Trip | `services/trip` | `8200` | 行程生成入口、持久化、版本、收藏、导出、异步 job、SSE 进度 |
| Agent | `services/agent` | `8400` | 聊天入口、会话、消息、同步摘要、异步摘要 job、摘要 worker |
| MCP | `services/mcp` | `8100` | 高德/FastMCP 旅行工具服务，提供 MCP 风格 JSON-RPC |
| Runtime | `agent-runtime` | `8000` | LangGraph/LangChain、LLM 调用、工具编排、Agent 执行核心 |
| Frontend | `frontend` | `5173` | React + Vite 用户界面 |

## 仓库结构

```text
travel-agent-cloud/
├─ agent-runtime/            # Agent 编排/执行核心
├─ frontend/                 # React + Vite 前端
├─ services/
│  ├─ gateway/               # 统一 API 网关
│  ├─ auth/                  # 认证与用户服务
│  ├─ trip/                  # 行程服务
│  ├─ agent/                 # 会话与聊天服务
│  ├─ mcp/                   # 旅行工具服务
│  └─ common/                # Python 微服务共享工具包
├─ deploy/k8s/               # K3s/Kubernetes 清单
├─ docs/                     # 架构、API、通信和原型对齐文档
├─ scripts/                  # 初始化和 smoke test 脚本
├─ .github/workflows/        # CI、镜像构建和 K3s 自动部署
├─ docker-compose.yml        # 本地编排
└─ README.md
```

## 本地开发

### 前置条件

- Docker Desktop 或 Docker Engine
- Node.js 22+
- Python 3.12+
- PowerShell 7+，或兼容 Bash 的终端

### 准备环境变量

```powershell
Copy-Item agent-runtime\.env.example agent-runtime\.env
Copy-Item services\gateway\.env.example services\gateway\.env
Copy-Item services\auth\.env.example services\auth\.env
Copy-Item services\trip\.env.example services\trip\.env
Copy-Item services\agent\.env.example services\agent\.env
Copy-Item services\mcp\.env.example services\mcp\.env
```

按需填写：

- LLM API key 和模型配置：`agent-runtime/.env`
- 高德 Web Service key：`services/mcp/.env`
- 高德 JS SDK key：`frontend/.env`
- SMTP 和 OAuth：`services/auth/.env`

### 启动完整环境

```powershell
docker compose --profile worker up -d --build
```

> [!TIP]
> 本地开发建议优先使用 Docker Compose 启动完整依赖，避免单服务调试时遗漏 PostgreSQL、RabbitMQ、MinIO 或 Redis。

访问：

```text
http://localhost:5173
```

### 健康检查

```powershell
Invoke-RestMethod http://localhost:5173/health
Invoke-RestMethod http://localhost:8080/gateway/health
```

### Smoke Test

```powershell
.\scripts\smoke-test.ps1 http://localhost:5173
```

## 环境变量

| 文件 | 说明 |
| --- | --- |
| `frontend/.env` | 前端构建配置，例如 API 地址和高德 JS SDK key |
| `agent-runtime/.env` | LLM、LangGraph、FastMCP、internal token 等执行配置 |
| `services/gateway/.env` | upstream 地址、请求超时、CORS、internal token |
| `services/auth/.env` | 数据库、认证、SMTP、OAuth、MinIO、账户导入导出 |
| `services/trip/.env` | 数据库、认证密钥、runtime 内部调用 |
| `services/agent/.env` | 数据库、RabbitMQ、worker、runtime 内部调用 |
| `services/mcp/.env` | 高德 Web Service key、base URL、超时 |

关键约束：

- `AUTH_SECRET_KEY` 必须在 `services/auth`、`services/agent`、`services/trip` 和需要解析用户 token 的服务中保持一致。
- `INTERNAL_SERVICE_TOKEN` 必须在 gateway、runtime 和领域服务之间保持一致。
- `.env` 文件不提交到 Git；VPS/K3s 使用 Kubernetes Secret 管理敏感配置。

## Docker 镜像

| 镜像 | 说明 |
| --- | --- |
| `travel-agent-cloud-frontend` | 前端 Nginx 静态站点 |
| `travel-agent-cloud-agent-runtime` | Agent 执行核心 |
| `travel-agent-cloud-gateway` | API 网关 |
| `travel-agent-cloud-auth` | 认证与用户服务 |
| `travel-agent-cloud-trip` | 行程服务 |
| `travel-agent-cloud-agent` | 会话与聊天服务；worker 复用同一镜像 |
| `travel-agent-cloud-mcp` | 旅行工具服务 |

Compose 服务名和 K8s Service 名保留 `travel-gateway`、`travel-auth`、`travel-trip`、`travel-agent`、`travel-mcp`，用于内部 DNS。镜像名和容器名已经去掉重复前缀。

## K3s / VPS 部署

当前自动部署链路：

```text
git push main
  -> CI
  -> Build Images Docker Hub
  -> Deploy K3s
  -> kubectl apply -k deploy/k8s
  -> kubectl set image 到当前 commit SHA
  -> rollout status
  -> sudo k3s crictl rmi --prune
```

GitHub repository secrets：

| Secret | 说明 |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub 用户名 |
| `DOCKERHUB_TOKEN` | Docker Hub access token |
| `VPS_HOST` | VPS 公网 IP 或域名 |
| `VPS_USER` | SSH 用户 |
| `VPS_SSH_KEY` | SSH 私钥 |

VPS 部署后检查：

```bash
sudo kubectl get pods -n travel-agent-cloud
sudo kubectl get deploy -n travel-agent-cloud
sudo kubectl get svc -n travel-agent-cloud
curl -i http://127.0.0.1/health
sudo k3s crictl images | grep travel-agent-cloud
```

详细部署说明见 [deploy/k8s/README.md](deploy/k8s/README.md)。

## 常用命令

| 场景 | 命令 |
| --- | --- |
| 启动完整本地环境 | `docker compose --profile worker up -d --build` |
| 停止本地环境 | `docker compose --profile worker down` |
| 只重建前端 | `docker compose up -d --build frontend` |
| 只重建行程服务 | `docker compose up -d --build travel-trip` |
| 只重建会话服务和 worker | `docker compose --profile worker up -d --build travel-agent travel-agent-worker` |
| 本地 smoke test | `.\scripts\smoke-test.ps1 http://localhost:5173` |
| 查看 K3s pod | `sudo kubectl get pods -n travel-agent-cloud` |
| 清理 K3s 未使用镜像 | `sudo k3s crictl rmi --prune` |

## 安全说明

- 漏洞报告流程见 [Security Policy](SECURITY.md)，请不要通过公开 issue 披露安全漏洞。
- 不要提交 `.env`、SSH 私钥、LLM API key、高德 key、SMTP 授权码或 OAuth client secret。
- 生产环境应使用 Kubernetes Secret 管理敏感配置。
- 纯 HTTP 环境不要启用 Secure cookie；配置 HTTPS 后再开启。
- 不要删除 PostgreSQL、MinIO、RabbitMQ、Redis 的 PVC/PV，除非明确要清空线上数据。
- GitHub Actions 部署使用 SSH 连接 VPS，应限制私钥权限并定期轮换。

> [!WARNING]
> 不要在 VPS/K3s 上清理 PostgreSQL、MinIO、RabbitMQ、Redis 的 PVC/PV，除非明确要清空线上数据。镜像清理应使用 `sudo k3s crictl rmi --prune`，不要删除持久化卷。

## 相关文档

| 文档 | 说明 |
| --- | --- |
| [架构说明](docs/architecture.md) | 系统架构和服务边界 |
| [API 规范](docs/api-guidelines.md) | REST API、字段命名、错误格式和分页规范 |
| [服务通信方案](docs/service-communication.md) | 服务间 HTTP、internal token、RabbitMQ 和健康检查 |
| [微服务路线图](docs/microservices-roadmap.md) | 微服务拆分过程和后续增强方向 |
| [原型功能对齐](docs/prototype-feature-parity.md) | 与 Hello-Agents 原型的功能映射 |
| [K3s 部署说明](deploy/k8s/README.md) | VPS/K3s 部署、Secret 和运维命令 |
| [Security Policy](SECURITY.md) | 漏洞报告流程、支持范围和安全注意事项 |

## 当前状态

- 微服务拆分已经完成主体迁移。
- 新镜像命名已经统一为 `travel-agent-cloud-*`。
- VPS/K3s 已验证 `travel-gateway`、`travel-auth`、`travel-trip`、`travel-agent`、`travel-agent-worker`、`travel-mcp`、`agent-runtime` 和 `frontend` 正常运行。
- 下一阶段重点是生产质量增强：持久化异步 job 状态、完善观测链路、强化服务级鉴权、补充端到端测试和优化运维脚本。

## License

本项目基于 [MIT License](LICENSE) 开源。
