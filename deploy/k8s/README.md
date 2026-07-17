# K3s 部署清单

本目录用于在 VPS 的 K3s 集群中部署 Travel Agent Cloud。

## 部署

```bash
kubectl apply -k deploy/k8s
```

检查状态：

```bash
kubectl get pods -n travel-agent-cloud
kubectl get svc -n travel-agent-cloud
kubectl get ingress -n travel-agent-cloud
```

默认 Ingress 没有配置 host。在单台 VPS 的 K3s Traefik 环境中，镜像发布后可以直接通过服务器公网 IP 测试。

## 默认镜像

```text
docker.io/sinxysai/travel-agent-cloud-frontend:latest
docker.io/sinxysai/travel-agent-cloud-agent-runtime:latest
docker.io/sinxysai/travel-agent-cloud-gateway:latest
docker.io/sinxysai/travel-agent-cloud-auth:latest
docker.io/sinxysai/travel-agent-cloud-trip:latest
docker.io/sinxysai/travel-agent-cloud-agent:latest
docker.io/sinxysai/travel-agent-cloud-mcp:latest
```

GHCR workflow 保留用于镜像发布，但 K3s 清单默认拉取 Docker Hub 镜像，因为国内 VPS 通常更容易访问 Docker Hub 镜像加速源。

如果 Docker Hub 命名空间不是 `sinxysai`，需要修改：

- `agent-runtime.yaml`
- `gateway.yaml`
- `auth.yaml`
- `trip.yaml`
- `agent.yaml`
- `mcp.yaml`
- `frontend.yaml`

## 默认部署内容

默认 Kustomize 会部署：

- PostgreSQL
- RabbitMQ
- Redis
- MinIO
- `travel-mcp`
- `travel-auth`
- `travel-trip`
- `travel-agent`
- `travel-gateway`
- `agent-runtime`
- `travel-agent-worker`
- `frontend`
- Ingress

自动部署前，需要提前创建必要 Secret。

## 创建 PostgreSQL Secret

```bash
kubectl create secret generic postgres-secrets \
  -n travel-agent-cloud \
  --from-literal=POSTGRES_USER='travel_agent' \
  --from-literal=POSTGRES_PASSWORD='change-me' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 创建 RabbitMQ Secret

```bash
kubectl create secret generic rabbitmq-secrets \
  -n travel-agent-cloud \
  --from-literal=RABBITMQ_DEFAULT_USER='travel_agent' \
  --from-literal=RABBITMQ_DEFAULT_PASS='change-me-to-a-strong-password' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 创建 MinIO Secret

```bash
kubectl create secret generic minio-secrets \
  -n travel-agent-cloud \
  --from-literal=MINIO_ROOT_USER='travel_agent' \
  --from-literal=MINIO_ROOT_PASSWORD='change-me-to-a-long-random-password' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 创建 travel-mcp Secret

如果希望工具服务使用真实高德数据，创建：

```bash
kubectl create secret generic travel-mcp-secrets \
  -n travel-agent-cloud \
  --from-literal=AMAP_WEB_SERVICE_KEY='your-amap-web-service-key' \
  --dry-run=client -o yaml | kubectl apply -f -
