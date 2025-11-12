from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, PlainTextResponse

from .config import load_config
from .simulation import Simulation
from .logging_setup import configure_logging
from .storage import EventStore
from .rules import Rules

configure_logging()
app = FastAPI(title="SmartHome Simulation", version="0.1.0")

# Singletons
cfg = load_config(None)
store = EventStore(Path(__file__).resolve().parents[2] / "smarthome.db")
rules_path = Path(__file__).resolve().parents[2] / "rules.yaml"
rules = Rules(rules_path, defaults={
    "temp_high": cfg.temp_high,
    "light_dark": cfg.light_dark,
    "motion_light_on_seconds": cfg.motion_light_on_seconds,
})

sim = Simulation(cfg, store=store, rules=rules)


@app.on_event("startup")
async def on_startup() -> None:
    await sim.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await sim.stop()


@app.get("/")
async def index() -> Any:
    # Serve the dashboard HTML file
    index_path = Path(__file__).resolve().parent / "web" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse("<h1>SmartHome Simulation</h1><p>UI not found.</p>")


@app.get("/api/state")
async def get_state() -> Dict[str, Any]:
    return sim.get_state()


@app.get("/api/rooms")
async def get_rooms() -> Dict[str, Any]:
    s = sim.get_state()
    return {"rooms": {rid: v["name"] for rid, v in s["rooms"].items()}}


@app.get("/api/history")
async def get_history(room: str, sensor_id: str, limit: int = 300) -> Dict[str, Any]:
    points = store.query_readings(room, sensor_id, limit=limit)
    return {"room": room, "sensor_id": sensor_id, "points": points}


@app.post("/api/rooms/{room}/actuators/{actuator_id}")
async def post_actuator(room: str, actuator_id: str, body: Dict[str, Any]) -> JSONResponse:
    try:
        new_state = sim.command_actuator(room, actuator_id, body)
        return JSONResponse({"room": room, "id": actuator_id, "state": new_state})
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@app.get("/api/rules")
async def get_rules() -> PlainTextResponse:
    # Return raw YAML for editing
    return PlainTextResponse((rules_path.read_text() if rules_path.exists() else "rooms: {}\n"), media_type="text/plain")


@app.put("/api/rules")
async def put_rules(content: str = Body(..., media_type="text/plain")) -> JSONResponse:
    try:
        rules.save(content)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    q = await sim.broadcaster.add_listener()
    try:
        # Immediately send current state snapshot
        await ws.send_json({"type": "snapshot", **sim.get_state()})
        while True:
            event = await q.get()
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        await sim.broadcaster.remove_listener(q)
