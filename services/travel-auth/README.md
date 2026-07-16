# travel-auth

`travel-auth` 是规划中的 Python/FastAPI 认证服务，目前还不是运行中的服务。认证能力当前仍在 `agent-runtime` 中。

## 未来职责

- 注册、登录、退出登录、邮箱验证、找回密码和 OAuth 回调。
- JWT 或 Session 签发与校验。
- 必要时使用 Redis 做登录限流和会话状态。
- 通过 RabbitMQ 发布用户生命周期事件。

## 迁移原则

- 保持现有 `agent-runtime` API 契约稳定。
- 通过 `travel-gateway` 按接口逐步迁移。
- 不让密码、会话逻辑在两个运行服务里长期重复存在。
