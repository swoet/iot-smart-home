from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Deque
import random
import time


@dataclass
class Device:
    id: str
    name: str
    kind: str  # 'sensor' or 'actuator'


@dataclass
class Sensor(Device):
    metric: str

    def read(self, env: Dict[str, Any]) -> Any:
        raise NotImplementedError


@dataclass
class TemperatureSensor(Sensor):
    metric: str = "temperature"

    def read(self, env: Dict[str, Any]) -> float:
        base = float(env.get("temp", 24.0))
        noise = random.uniform(-0.2, 0.2)
        return round(base + noise, 2)


@dataclass
class LightSensor(Sensor):
    metric: str = "light"

    def read(self, env: Dict[str, Any]) -> float:
        base = float(env.get("light", 40.0))
        noise = random.uniform(-2.0, 2.0)
        v = max(0.0, min(100.0, base + noise))
        return round(v, 1)


@dataclass
class MotionSensor(Sensor):
    metric: str = "motion"

    def read(self, env: Dict[str, Any]) -> bool:
        # motion spikes; probability is influenced by env 'motion_prob'
        p = float(env.get("motion_prob", 0.12))
        return random.random() < p


@dataclass
class Actuator(Device):
    state: Dict[str, Any] = field(default_factory=dict)

    def apply(self, changes: Dict[str, Any]) -> None:
        self.state.update(changes)
        self.state["ts"] = time.time()


@dataclass
class Fan(Actuator):
    # state: {"on": bool}
    pass


@dataclass
class LightBulb(Actuator):
    # state: {"on": bool}
    pass


@dataclass
class Thermostat(Actuator):
    # state: {"setpoint": float}
    pass


@dataclass
class Reading:
    ts: float
    room: str
    device_id: str
    name: str
    metric: str
    value: Any


@dataclass
class Room:
    id: str
    name: str
    env: Dict[str, Any]
    sensors: Dict[str, Sensor]
    actuators: Dict[str, Actuator]
    latest: Dict[str, Reading] = field(default_factory=dict)
    history: Dict[str, Deque[Reading]] = field(default_factory=dict)
    memory: Dict[str, Any] = field(
        default_factory=lambda: {"last_motion_ts": None, "light_on_until": 0.0}
    )
