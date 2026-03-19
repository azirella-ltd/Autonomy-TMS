"""
Checkpoint Storage Service — SOC II Compliant Model Lifecycle Management

Provides tenant-scoped checkpoint save/load/delete operations with:
- Tenant isolation: paths always include /{tenant_id}/{config_id}/
- Registry: every checkpoint tracked in model_checkpoints table
- CASCADE cleanup: tenant/config deletion auto-removes DB records;
  storage cleanup triggered via post-delete hook
- Integrity verification: SHA-256 hash on save, verified on load
- Version management: monotonic versioning per (config, model_type, site)

Storage backends:
- filesystem (default): checkpoints/{tenant_id}/{config_id}/...
- s3 (future): s3://bucket/{tenant_id}/{config_id}/...
- postgresql (small models): BYTEA in model_checkpoints.data column

Usage:
    service = CheckpointStorageService(db, tenant_id=3, config_id=22)
    path = await service.save_checkpoint(
        model_type="trm_atp_executor",
        site_key="CDC_WEST",
        state_dict=model.state_dict(),
        metadata={"loss": 0.15, "phase": "phase1_bc"},
    )
    state_dict = await service.load_checkpoint(
        model_type="trm_atp_executor",
        site_key="CDC_WEST",
    )
    await service.delete_config_checkpoints(config_id=22)
"""

import hashlib
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_checkpoint import ModelCheckpoint, TrainingDataset

logger = logging.getLogger(__name__)

# Base directory for checkpoint files (inside container: /app/checkpoints)
_CHECKPOINTS_ROOT = Path(os.environ.get("CHECKPOINT_DIR", "/app/checkpoints"))


