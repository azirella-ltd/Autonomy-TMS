import os
import yaml
import torch
import logging
import random
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple

def setup_logging(log_dir: str = "logs", log_level: int = logging.INFO, 
                log_file: str = "training.log") -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        log_dir: Directory to save log files
        log_level: Logging level (e.g., logging.INFO, logging.DEBUG)
        log_file: Name of the log file
        
    Returns:
        Configured logger instance
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Clear existing handlers to avoid duplicate logs
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler
    file_handler = logging.FileHandler(log_dir / log_file)
    file_handler.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def save_checkpoint(
    state: Dict[str, Any],
    filename: Union[str, Path],
    is_best: bool = False,
    max_keep: int = 5,
    checkpoint_dir: Optional[Union[str, Path]] = None
) -> None:
    """
    Save training checkpoint.
    
    Args:
        state: Dictionary containing model and optimizer state
        filename: Path to save the checkpoint
        is_best: Whether this is the best model so far
        max_keep: Maximum number of checkpoints to keep
        checkpoint_dir: Directory to save checkpoints (if filename is not a full path)
    """
    if checkpoint_dir is not None and not isinstance(filename, Path):
        filename = Path(checkpoint_dir) / filename
    
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    
    # Save the checkpoint
    torch.save(state, filename)
    logging.info(f"Checkpoint saved to {filename}")
    
    # If this is the best model, create a copy
    if is_best:
        best_path = filename.parent / 'model_best.pth'
        torch.save(state, best_path)
        logging.info(f"New best model saved to {best_path}")
    
    # Remove old checkpoints if we have too many
    if max_keep > 0:
        checkpoint_dir = filename.parent
        checkpoints = sorted(checkpoint_dir.glob('checkpoint_epoch*.pth'))
        
        # Keep only the most recent max_keep checkpoints
        if len(checkpoints) > max_keep:
            for old_checkpoint in checkpoints[:-max_keep]:
                try:
                    old_checkpoint.unlink()
                    logging.info(f"Removed old checkpoint: {old_checkpoint}")
                except Exception as e:
                    logging.warning(f"Failed to remove {old_checkpoint}: {e}")

def load_checkpoint(
    model: torch.nn.Module,
    checkpoint_path: Union[str, Path],
    optimizer: Optional[torch.optim.Optimizer] = None,
    map_location: Optional[Union[str, torch.device]] = None,
    strict: bool = True
) -> Dict[str, Any]:
    """
    Load model checkpoint.
    
    Args:
        model: Model to load the weights into
        checkpoint_path: Path to the checkpoint file
        optimizer: Optional optimizer to load state into
        map_location: Device to map the storage to
        strict: Whether to strictly enforce that the keys in checkpoint match
                the model's state dict
                
    Returns:
        Dictionary containing the loaded checkpoint
    """
    if not os.path.isfile(checkpoint_path):
        raise FileNotFoundError(f"No checkpoint found at {checkpoint_path}")
        
    logging.info(f"Loading checkpoint from {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location=map_location)
    
    # Handle DataParallel if needed
    if isinstance(model, torch.nn.DataParallel):
        model.module.load_state_dict(checkpoint['model_state_dict'], strict=strict)
    else:
        model.load_state_dict(checkpoint['model_state_dict'], strict=strict)
    
    # Load optimizer state if provided
    if optimizer is not None and 'optimizer_state_dict' in checkpoint:
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    
    # Log training state
    if 'epoch' in checkpoint:
        logging.info(f"Loaded checkpoint from epoch {checkpoint['epoch']}")
    if 'val_loss' in checkpoint:
        logging.info(f"Validation loss: {checkpoint['val_loss']:.4f}")
    
    return checkpoint

def load_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        Dictionary containing the configuration
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Set random seeds for reproducibility
    if 'seed' in config.get('training', {}):
        seed = config['training']['seed']
        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    
    return config

def get_device(device_id: int = 0) -> torch.device:
    """
    Get the appropriate device (GPU if available, else CPU).
    
    Args:
        device_id: ID of the GPU to use (if available)
        
    Returns:
        torch.device: The device to use for computation
    """
    if torch.cuda.is_available():
        device = torch.device(f'cuda:{device_id}')
        torch.cuda.set_device(device)
        logging.info(f'Using GPU: {torch.cuda.get_device_name(0)}')
    else:
        device = torch.device('cpu')
        logging.info('Using CPU')
    
    return device

def count_parameters(model: torch.nn.Module) -> Tuple[int, int]:
    """
    Count the number of trainable parameters in a model.
    
    Args:
        model: PyTorch model
        
    Returns:
        Tuple of (total_params, trainable_params)
    """
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return total_params, trainable_params
