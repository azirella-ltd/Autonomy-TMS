import os
from typing import Tuple

import torch

from app.rl.policy import SimpleTemporalHead

# Import the TinyBackbone from the training script
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'training'))

try:
    from train_gnn import TinyBackbone
except ImportError:
    # Fallback if running from a different directory
    class TinyBackbone(torch.nn.Module):
        def __init__(self, in_dim: int, hidden_dim: int = 64):
            super().__init__()
            self.net = torch.nn.Sequential(
                torch.nn.LayerNorm(in_dim),
                torch.nn.Linear(in_dim, hidden_dim),
                torch.nn.ReLU(),
                torch.nn.Linear(hidden_dim, hidden_dim),
            )
        def forward(self, x):
            B, T, N, F = x.shape
            x = x.reshape(B * T * N, F)
            h = self.net(x)
            return h.reshape(B, T, N, -1)

def load_temporal_gnn(path: str = "artifacts/temporal_gnn.pt") -> Tuple[torch.nn.Module, torch.nn.Module, int]:
    """
    Load a trained temporal GNN model and its head.
    
    Args:
        path: Path to the saved model checkpoint
        
    Returns:
        model: The loaded backbone model
        head: The loaded policy head
        in_dim: Input feature dimension
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model not found at {path}. Please train a model first.")
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(path, map_location=device)
    
    # Get model dimensions from checkpoint or use defaults
    in_dim = ckpt.get('in_dim', 13)  # Default to 13 features if not in checkpoint
    hidden_dim = ckpt.get('hidden_dim', 64)
    
    # Initialize model and head
    model = TinyBackbone(in_dim=in_dim, hidden_dim=hidden_dim).to(device)
    head = SimpleTemporalHead(hidden_dim=hidden_dim).to(device)
    
    # Load state dicts
    model.load_state_dict(ckpt['backbone_state_dict'])
    head.load_state_dict(ckpt['head_state_dict'])
    
    model.eval()
    head.eval()
    
    return model, head, in_dim
