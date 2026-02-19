#!/bin/bash

# Set up environment
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Create necessary directories
mkdir -p data/processed logs checkpoints

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Virtual environment not found. Please run setup_training_env.sh first."
    exit 1
fi

# Check if CUDA is available
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Run the training script with GPU
python scripts/training/train_gnn.py \
    --source sim \
    --window 52 \
    --horizon 1 \
    --epochs 50 \
    --device cuda \
    --save-path checkpoints/temporal_gnn.pt

# Deactivate virtual environment
deactivate
