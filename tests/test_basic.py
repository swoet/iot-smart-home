import asyncio

import pytest

from smarthome.simulation import Simulation


@pytest.mark.asyncio
async def test_simulation_runs_briefly():
    sim = Simulation()
    await sim.start()
    # allow a couple of ticks
    await asyncio.sleep(2.5)
    state = sim.get_state()
    assert "rooms" in state and len(state["rooms"]) >= 1
    await sim.stop()
