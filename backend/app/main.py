from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.controllers.registry import CONTROLLERS, describe
from app.services.benchmark import run_benchmark, run_benchmark_suite
from app.services.calibration import CalibrationError, calibrate
from app.services.comparison import run_comparison
from app.services.emergency import PRIORITY_PROFILES, plan_green_corridor, run_preemption_comparison
from app.services.greenwave import plan_green_wave
from app.services.impact import ImpactAssumptions, compare_impact
from app.services.runner import RunConfig, SimulationRunner
from app.services.scenario import ScenarioConfig, simulate
from app.services.single_junction import run_single_junction_comparison
from app.services.vision import apply_corrections, detect_vehicles, detector_status, seed_engine
from app.services.whatif import run_whatif

runner = SimulationRunner()
loop_task: asyncio.Task | None = None

#: Vision estimates are held between the analyse call and the operator's
#: correction so a reviewer can adjust lanes before they seed the controller.
last_vision_estimate: dict | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner.reset()
    yield
    runner.running = False
    global loop_task
    if loop_task:
        loop_task.cancel()


app = FastAPI(title='SmartTraffic API', version='2.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False, allow_methods=['*'], allow_headers=['*'])


# --------------------------------------------------------------------- models

class ResetRequest(BaseModel):
    controller: str = 'predictive-pressure-v2'
    scenario: str = 'normal'
    seed: int = 7
    shielded: bool = True


class EventRequest(BaseModel):
    event: str


class FaultRequest(BaseModel):
    kind: str = 'detector-dropout'
    junction: str = 'J1'
    direction: str | None = None


class WeatherRequest(BaseModel):
    condition: str = 'clear'


class CorridorRequest(BaseModel):
    route: list[str]
    vehicle_type: str = 'ambulance'
    segment_travel_seconds: list[float] | None = None
    lead_seconds: float | None = None
    hold_seconds: float | None = None


class DispatchRequest(BaseModel):
    route: list[str] = ['J1', 'J2', 'J4']
    vehicle_type: str = 'ambulance'


class WhatIfRequest(BaseModel):
    controllers: list[str] | None = None
    baseline: str = 'fixed-time'
    seeds: list[int] | None = None
    steps: int = 180
    scenario: str = 'normal'
    demand_multiplier: float = 1.0
    weather: str = 'clear'
    pedestrian_rate: float = 1.0
    lane_closure: dict | None = None
    event: str | None = None
    shielded: bool = True


class CalibrationRequest(BaseModel):
    csv_text: str
    verify_steps: int = 240
    seed: int = 7


class VisionApplyRequest(BaseModel):
    junction: str = 'J1'
    corrections: dict[str, int] = {}
    force: bool = False


class ImpactRequest(BaseModel):
    baseline: str = 'fixed-time'
    candidate: str = 'mpc-lite-v1'
    steps: int = 180
    #: Pooled over several seeds. A single run is an anecdote, and the
    #: seed-to-seed spread here is larger than the effect being measured.
    seeds: list[int] = [3, 7, 11, 19, 29]
    scenario: str = 'normal'
    assumptions: dict | None = None


# --------------------------------------------------------------------- health

@app.get('/health')
def health():
    return {
        'status': 'ok',
        'engine': runner.engine.__class__.__name__,
        'controller': runner.controller.name,
        'controllers': list(CONTROLLERS),
        'shielded': runner.config.shielded,
        'vision': detector_status(),
    }


@app.get('/api/state')
def state():
    return runner.snapshot().to_dict()


@app.post('/api/reset')
def reset(body: ResetRequest):
    return runner.reset(RunConfig(**body.model_dump())).to_dict()


@app.post('/api/event')
def event(body: EventRequest):
    return runner.inject(body.event).to_dict()


@app.post('/api/step')
def step():
    return runner.one_step().to_dict()


@app.get('/api/controllers')
def controllers():
    return {'controllers': list(CONTROLLERS), 'detail': describe()}


# ------------------------------------------------------------- fault handling

@app.post('/api/fault')
def fault(body: FaultRequest):
    """Break something on purpose and watch the controller degrade safely."""
    try:
        return runner.inject_fault(body.kind, body.junction, body.direction).to_dict()
    except (RuntimeError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/faults/clear')
def faults_clear():
    return runner.clear_faults().to_dict()


@app.post('/api/weather')
def weather(body: WeatherRequest):
    return runner.set_weather(body.condition).to_dict()


# ------------------------------------------------------------ explainability

@app.get('/api/safety/audit')
def safety_audit(limit: int = 60, junction: str | None = None):
    """Why the controller did what it did, decision by decision."""
    return runner.safety_report(limit=limit, junction=junction)


# --------------------------------------------------------------------- impact

@app.get('/api/impact/live')
def impact_live():
    return runner.live_impact()


@app.post('/api/impact/compare')
def impact_compare(body: ImpactRequest):
    """Fuel, CO2 and rupees saved by the candidate against the baseline."""
    assumptions = ImpactAssumptions(**body.assumptions) if body.assumptions else None
    seeds = body.seeds or [7]
    keys = ('total_vehicle_wait_ticks', 'total_bus_wait_ticks', 'total_person_wait_ticks')

    def pooled_metrics(name: str) -> dict:
        runs = [
            simulate(ScenarioConfig(
                controller=name, steps=body.steps, seed=seed, scenario=body.scenario,
            ))['metrics']
            for seed in seeds
        ]
        return {k: sum(m.get(k, 0) for m in runs) / len(runs) for k in keys}

    result = compare_impact(
        pooled_metrics(body.baseline),
        pooled_metrics(body.candidate),
        steps=body.steps,
        assumptions=assumptions,
    )
    result['comparison'] = {
        'baseline': body.baseline,
        'candidate': body.candidate,
        'scenario': body.scenario,
        'seeds': seeds,
    }
    return result


# ------------------------------------------------------------------ benchmarks

@app.get('/api/benchmark')
def benchmark(steps: int = 120, seed: int = 7, scenario: str = 'rush', shielded: bool = True):
    return {'results': run_benchmark(steps=steps, seed=seed, scenario=scenario, shielded=shielded)}


@app.get('/api/benchmark/suite')
def benchmark_suite(steps: int = 180, shielded: bool = True):
    return run_benchmark_suite(steps=max(30, min(steps, 600)), shielded=shielded)


@app.post('/api/whatif')
def whatif(body: WhatIfRequest):
    """Planning question answered across many seeds, with confidence intervals."""
    return run_whatif(**body.model_dump())


@app.get('/api/single-junction/comparison')
def single_junction_comparison(steps: int = 90, seed: int = 7, scenario: str = 'north-surge'):
    return run_single_junction_comparison(steps=steps, seed=seed, scenario=scenario)


@app.get('/api/forecast')
def forecast(horizon: int = 15):
    return runner.forecast(horizon).to_dict()


@app.get('/api/comparison')
def comparison(left: str = 'fixed-time', right: str = 'predictive-pressure-v2', steps: int = 90, seed: int = 7, event: str = 'accident', event_tick: int = 20, scenario: str = 'normal', shielded: bool = True):
    return run_comparison(left=left, right=right, steps=steps, seed=seed, event=event or None, event_tick=event_tick, scenario=scenario, shielded=shielded)


# ----------------------------------------------------------------- green wave

@app.get('/api/greenwave')
def greenwave(corridor: str = 'J1,J2,J4', cycle: float = 16.0, green: float = 8.0, speed_kmph: float = 40.0):
    """Offsets and time-space diagram data for a coordinated corridor."""
    junctions = [j.strip().upper() for j in corridor.split(',') if j.strip()]
    try:
        return plan_green_wave(junctions, cycle=cycle, green=green, speed_kmph=speed_kmph)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------- calibration

@app.post('/api/calibrate')
def calibrate_counts(body: CalibrationRequest):
    """Fit demand to observed counts, then verify the fit reproduces them."""
    try:
        return calibrate(body.csv_text, verify_steps=body.verify_steps, seed=body.seed)
    except CalibrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/api/calibrate/upload')
async def calibrate_upload(file: UploadFile = File(...)):
    payload = await file.read()
    try:
        return calibrate(payload.decode('utf-8-sig'))
    except CalibrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail='counts file must be UTF-8 text') from exc


# --------------------------------------------------------------------- vision

@app.get('/api/vision/status')
def vision_status():
    return detector_status()


@app.post('/api/vision/analyse')
async def vision_analyse(file: UploadFile = File(...)):
    global last_vision_estimate
    payload = await file.read()
    result = detect_vehicles(payload, file.filename or 'upload.jpg')
    last_vision_estimate = result.get('estimate')
    return result


@app.post('/api/vision/apply')
def vision_apply(body: VisionApplyRequest):
    """Correct the model's lane counts, then seed the junction with them."""
    if last_vision_estimate is None:
        raise HTTPException(status_code=409, detail='analyse a frame before applying it')
    corrected = apply_corrections(last_vision_estimate, body.corrections)
    try:
        outcome = seed_engine(runner.engine, body.junction.upper(), corrected, force=body.force)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'estimate': corrected, 'seeding': outcome, 'state': runner.snapshot().to_dict()}


