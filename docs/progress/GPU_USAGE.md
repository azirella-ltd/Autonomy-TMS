# GPU/CPU Support in The Beer Game

This document explains how to run The Beer Game with either GPU or CPU support.

## Prerequisites

### For GPU Support
1. NVIDIA Container Toolkit must be installed on the host machine
2. NVIDIA drivers must be properly installed
3. Docker must be configured to use NVIDIA runtime

## Quick Start

### Using GPU
```bash
# Start with GPU support (development mode)
make gpu-up-dev

# Or for production build
make gpu-up
```

### Using CPU (default)
```bash
# Start with CPU support (development mode)
make up-dev

# Or for production build
make up
```

## Environment Variables

### GPU Configuration
- `GPU_ENABLED`: Set to `true` to enable GPU support (default: `false`)
- `CUDA_VISIBLE_DEVICES`: Controls which GPUs are visible (default: `all`)
- `NVIDIA_VISIBLE_DEVICES`: Controls which GPUs are visible (default: `all`)
- `GPU_RUNTIME`: Set to `nvidia` to use NVIDIA runtime (auto-set by Makefile)

### Example: Using Specific GPUs
```bash
# Use only GPU 0
CUDA_VISIBLE_DEVICES=0 make gpu-up-dev

# Use multiple GPUs (0 and 1)
CUDA_VISIBLE_DEVICES=0,1 make gpu-up-dev
```

## Verifying GPU Support

After starting the application, check the logs to verify GPU support:

```bash
docker logs the_beer_game_backend | grep -i cuda
```

You should see output similar to:
```
[INFO] CUDA available: True
[INFO] CUDA device: NVIDIA GeForce RTX 3090
```

## Troubleshooting

### Common Issues

1. **NVIDIA Container Toolkit not installed**
   - Install the NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

2. **Insufficient permissions**
   - Ensure your user is in the `docker` group
   - Try running with `sudo` if necessary

3. **CUDA version mismatch**
   - The Dockerfile is configured for CUDA 11.3
   - Update the Dockerfile if you need a different CUDA version

4. **No GPUs available**
   - Check if NVIDIA drivers are properly installed with `nvidia-smi`
   - Verify Docker can access the GPUs with `docker run --gpus all nvidia/cuda:11.3.0-base nvidia-smi`

## Advanced Configuration

### Building with Specific CUDA Version
Edit the `Dockerfile` to change the CUDA version:

```dockerfile
# For CUDA 11.3 (default)
RUN if [ "$GPU_ENABLED" = "true" ]; then \
        apt-get install -y --no-install-recommends \
        cuda-toolkit-11.3 \
        libcudnn8=8.2.1.32-1+cuda11.3 \
        libcudnn8-dev=8.2.1.32-1+cuda11.3; \
    fi
```

### Customizing GPU Memory Limits
Add resource limits in `docker-compose.yml`:

```yaml
devices:
  - capabilities: [gpu]
    count: 1
    device_ids: ['0']
    driver: nvidia
    options:
      memory: 1024  # MB of GPU memory
```
