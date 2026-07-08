#!/usr/bin/env bash
set -e

sudo apt update
sudo apt upgrade -y

sudo apt install -y curl wget git vim unzip htop net-tools ca-certificates gnupg lsb-release

sudo mkdir -p /etc/rancher/k3s
sudo tee /etc/rancher/k3s/registries.yaml >/dev/null <<'EOF'
mirrors:
  docker.io:
    endpoint:
      - "https://docker.m.daocloud.io"
      - "https://docker.1ms.run"
  registry.k8s.io:
    endpoint:
      - "https://k8s.m.daocloud.io"
  gcr.io:
    endpoint:
      - "https://gcr.m.daocloud.io"
  ghcr.io:
    endpoint:
      - "https://ghcr.m.daocloud.io"
  quay.io:
    endpoint:
      - "https://quay.m.daocloud.io"
EOF

curl -sfL https://rancher-mirror.rancher.cn/k3s/k3s-install.sh | INSTALL_K3S_MIRROR=cn INSTALL_K3S_VERSION=v1.36.2+k3s1 sh -

sudo kubectl get nodes