# ------------------------------------------------------------------ emergency

@app.get('/api/priority/types')
def priority_types():
    return {'types': PRIORITY_PROFILES}


@app.post('/api/emergency/corridor')
def emergency_corridor(body: CorridorRequest):
    return plan_green_corridor(
        route=body.route,
        vehicle_type=body.vehicle_type,
        segment_travel_seconds=body.segment_travel_seconds,
        lead_seconds=body.lead_seconds,
        hold_seconds=body.hold_seconds,
    )


@app.post('/api/emergency/dispatch')
def emergency_dispatch(body: DispatchRequest):
    """Put a priority vehicle on the live network and preempt ahead of it."""
    try:
        return runner.dispatch_emergency(body.route, body.vehicle_type).to_dict()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get('/api/emergency/comparison')
def emergency_comparison(steps: int = 140, seed: int = 7, scenario: str = 'rush', route: str = 'J1,J2,J4'):
    """Ambulance travel time with and without preemption, on identical traffic."""
    junctions = [j.strip().upper() for j in route.split(',') if j.strip()]
    return run_preemption_comparison(route=junctions, steps=steps, seed=seed, scenario=scenario)


# ------------------------------------------------------ hardware in the loop

@app.get('/api/hil/state')
def hil_state(format: str = 'json'):
    """Signal-head aspects for a physical model junction."""
    payload = runner.hil_state()
    if format == 'wire':
        return Response(content=payload['wire'], media_type='text/plain')
    return payload


# ----------------------------------------------------------------- execution

@app.post('/api/run')
async def run():
    global loop_task
    if not runner.running:
        loop_task = asyncio.create_task(runner.loop())
    return {'running': True}


@app.post('/api/pause')
def pause():
    runner.running = False
    return {'running': False}


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    runner.clients.add(ws)
    try:
        await ws.send_json(runner.snapshot().to_dict())
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        runner.clients.discard(ws)
