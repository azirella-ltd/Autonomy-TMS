from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict
import json
import os

router = APIRouter()

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "../../../data")
CONFIG_PATH = os.path.abspath(os.path.join(CONFIG_DIR, "system_config.json"))


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