def _tenant_config_dir(tenant_id: int, config_id: int) -> Path:
    """Return the tenant-scoped checkpoint directory.

    Pattern: checkpoints/{tenant_id}/{config_id}/
    SOC II: tenant_id in path ensures physical file isolation.
    """
    d = _CHECKPOINTS_ROOT / str(tenant_id) / str(config_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _model_subdir(base: Path, model_type: str, site_key: Optional[str] = None) -> Path:
    """Return the model-specific subdirectory.

    Pattern: {base}/trm/ or {base}/site_tgnn/{site_key}/
    """
    if model_type.startswith("trm_"):
        d = base / "trm"
    elif model_type == "site_tgnn":
        d = base / "site_tgnn" / (site_key or "default")
    elif model_type == "lgbm_forecast":
        d = base / "lgbm"
    else:
        d = base
    d.mkdir(parents=True, exist_ok=True)
    return d


def _compute_hash(data: bytes) -> str:
    """SHA-256 hash for integrity verification."""
    return hashlib.sha256(data).hexdigest()


class CheckpointStorageService:
    """Tenant-scoped checkpoint storage with DB registry and file management."""

    def __init__(self, db: AsyncSession, tenant_id: int, config_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id
        self.base_dir = _tenant_config_dir(tenant_id, config_id)

    async def save_checkpoint(
        self,
        model_type: str,
        state_dict: Any,
        site_key: Optional[str] = None,
        metadata: Optional[Dict] = None,
        model_class: Optional[str] = None,
        parameter_count: Optional[int] = None,
        training_phase: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> str:
        """Save a model checkpoint to disk and register in DB.

        Returns the file path.
        """
        import torch

        # Determine next version
        next_version = await self._next_version(model_type, site_key)

        # Build file path
        subdir = _model_subdir(self.base_dir, model_type, site_key)
        if site_key:
            filename = f"{model_type}_site{site_key}_v{next_version}.pt"
        else:
            filename = f"{model_type}_v{next_version}.pt"
        file_path = subdir / filename

        # Build checkpoint payload
        payload = {
            "model_state_dict": state_dict,
            "model_type": model_type,
            "site_key": site_key,
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "version": next_version,
            "saved_at": datetime.utcnow().isoformat(),
        }
        if metadata:
            payload.update(metadata)

        # Save to disk
        torch.save(payload, file_path)
        file_bytes = file_path.stat().st_size
        file_hash = _compute_hash(file_path.read_bytes())

        # Deactivate previous active checkpoint for this model+site
        await self.db.execute(
            update(ModelCheckpoint).where(
                and_(
                    ModelCheckpoint.config_id == self.config_id,
                    ModelCheckpoint.model_type == model_type,
                    ModelCheckpoint.site_key == site_key,
                    ModelCheckpoint.is_active == True,
                )
            ).values(is_active=False)
        )

        # Register in DB
        record = ModelCheckpoint(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            model_type=model_type,
            site_key=site_key,
            version=next_version,
            storage_backend="filesystem",
            file_path=str(file_path),
            file_size_bytes=file_bytes,
            file_hash=file_hash,
            model_class=model_class,
            parameter_count=parameter_count,
            training_phase=training_phase,
            training_metadata=metadata,
            is_active=True,
            is_best=False,
            created_by=created_by,
        )
        self.db.add(record)
        await self.db.flush()

        logger.info(
            "Saved checkpoint: %s (tenant=%d, config=%d, v%d, %d bytes, hash=%s)",
            file_path, self.tenant_id, self.config_id, next_version,
            file_bytes, file_hash[:12],
        )
        return str(file_path)

    async def load_checkpoint(
        self,
        model_type: str,
        site_key: Optional[str] = None,
        version: Optional[int] = None,
        verify_hash: bool = True,
    ) -> Optional[Dict]:
        """Load the active (or specific version) checkpoint.

        Returns the full checkpoint dict (including model_state_dict).
        Returns None if no checkpoint exists.
        """
        import torch

        # Find the checkpoint record
        query = select(ModelCheckpoint).where(
            and_(
                ModelCheckpoint.config_id == self.config_id,
                ModelCheckpoint.model_type == model_type,
                ModelCheckpoint.site_key == site_key,
            )
        )
        if version:
            query = query.where(ModelCheckpoint.version == version)
        else:
            query = query.where(ModelCheckpoint.is_active == True)
        query = query.order_by(desc(ModelCheckpoint.version)).limit(1)

        result = await self.db.execute(query)
        record = result.scalar_one_or_none()
        if not record:
            return None

        file_path = Path(record.file_path)
        if not file_path.exists():
            logger.warning("Checkpoint file missing: %s (DB record %d)", file_path, record.id)
            return None

        # Verify integrity
        if verify_hash and record.file_hash:
            actual_hash = _compute_hash(file_path.read_bytes())
            if actual_hash != record.file_hash:
                logger.error(
                    "Checkpoint integrity check FAILED: %s expected=%s actual=%s",
                    file_path, record.file_hash[:12], actual_hash[:12],
                )
                return None

        checkpoint = torch.load(file_path, map_location="cpu")
        return checkpoint

    async def list_checkpoints(
        self,
        model_type: Optional[str] = None,
        active_only: bool = False,
    ) -> List[Dict]:
        """List checkpoints for this config (optionally filtered)."""
        query = select(ModelCheckpoint).where(
            ModelCheckpoint.config_id == self.config_id,
        )
        if model_type:
            query = query.where(ModelCheckpoint.model_type == model_type)
        if active_only:
            query = query.where(ModelCheckpoint.is_active == True)
        query = query.order_by(ModelCheckpoint.model_type, desc(ModelCheckpoint.version))

        result = await self.db.execute(query)
        return [
            {
                "id": r.id,
                "model_type": r.model_type,
                "site_key": r.site_key,
                "version": r.version,
                "is_active": r.is_active,
                "file_size_bytes": r.file_size_bytes,
                "training_phase": r.training_phase,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in result.scalars().all()
        ]

    async def delete_config_checkpoints(self, config_id: Optional[int] = None):
        """Delete all checkpoints for a config (DB records + files).

        Called by ProvisioningService.delete_config().
        DB records are auto-deleted by CASCADE, but files must be removed explicitly.
        """
        target_config = config_id or self.config_id
        config_dir = _tenant_config_dir(self.tenant_id, target_config)
        if config_dir.exists():
            shutil.rmtree(config_dir, ignore_errors=True)
            logger.info("Deleted checkpoint dir: %s", config_dir)

    async def delete_tenant_checkpoints(self):
        """Delete ALL checkpoints for the entire tenant (DB records + files).

        Called when a tenant is deleted. DB records are auto-deleted by CASCADE.
        """
        tenant_dir = _CHECKPOINTS_ROOT / str(self.tenant_id)
        if tenant_dir.exists():
            shutil.rmtree(tenant_dir, ignore_errors=True)
            logger.info("Deleted all checkpoints for tenant %d: %s", self.tenant_id, tenant_dir)

    async def _next_version(self, model_type: str, site_key: Optional[str]) -> int:
        """Get the next version number for this model+site combo."""
        result = await self.db.execute(
            select(ModelCheckpoint.version).where(
                and_(
                    ModelCheckpoint.config_id == self.config_id,
                    ModelCheckpoint.model_type == model_type,
                    ModelCheckpoint.site_key == site_key,
                )
            ).order_by(desc(ModelCheckpoint.version)).limit(1)
        )
        current = result.scalar_one_or_none()
        return (current or 0) + 1


# ── Public API for checkpoint directory resolution ───────────────────────────
# All code that needs checkpoint paths MUST use this function.
# No legacy config_{id} paths — tenant isolation is mandatory (SOC II).

def checkpoint_dir(tenant_id: int, config_id: int) -> Path:
    """Return the tenant-scoped checkpoint directory.

    Path: checkpoints/{tenant_id}/{config_id}/

    ALL checkpoint code must use this function. No exceptions.
    SOC II: tenant_id in path ensures physical file isolation.
    """
    return _tenant_config_dir(tenant_id, config_id)


def cleanup_orphaned_checkpoint_dirs(existing_config_ids: set, existing_tenant_ids: set) -> List[str]:
    """Remove checkpoint directories for deleted configs/tenants."""
    cleaned = []
    if not _CHECKPOINTS_ROOT.exists():
        return cleaned

    for entry in _CHECKPOINTS_ROOT.iterdir():
        if entry.is_dir():
            if entry.name.isdigit():
                tid = int(entry.name)
                if tid not in existing_tenant_ids:
                    shutil.rmtree(entry, ignore_errors=True)
                    cleaned.append(str(entry))
                else:
                    for sub in entry.iterdir():
                        if sub.is_dir() and sub.name.isdigit():
                            cfg_id = int(sub.name)
                            if cfg_id not in existing_config_ids:
                                shutil.rmtree(sub, ignore_errors=True)
                                cleaned.append(str(sub))
            # Nuke any legacy config_{id} dirs
            elif entry.name.startswith("config_"):
                shutil.rmtree(entry, ignore_errors=True)
                cleaned.append(str(entry))

    return cleaned
