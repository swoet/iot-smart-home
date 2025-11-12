from __future__ import annotations

import asyncio
from typing import Optional

import typer
import uvicorn

from .api import app as fastapi_app
from .simulation import Simulation
from .config import load_config

app = typer.Typer(help="SmartHome Simulation CLI")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes"),
):
    """Run the API server with web dashboard."""
    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def simulate(seconds: Optional[int] = typer.Option(10, help="Run headless simulation for N seconds")):
    """Run the simulation headless and print state updates."""
    cfg = load_config(None)
    sim = Simulation(cfg)

    async def _run():
        await sim.start()
        try:
            await asyncio.sleep(seconds if seconds is not None else 10)
        finally:
            await sim.stop()
            typer.echo("Done.")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
