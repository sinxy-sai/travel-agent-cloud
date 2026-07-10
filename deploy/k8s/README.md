# K3s Manifests

Apply the initial deployment:

```bash
kubectl apply -k deploy/k8s
```

Check status:

```bash
kubectl get pods -n travel-agent-cloud
kubectl get svc -n travel-agent-cloud
kubectl get ingress -n travel-agent-cloud
```

The default Ingress has no host rule. On a single VPS with K3s Traefik, it can be tested through the server public IP after images are published.

Deployment images:

```text
docker.io/sinxysai/travel-agent-cloud-frontend:latest
docker.io/sinxysai/travel-agent-cloud-agent-runtime:latest
```

The GHCR workflow is still kept for image publishing, but these K3s manifests pull from Docker Hub by default because it is usually easier for domestic VPS networking.

If your Docker Hub namespace is not `sinxysai`, update the image fields in:

- `agent-runtime.yaml`
- `frontend.yaml`

`postgres.yaml`, RabbitMQ, and `agent-runtime-worker` are part of the default kustomization. Create the required Secrets before running automated deployment.

Create `postgres-secrets`:

```bash
kubectl create secret generic postgres-secrets \
  -n travel-agent-cloud \
  --from-literal=POSTGRES_USER='travel_agent' \
  --from-literal=POSTGRES_PASSWORD='change-me' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Create `rabbitmq-secrets`:

```bash
kubectl create secret generic rabbitmq-secrets \
  -n travel-agent-cloud \
  --from-literal=RABBITMQ_DEFAULT_USER='travel_agent' \
  --from-literal=RABBITMQ_DEFAULT_PASS='change-me-to-a-strong-password' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Then create or recreate `agent-runtime-secrets` with the existing database and LLM keys plus `MESSAGE_QUEUE_URL`. Do not apply a single-key Secret over the existing one, because that can remove the existing keys.

```bash
kubectl create secret generic agent-runtime-secrets \
  -n travel-agent-cloud \
  --from-literal=DATABASE_URL='postgresql://travel_agent:postgres-password@postgres:5432/travel_agent_cloud' \
  --from-literal=LLM_PROVIDER='openai_compatible' \
  --from-literal=LLM_API_KEY='your-llm-api-key' \
  --from-literal=LLM_BASE_URL='https://api.deepseek.com' \
  --from-literal=LLM_MODEL='deepseek-v4-flash' \
  --from-literal=MESSAGE_QUEUE_URL='amqp://travel_agent:change-me-to-a-strong-password@rabbitmq:5672/' \
  --from-literal=AUTH_SECRET_KEY='change-me-to-a-long-random-secret' \
  --from-literal=AUTH_TOKEN_TTL_SECONDS='604800' \
  --from-literal=AUTH_COOKIE_SECURE='false' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Use `AUTH_COOKIE_SECURE='true'` only after HTTPS is configured. Plain HTTP browsers will not send Secure cookies.

The normal deploy command will create/update PostgreSQL, RabbitMQ, the API, worker, frontend, and ingress together:

```bash
kubectl apply -k deploy/k8s
kubectl get pods -n travel-agent-cloud
kubectl get pods -n travel-agent-cloud -l app=agent-runtime-worker
```

The worker uses the same Agent Runtime image and runs:

```bash
python -m app.worker_main
```

It consumes `agent.conversation.summarize.requested` events from RabbitMQ. Manual API summary requests are skipped by the worker because the HTTP request already generated the summary synchronously.
If RabbitMQ or PostgreSQL is not ready, the worker retries with exponential backoff. The default retry window starts at 2 seconds and caps at 30 seconds.
