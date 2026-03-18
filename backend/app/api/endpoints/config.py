from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Literal, Optional
import json
import os

from app.api.deps import get_current_user

router = APIRouter()

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "../../../data")
CONFIG_PATH = os.path.abspath(os.path.join(CONFIG_DIR, "system_config.json"))
LLM_SETTINGS_PATH = os.path.abspath(os.path.join(CONFIG_DIR, "llm_settings.json"))


class Range(BaseModel):
  min: float
  max: float


class SystemConfigModel(BaseModel):
  order_leadtime: Range = Field(default=Range(min=0, max=8))
  supply_leadtime: Range = Field(default=Range(min=0, max=8))
  init_inventory: Range = Field(default=Range(min=0, max=1000))
  holding_cost: Range = Field(default=Range(min=0, max=100))
  backlog_cost: Range = Field(default=Range(min=0, max=200))
  max_inbound_per_link: Range = Field(default=Range(min=10, max=2000))
  max_order: Range = Field(default=Range(min=10, max=2000))
  price: Range = Field(default=Range(min=0, max=10000))
  standard_cost: Range = Field(default=Range(min=0, max=10000))
  variable_cost: Range = Field(default=Range(min=0, max=10000))
  min_order_qty: Range = Field(default=Range(min=0, max=1000))
  max_rounds: Range = Field(default=Range(min=0, max=100))

  class Config:
    allow_population_by_field_name = True


def _ensure_dir():
  os.makedirs(CONFIG_DIR, exist_ok=True)


def _read_cfg() -> SystemConfigModel:
  try:
    if os.path.exists(CONFIG_PATH):
      with open(CONFIG_PATH, "r") as f:
        data = json.load(f)
        return SystemConfigModel(**data)
  except Exception:
    pass
  return SystemConfigModel()


@router.get("/config/system", response_model=SystemConfigModel)
def get_system_config():
  return _read_cfg()


@router.put("/config/system", response_model=SystemConfigModel)
def put_system_config(cfg: SystemConfigModel):
  try:
    _ensure_dir()
    with open(CONFIG_PATH, "w") as f:
      json.dump(cfg.model_dump(by_alias=False), f)
    return cfg
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Failed to save system config: {e}")


# ---------------------------------------------------------------------------
# LLM Settings — provider routing without restart
# ---------------------------------------------------------------------------

class LLMSettings(BaseModel):
  """Runtime LLM routing settings. Changes take effect immediately (no restart needed).

  briefing_provider:
    "claude"  — Use Anthropic Claude API (CLAUDE_API_KEY required). Best quality,
                recommended for executive briefings (~$0.05/briefing).
    "vllm"    — Use local vLLM on LLM_API_BASE. Free, but limited by hardware
                context window (set --max-model-len >= 8192 on the vLLM server).
    "auto"    — Use Claude if CLAUDE_API_KEY is set, otherwise fall back to vLLM.
  """
  briefing_provider: Literal["auto", "claude", "vllm"] = Field(
    default="auto",
    description="LLM provider for executive briefings",
  )
  skills_provider: Literal["auto", "claude", "vllm"] = Field(
    default="auto",
    description="LLM provider for TRM Skills exception handling",
  )


def read_llm_settings() -> LLMSettings:
  """Read LLM settings from file. Falls back to defaults if file missing."""
  try:
    if os.path.exists(LLM_SETTINGS_PATH):
      with open(LLM_SETTINGS_PATH, "r") as f:
        return LLMSettings(**json.load(f))
  except Exception:
    pass
  return LLMSettings()


@router.get("/config/llm", response_model=LLMSettings)
def get_llm_settings(_user=Depends(get_current_user)):
  """Get current LLM routing settings."""
  return read_llm_settings()


@router.put("/config/llm", response_model=LLMSettings)
def put_llm_settings(settings: LLMSettings, _user=Depends(get_current_user)):
  """Update LLM routing settings. Takes effect immediately — no restart required."""
  try:
    _ensure_dir()
    with open(LLM_SETTINGS_PATH, "w") as f:
      json.dump(settings.model_dump(), f, indent=2)
    return settings
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Failed to save LLM settings: {e}")
