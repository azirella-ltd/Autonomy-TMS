#!/bin/bash

# Set up environment
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Create necessary directories
mkdir -p data/processed logs_cpu checkpoints_cpu

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Virtual environment not found. Please run setup_training_env.sh first."
    exit 1
fi

# Run the training script (use simple training CLI)
python scripts/training/train_gnn.py \
    --source sim \
    --window 52 \
    --horizon 1 \
    --epochs 10 \
    --device cpu \
    --save-path checkpoints_cpu/temporal_gnn.pt

# Deactivate virtual environment
deactivate