```

如果缺少该 Secret 或 key，`travel-mcp` 会使用 fallback 工具数据启动。

## 创建 Agent Runtime Secret

创建或重建 `agent-runtime-secrets` 时要包含已有的数据库、LLM、认证、邮箱和 RabbitMQ 配置。不要只 apply 单个 key，否则会覆盖并删除其他 key。

```bash
kubectl create secret generic agent-runtime-secrets \
  -n travel-agent-cloud \
  --from-literal=DATABASE_URL='postgresql://travel_agent:postgres-password@postgres:5432/travel_agent_cloud' \
  --from-literal=LLM_PROVIDER='openai_compatible' \
  --from-literal=LLM_API_KEY='your-llm-api-key' \
  --from-literal=LLM_BASE_URL='https://api.deepseek.com' \
  --from-literal=LLM_MODEL='deepseek-v4-flash' \
  --from-literal=MESSAGE_QUEUE_URL='amqp://travel_agent:change-me-to-a-strong-password@rabbitmq:5672/' \
  --from-literal=REDIS_URL='redis://redis:6379/0' \
  --from-literal=REDIS_KEY_PREFIX='travel-agent-cloud' \
  --from-literal=AUTH_SECRET_KEY='change-me-to-a-long-random-secret' \
  --from-literal=INTERNAL_SERVICE_TOKEN='change-me-to-a-long-random-internal-service-token' \
  --from-literal=AUTH_TOKEN_TTL_SECONDS='604800' \
  --from-literal=AUTH_COOKIE_SECURE='false' \
  --from-literal=AUTH_RATE_LIMIT_MAX_ATTEMPTS='20' \
  --from-literal=AUTH_RATE_LIMIT_WINDOW_SECONDS='900' \
  --from-literal=EMAIL_PROVIDER='mock' \
  --from-literal=EMAIL_FROM='no-reply@travel-agent-cloud.local' \
  --from-literal=PUBLIC_APP_URL='http://your-server-public-ip' \
  --from-literal=GITHUB_OAUTH_CLIENT_ID='your-github-oauth-client-id' \
  --from-literal=GITHUB_OAUTH_CLIENT_SECRET='your-github-oauth-client-secret' \
  --from-literal=GITHUB_OAUTH_REDIRECT_URI='http://your-server-public-ip/api/v1/auth/oauth/github/callback' \
  --dry-run=client -o yaml | kubectl apply -f -
```

`AUTH_COOKIE_SECURE='true'` 只应在 HTTPS 配好后启用。纯 HTTP 下浏览器不会发送 Secure cookie。

## 邮箱配置

真实邮箱验证和找回密码需要把 mock 邮箱配置替换为 SMTP。

QQ 邮箱通常使用 465 端口 SSL 和 SMTP 授权码：

```bash
  --from-literal=EMAIL_PROVIDER='smtp' \
  --from-literal=EMAIL_FROM='your-address@qq.com' \
  --from-literal=SMTP_HOST='smtp.qq.com' \
  --from-literal=SMTP_PORT='465' \
  --from-literal=SMTP_USERNAME='your-address@qq.com' \
  --from-literal=SMTP_PASSWORD='your-qq-smtp-authorization-code' \
  --from-literal=SMTP_USE_SSL='true' \
  --from-literal=SMTP_STARTTLS='false' \
  --from-literal=PUBLIC_APP_URL='http://your-server-public-ip'
```

Gmail 通常使用 587 端口 STARTTLS 和 Google app password：

```bash
  --from-literal=EMAIL_PROVIDER='smtp' \
  --from-literal=EMAIL_FROM='your-address@gmail.com' \
  --from-literal=SMTP_HOST='smtp.gmail.com' \
  --from-literal=SMTP_PORT='587' \
  --from-literal=SMTP_USERNAME='your-address@gmail.com' \
  --from-literal=SMTP_PASSWORD='your-google-app-password' \
  --from-literal=SMTP_USE_SSL='false' \
  --from-literal=SMTP_STARTTLS='true' \
  --from-literal=PUBLIC_APP_URL='https://your-domain.example'
```

## 常用检查

```bash
kubectl apply -k deploy/k8s
kubectl get pods -n travel-agent-cloud
kubectl get pods -n travel-agent-cloud -l app=travel-agent-worker
kubectl get pods -n travel-agent-cloud -l app=travel-gateway
kubectl get pods -n travel-agent-cloud -l app=travel-auth
kubectl get pods -n travel-agent-cloud -l app=travel-trip
kubectl get pods -n travel-agent-cloud -l app=travel-agent
kubectl get pods -n travel-agent-cloud -l app=travel-mcp
```

`travel-agent-worker` 使用和 `travel-agent` 相同的镜像，并运行：

```bash
python -m app.worker_main
```

它消费 RabbitMQ 中的 `agent.conversation.summarize.requested` 事件。RabbitMQ 或 PostgreSQL 尚未就绪时，worker 会按指数退避重连。
