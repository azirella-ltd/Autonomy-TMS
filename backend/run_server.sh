#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Set Python path
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Run the FastAPI server with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
