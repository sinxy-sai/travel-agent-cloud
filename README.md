# Travel Agent Cloud

基于 Spring Cloud + Kubernetes/K3s + AI Agent 的多用户并发旅游助手系统。

## Project Goal

本项目面向旅游规划场景，提供多轮对话、行程生成、旅游知识检索、地图天气工具调用、行程保存与导出等能力。

## Tech Stack

- Frontend: React, Vite, TypeScript, Tailwind CSS, Ant Design, TanStack Query, Zustand
- Backend: Java 17, Spring Boot, Spring Cloud, Spring Cloud Gateway
- Auth: Sa-Token, JWT, Redis
- Agent Runtime: Python, FastAPI, LangGraph or HelloAgents, MCP
- Data: MySQL, Redis, MinIO, pgvector or Qdrant
- Async: RabbitMQ
- Deployment: Docker, K3s, Helm, Ingress, cert-manager
- CI/CD: GitHub Actions, GHCR
- Observability: Prometheus, Grafana, Loki, OpenTelemetry

## Planned Modules

- travel-gateway
- travel-auth
- travel-user
- travel-agent
- travel-trip
- travel-knowledge
- travel-task
- travel-common

## Current Milestone

The first runnable version contains:

- `frontend`: React + Vite trip planner workspace
- `agent-runtime`: FastAPI mock travel planning service
- `services`: placeholders for future Spring Cloud services
- `scripts`: VPS bootstrap scripts
- `deploy`: future Kubernetes and Helm deployment assets

## Local Development

Start Agent Runtime:

```bash
cd agent-runtime
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```
