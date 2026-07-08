# Scripts

## Ubuntu Server Bootstrap

在新 Ubuntu 服务器上执行：

```bash
bash scripts/bootstrap-ubuntu.sh
```

脚本会执行：

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl wget git vim unzip htop net-tools ca-certificates gnupg lsb-release
curl -sfL https://rancher-mirror.rancher.cn/k3s/k3s-install.sh | INSTALL_K3S_MIRROR=cn INSTALL_K3S_VERSION=v1.36.2+k3s1 sh -
sudo kubectl get nodes
```
