# SmartTraffic

**SIH PS90 — Adaptive Smart Traffic Signal Control**

## What is actually new here

Max-pressure control, green waves, emergency preemption, transit priority and RL
for signals are all established work. They are implemented here, carefully, but
they are not the contribution. Two things are.

**1. Signal control imported from the West assumes lane discipline, and Indian
traffic does not have it.** Two-wheelers filter into lateral gaps and discharge
two or three abreast where one car fits. We model discharge from physical width
and headway instead of a static PCU factor, and the conventional factor turns out
to over-state two-wheeler discharge by **56%**, over-allocating green by **21.5%**
at Indian traffic mixes. The model reproduces textbook saturation flow for cars
*exactly*, so it departs from convention only where lane discipline does.

Correcting the measure alone starved the two-wheeler road, so the controller
optimises **people moved per second of green** with an explicit fairness term.
Against what a deployed Indian system does today, on a scooter feeder meeting a
bus arterial at saturation: **+1,900 people moved**, with worst-case waiting cut
from 184 ticks to 37.

**2. Two widely used evaluation metrics are gameable, and we show it.** Ranking
controllers by average queue rewards *refusing* traffic — an approach held at red
fills up and turns arrivals away, so they never appear in the statistic. And a
queue-based RL reward taught a policy to keep approaches permanently red: lowest
mean queue in the benchmark, 95th-percentile delay of 66 against fixed-time's 27.

### Every number above is reproducible

```bash
python scripts/reproduce_results.py
```

It re-measures each documented claim, prints what it comes out at today, and
**exits non-zero if any claim no longer holds** — including the negative results,
which must stay negative. `docs/BENCHMARKS.md` and `docs/HETEROGENEOUS_FLOW.md`
record what failed as well as what worked: four refinements measured over eight
seeds with paired confidence intervals and rejected, and the conditions under
which the heterogeneous result does *not* apply.

---

SmartTraffic is a local-first traffic-control prototype focused on a clear single-junction A/B demonstration: the same intersection and the same seeded vehicle arrivals are run under a conventional fixed-clock signal and under SmartTraffic's adaptive controller. The browser visualizes both simulations side-by-side with proper signal phases, queue spacing, and POV/bird's-eye views.

## Current judge-facing demo

- One physical intersection shown twice side-by-side.
- Left: conventional fixed-clock signal timing.
- Right: SmartTraffic adaptive-predictive controller.
- Both sides receive the exact same deterministic arrival schedule.
- Proper N/S green, amber clearance, and E/W green transitions.
- Queue-positioned cars with fixed spacing so vehicles do not overlap.
- North/south surge, east/west surge, and balanced scenarios.
- Average queue, wait, throughput, peak queue, and current queue comparison.
- POV and bird's-eye camera modes.

The wider repository contains network-level controller experiments, SUMO/TraCI adapters, emergency priority work, and benchmark services. The main browser demo is intentionally single-junction so the comparison is easy to understand and defend.

## Operations console

Below the A/B demo, the control room carries an **operations console** covering the
questions a city asks after "does it work?".

| Tab | Answers |
| --- | --- |
| Network health | Per-junction mode, delay distribution (p95, worst approach), pedestrian and bus waits. Inject detector, comms and signal-head faults and watch the fallback happen. |
| Why this decision | Every phase change with the pressures behind it and the constraint that overrode the optimiser. |
| City impact | Idle fuel, CO₂ and rupees saved per year, pooled over five seeds, with every assumption listed. |
| Controller benchmark | All fifteen controllers ranked, with fairness and person-delay columns beside the averages. |
| Green wave | Corridor offsets, through-band width, and a time-space diagram. |
| Emergency priority | Ambulance travel time with and without preemption, plus what the rest of the traffic paid. |
| What-if planner | Demand, weather, footfall and infrastructure failure, answered across seeds with 95% confidence intervals. |
| Calibration & sensing | Fit demand to observed counts and verify the fit; vision detector and hardware feed status. |

## What makes this deployable rather than just adaptive

- **Safety shield.** Every controller runs behind minimum green, a maximum-green
  starvation guard, a guaranteed maximum pedestrian wait, emergency preemption
  and fault fallback. The optimiser proposes; the shield disposes and records
  why. This is what makes the reinforcement-learning controller safe to run.
- **Pedestrians and buses count.** Person-weighted delay stops the system
  quietly optimising for private cars; a bus carrying 35 people outranks a
  longer queue of single-occupancy cars.
- **It degrades safely.** Detector dropout, stuck detectors, comms loss and
  signal-head failure each route to a documented fallback, and faults corrupt
  what the controller *sees* without changing physical truth.
- **It explains itself.** `GET /api/safety/audit` is an engineering audit trail,
  not a log.
