# 可观测性方案

本项目先采用轻量可观测性方案：FastAPI 服务暴露 Prometheus 指标，Prometheus 负责抓取和存储，Grafana 负责查询和看板。暂不默认引入 ELK、Jaeger、Consul 或 Traefik 扩展组件，避免在 4 核 4G VPS 上过早增加资源压力。

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

Prometheus 和 Grafana 在 K3s 中均设置了较低的资源 requests/limits，并把 Prometheus 数据保留期限制为 7 天。当前目标是满足开发、演示、小规模生产排障，而不是大规模长期指标存储。

## 后续演进

建议按以下顺序继续：

1. 增加 Grafana JSON dashboard，覆盖错误率、P95 延迟、请求量、上游健康状态。
2. 引入 OpenTelemetry SDK，把请求链路 trace id 贯穿 gateway、领域服务和 agent-runtime。
3. 在轻量 VPS 上优先考虑 Loki + Promtail 做日志聚合；除非确实需要全文检索和复杂日志分析，否则不建议上 ELK。
4. 如需分布式追踪，优先考虑 Tempo 或 Jaeger 二选一，不要同时引入。
5. 如果后续服务数量明显增加，再评估服务发现、服务网格、gRPC 或专用 API Gateway。
