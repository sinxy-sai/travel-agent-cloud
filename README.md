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

- 前端：React、Vite、TypeScript、Tailwind CSS、Ant Design、TanStack Query、Zustand
- Agent Runtime：Python、FastAPI、LangGraph、LangChain、OpenAI-compatible LLM API
- 工具服务：FastAPI、MCP 风格 JSON-RPC、高德 Web Service
- 网关：Python/FastAPI `travel-gateway`
- 数据和基础设施：PostgreSQL、Redis、RabbitMQ、MinIO、pgvector
- 部署：Docker、Docker Compose、K3s、Kubernetes Ingress
- CI/CD：GitHub Actions、Docker Hub、GHCR

## 当前模块

- `frontend`：React + Vite 前端工作台。
- `agent-runtime`：核心 FastAPI 服务，当前承载认证、行程、聊天、导出和 Agent 编排。
- `services/travel-gateway`：轻量 FastAPI 网关，本地和 K3s 的后端入口。
- `services/travel-mcp`：旅行工具微服务，负责高德 POI、天气、路线等工具数据。
- `services/common`：Python 微服务共享工具包，当前包含 HTTP 代理、header 转发和 upstream 健康检查。
- `services/travel-auth`：已运行的认证门面服务，当前代理到 `agent-runtime`，后续迁移真实认证存储逻辑。
- `services/travel-trip`：已运行的行程管理门面服务，当前代理到 `agent-runtime`，后续迁移真实行程存储逻辑。
- `services/travel-agent`：已运行的 Agent 门面服务，当前代理到 `agent-runtime`，后续迁移配额、审计和请求策略逻辑。
- `deploy/k8s`：K3s/Kubernetes 部署清单。
- `docs`：架构、API、通信和原型对齐文档。
- `scripts`：服务器初始化和 smoke test 脚本。

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

访问：

```text
http://localhost:5173
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

如果希望 Docker Compose 中的容器读取本地 `agent-runtime/.env` 里的真实 LLM 配置，先创建本地 override 文件：

```powershell
Copy-Item docker-compose.override.example.yml docker-compose.override.yml
```

`docker-compose.override.yml` 已被 `.gitignore` 忽略，不要提交。

## K3s/VPS 部署

当前推荐链路：

```text
本地测试 -> git push main -> CI -> 构建 Docker Hub 镜像 -> 自动部署到 K3s
```

自动部署流程：

- `CI` 成功后触发 `Build Images Docker Hub`。
- Docker Hub 镜像构建成功后触发 `Deploy K3s`。
- `Deploy K3s` 执行 `kubectl apply -k deploy/k8s`。
- K3s 默认部署 frontend、travel-gateway、travel-auth、travel-trip、travel-agent、agent-runtime、agent-runtime-worker、travel-mcp、PostgreSQL、RabbitMQ、Redis、MinIO 和 Ingress。

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

本地开发使用 Docker Compose；VPS 使用 K3s。

```text
本地 Docker Compose:
localhost:5173 -> frontend nginx -> travel-gateway -> travel-auth / travel-trip / travel-agent / agent-runtime / travel-mcp

VPS K3s:
公网 IP 或域名 -> Ingress -> frontend / travel-gateway -> travel-auth / travel-trip / travel-agent / agent-runtime / travel-mcp
```

本地 `.env` 不会自动同步到 VPS。VPS 使用 Kubernetes Secret 管理数据库、LLM、邮箱、OAuth、高德 key 等配置。
