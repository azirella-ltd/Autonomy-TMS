#!/bin/bash
set -e
echo "==> Installing NVIDIA Container Toolkit..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update -qq
sudo apt-get install -y nvidia-container-toolkit

echo "==> Configuring Docker NVIDIA runtime..."
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

echo "==> Done. Testing GPU access..."
docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
echo "==> NVIDIA Docker runtime is working."
