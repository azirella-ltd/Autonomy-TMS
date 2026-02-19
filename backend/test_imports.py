#!/usr/bin/env python3
"""Test script to verify all imports are working correctly."""

print("Testing imports...")

try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    
    import torch_geometric
    print(f"PyTorch Geometric version: {torch_geometric.__version__}")
    
    from app.data.basic_dataset import BasicSupplyChainDataset
    print("Successfully imported BasicSupplyChainDataset")
    
    # Test creating a dataset instance
    print("Creating dataset...")
    dataset = BasicSupplyChainDataset()
    print(f"Created dataset with {len(dataset)} samples")
    
    # Test getting a sample
    sample = dataset[0]
    print(f"Sample features shape: {sample['x'].shape}")
    print(f"Sample targets shape: {sample['y'].shape}")
    print(f"Edge index shape: {sample['edge_index'].shape}")
    
    print("\nAll imports and basic functionality are working!")
    
except Exception as e:
    print(f"\nError: {e}")
    print("\nPlease make sure you have activated the virtual environment")
    print("and installed all required dependencies.")
    raise
