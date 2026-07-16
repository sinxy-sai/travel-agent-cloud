# travel-common

`travel-common` 是后端微服务共享 Python 包。它只承载跨服务基础设施能力，不承载旅行规划、认证、行程或 Agent 业务逻辑。

## 当前能力

- `travel_common.proxy.check_upstream`：统一检查 upstream 健康状态。
- `travel_common.proxy.proxy_request`：统一代理 HTTP 请求，并过滤不适合转发的 hop-by-hop 响应头。
- `travel_common.proxy.forward_headers`：保留必要请求头，并补充 `x-forwarded-for`、`x-real-ip`、`x-forwarded-proto` 和服务边界标记。
- `travel_common.app.allowed_origins_from_env`：统一解析 `ALLOWED_ORIGINS`。
- `travel_common.app.add_cors`：统一给 FastAPI 服务挂载 CORS 中间件。

## 使用方式

各服务通过 `requirements.txt` 以 editable 方式安装：

```text
-e ../common
```

Docker 构建时以 `services` 为 build context，因此可以同时访问当前服务目录和 `common` 目录。

## 放入 common 的判断标准

- 可以被多个服务复用。
- 不依赖具体业务实体。
- 不让某个领域服务隐式依赖另一个领域服务。
- 修改后不会改变用户侧业务语义。
