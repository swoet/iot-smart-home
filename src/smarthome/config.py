from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Config:
    temp_high: float = 25.0
    light_dark: float = 30.0
    motion_light_on_seconds: int = 120

    tick_temp: float = 2.0
    tick_light: float = 3.0
    tick_motion: float = 1.0


def load_config(path: Optional[str | Path] = None) -> Config:
    cfg = Config()
    p: Optional[Path]
    if path is not None:
        p = Path(path)
    else:
        # Look for config.yaml in project root by default
        p = Path(__file__).resolve().parents[2] / "config.yaml"

    if p and p.exists():
        data = yaml.safe_load(p.read_text()) or {}
        for field in (f.name for f in dataclass_fields(Config)):
            if field in data:
                setattr(cfg, field, data[field])
    return cfg


def dataclass_fields(cls):
    # Local helper to avoid importing dataclasses.fields at module import time for speed
    from dataclasses import fields

    return fields(cls)
