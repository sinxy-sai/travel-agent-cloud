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

Images:

```text
ghcr.io/sinxy-sai/travel-agent-cloud-frontend:latest
ghcr.io/sinxy-sai/travel-agent-cloud-agent-runtime:latest
```

If the GHCR packages are private, create an image pull secret or make the packages public before applying these manifests.
