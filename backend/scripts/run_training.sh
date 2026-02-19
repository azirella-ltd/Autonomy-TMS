#!/bin/bash

# Configuration
VENV_NAME="autonomy_env"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUIREMENTS_FILE="$PROJECT_DIR/scripts/requirements-server.txt"
TRAIN_SCRIPT="$PROJECT_DIR/scripts/train.py"
OUTPUT_DIR="$PROJECT_DIR/training_output"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Print configuration
echo "=== Configuration ==="
echo "Project directory: $PROJECT_DIR"
echo "Requirements file: $REQUIREMENTS_FILE"
echo "Training script: $TRAIN_SCRIPT"
echo "Output directory: $OUTPUT_DIR"

# Check for GPU
if command -v nvidia-smi &> /dev/null; then
    echo "=== GPU Information ==="
    nvidia-smi
    echo "======================"
    export CUDA_VISIBLE_DEVICES=0  # Use first GPU
    DEVICE="cuda"
else
    echo "No GPU detected, using CPU."
    DEVICE="cpu"
fi

# Create and activate virtual environment
echo "=== Setting up Python environment ==="
python3 -m venv "$VENV_NAME"
source "$VENV_NAME/bin/activate"

# Upgrade pip and install dependencies
echo "=== Installing dependencies ==="
pip install --upgrade pip
pip install -r "$REQUIREMENTS_FILE"

# Install PyTorch with CUDA support if GPU is available
if [ "$DEVICE" = "cuda" ]; then
    echo "Installing PyTorch with CUDA support..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    
    # Install PyTorch Geometric with CUDA support
    pip install pyg-lib torch-scatter torch-sparse -f https://data.pyg.org/whl/torch-2.0.0+cu118.html
    pip install torch-geometric
fi

# Run training
echo "=== Starting training ==="
cd "$PROJECT_DIR"
python "$TRAIN_SCRIPT" \
    --env prod \
    --log_dir "$OUTPUT_DIR" \
    --device "$DEVICE" \
    --batch_size 16 \
    --num_epochs 100 \
    --learning_rate 0.001

echo "=== Training complete ==="
echo "Output saved to: $OUTPUT_DIR"
