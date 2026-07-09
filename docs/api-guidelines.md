# API Guidelines

本项目默认采用 RESTful API 设计。业务资源接口严格遵守 RESTful 风格；Agent 推理、流式输出、工具调用等运行时能力允许少量动作式接口。

## Base Path

所有业务 API 使用版本前缀:

```text
/api/v1
```

示例:

```text
GET  /api/v1/conversations
POST /api/v1/trip-plans
```

## Resource Naming

资源名使用复数名词，不使用动词。

推荐:

```text
/conversations
/messages
/trip-plans
/users
/profiles
```

避免:

```text
/createTrip
/getConversation
/deleteMessage
```

## HTTP Methods

```text
GET     查询资源
POST    创建资源或提交一次处理请求
PATCH   部分更新资源
DELETE  删除资源
```

示例:

```text
GET    /api/v1/conversations
GET    /api/v1/conversations/{conversationId}
PATCH  /api/v1/conversations/{conversationId}
DELETE /api/v1/conversations/{conversationId}
GET    /api/v1/trip-plans
PATCH  /api/v1/trip-plans/{tripPlanId}
```

## Field Naming

HTTP JSON 请求和响应字段统一使用 camelCase。

```json
{
  "conversationId": "abc",
  "createdAt": "2026-07-08T10:00:00Z",
  "pageSize": 20
}
```

Python 内部可以使用 snake_case，但 API 边界必须输出 camelCase。

## Pagination

列表接口必须支持分页。

请求:

```text
GET /api/v1/conversations?page=1&pageSize=20
```

响应:

```json
{
  "data": [],
  "page": 1,
  "pageSize": 20,
  "totalItems": 0,
  "totalPages": 0
}
```

## Error Format

错误响应使用统一结构。

```json
{
  "error": {
    "code": "CONVERSATION_NOT_FOUND",
    "message": "Conversation not found",
    "details": {}
  }
}
```

状态码约定:

```text
400  请求格式错误
401  未认证
403  无权限
404  资源不存在
409  资源冲突
422  参数校验失败
500  服务端错误
```

## Time Format

时间字段统一使用 ISO 8601。

```text
2026-07-08T10:00:00Z
```

## RPC Boundary

RPC 只用于服务内部调用，不作为前端直接访问的接口形式。

- 前端访问 Gateway: REST
- Java 微服务之间: Spring Cloud OpenFeign
- Java 服务访问 Python Agent Runtime: REST
- 高性能流式场景: 预留 gRPC，不作为当前默认方案

## Message Queue Boundary

RabbitMQ 用于异步事件和后台任务，不替代同步 API。

适合:

```text
trip.plan.created
trip.plan.export.requested
agent.conversation.summarize.requested
user.profile.updated
```

不适合:

```text
用户点击按钮后必须立即返回的数据查询
需要强一致响应的同步写操作
包含密钥或大体积正文的数据传输
```

## Agent Runtime Exceptions

Agent Runtime 可以保留少量动作式接口，因为它们表达的是一次推理、一次工具调用或一次流式会话，而不是传统资源 CRUD。

允许:

```text
POST /api/v1/chat
POST /api/v1/tool-calls
GET  /api/v1/chat-stream
```

但持久化资源仍然使用 RESTful:

```text
GET    /api/v1/conversations
GET    /api/v1/conversations/{conversationId}
PATCH  /api/v1/conversations/{conversationId}
GET    /api/v1/trip-plans
PATCH  /api/v1/trip-plans/{tripPlanId}
DELETE /api/v1/trip-plans/{tripPlanId}
```

## Current API

当前已实现:

```text
GET    /health
GET    /api/v1/me/profile
PATCH  /api/v1/me/profile
POST   /api/v1/trip-plan
POST   /api/v1/chat
GET    /api/v1/conversations
GET    /api/v1/conversations/{conversationId}
PATCH  /api/v1/conversations/{conversationId}
DELETE /api/v1/conversations/{conversationId}
GET    /api/v1/trip-plans
GET    /api/v1/trip-plans/{tripPlanId}
PATCH  /api/v1/trip-plans/{tripPlanId}
DELETE /api/v1/trip-plans/{tripPlanId}
GET    /api/v1/trip-plans/{tripPlanId}/export
```

后续建议将旧接口:

```text
POST /api/v1/trip-plan
```

迁移为:

```text
POST /api/v1/trip-plans
```

旧接口可以保留一段时间作为兼容入口。
