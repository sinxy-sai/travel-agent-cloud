# Travel Agent Cloud

基于 React、FastAPI、Spring Cloud、PostgreSQL 和 K3s 的多用户并发 AI 旅游助手项目。目标是在 VPS 上通过 Docker、K3s 和 GitHub Actions 完成全栈自动部署。

## 项目目标

本项目面向旅游规划场景，提供多轮对话、行程生成、行程保存、收藏、搜索、导出、用户旅行偏好等能力。当前阶段先实现可运行的前端工作台和 Python Agent Runtime，后续逐步接入 Java 微服务、微信登录、RAG 知识库、消息队列和更完整的 Agent 工具链。

## 技术栈

- Frontend: React, Vite, TypeScript, Tailwind CSS, Ant Design, TanStack Query, Zustand
- Agent Runtime: Python, FastAPI, OpenAI-compatible LLM API, LangChain/LangGraph planned for agent orchestration, FastMCP planned for tool access, DeepAgent planned for advanced agent workflows
- Backend Services: Java 17, Spring Boot, Spring Cloud, Spring Cloud Gateway
- RPC / Service Calls: Spring Cloud OpenFeign for Java service-to-service calls; REST between Gateway and Agent Runtime; gRPC reserved for future low-latency streaming needs
- Message Queue: RabbitMQ for domain events and async jobs
- Data: PostgreSQL, Redis, MinIO, pgvector
- Deployment: Docker, Docker Compose, K3s, Kubernetes Ingress
- CI/CD: GitHub Actions, Docker Hub, GHCR
- Observability: Prometheus, Grafana, Loki, OpenTelemetry

## Agent Runtime status

- `GET /health` exposes the selected agent engine and engine capabilities.
- `GET /api/v1/agent/status` exposes the current engine, capabilities, the latest privacy-safe run trace, recent run traces, and `runSummary` / `qualitySummary` aggregates.
- `POST /api/v1/trip-plans/{id}/revise` rewrites a saved itinerary from an agent instruction while preserving optimistic version control.
- `GET /api/v1/trip-plans/{id}/versions` and restore endpoints keep itinerary edits reversible.
- Run traces and summaries are in-memory only and do not include prompts, messages, user ids, API keys, or generated itinerary content.
- Prototype parity tracking lives in `docs/prototype-feature-parity.md`, based on `Hello-Agents/hello-agents-main/code/chapter13/helloagents-trip-planner`.

## 当前模块

- `frontend`: React + Vite 旅游助手前端工作台
- `agent-runtime`: FastAPI Agent 服务，提供行程规划、聊天、用户偏好和历史记录接口
- `services`: 后续 Spring Cloud 微服务预留目录
- `deploy`: K3s/Kubernetes 部署清单
- `docs`: 架构、API 和服务通信规范
- `scripts`: 服务器初始化和 smoke test 脚本

## 本地开发

启动 Agent Runtime:

```powershell
cd agent-runtime
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动前端:

```powershell
cd frontend
npm install
$env:VITE_AGENT_API_BASE_URL="http://localhost:8000"
npm run dev
```

访问:

```text
http://localhost:5173
```

本地 API smoke test:

```powershell
.\scripts\smoke-test.ps1 http://localhost:8000
```

## Docker Compose 本地测试

Docker Compose 会启动 PostgreSQL、RabbitMQ、Agent Runtime 和前端:

```bash
docker compose --profile worker up --build
```

访问:

```text
http://localhost:5173
```

RabbitMQ 管理后台:

```text
http://localhost:15672
```

Compose 环境会给 `agent-runtime` 注入:

```text
DATABASE_URL=postgresql://travel_agent:travel_agent_dev@postgres:5432/travel_agent_cloud
MESSAGE_QUEUE_URL=amqp://travel_agent:travel_agent_dev@rabbitmq:5672/
```

如果要让 Docker Compose 里的 Agent Runtime 读取本地 `agent-runtime/.env` 中的真实 LLM 配置，先创建本地 override 文件:

```powershell
Copy-Item docker-compose.override.example.yml docker-compose.override.yml
```

`docker-compose.override.yml` 已被 `.gitignore` 忽略，不要提交。Compose 文件中的 `DATABASE_URL` 和 `MESSAGE_QUEUE_URL` 会继续覆盖 `.env` 里的同名值，避免容器误连到宿主机地址。

当前 Agent Runtime 已支持在配置 `MESSAGE_QUEUE_URL` 后向 RabbitMQ 发布领域事件；`--profile worker` 会同时启动异步摘要消费者。未配置队列时，现有接口照常运行。

## 自动部署

当前推荐流程:

```text
本地测试 -> git push main -> CI -> 构建 Docker Hub 镜像 -> 自动部署到 K3s
```

自动部署链路:

- `CI` 成功后触发 `Build Images Docker Hub`
- Docker Hub 镜像构建成功后触发 `Deploy K3s`
- `Deploy K3s` 执行 `kubectl apply -k deploy/k8s`
- PostgreSQL 已加入默认 Kustomize 部署
- RabbitMQ 和 agent-runtime-worker 已加入默认 K3s 自动部署，前提是 VPS 已提前创建对应 Secret
- GHCR 镜像构建 workflow 保留，但 K3s 默认部署 Docker Hub 镜像

GitHub repository secrets:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
VPS_HOST
VPS_USER
VPS_SSH_KEY
```

## VPS 前置 Secret

如果希望 push 后自动部署并连接 PostgreSQL 和 DeepSeek，需要先在 VPS 创建 `postgres-secrets` 和 `agent-runtime-secrets`。

创建 PostgreSQL Secret:

```bash
sudo kubectl create secret generic postgres-secrets -n travel-agent-cloud --from-literal=POSTGRES_USER='travel_agent' --from-literal=POSTGRES_PASSWORD='换成强密码' --dry-run=client -o yaml | sudo kubectl apply -f -
```

创建 Agent Runtime Secret，同时配置数据库和 DeepSeek:

```bash
sudo kubectl create secret generic agent-runtime-secrets -n travel-agent-cloud --from-literal=DATABASE_URL='postgresql://travel_agent:换成强密码@postgres:5432/travel_agent_cloud' --from-literal=LLM_PROVIDER=openai_compatible --from-literal=LLM_API_KEY='你的 DeepSeek API Key' --from-literal=LLM_BASE_URL='https://api.deepseek.com' --from-literal=LLM_MODEL='deepseek-v4-flash' --dry-run=client -o yaml | sudo kubectl apply -f -
```

本地的 `agent-runtime/.env` 只用于本机测试，不会自动同步到 VPS。VPS 使用 Kubernetes Secret。

## K3s 验证

部署完成后，在 VPS 上检查:

```bash
sudo kubectl get pods -n travel-agent-cloud
curl http://localhost/health
```

如果返回中有下面两个字段，说明真实模型和数据库都已生效:

```json
{
  "llmEnabled": true,
  "databaseEnabled": true,
  "messageQueueEnabled": false
}
```

`messageQueueEnabled` 为 `true` 代表 Agent Runtime 已配置 RabbitMQ 发布入口；默认 K3s 部署也会启动 `agent-runtime-worker` 处理异步摘要事件。

也可以通过公网 IP 访问前端:

```text
http://你的服务器公网IP
```
