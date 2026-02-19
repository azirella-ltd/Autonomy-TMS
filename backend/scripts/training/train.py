import os
import time
import yaml
import torch
import logging
from pathlib import Path
from datetime import datetime
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm

from app.models.gnn.temporal_gnn import SupplyChainTemporalGNN
from .monitor import TrainingMonitor
from .utils import setup_logging, save_checkpoint, load_checkpoint

class Trainer:
    def __init__(self, config_path="scripts/training/config/default.yaml"):
        self.config = self._load_config(config_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.setup_directories()
        self.setup_logging()
        self.model = self._init_model()
        self.optimizer = self._init_optimizer()
        self.scheduler = self._init_scheduler()
        self.writer = SummaryWriter(log_dir=str(self.log_dir))
        self.monitor = TrainingMonitor()
        
    def _load_config(self, config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
            
    def setup_directories(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path("logs") / f"train_{timestamp}"
        self.ckpt_dir = Path("checkpoints") / f"train_{timestamp}"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_dir / "training.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _init_model(self):
        model = SupplyChainTemporalGNN(**self.config['model'])
        if torch.cuda.device_count() > 1:
            model = torch.nn.DataParallel(model)
        return model.to(self.device)
        
    def _init_optimizer(self):
        return torch.optim.Adam(
            self.model.parameters(),
            lr=self.config['training']['learning_rate']
        )
        
    def _init_scheduler(self):
        return torch.optim.lr_scheduler.StepLR(
            self.optimizer,
            step_size=self.config['training']['lr_step_size'],
            gamma=self.config['training']['lr_gamma']
        )
        
    def train_epoch(self, train_loader):
        self.model.train()
        total_loss = 0.0
        
        pbar = tqdm(train_loader, desc="Training")
        for batch_idx, batch in enumerate(pbar):
            if isinstance(batch, dict):
                batch = {k: v.to(self.device) if torch.is_tensor(v) else v 
                        for k, v in batch.items()}
            else:
                batch = batch.to(self.device)
            
            self.optimizer.zero_grad()
            outputs = self.model(batch)
            loss = outputs['loss']
            
            loss.backward()
            self.optimizer.step()
            
            total_loss += loss.item()
            pbar.set_postfix(loss=loss.item())
            
            # Log metrics every 10 batches
            if batch_idx % 10 == 0:
                gpu_stats = self.monitor.get_gpu_stats()
                self.monitor.log_metrics(
                    epoch=self.current_epoch,
                    step=batch_idx,
                    loss=loss.item(),
                    gpu_stats=gpu_stats
                )
                
                # Log to tensorboard
                self.writer.add_scalar('Loss/train_batch', loss.item(), 
                                     self.current_epoch * len(train_loader) + batch_idx)
                
                if gpu_stats:
                    self.writer.add_scalar('GPU/memory_used', gpu_stats.get('memory.used', 0),
                                         self.current_epoch * len(train_loader) + batch_idx)
                    self.writer.add_scalar('GPU/utilization', gpu_stats.get('utilization.gpu', 0),
                                         self.current_epoch * len(train_loader) + batch_idx)
            
        return total_loss / len(train_loader)
        
    def validate(self, val_loader):
        self.model.eval()
        total_loss = 0.0
        
        with torch.no_grad():
            for batch in tqdm(val_loader, desc="Validating"):
                if isinstance(batch, dict):
                    batch = {k: v.to(self.device) if torch.is_tensor(v) else v 
                            for k, v in batch.items()}
                else:
                    batch = batch.to(self.device)
                    
                outputs = self.model(batch)
                total_loss += outputs['loss'].item()
                
        return total_loss / len(val_loader)
        
    def train(self, train_loader, val_loader=None, epochs=100):
        best_val_loss = float('inf')
        
        for epoch in range(epochs):
            self.current_epoch = epoch
            self.logger.info(f"Epoch {epoch+1}/{epochs}")
            
            # Train for one epoch
            train_loss = self.train_epoch(train_loader)
            self.writer.add_scalar('Loss/train', train_loss, epoch)
            
            # Validate
            val_loss = None
            if val_loader:
                val_loss = self.validate(val_loader)
                self.writer.add_scalar('Loss/val', val_loss, epoch)
                
                # Save best model
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    save_checkpoint({
                        'epoch': epoch,
                        'model_state_dict': self.model.state_dict(),
                        'optimizer_state_dict': self.optimizer.state_dict(),
                        'val_loss': val_loss,
                    }, self.ckpt_dir / 'best_model.pth', is_best=True)
            
            # Log metrics
            self.logger.info(f"Train Loss: {train_loss:.4f}" + 
                           (f" | Val Loss: {val_loss:.4f}" if val_loss else ""))
            
            # Step scheduler
            if self.scheduler:
                self.scheduler.step()
                
            # Save checkpoint
            if (epoch + 1) % self.config['training'].get('save_interval', 5) == 0:
                save_checkpoint({
                    'epoch': epoch,
                    'model_state_dict': self.model.state_dict(),
                    'optimizer_state_dict': self.optimizer.state_dict(),
                    'val_loss': val_loss if val_loss else train_loss,
                }, self.ckpt_dir / f'checkpoint_epoch{epoch+1}.pth')
                
        # Save final model
        save_checkpoint({
            'epoch': epochs,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'val_loss': val_loss if val_loss else train_loss,
        }, self.ckpt_dir / 'final_model.pth')
        
        self.writer.close()
        return best_val_loss if val_loss is not None else train_loss
