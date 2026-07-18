# K3s 部署说明

本目录用于在 VPS 的 K3s 集群中部署 Travel Agent Cloud。当前默认部署包含业务微服务、基础设施服务和可观测性组件。

## 部署命令

```bash
kubectl apply -k deploy/k8s
```

检查状态：

```bash
kubectl get pods -n travel-agent-cloud
kubectl get deploy -n travel-agent-cloud
kubectl get svc -n travel-agent-cloud
kubectl get ingress -n travel-agent-cloud
```

## 默认部署内容

默认 Kustomize 会部署：

- PostgreSQL
- RabbitMQ
- Redis
- MinIO
- Prometheus
- Grafana
- Loki
- Promtail
- Tempo
- `travel-gateway`
- `travel-auth`
- `travel-trip`
- `travel-agent`
- `travel-agent-worker`
- `travel-mcp`
- `agent-runtime`
- `frontend`
- Ingress

业务服务默认开启 OpenTelemetry，并把 trace 发送到：

```text
http://tempo:4318
```

## 默认镜像

K3s 清单默认从 Docker Hub 拉取以下镜像：

```text
docker.io/sinxysai/travel-agent-cloud-frontend:latest
docker.io/sinxysai/travel-agent-cloud-agent-runtime:latest
docker.io/sinxysai/travel-agent-cloud-gateway:latest
docker.io/sinxysai/travel-agent-cloud-auth:latest
docker.io/sinxysai/travel-agent-cloud-trip:latest
docker.io/sinxysai/travel-agent-cloud-agent:latest
docker.io/sinxysai/travel-agent-cloud-mcp:latest
```

如果 Docker Hub 命名空间不是 `sinxysai`，需要修改：

- `agent-runtime.yaml`
- `gateway.yaml`
- `auth.yaml`
- `trip.yaml`
- `agent.yaml`
- `mcp.yaml`
- `frontend.yaml`

## Secret 边界

当前 K3s 部署按服务拆分 Secret：

| Secret | 用途 |
| --- | --- |
| `postgres-secrets` | PostgreSQL root/user 密码 |
| `rabbitmq-secrets` | RabbitMQ 用户名和密码 |
| `minio-secrets` | MinIO root 用户名和密码 |
| `travel-gateway-secrets` | Gateway 内部服务 token |
| `travel-auth-secrets` | 用户认证、邮箱、OAuth、auth 数据库连接 |
| `travel-trip-secrets` | 行程服务数据库连接和用户 token 校验 |
| `travel-agent-secrets` | 会话服务数据库连接和 RabbitMQ 连接 |
| `agent-runtime-secrets` | LLM、Agent Runtime 内部 token 和用户 token 校验 |
| `travel-mcp-secrets` | 高德 Web Service key |
| `observability-secrets` | Grafana 管理员密码 |

以下值必须在相关 Secret 中保持一致：

- `AUTH_SECRET_KEY`：`travel-auth-secrets`、`travel-trip-secrets`、`travel-agent-secrets`、`agent-runtime-secrets`
- `INTERNAL_SERVICE_TOKEN`：`travel-gateway-secrets`、`travel-auth-secrets`、`travel-trip-secrets`、`travel-agent-secrets`、`agent-runtime-secrets`
- `DATABASE_URL`：`travel-auth-secrets`、`travel-trip-secrets`、`travel-agent-secrets`
- `MESSAGE_QUEUE_URL`：`travel-agent-secrets`

不要只 apply 单个 key 到已有 Secret，否则会覆盖并删除该 Secret 的其他 key。更新 Secret 时应使用完整 key 集合。

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

## 创建 Gateway Secret

```bash
kubectl create secret generic travel-gateway-secrets \
  -n travel-agent-cloud \
  --from-literal=INTERNAL_SERVICE_TOKEN='same-internal-service-token' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 创建 Auth Secret

```bash
kubectl create secret generic travel-auth-secrets \
  -n travel-agent-cloud \
  --from-literal=DATABASE_URL='postgresql://travel_agent:postgres-password@postgres:5432/travel_agent_cloud' \
  --from-literal=AUTH_SECRET_KEY='same-auth-secret-key' \
  --from-literal=INTERNAL_SERVICE_TOKEN='same-internal-service-token' \
  --from-literal=AUTH_TOKEN_TTL_SECONDS='604800' \
  --from-literal=AUTH_COOKIE_SECURE='false' \
  --from-literal=AUTH_RATE_LIMIT_MAX_ATTEMPTS='20' \
  --from-literal=AUTH_RATE_LIMIT_WINDOW_SECONDS='900' \
  --from-literal=EMAIL_PROVIDER='mock' \
  --from-literal=EMAIL_FROM='no-reply@travel-agent-cloud.local' \
  --from-literal=SMTP_HOST='' \
  --from-literal=SMTP_PORT='587' \
  --from-literal=SMTP_USERNAME='' \
  --from-literal=SMTP_PASSWORD='' \
  --from-literal=SMTP_USE_SSL='false' \
  --from-literal=SMTP_STARTTLS='true' \
  --from-literal=PUBLIC_APP_URL='http://your-server-public-ip' \
  --from-literal=GITHUB_OAUTH_CLIENT_ID='' \
  --from-literal=GITHUB_OAUTH_CLIENT_SECRET='' \
  --from-literal=GITHUB_OAUTH_REDIRECT_URI='http://your-server-public-ip/api/v1/auth/oauth/github/callback' \
  --from-literal=OAUTH_HTTP_TIMEOUT_SECONDS='10' \
  --from-literal=EMAIL_VERIFICATION_TOKEN_TTL_SECONDS='86400' \
  --from-literal=PASSWORD_RESET_TOKEN_TTL_SECONDS='1800' \
  --dry-run=client -o yaml | kubectl apply -f -
