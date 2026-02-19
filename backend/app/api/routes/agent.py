from typing import Dict, List

import numpy as np
import torch
from fastapi import APIRouter, HTTPException, Depends

from app.rl.config import NODES, NODE_INDEX, NODE_FEATURES, SimulationParams
from app.rl.policy import SimpleTemporalHead, select_action, indices_to_units
from app.svc.model_registry import load_temporal_gnn
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/agent", tags=["agent"])

# Cache for the loaded model
_model_cache = {}

def get_model():
    """Get or load the model with caching."""
    if not _model_cache:
        try:
            model, head, in_dim = load_temporal_gnn()
            _model_cache.update({
                'model': model,
                'head': head,
                'in_dim': in_dim
            })
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load model: {str(e)}"
            )
    return _model_cache

@router.post("/suggest-orders")
async def suggest_orders(
    payload: Dict,
    current_user: User = Depends(get_current_user)
):
    """
    Suggest order quantities for all nodes based on the current game state.
    
    Payload must include a window of observations per node:
    {
      "window": [
        { 
          "retailer": {"inventory": 10, "backlog": 0, ...}, 
          "wholesaler": {...}, 
          "distributor": {...}, 
          "manufacturer": {...} 
        },
        ...  # window_size time steps
      ]
    }
    
    Each feature dict must contain the same keys used in NODE_FEATURES.
    """
    window = payload.get("window")
    if not window or not isinstance(window, list):
        raise HTTPException(status_code=400, detail="window must be a non-empty list")

    # Get model and required input dimensions
    try:
        cache = get_model()
        model = cache['model']
        head = cache['head']
        expected_in_dim = cache['in_dim']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model loading error: {str(e)}")
    
    # Build input tensor [1, T, N, F]
    try:
        W = len(window)
        N = len(NODES)
        F = expected_in_dim
        
        # Default parameters for feature assembly
        params = SimulationParams()
        
        # Initialize feature array
        X = np.zeros((1, W, N, F), dtype=np.float32)
        
        # Fill in features for each time step and node
        for t, frame in enumerate(window):
            for role in NODES:
                if role not in frame:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Missing role '{role}' in time step {t}"
                    )
                
                # Get node features
                node_data = frame[role]
                
                # Assemble features in the expected order
                feats = [
                    float(node_data.get("inventory", 0)),
                    float(node_data.get("backlog", 0)),
                    float(node_data.get("incoming_orders", 0)),
                    float(node_data.get("incoming_shipments", 0)),
                    float(node_data.get("on_order", 0)),
                    *[1.0 if role == r else 0.0 for r in NODES],  # one-hot role
                    float(params.order_leadtime),
                    float(params.supply_leadtime),
                ]
                
                # Ensure correct feature dimension
                if len(feats) != F:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Expected {F} features, got {len(feats)}. "
                               "Check NODE_FEATURES in config.py"
                    )
                
                X[0, t, NODE_INDEX[role]] = np.array(feats, dtype=np.float32)
                
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing features: {str(e)}")
    
    # Run inference
    with torch.no_grad():
        try:
            device = next(model.parameters()).device
            x = torch.from_numpy(X).float().to(device)
            
            # Get node embeddings
            h = model(x)           # [1, W, N, H]
            h_cur = h[:, -1]       # [1, N, H] - use last time step
            
            # Get action logits
            logits = head(h_cur)   # [1, N, A]
            
            # Select actions (greedy)
            indices = select_action(logits, epsilon=0.0)  # [1, N]
            
            # Convert to order quantities
            orders = indices_to_units(indices.cpu().numpy())[0].tolist()
            
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"Inference error: {str(e)}"
            )
    
    # Return order suggestions
    return {
        role: {
            "order_quantity": int(orders[NODE_INDEX[role]]),
            "action_index": int(indices[0, NODE_INDEX[role]].item())
        }
        for role in NODES
    }
