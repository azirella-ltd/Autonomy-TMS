import time
import psutil
import torch
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any

class TrainingMonitor:
    """
    Monitors training progress and system resources.
    """
    def __init__(self, log_dir: str = "logs/monitoring"):
        """
        Initialize the training monitor.
        
        Args:
            log_dir: Directory to save monitoring logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self._write_header()
        
    def _write_header(self) -> None:
        """Write CSV header to the log file."""
        with open(self.log_file, 'w') as f:
            f.write("timestamp,epoch,step,loss,gpu_mem_used,"
                   "gpu_mem_total,gpu_util,cpu_util,ram_used,ram_total\n")
            
    def log_metrics(self, epoch: int, step: int, loss: float, 
                   gpu_stats: Optional[Dict[str, Any]] = None) -> None:
        """
        Log training metrics and system stats.
        
        Args:
            epoch: Current epoch number
            step: Current step (batch) number
            loss: Current loss value
            gpu_stats: Dictionary containing GPU statistics
        """
        timestamp = datetime.now().isoformat()
        
        # Get system metrics
        cpu_percent = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        
        # Get GPU metrics if available
        gpu_mem_used = gpu_mem_total = gpu_util = 0
        if torch.cuda.is_available() and gpu_stats is not None:
            gpu_mem_used = gpu_stats.get('memory.used', 0)
            gpu_mem_total = gpu_stats.get('memory.total', 0)
            gpu_util = gpu_stats.get('utilization.gpu', 0)
            
        # Write to log file
        with open(self.log_file, 'a') as f:
            f.write(f"{timestamp},{epoch},{step},{loss:.4f},"
                   f"{gpu_mem_used},{gpu_mem_total},{gpu_util},"
                   f"{cpu_percent},{ram.used},{ram.total}\n")
    
    @staticmethod
    def get_gpu_stats() -> Optional[Dict[str, Any]]:
        """
        Get GPU statistics if available.
        
        Returns:
            Dictionary containing GPU statistics or None if not available
        """
        if not torch.cuda.is_available():
            return None
            
        stats = {}
        try:
            # Get basic GPU info
            for i in range(torch.cuda.device_count()):
                device = torch.cuda.get_device_properties(i)
                stats[f'cuda:{i}.name'] = device.name
                stats[f'cuda:{i}.memory.total'] = device.total_memory
                
            # Get memory and utilization stats
            torch.cuda.synchronize()
            stats['memory.used'] = torch.cuda.memory_allocated()
            stats['memory.free'] = torch.cuda.memory_reserved() - stats['memory.used']
            
            # Try to get utilization if available (PyTorch 1.7+)
            if hasattr(torch.cuda, 'utilization'):
                stats['utilization.gpu'] = torch.cuda.utilization()
            else:
                # Fallback to nvidia-smi or other methods if needed
                stats['utilization.gpu'] = 0  # Default to 0 if not available
                
        except Exception as e:
            print(f"Error getting GPU stats: {e}")
            return None
            
        return stats
    
    def plot_metrics(self, output_file: str = None) -> None:
        """
        Plot training metrics from the log file.
        
        Args:
            output_file: Path to save the plot. If None, displays the plot.
        """
        try:
            import pandas as pd
            import matplotlib.pyplot as plt
            
            # Read log file
            df = pd.read_csv(self.log_file)
            
            # Create figure with subplots
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12))
            
            # Plot loss
            ax1.plot(df['step'], df['loss'], label='Training Loss')
            ax1.set_title('Training Loss')
            ax1.set_xlabel('Step')
            ax1.set_ylabel('Loss')
            ax1.legend()
            
            # Plot GPU memory
            if 'gpu_mem_used' in df.columns and 'gpu_mem_total' in df.columns:
                ax2.plot(df['step'], df['gpu_mem_used']/1e9, label='Used')
                ax2.axhline(y=df['gpu_mem_total'].iloc[0]/1e9, color='r', linestyle='--', label='Total')
                ax2.set_title('GPU Memory Usage')
                ax2.set_xlabel('Step')
                ax2.set_ylabel('Memory (GB)')
                ax2.legend()
            
            # Plot CPU and GPU utilization
            if 'gpu_util' in df.columns:
                ax3.plot(df['step'], df['gpu_util'], label='GPU')
            if 'cpu_util' in df.columns:
                ax3.plot(df['step'], df['cpu_util'], label='CPU')
            
            ax3.set_title('Utilization')
            ax3.set_xlabel('Step')
            ax3.set_ylabel('Utilization (%)')
            ax3.legend()
            
            plt.tight_layout()
            
            if output_file:
                plt.savefig(output_file)
                print(f"Plot saved to {output_file}")
            else:
                plt.show()
                
        except ImportError:
            print("Plotting requires pandas and matplotlib. Install with: pip install pandas matplotlib")
        except Exception as e:
            print(f"Error plotting metrics: {e}")
