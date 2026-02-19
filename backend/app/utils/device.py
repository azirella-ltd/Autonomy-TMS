"""
Device management utilities for PyTorch models.
Handles automatic device selection, data movement, and GPU memory management.
"""
import os
import torch
import contextlib
from typing import Union, Dict, Any, Optional, TypeVar, Type, Callable, Tuple, List, cast

# Type variable for generic type hints
T = TypeVar('T')

# Environment variable to force CPU usage
FORCE_CPU = os.environ.get('FORCE_CPU', '0').lower() in ('1', 'true', 'yes')

# Global device variable
DEVICE = torch.device('cpu')

# Initialize device on import
if not FORCE_CPU:
    if torch.cuda.is_available():
        DEVICE = torch.device('cuda')
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        DEVICE = torch.device('mps')

# Context manager for device operations
@contextlib.contextmanager
def device_scope(device: Union[str, torch.device]):
    """Context manager for setting the default device temporarily."""
    global DEVICE
    old_device = DEVICE
    DEVICE = torch.device(device) if isinstance(device, str) else device
    try:
        yield
    finally:
        DEVICE = old_device

def get_available_device(device_preference: Optional[Union[str, torch.device]] = None) -> torch.device:
    """
    Get the best available device based on availability and preferences.
    
    Args:
        device_preference: Preferred device ('cuda', 'mps', 'cpu' or None for auto-detect)
        
    Returns:
        torch.device: The selected device
    """
    if FORCE_CPU:
        return torch.device('cpu')
        
    if device_preference is not None:
        if isinstance(device_preference, torch.device):
            return device_preference
            
        device_preference = str(device_preference).lower()
        if device_preference == 'cuda' and torch.cuda.is_available():
            return torch.device('cuda')
        elif device_preference == 'mps' and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return torch.device('mps')
        return torch.device('cpu')
    
    return DEVICE

def to_device(
    data: T, 
    device: Optional[Union[str, torch.device]] = None,
    non_blocking: bool = False
) -> T:
    """
    Move data to the specified device. Handles tensors, dictionaries, lists, and other types.
    
    Args:
        data: Data to move (tensor, dict, list, or any other type)
        device: Target device (defaults to current device if None)
        non_blocking: If True and the data is in pinned memory, moves data asynchronously
        
    Returns:
        Data moved to the target device
    """
    if device is None:
        device = DEVICE
    elif isinstance(device, str):
        device = torch.device(device)
    
    if isinstance(data, torch.Tensor):
        return data.to(device, non_blocking=non_blocking)
    elif isinstance(data, (list, tuple)):
        return type(data)(to_device(x, device, non_blocking) for x in data)
    elif isinstance(data, dict):
        return {k: to_device(v, device, non_blocking) for k, v in data.items()}
    elif hasattr(data, 'to'):
        return data.to(device, non_blocking=non_blocking)
    return data

def set_device(device: Union[str, torch.device]) -> None:
    """
    Set the global device.
    
    Args:
        device: Device to set as global (string or torch.device)
    """
    global DEVICE
    DEVICE = get_available_device(device)

def get_device() -> torch.device:
    """
    Get the current global device.
    
    Returns:
        torch.device: The current global device
    """
    return DEVICE

def get_device_name() -> str:
    """
    Get a string representation of the current device.
    
    Returns:
        str: Device name (e.g., 'cuda:0', 'cpu', 'mps')
    """
    return str(DEVICE)

def is_cuda_available() -> bool:
    """Check if CUDA is available."""
    return torch.cuda.is_available() and not FORCE_CPU

def is_mps_available() -> bool:
    """Check if MPS (Metal Performance Shaders) is available."""
    return hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() and not FORCE_CPU

def empty_cache() -> None:
    """Empty CUDA cache if CUDA is available."""
    if torch.cuda.is_available() and not FORCE_CPU:
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

# For backward compatibility
device = get_device
