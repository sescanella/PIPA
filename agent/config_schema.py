"""Modelo Pydantic para validar config.json (§10.1 de v1-spec.md)."""

import json
import re
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field, field_validator


class ActiveHours(BaseModel):
    start: str = "07:00"
    end: str = "22:00"

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"Formato invalido: {v}. Usar HH:MM")
        h, m = map(int, v.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(f"Hora fuera de rango: {v}")
        return v


class AgentConfig(BaseModel):
    name: str = "PIPA"
    timezone: str = "America/Santiago"
    active_hours: ActiveHours = Field(default_factory=ActiveHours)
    heartbeat_interval_minutes: int = 30


class GmailConfig(BaseModel):
    account: str  # Requerido, sin default
    whitelist: List[str]  # Requerido, al menos 1 email

    @field_validator("whitelist")
    @classmethod
    def whitelist_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("whitelist no puede estar vacia")
        return v


class SkillConfig(BaseModel):
    enabled: bool = True
    model: str = "haiku"
    max_turns: int = 10
    timeout_seconds: int = 300


class OwnerConfig(BaseModel):
    email: str  # Requerido: correo del dueno para alertas
    alert_consecutive_failures: int = 3
    alert_cooldown_hours: int = 24

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(f"Email invalido: {v}")
        return v


class PIPAConfig(BaseModel):
    model_config = {"populate_by_name": True, "extra": "forbid"}

    version: str = "1.0"
    agent: AgentConfig = Field(default_factory=AgentConfig)
    gmail: GmailConfig  # Requerido
    owner: OwnerConfig  # Requerido (§12.3)
    skills: Dict[str, SkillConfig] = {}
    email_signature: str = "-- Procesado automaticamente por PIPA v1"


def load_config(path: str = "config.json") -> PIPAConfig:
    """Carga y valida config.json. Lanza ValidationError si es invalido."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return PIPAConfig(**raw)


def get_project_root() -> Path:
    """Retorna la raiz del proyecto PIPA (directorio padre de agent/)."""
    return Path(__file__).resolve().parent.parent
