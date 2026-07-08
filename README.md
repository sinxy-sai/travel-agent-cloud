# Travel Agent Cloud

基于 React + FastAPI + Spring Cloud 规划的多用户并发 AI 旅游助手项目，目标是在 VPS 上通过 Docker、K3s 和 GitHub Actions 完成全栈部署。

## 项目目标

本项目面向旅游规划场景，提供多轮对话、行程生成、旅游知识检索、地图天气工具调用、行程保存与导出等能力。当前阶段先实现可运行的前端工作台和 Agent Runtime，后续再逐步接入 Java 微服务、数据库、用户体系和真实大模型能力。

## 技术栈

- Frontend: React, Vite, TypeScript, Tailwind CSS, Ant Design, TanStack Query, Zustand
- Agent Runtime: Python, FastAPI
- Backend Services: Java 17, Spring Boot, Spring Cloud, Spring Cloud Gateway
- Auth: Sa-Token, JWT, Redis
- Data: MySQL, Redis, MinIO, pgvector or Qdrant
- Async: RabbitMQ
- Deployment: Docker, K3s, Kubernetes Ingress
- CI/CD: GitHub Actions, Docker Hub, GHCR
- Observability: Prometheus, Grafana, Loki, OpenTelemetry

## 当前模块

- `frontend`: React + Vite 旅游助手前端工作台
- `agent-runtime`: FastAPI Agent 服务，提供行程规划和对话接口
- `services`: 后续 Spring Cloud 微服务预留目录
- `deploy`: K3s/Kubernetes 部署清单
- `scripts`: 服务器初始化和本地 smoke test 脚本

## 本地开发

日常开发优先在本地测试，不需要每次都部署到 VPS。

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

访问本地页面:

```text
http://localhost:5173
```

本地 API smoke test:

```powershell
.\scripts\smoke-test.ps1 http://localhost:8000
```

Linux 或 VPS 上可以运行:

```bash
bash scripts/smoke-test.sh http://localhost:8000
```

## Docker Compose 本地测试

如果想模拟容器环境，可以使用 Docker Compose:

```bash
docker compose up --build
```

访问:

```text
http://localhost:5173
```

Docker Compose 会同时启动本地 PostgreSQL，并给 `agent-runtime` 注入:

```text
DATABASE_URL=postgresql://travel_agent:travel_agent_dev@postgres:5432/travel_agent_cloud
```

后端会自动创建当前需要的 `conversations`、`messages`、`trip_plans` 表。

## 自动部署流程

当前推荐流程:

```text
本地测试 -> git push main -> CI -> 构建 Docker Hub 镜像 -> 自动部署到 K3s
```

自动部署已经通过 `.github/workflows/deploy-k3s.yml` 配置：

- `CI` 成功后触发 `Build Images Docker Hub`
- Docker Hub 镜像构建成功后触发 `Deploy K3s`
- 自动部署默认使用 commit SHA 作为镜像 tag
- 手动部署入口仍然保留，可以在 GitHub Actions 页面运行 `Deploy K3s`
- GHCR 镜像构建 workflow 保留，但 K3s 默认部署 Docker Hub 镜像

需要配置 GitHub repository secrets:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
VPS_HOST
VPS_USER
VPS_SSH_KEY
```

## K3s 手动验证

服务器上可以用这些命令检查部署状态:

```bash
sudo kubectl get nodes
sudo kubectl get pods -n travel-agent-cloud
sudo kubectl get ingress -n travel-agent-cloud
```

如果需要手动应用部署清单:

```bash
sudo kubectl apply -k deploy/k8s
sudo kubectl get pods -n travel-agent-cloud
```

## 配置真实大模型

`agent-runtime` 默认使用 mock 响应。要在 K3s 里启用 OpenAI-compatible 模型接口，在服务器执行:

```bash
sudo kubectl create secret generic agent-runtime-secrets \
  -n travel-agent-cloud \
  --from-literal=LLM_PROVIDER=openai_compatible \
  --from-literal=LLM_API_KEY='你的 API Key' \
  --from-literal=LLM_BASE_URL='https://api.openai.com/v1' \
  --from-literal=LLM_MODEL='你的模型名称' \
  --dry-run=client -o yaml | sudo kubectl apply -f -
```

然后重启 Agent Runtime:

```bash
sudo kubectl rollout restart deployment/agent-runtime -n travel-agent-cloud
sudo kubectl rollout status deployment/agent-runtime -n travel-agent-cloud
```

验证是否启用:

```bash
curl http://localhost/health
```

返回里的 `llmEnabled` 为 `true` 表示真实模型配置已经生效。

你本地的 `agent-runtime/.env` 只用于本机测试，不会自动同步到 VPS。VPS 上的大模型配置也要写入 Kubernetes Secret:

```bash
sudo kubectl create secret generic agent-runtime-secrets \
  -n travel-agent-cloud \
  --from-literal=LLM_PROVIDER=openai_compatible \
  --from-literal=LLM_API_KEY='你的 API Key' \
  --from-literal=LLM_BASE_URL='https://api.deepseek.com' \
  --from-literal=LLM_MODEL='deepseek-v4-flash' \
  --dry-run=client -o yaml | sudo kubectl apply -f -
```

## 配置 PostgreSQL 持久化

当前后端支持两种存储模式:

- 未配置 `DATABASE_URL`: 使用内存存储，Pod 重启后会话丢失。
- 配置 `DATABASE_URL`: 使用数据库持久化，并按 `X-User-Id` 隔离不同用户的会话。

如果要在 K3s 内部署项目自带的 PostgreSQL，先创建数据库 Secret:

```bash
sudo kubectl create secret generic postgres-secrets \
  -n travel-agent-cloud \
  --from-literal=POSTGRES_USER='travel_agent' \
  --from-literal=POSTGRES_PASSWORD='换成强密码' \
  --dry-run=client -o yaml | sudo kubectl apply -f -
```

再部署 PostgreSQL:

```bash
sudo kubectl apply -f deploy/k8s/postgres.yaml
sudo kubectl rollout status deployment/postgres -n travel-agent-cloud
```

然后把数据库连接写入 `agent-runtime-secrets`。如果这个 Secret 已经用于 LLM 配置，下面命令要同时保留原来的 LLM 字段:

```bash
sudo kubectl create secret generic agent-runtime-secrets \
  -n travel-agent-cloud \
  --from-literal=DATABASE_URL='postgresql://travel_agent:换成强密码@postgres:5432/travel_agent_cloud' \
  --from-literal=LLM_PROVIDER=openai_compatible \
  --from-literal=LLM_API_KEY='你的 API Key' \
  --from-literal=LLM_BASE_URL='https://api.deepseek.com' \
  --from-literal=LLM_MODEL='deepseek-v4-flash' \
  --dry-run=client -o yaml | sudo kubectl apply -f -
```

重启后端:

```bash
sudo kubectl rollout restart deployment/agent-runtime -n travel-agent-cloud
sudo kubectl rollout status deployment/agent-runtime -n travel-agent-cloud
curl http://localhost/health
```

返回里的 `databaseEnabled` 为 `true` 表示数据库持久化已经生效。
