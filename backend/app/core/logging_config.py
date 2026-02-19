"""Logging configuration for the application."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging(name: str = None) -> logging.Logger:
    """Set up logging configuration.
    
    Args:
        name: Name of the logger. If None, creates a root logger.
        
    Returns:
        Configured logger instance.
    """
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create formatters
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create handlers
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    
    # Create a file handler that rotates log files
    log_file = log_dir / "app.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(file_formatter)
    
    # Get the logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Add handlers if they haven't been added before
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    
    # Prevent logging from propagating to the root logger
    logger.propagate = False
    
    return logger
