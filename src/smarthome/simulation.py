from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from .config import Config, load_config
from .models import Fan, LightBulb, MotionSensor, Sensor, TemperatureSensor, LightSensor, Thermostat, Room, Reading, HumiditySensor, SmartPlug
from .storage import EventStore
from .rules import Rules
from . import __version__


class Broadcaster:
    def __init__(self) -> None:
        self._listeners: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def add_listener(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._listeners.append(q)
        return q

    async def remove_listener(self, q: asyncio.Queue) -> None:
        async with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)

    async def publish(self, event: Dict[str, Any]) -> None:
        async with self._lock:
            for q in self._listeners:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass


class Simulation:
    def __init__(self, cfg: Optional[Config] = None, store: Optional[EventStore] = None, rules: Optional[Rules] = None) -> None:
        self.cfg = cfg or load_config(None)
        self.broadcaster = Broadcaster()
        self.store = store
        self.rules = rules
        self._tasks: List[asyncio.Task] = []

        # Rooms with independent environments
        self.rooms: Dict[str, Room] = {
            "living": Room(
                id="living",
                name="Living Room",
                env={"temp": 24.0, "light": 40.0, "motion_prob": 0.12},
                sensors={
                    "temp": TemperatureSensor(id="temp", name="Temperature", kind="sensor", metric="temperature"),
                    "light": LightSensor(id="light", name="Light", kind="sensor", metric="light"),
                    "motion": MotionSensor(id="motion", name="Motion", kind="sensor", metric="motion"),
                },
                actuators={
                    "fan": Fan(id="fan", name="Fan", kind="actuator", state={"on": False, "ts": time.time()}),
                    "lightbulb": LightBulb(id="lightbulb", name="Lightbulb", kind="actuator", state={"on": False, "ts": time.time()}),
                    "thermostat": Thermostat(id="thermostat", name="Thermostat", kind="actuator", state={"setpoint": 24.0, "ts": time.time()}),
                },
            ),
            "bedroom": Room(
                id="bedroom",
                name="Bedroom",
                env={"temp": 23.0, "light": 35.0, "motion_prob": 0.08},
                sensors={
                    "temp": TemperatureSensor(id="temp", name="Temperature", kind="sensor", metric="temperature"),
                    "light": LightSensor(id="light", name="Light", kind="sensor", metric="light"),
                    "motion": MotionSensor(id="motion", name="Motion", kind="sensor", metric="motion"),
                },
                actuators={
                    "fan": Fan(id="fan", name="Fan", kind="actuator", state={"on": False, "ts": time.time()}),
                    "lightbulb": LightBulb(id="lightbulb", name="Lightbulb", kind="actuator", state={"on": False, "ts": time.time()}),
                    "thermostat": Thermostat(id="thermostat", name="Thermostat", kind="actuator", state={"setpoint": 23.5, "ts": time.time()}),
                },
            ),
            "kitchen": Room(
                id="kitchen",
                name="Kitchen",
                env={"temp": 24.5, "light": 38.0, "motion_prob": 0.10, "humidity": 50.0},
                sensors={
                    "temp": TemperatureSensor(id="temp", name="Temperature", kind="sensor", metric="temperature"),
                    "light": LightSensor(id="light", name="Light", kind="sensor", metric="light"),
                    "motion": MotionSensor(id="motion", name="Motion", kind="sensor", metric="motion"),
                    "humidity": HumiditySensor(id="humidity", name="Humidity", kind="sensor", metric="humidity"),
                },
                actuators={
                    "lightbulb": LightBulb(id="lightbulb", name="Lightbulb", kind="actuator", state={"on": False, "ts": time.time()}),
                    "plug": SmartPlug(id="plug", name="Smart Plug", kind="actuator", state={"on": False, "ts": time.time()}),
                },
            ),
        }
        # Initialize histories
        for room in self.rooms.values():
            room.history = {sid: deque(maxlen=600) for sid in room.sensors.keys()}

    # Public API
    def get_state(self) -> Dict[str, Any]:
        return {
            "version": __version__,
            "rooms": {
                rid: {
                    "name": room.name,
                    "sensors": {
                        sid: {
                            "name": room.sensors[sid].name,
                            "metric": room.sensors[sid].metric,
                            "reading": None
                            if sid not in room.latest
                            else {"value": room.latest[sid].value, "ts": room.latest[sid].ts},
                        }
                        for sid in room.sensors
                    },
                    "actuators": {
                        aid: {"name": room.actuators[aid].name, "state": room.actuators[aid].state}
                        for aid in room.actuators
                    },
                }
                for rid, room in self.rooms.items()
            },
        }

    def command_actuator(self, room_id: str, actuator_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        if room_id not in self.rooms:
            raise KeyError(f"unknown room {room_id}")
        room = self.rooms[room_id]
        if actuator_id not in room.actuators:
            raise KeyError(f"unknown actuator {actuator_id}")
        actuator = room.actuators[actuator_id]
        actuator.apply(changes)
        event = {
            "type": "actuator",
            "room": room_id,
            "device_id": actuator_id,
            "name": actuator.name,
            "metric": list(changes.keys())[0],
            "value": list(changes.values())[0],
            "ts": actuator.state.get("ts", time.time()),
        }
        asyncio.create_task(self.broadcaster.publish(event))
        if self.store:
            asyncio.create_task(self.store.enqueue(event))
        return actuator.state

    async def start(self) -> None:
        # Start storage writer
        if self.store:
            await self.store.start()
        # Launch sensor loops for each room
        for rid, room in self.rooms.items():
            self._tasks.append(asyncio.create_task(self._sensor_loop(rid, "temp", self.cfg.tick_temp)))
            self._tasks.append(asyncio.create_task(self._sensor_loop(rid, "light", self.cfg.tick_light)))
            self._tasks.append(asyncio.create_task(self._sensor_loop(rid, "motion", self.cfg.tick_motion)))
            if "humidity" in room.sensors:
                self._tasks.append(asyncio.create_task(self._sensor_loop(rid, "humidity", 3.0)))
        self._tasks.append(asyncio.create_task(self._environment_loop(0.5)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.store:
            await self.store.stop()

    async def _sensor_loop(self, room_id: str, sensor_id: str, interval: float) -> None:
        room = self.rooms[room_id]
        sensor = room.sensors[sensor_id]
        while True:
            try:
                v = sensor.read(room.env)
                now = time.time()
                reading = Reading(
                    ts=now,
                    room=room_id,
                    device_id=sensor_id,
                    name=sensor.name,
                    metric=sensor.metric,
                    value=v,
                )
                room.latest[sensor_id] = reading
                room.history[sensor_id].append(reading)
                event = {
                    "type": "reading",
                    "room": room_id,
                    "device_id": sensor_id,
                    "name": sensor.name,
                    "metric": sensor.metric,
                    "value": v,
                    "ts": now,
                }
                await self.broadcaster.publish(event)
                if self.store:
                    await self.store.enqueue(event)
                await self._apply_rules(room_id, sensor_id, reading)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def _environment_loop(self, interval: float) -> None:
        while True:
            try:
                for room in self.rooms.values():
                    self._step_env(room)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    def _step_env(self, room: Room) -> None:
        # Temperature dynamics: drift toward thermostat setpoint; fan accelerates cooling (if room has thermostat/fan)
        setpoint = float(room.actuators.get("thermostat", Thermostat(id="_", name="_", kind="actuator", state={"setpoint": room.env.get("temp", 24.0)})).state.get("setpoint", 24.0))
        fan_on = bool(room.actuators.get("fan", Fan(id="_", name="_", kind="actuator", state={"on": False})).state.get("on", False))
        temp = float(room.env.get("temp", 24.0))
        delta = (setpoint - temp) * (0.01 if not fan_on else 0.03)
        temp += delta + random.uniform(-0.05, 0.05)
        room.env["temp"] = temp

        # Light dynamics: depends on time of day and bulb state
        hour = time.localtime().tm_hour
        is_day = 7 <= hour <= 17
        target = 75.0 if is_day else 10.0
        bulb_on = bool(room.actuators["lightbulb"].state.get("on", False))
        if bulb_on:
            target += 22.0
        light = float(room.env.get("light", 40.0))
        light += (target - light) * 0.05 + random.uniform(-0.5, 0.5)
        room.env["light"] = max(0.0, min(100.0, light))

        # Motion probability drifts slightly
        mp = float(room.env.get("motion_prob", 0.12))
        room.env["motion_prob"] = max(0.02, min(0.5, mp + random.uniform(-0.01, 0.01)))

        # Humidity slow drift toward target (depends on time of day slightly)
        if "humidity" in room.env:
            hour = time.localtime().tm_hour
            target_h = 45.0 if 10 <= hour <= 18 else 50.0
            h = float(room.env.get("humidity", 50.0))
            h += (target_h - h) * 0.02 + random.uniform(-0.3, 0.3)
            room.env["humidity"] = max(0.0, min(100.0, h))

    async def _apply_rules(self, room_id: str, sensor_id: str, reading: Reading) -> None:
        room = self.rooms[room_id]
        # Fan automation: if temperature > threshold, fan on else off
        if sensor_id == "temp" and reading.metric == "temperature":
            cfg_room = (self.rules.get_room_cfg(room_id) if self.rules else {})
            threshold = float(cfg_room.get("temp_high", self.cfg.temp_high))
            want_on = reading.value > threshold
            current = bool(room.actuators["fan"].state.get("on", False))
            if want_on != current:
                self.command_actuator(room_id, "fan", {"on": want_on})

        # Night motion lighting automation
        if sensor_id == "motion" and reading.metric == "motion":
            now = time.time()
            if reading.value:
                room.memory["last_motion_ts"] = now
            latest_light = room.latest.get("light")
            light_val = latest_light.value if latest_light else room.env.get("light", 0.0)
            hour = time.localtime().tm_hour
            cfg_room = (self.rules.get_room_cfg(room_id) if self.rules else {})
            dark_threshold = float(cfg_room.get("light_dark", self.cfg.light_dark))
            on_seconds = float(cfg_room.get("motion_light_on_seconds", self.cfg.motion_light_on_seconds))
            dark = light_val < dark_threshold or (hour >= 18 or hour <= 6)
            if reading.value and dark:
                room.memory["light_on_until"] = max(room.memory.get("light_on_until", 0.0), now + on_seconds)
                if not room.actuators["lightbulb"].state.get("on", False):
                    self.command_actuator(room_id, "lightbulb", {"on": True})
            if room.actuators["lightbulb"].state.get("on", False):
                if now > float(room.memory.get("light_on_until", 0.0)):
                    self.command_actuator(room_id, "lightbulb", {"on": False})
