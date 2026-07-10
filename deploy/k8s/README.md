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

`postgres.yaml` is part of the default kustomization. Create `postgres-secrets` before running automated deployment:

```bash
kubectl create secret generic postgres-secrets \
  -n travel-agent-cloud \
  --from-literal=POSTGRES_USER='travel_agent' \
  --from-literal=POSTGRES_PASSWORD='change-me' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Then add `DATABASE_URL` to `agent-runtime-secrets`. The normal deploy command will create/update PostgreSQL together with the application:

```bash
kubectl apply -k deploy/k8s
```

## Optional RabbitMQ And Worker Addons

RabbitMQ is the selected message queue, but it is not part of the default Kustomize deployment. The conversation summarizer worker is also an optional addon. This keeps the normal VPS deploy small and lets the API run even when the queue is not enabled.

Create credentials first:

```bash
kubectl create secret generic rabbitmq-secrets \
  -n travel-agent-cloud \
  --from-literal=RABBITMQ_DEFAULT_USER='travel_agent' \
  --from-literal=RABBITMQ_DEFAULT_PASS='change-me-to-a-strong-password' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Apply the addon when needed:

```bash
kubectl apply -f deploy/k8s/addons/rabbitmq.yaml
```

If the Agent Runtime needs to publish queue events, recreate `agent-runtime-secrets` with the existing database and LLM keys plus `MESSAGE_QUEUE_URL`. Do not apply a single-key Secret over the existing one, because that can remove the existing keys.

```bash
kubectl create secret generic agent-runtime-secrets \
  -n travel-agent-cloud \
  --from-literal=DATABASE_URL='postgresql://travel_agent:postgres-password@postgres:5432/travel_agent_cloud' \
  --from-literal=LLM_PROVIDER='openai_compatible' \
  --from-literal=LLM_API_KEY='your-llm-api-key' \
  --from-literal=LLM_BASE_URL='https://api.deepseek.com' \
  --from-literal=LLM_MODEL='deepseek-v4-flash' \
  --from-literal=MESSAGE_QUEUE_URL='amqp://travel_agent:change-me-to-a-strong-password@rabbitmq:5672/' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Restart the API deployment so it picks up `MESSAGE_QUEUE_URL`:

```bash
kubectl rollout restart deployment/agent-runtime -n travel-agent-cloud
```

Then start the optional worker:

```bash
kubectl apply -f deploy/k8s/addons/agent-runtime-worker.yaml
kubectl get pods -n travel-agent-cloud -l app=agent-runtime-worker
```

The worker uses the same Agent Runtime image and runs:

```bash
python -m app.worker_main
```

It consumes `agent.conversation.summarize.requested` events from RabbitMQ. Manual API summary requests are skipped by the worker because the HTTP request already generated the summary synchronously.