- **It reports in city units.** See `docs/IMPACT.md` for every constant.
- **It coordinates rather than optimising each junction alone.** The benchmark
  originally showed every adaptive controller losing to a fixed clock under
  saturation. The cause turned out to be that a fixed clock switches every
  junction in unison, accidentally creating a green wave that independent
  optimisers destroy. `coordinated-pressure-v1` fixes it: **28% lower queues and
  29% lower p95 delay than fixed-time** under normal demand, and the best
  throughput and p95 under saturation. The full diagnosis is in
  `docs/BENCHMARKS.md`.
- **It collects counts, not identities.** No ANPR, no faces, no image retention.
  See `docs/PRIVACY.md`.

## Verifying the claims

| command | what it checks |
| --- | --- |
| `python scripts/reproduce_results.py` | every headline number in the docs, with pass/fail |
| `cd backend && pytest -q` | 119 tests, including the negative results |
| `curl localhost:8000/api/saturation/report` | the lane-less discharge study, live |
| `curl localhost:8000/api/benchmark/suite` | all controllers across seeds and disturbances |

## Run locally

SmartTraffic is **not dependent on Vercel or any hosted backend**. Run the backend and frontend in two terminals.

### 1. Backend

From the repository root:

```bash
cd backend
python -m venv .venv
```

Activate the environment:

**Windows PowerShell**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows Command Prompt**

```bat
.venv\Scripts\activate.bat
```

**Linux/macOS**

```bash
source .venv/bin/activate
```

Then install and start FastAPI:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Check the backend directly in your browser:

```text
http://localhost:8000/health
```

For the single-junction comparison API:

```text
http://localhost:8000/api/single-junction/comparison?steps=100&seed=7&scenario=north-surge
```

Both URLs should return JSON.

### 2. Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally:

```text
http://localhost:5173
```

The frontend connects directly to:

```text
http://localhost:8000
```

You can override it with `VITE_API_URL` if needed.

## If the browser says BACKEND OFFLINE

1. Confirm `uvicorn app.main:app --reload --port 8000` is still running.
2. Open `http://localhost:8000/health` manually.
3. If that page does not return JSON, fix/start the backend first.
4. Return to the frontend and click **Reconnect backend**.

The frontend now reports the actual backend URL instead of showing an ambiguous JSON/token parsing error.

## Single-junction experiment

The endpoint:

```text
GET /api/single-junction/comparison
```

creates one seeded arrival schedule and feeds the same arrivals into both controllers.

### Fixed Clock

- equal timed green windows
- no awareness of queue demand
- amber transition when changing phase

### SmartTraffic Adaptive

- compares N/S and E/W queue pressure
- includes recent queue growth in the short-horizon score
- minimum-green hysteresis prevents rapid flickering
- maximum-green protection prevents starvation
- amber transition before changing phase

This makes the A/B comparison reproducible and fair.

## API reference

| Endpoint | Purpose |
| --- | --- |
| `GET /api/state` | Live network state, metrics, faults, decisions |
| `POST /api/fault` · `/api/faults/clear` | Inject or clear infrastructure faults |
| `POST /api/weather` | Set saturation-flow conditions |
| `GET /api/safety/audit` | Per-decision explanation and override statistics |
| `POST /api/impact/compare` | Fuel / CO₂ / rupee savings, pooled over seeds |
| `GET /api/benchmark/suite` | Full controller comparison |
| `POST /api/whatif` | Planning question with confidence intervals |
| `GET /api/greenwave` | Corridor offsets and time-space diagram data |
| `GET /api/emergency/comparison` | Ambulance travel time with/without preemption |
| `POST /api/emergency/dispatch` | Put a priority vehicle on the live network |
| `POST /api/calibrate` | Fit demand to an observed-counts CSV |
| `POST /api/vision/analyse` · `/api/vision/apply` | Frame to lane counts, then operator correction |
| `GET /api/hil/state` | Signal-head aspects for physical hardware (`?format=wire`) |

## Hardware demo

`hardware/` contains ESP32 firmware that drives real signal heads from
`/api/hil/state`, with a link-loss fail-safe. See `hardware/README.md`.

## Tests

```bash
cd backend && python -m pytest -q     # 104 tests
```

## Research / expansion path

The wider research track remains:

1. fixed-clock baseline
2. actuated baseline
3. max-pressure baseline
4. predictive pressure control
5. movement-level/network pressure
6. SUMO/TraCI validation
7. real OpenStreetMap junction geometry
8. emergency / ambulance / fire / police priority handling
9. robustness testing across incidents and unseen demand patterns

No mock-simulator result should be presented as a final SIH performance claim. Final claims should come from controlled SUMO experiments using identical scenarios/seeds.
