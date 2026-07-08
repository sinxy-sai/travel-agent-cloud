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
