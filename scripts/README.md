# 脚本目录

本目录存放本地测试、服务器初始化和 smoke test 脚本。

## Ubuntu 服务器初始化

在新的 Ubuntu VPS 上执行：

```bash
bash scripts/bootstrap-ubuntu.sh
```

脚本会执行系统更新、安装常用工具，并通过国内镜像安装指定版本 K3s。

核心步骤包括：

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl wget git vim unzip htop net-tools ca-certificates gnupg lsb-release
curl -sfL https://rancher-mirror.rancher.cn/k3s/k3s-install.sh | INSTALL_K3S_MIRROR=cn INSTALL_K3S_VERSION=v1.36.2+k3s1 sh -
sudo kubectl get nodes
```

## Smoke Test

本地或 VPS 部署完成后可以运行：

```powershell
.\scripts\smoke-test.ps1 http://localhost:5173
```

如果直接测试 Agent Runtime：

```powershell
.\scripts\smoke-test.ps1 http://localhost:8000
```
