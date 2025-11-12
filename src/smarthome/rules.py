from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


class Rules:
    """
    Simple per-room rule configuration backed by YAML.

    Structure:
    rooms:
      living:
        temp_high: 25.0
        light_dark: 30.0
        motion_light_on_seconds: 120
    """

    def __init__(self, path: Path, defaults: Dict[str, Any]) -> None:
        self.path = Path(path)
        self.defaults = defaults
        self.data: Dict[str, Any] = {"rooms": {}}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            self.data = yaml.safe_load(self.path.read_text()) or {"rooms": {}}
        else:
            self.data = {"rooms": {}}

    def save(self, raw_yaml: str) -> None:
        # Validate before saving
        data = yaml.safe_load(raw_yaml) or {"rooms": {}}
        if not isinstance(data, dict) or "rooms" not in data:
            raise ValueError("rules yaml must contain a top-level 'rooms' mapping")
        self.path.write_text(yaml.safe_dump(data, sort_keys=True))
        self.data = data

    def get_room_cfg(self, room_id: str) -> Dict[str, Any]:
        room_cfg = dict(self.defaults)
        room_over = (self.data.get("rooms") or {}).get(room_id, {})
        room_cfg.update(room_over)
        return room_cfg
