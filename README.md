# Travel Agent Cloud

基于 React + FastAPI + PostgreSQL + K3s 的多用户并发 AI 旅游助手项目，目标是在 VPS 上通过 Docker、K3s 和 GitHub Actions 完成全栈部署。

## 项目目标

本项目面向旅游规划场景，提供多轮对话、行程生成、旅游知识检索、地图天气工具调用、行程保存与导出等能力。当前阶段先实现可运行的前端工作台和 Agent Runtime，后续再逐步接入 Java 微服务、用户体系、RAG 知识库和更完整的 Agent 工具链。

## 技术栈

- Frontend: React, Vite, TypeScript, Tailwind CSS, Ant Design, TanStack Query, Zustand
- Agent Runtime: Python, FastAPI, OpenAI-compatible LLM API
- Backend Services: Java 17, Spring Boot, Spring Cloud, Spring Cloud Gateway
- Data: PostgreSQL, Redis, MinIO, pgvector
- Deployment: Docker, K3s, Kubernetes Ingress
- CI/CD: GitHub Actions, Docker Hub, GHCR
- Observability: Prometheus, Grafana, Loki, OpenTelemetry

## 当前模块

- `frontend`: React + Vite 旅游助手前端工作台
- `agent-runtime`: FastAPI Agent 服务，提供行程规划和对话接口
- `services`: 后续 Spring Cloud 微服务预留目录
- `deploy`: K3s/Kubernetes 部署清单
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

Docker Compose 会同时启动 PostgreSQL、Agent Runtime 和前端:

```bash
docker compose up --build
```

访问:

```text
http://localhost:5173
```

Compose 环境会给 `agent-runtime` 注入:

```text
DATABASE_URL=postgresql://travel_agent:travel_agent_dev@postgres:5432/travel_agent_cloud
```

后端会自动创建当前需要的 `conversations`、`messages`、`trip_plans` 表。

## 自动部署

当前推荐流程:

```text
本地测试 -> git push main -> CI -> 构建 Docker Hub 镜像 -> 自动部署到 K3s
```

自动部署链路:

- `CI` 成功后触发 `Build Images Docker Hub`
- Docker Hub 镜像构建成功后触发 `Deploy K3s`
- `Deploy K3s` 会执行 `kubectl apply -k deploy/k8s`
- PostgreSQL 已加入默认 Kustomize 部署
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

如果希望 push 后自动部署并连接 PostgreSQL，需要先在 VPS 创建 `postgres-secrets` 和 `agent-runtime-secrets`。

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
  "databaseEnabled": true
}
```

也可以通过公网 IP 访问前端:

```text
http://你的服务器公网IP
```
