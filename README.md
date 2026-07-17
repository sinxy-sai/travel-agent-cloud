# Travel Agent Cloud

Travel Agent Cloud 是一个面向旅行规划场景的 AI 助手项目。当前目标是先复现 `Hello-Agents/hello-agents-main/code/chapter13/helloagents-trip-planner` 的核心用户体验，再逐步演进为可在 VPS/K3s 上部署的云原生全栈应用。

## 项目目标

当前重点能力：

- 多轮旅行规划对话
- 结构化行程生成
- 行程保存、编辑、版本恢复和删除
- Markdown、图片和 PDF 导出
- 用户注册、登录、邮箱验证、找回密码和 GitHub OAuth
- 用户旅行偏好
- 高德地图和高德 Web Service 数据接入
- LangGraph/LangChain 多 Agent 旅行规划工作流
- Docker Compose 本地联调
- K3s/VPS 自动部署

## 技术栈

- 前端：React、Vite、TypeScript、Tailwind CSS、Ant Design、TanStack Query、zustand
- Agent Runtime：Python、FastAPI、LangGraph、LangChain、OpenAI-compatible LLM API
- 工具服务：FastAPI、MCP 风格 JSON-RPC、高德 Web Service
- 网关：Python/FastAPI `travel-gateway`
- 数据和基础设施：PostgreSQL、Redis、RabbitMQ、MinIO、pgvector
- 部署：Docker、Docker Compose、K3s、Kubernetes Ingress
- CI/CD：GitHub Actions、Docker Hub、GHCR

## 当前模块

- `frontend`：React + Vite 前端工作台。
- `services/gateway`：统一 API 入口，负责把 `/api/v1` 请求转发到领域服务。
- `services/auth`：认证和用户领域服务，负责账号、session、profile、邮箱 token、OAuth identity、GitHub OAuth、账户导入导出和导出文件。
- `services/trip`：行程领域服务，负责行程历史、详情、编辑、版本、恢复、收藏、删除和 Markdown 导出。
- `services/agent`：Agent 领域入口，负责会话 CRUD、同步摘要、异步摘要 job 生产；执行核心通过内部接口调用 `agent-runtime`。
- `services/mcp`：旅行工具微服务，负责高德 POI、天气、路线等工具数据。
- `services/common`：Python 微服务共享工具包，只放 HTTP 代理、CORS、健康检查、通用错误等基础设施能力。
- `agent-runtime`：Agent 编排/执行核心，负责 LangGraph/LangChain 工作流、LLM 调用和旅行工具编排。
- `deploy/k8s`：K3s/Kubernetes 部署清单。
- `docs`：架构、API、通信和原型对齐文档。
- `scripts`：服务器初始化和 smoke test 脚本。

## 环境变量

本项目采用“每个服务一个 `.env`”的配置边界：

- `agent-runtime/.env`：Agent 编排/执行、LLM、LangGraph、FastMCP、Redis、RabbitMQ 等运行时配置。
- `frontend/.env`：Vite 前端构建配置，例如 API 地址和高德 JS SDK key。
- `services/gateway/.env`：网关上游服务地址和请求超时。
- `services/auth/.env`：认证、SMTP、OAuth、MinIO、账户导入导出等配置。
- `services/trip/.env`：行程服务数据库、认证密钥和 runtime 内部调用配置。
- `services/agent/.env`：会话服务数据库、RabbitMQ、worker 和 runtime 内部调用配置。
- `services/mcp/.env`：高德 Web Service key 和工具服务配置。

`.env` 文件只用于本地，不提交到 Git；`.env.example` 是模板，需要随代码维护。VPS/K3s 环境应把这些配置迁移为 Kubernetes `ConfigMap` 和 `Secret`。

微服务间调用使用 `INTERNAL_SERVICE_TOKEN` 做轻量内部鉴权。本地 `.env` 使用开发默认值；VPS/K3s 必须用 Kubernetes Secret 覆盖，并保证 `travel-gateway`、`travel-auth`、`travel-trip`、`travel-agent` 和 `agent-runtime` 使用同一个值。

## 本地开发

启动 Agent Runtime：

```powershell
cd agent-runtime
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动前端：

```powershell
cd frontend
npm install
$env:VITE_AGENT_API_BASE_URL="http://localhost:8000"
npm run dev
```

本地 API smoke test：

```powershell
.\scripts\smoke-test.ps1 http://localhost:8000
```

## Docker Compose 本地联调

Docker Compose 会启动 PostgreSQL、RabbitMQ、Redis、MinIO、`travel-mcp`、`travel-auth`、`travel-trip`、`travel-agent`、`travel-gateway`、`agent-runtime` 和前端。

```powershell
docker compose --profile worker up --build
```

访问：

```text
http://localhost:5173
```

常用检查：

```powershell
Invoke-RestMethod http://localhost:8080/gateway/health
Invoke-RestMethod http://localhost:5173/health
.\scripts\smoke-test.ps1 http://localhost:5173
```

RabbitMQ 管理后台：

```text
http://localhost:15672
```

## K3s/VPS 部署

当前推荐链路：

```text
本地测试 -> git push main -> CI -> 构建 Docker Hub 镜像 -> 自动部署到 K3s
```

自动部署流程：

- `CI` 成功后触发 `Build Images Docker Hub`。
- Docker Hub 镜像构建成功后触发 `Deploy K3s`。
- `Deploy K3s` 执行 `kubectl apply -k deploy/k8s`。
- K3s 默认部署 frontend、travel-gateway、travel-auth、travel-trip、travel-agent、travel-agent-worker、agent-runtime、travel-mcp、PostgreSQL、RabbitMQ、Redis、MinIO 和 Ingress。

GitHub repository secrets：

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
VPS_HOST
VPS_USER
VPS_SSH_KEY
```

详细 K3s 配置见 [deploy/k8s/README.md](deploy/k8s/README.md)。

## 重要文档

- [架构说明](docs/architecture.md)
- [API 规范](docs/api-guidelines.md)
- [服务通信方案](docs/service-communication.md)
- [Kubernetes 原生 Python 微服务路线图](docs/microservices-roadmap.md)
- [原型功能对齐](docs/prototype-feature-parity.md)

## 当前部署差异

本地开发使用 Docker Compose，VPS 使用 K3s。

```text
本地 Docker Compose:
localhost:5173 -> frontend nginx -> travel-gateway -> travel-auth / travel-trip / travel-agent / agent-runtime / travel-mcp

VPS K3s:
公网 IP 或域名 -> Ingress -> frontend / travel-gateway -> travel-auth / travel-trip / travel-agent / agent-runtime / travel-mcp
```

本地 `.env` 不会自动同步到 VPS。VPS 使用 Kubernetes Secret 管理数据库、LLM、邮箱、OAuth、高德 key 等配置。
