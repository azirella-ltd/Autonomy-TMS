#!/bin/bash

set -euo pipefail

# Create and activate virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    # Prefer python3 explicitly to avoid 'python' not found
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv venv
    else
        echo "python3 not found. Please install Python 3 (e.g., apt install python3-full)." >&2
        exit 1
    fi

    # Activate the venv
    source venv/bin/activate

    # Upgrade pip and build tooling inside the venv
    python -m pip install --upgrade pip setuptools wheel

    # Install PyTorch with CUDA 12.1 support (compatible with your CUDA 12.2)
    echo "Installing PyTorch with CUDA 12.1 support..."
    python -m pip install torch==2.1.0+cu121 torchvision==0.16.0+cu121 torchaudio==2.1.0+cu121 --index-url https://download.pytorch.org/whl/cu121

    # Install PyTorch Geometric and its dependencies
    echo "Installing PyTorch Geometric dependencies with CUDA support..."
    python -m pip install pyg-lib torch-scatter torch-sparse -f https://data.pyg.org/whl/torch-2.1.0+cu121.html
    python -m pip install torch-geometric

    # Install other requirements
    echo "Installing other requirements..."
    python -m pip install -r scripts/requirements-train.txt

    echo "Environment setup complete!"
    echo "Activate the virtual environment with: source venv/bin/activate"
else
    echo "Virtual environment already exists. Activate it with: source venv/bin/activate"
fi