```

`AUTH_COOKIE_SECURE='true'` 只应在 HTTPS 配好后启用。纯 HTTP 下浏览器不会发送 Secure cookie。

## 创建 Trip Secret

```bash
kubectl create secret generic travel-trip-secrets \
  -n travel-agent-cloud \
  --from-literal=DATABASE_URL='postgresql://travel_agent:postgres-password@postgres:5432/travel_agent_cloud' \
  --from-literal=AUTH_SECRET_KEY='same-auth-secret-key' \
  --from-literal=INTERNAL_SERVICE_TOKEN='same-internal-service-token' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 创建 Agent Secret

```bash
kubectl create secret generic travel-agent-secrets \
  -n travel-agent-cloud \
  --from-literal=DATABASE_URL='postgresql://travel_agent:postgres-password@postgres:5432/travel_agent_cloud' \
  --from-literal=AUTH_SECRET_KEY='same-auth-secret-key' \
  --from-literal=INTERNAL_SERVICE_TOKEN='same-internal-service-token' \
  --from-literal=MESSAGE_QUEUE_URL='amqp://travel_agent:change-me-to-a-strong-password@rabbitmq:5672/' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 创建 Agent Runtime Secret

```bash
kubectl create secret generic agent-runtime-secrets \
  -n travel-agent-cloud \
  --from-literal=INTERNAL_SERVICE_TOKEN='same-internal-service-token' \
  --from-literal=AUTH_SECRET_KEY='same-auth-secret-key' \
  --from-literal=LLM_PROVIDER='openai_compatible' \
  --from-literal=LLM_API_KEY='your-llm-api-key' \
  --from-literal=LLM_BASE_URL='https://api.deepseek.com' \
  --from-literal=LLM_MODEL='deepseek-v4-flash' \
  --from-literal=LLM_TEMPERATURE='0.4' \
  --from-literal=LLM_MAX_TOKENS='1200' \
  --from-literal=LLM_TIMEOUT_SECONDS='30' \
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

## 创建 observability Secret

Grafana 管理员密码建议显式配置：

```bash
kubectl create secret generic observability-secrets \
  -n travel-agent-cloud \
  --from-literal=GRAFANA_ADMIN_PASSWORD='change-me-to-a-strong-password' \
  --dry-run=client -o yaml | kubectl apply -f -
```

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

## 可观测性访问

Grafana 默认在集群内暴露为 ClusterIP 服务：

```bash
kubectl port-forward -n travel-agent-cloud svc/grafana 3000:3000
```

Prometheus：

```bash
kubectl port-forward -n travel-agent-cloud svc/prometheus 9090:9090
```

Tempo：

```bash
kubectl port-forward -n travel-agent-cloud svc/tempo 3200:3200
```

Loki：

```bash
kubectl port-forward -n travel-agent-cloud svc/loki 3100:3100
```

Grafana 中会自动配置 Prometheus、Loki、Tempo 数据源，并自动加载 `Travel Agent Cloud Overview` 面板。

## 常用检查

```bash
kubectl get pods -n travel-agent-cloud
kubectl get deploy -n travel-agent-cloud
kubectl get svc -n travel-agent-cloud
kubectl get pods -n travel-agent-cloud -l app=travel-gateway
kubectl get pods -n travel-agent-cloud -l app=travel-auth
kubectl get pods -n travel-agent-cloud -l app=travel-trip
kubectl get pods -n travel-agent-cloud -l app=travel-agent
kubectl get pods -n travel-agent-cloud -l app=travel-mcp
kubectl get pods -n travel-agent-cloud -l app=agent-runtime
kubectl get pods -n travel-agent-cloud -l app=grafana
kubectl get pods -n travel-agent-cloud -l app=prometheus
kubectl get pods -n travel-agent-cloud -l app=loki
kubectl get pods -n travel-agent-cloud -l app=tempo
kubectl get pods -n travel-agent-cloud -l app=promtail
```

`travel-agent-worker` 使用和 `travel-agent` 相同的镜像，并运行：

```bash
python -m app.worker_main
```

它消费 RabbitMQ 中的 `agent.conversation.summarize.requested` 事件。RabbitMQ 或 PostgreSQL 尚未就绪时，worker 会按指数退避重连。
