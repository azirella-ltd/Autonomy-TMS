"""Configuration module for training."""

import os
from pathlib import Path
import yaml
from typing import Dict, Any

class Config:
    """Configuration class for training."""
    
    def __init__(self, config_dict: Dict[str, Any]):
        """Initialize configuration from dictionary."""
        for key, value in config_dict.items():
            if isinstance(value, dict):
                value = Config(value)
            setattr(self, key, value)
    
    def __getattr__(self, name):
        """Return None for non-existent attributes."""
        return None

def load_config(config_path: str) -> Config:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    return Config(config_dict)

def get_config(env: str = 'local') -> Config:
    """Get configuration for the specified environment."""
    config_dir = Path(__file__).parent
    base_config = load_config(config_dir / 'base.yaml')
    
    env_config_path = config_dir / f'{env}.yaml'
    if env_config_path.exists():
        env_config = load_config(env_config_path)
        # Merge with base config
        for key, value in vars(env_config).items():
            setattr(base_config, key, value)
    
    return base_config
