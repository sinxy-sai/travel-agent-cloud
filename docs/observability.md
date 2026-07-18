# 可观测性方案

本项目采用轻量可观测性方案：FastAPI 服务暴露 Prometheus 指标，Prometheus 负责抓取和存储，Loki/Promtail 负责日志聚合，Tempo 负责 OpenTelemetry trace 存储，Grafana 负责统一查询和看板。暂不默认引入 ELK、Jaeger、Consul 或额外 Traefik 扩展组件，避免在 4 核 4G VPS 上过早增加资源压力。

## 当前已接入的服务

以下服务均暴露 `/metrics`：

- `travel-gateway`
- `travel-auth`
- `travel-trip`
- `travel-agent`
- `travel-mcp`
- `agent-runtime`

核心指标：

- `travel_http_requests_total`：按服务、方法、路径、状态码统计请求量。
- `travel_http_request_duration_seconds`：按服务、方法、路径统计请求耗时直方图。
- `travel_http_requests_in_progress`：按服务、方法、路径统计进行中的请求数。

路径标签会优先使用 FastAPI 路由模板，例如 `/api/v1/trip-plans/{trip_plan_id}`。未命中路由模板时，会把数字和 UUID 风格路径段归一为 `{id}`，降低 Prometheus 高基数风险。

## 本地 Docker Compose 启动

```powershell
docker compose --profile worker --profile observability up -d --build
```

访问地址：

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

Grafana 本地默认账号：

- 用户名：`admin`
- 密码：`admin`

Prometheus 数据源会通过 `deploy/observability/grafana-datasources.yml` 自动配置。
Grafana 同时会自动配置三个数据源：

- Prometheus：指标。
- Loki：服务日志。
- Tempo：链路追踪。

Grafana 会自动加载 `Travel Agent Cloud Overview` 面板，覆盖：

- 在线 scrape target 数量。
- 服务请求速率。
- 全局和服务级 5xx 错误率。
- 服务 P50/P95 HTTP 延迟。
- 服务进行中请求数。

Prometheus 会自动加载 `deploy/observability/alert-rules.yml`，当前规则包括：

- `TravelServiceTargetDown`：服务指标抓取失败。
- `TravelServiceHighErrorRate`：服务 5xx 错误率超过 5%。
- `TravelServiceHighLatencyP95`：服务 P95 延迟超过 2 秒。
- `TravelServiceNoTraffic`：服务长时间没有请求流量。

### 查看日志

本地启动 observability profile 后，Promtail 会通过 Docker socket 发现容器并把日志推送到 Loki：

```powershell
docker compose --profile worker --profile observability up -d --build
```

进入 Grafana 的 Explore 页面，选择 `Loki` 数据源，可以使用：

```logql
{service="travel-gateway"}
```

或：

```logql
{container="gateway"}
```

K3s 中 Promtail 以 DaemonSet 运行，从 `/var/log/pods` 采集 pod 日志。常用查询：

```logql
{namespace="travel-agent-cloud", app="travel-gateway"}
```

### 打开链路追踪

OpenTelemetry 代码已接入所有 FastAPI 服务，但默认关闭。需要追踪时，推荐使用 Compose override 启动：

```powershell
docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile worker --profile observability up -d --build
```

也可以在相关服务 `.env` 中手动启用：

```env
OTEL_ENABLED=true
OTEL_SERVICE_NAMESPACE=travel-agent-cloud
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318
```

然后重建服务：

```powershell
docker compose --profile worker --profile observability up -d --build
```

进入 Grafana Explore，选择 `Tempo` 数据源即可查询 trace。当前已自动埋点：

- FastAPI 入站请求。
- `httpx` 出站 HTTP 请求。

K3s 中需要对业务服务显式打开 OTEL 环境变量，例如：

```bash
kubectl set env deployment/travel-gateway -n travel-agent-cloud \
  OTEL_ENABLED=true \
  OTEL_SERVICE_NAMESPACE=travel-agent-cloud \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318
```

其他服务同理：`travel-auth`、`travel-trip`、`travel-agent`、`travel-mcp`、`agent-runtime`。

后续可以继续补充业务 span，例如 `trip_context`、`attraction_agent`、`weather_agent`、`hotel_agent`、`planner_agent` 等 LangGraph 节点级 span。

## K3s 启动

监控清单是可选 addon，不包含在默认 `deploy/k8s/kustomization.yaml` 中。需要在 VPS 上开启时执行：

```bash
kubectl create secret generic observability-secrets \
  -n travel-agent-cloud \
  --from-literal=GRAFANA_ADMIN_PASSWORD='change-me-to-a-strong-password' \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f deploy/k8s/addons/observability.yaml
```

K3s addon 会加载同样的 Prometheus 抓取配置、告警规则和 Grafana Overview 面板。

本地访问 K3s 中的 Grafana：

```bash
kubectl port-forward -n travel-agent-cloud svc/grafana 3000:3000
```

本地访问 K3s 中的 Prometheus：

```bash
kubectl port-forward -n travel-agent-cloud svc/prometheus 9090:9090
```

## 资源策略

Prometheus、Grafana、Loki 和 Tempo 在 K3s 中均设置了较低的资源 requests/limits。Prometheus、Loki 默认保留 7 天数据，Tempo 默认保留 24 小时 trace。当前目标是满足开发、演示、小规模生产排障，而不是大规模长期指标、日志、trace 存储。

## 后续演进

建议按以下顺序继续：

1. 增加服务级 SLO 面板，例如 gateway 成功率、Agent 生成耗时、异步 job 失败率。
2. 为 LangGraph 节点增加业务 span，把 Agent 内部执行步骤展示到 Tempo。
3. 把 request id、trace id、user id 摘要写入结构化 JSON 日志，提升 Loki 查询体验。
4. 为 Prometheus 告警接入 Alertmanager、邮件或 Webhook。
5. 如果后续服务数量明显增加，再评估服务发现、服务网格、gRPC 或专用 API Gateway。当前 K3s DNS 已足够，不需要 Consul。
