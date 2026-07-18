# Security Policy

## Supported Versions

Travel Agent Cloud is currently developed as a single active product line. Security fixes are provided for the `main` branch and the latest Docker images published from `main`.

| Version | Supported |
| --- | --- |
| `main` | Yes |
| Latest Docker Hub images | Yes |
| Older commits or images | No |

## Reporting a Vulnerability

Please do not open a public GitHub issue for security vulnerabilities.

Use one of the following private channels:

- GitHub private vulnerability reporting, if enabled for this repository.
- A private GitHub Security Advisory draft shared with the maintainers.
- If private reporting is unavailable, contact the repository owner privately before publishing details.

When reporting a vulnerability, include as much detail as possible:

- Affected component, such as `frontend`, `services/auth`, `services/trip`, `services/agent`, `services/gateway`, `services/mcp`, `agent-runtime`, or `deploy/k8s`.
- Impact and severity estimate.
- Reproduction steps.
- Relevant request/response examples with secrets removed.
- Whether the issue affects local Docker Compose, VPS/K3s, or both.
- Suggested fix, if available.

## Response Process

The maintainers will triage reported vulnerabilities and decide whether they affect a supported version.

Expected process:

1. Confirm receipt and request missing details if needed.
2. Reproduce and assess impact.
3. Prepare a fix on a private branch or advisory when appropriate.
4. Release patched images and deployment manifests.
5. Publish disclosure notes after users have a reasonable chance to update.

For critical issues involving leaked secrets, account takeover, authentication bypass, arbitrary code execution, data exposure, or K3s deployment compromise, rotate affected credentials immediately.

## Security Scope

Security-sensitive areas include:

- Authentication, sessions, cookies, password reset, email verification, and OAuth flows in `services/auth`.
- User-owned trip plans, conversations, exports, and profile data.
- Internal service authentication using `INTERNAL_SERVICE_TOKEN`.
- LLM prompts, model outputs, LangGraph/LangChain tool calling, and agent tool permissions.
- FastMCP/Amap travel tool integrations and external HTTP calls.
- MinIO object storage, PostgreSQL data, RabbitMQ messages, and Redis state.
- K3s manifests, GitHub Actions deployment secrets, and VPS SSH access.

## Secrets and Sensitive Data

Never commit real secrets to this repository.

Do not commit:

- `.env` files.
- SSH private keys.
- LLM API keys.
- Amap API keys.
- SMTP passwords or authorization codes.
- OAuth client secrets.
- Database passwords.
- Kubernetes Secret manifests containing real values.

If a secret is committed or exposed, assume it is compromised. Revoke and rotate it before relying on any cleanup commit.

## Security Expectations

Contributors should follow these rules:

- Validate external input at API boundaries.
- Use ORM or parameterized queries for database access.
- Do not expose stack traces, raw exceptions, tokens, or internal URLs in user-facing responses.
- Treat LLM output as untrusted data. Validate structured model output before using it.
- Keep destructive or privileged tool actions behind explicit server-side checks.
- Keep CORS, cookies, and internal service tokens restrictive in production.
- Use Kubernetes Secrets for VPS/K3s production credentials.

## Deployment Notes

For VPS/K3s deployments:

- Keep `AUTH_SECRET_KEY` consistent across services that verify user tokens.
- Keep `INTERNAL_SERVICE_TOKEN` consistent across gateway, runtime, and internal services.
- Use HTTPS before enabling Secure cookies.
- Do not delete PostgreSQL, MinIO, RabbitMQ, or Redis PVC/PV unless intentionally clearing production data.
- Use `sudo k3s crictl rmi --prune` to clean unused images instead of deleting persistent volumes.

## Dependency Security

Before release, run the project checks that apply to the changed area:

```powershell
npm audit
python -m compileall agent-runtime\app services\agent\app services\auth\app services\gateway\app services\mcp\app services\trip\app
.\scripts\smoke-test.ps1 http://localhost:5173
```

Known vulnerable dependencies should be updated promptly when reachable in production.
