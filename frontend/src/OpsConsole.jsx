/*
 * Operations console.
 *
 * The A/B view above answers "does adaptive control beat a fixed clock?".
 * This panel answers the questions a city asks next: what is it worth, is it
 * fair, what happens when it breaks, why did it do that, and what if demand
 * grows? Everything here is served by the FastAPI backend, so the numbers are
 * the same ones the benchmark and the test suite produce.
 */

import React, { useCallback, useEffect, useState } from 'react'

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

const TABS = [
  ['health',    'Network health'],
  ['why',       'Why this decision'],
  ['impact',    'City impact'],
  ['bench',     'Controller benchmark'],
  ['wave',      'Green wave'],
  ['ev',        'Emergency priority'],
  ['whatif',    'What-if planner'],
  ['data',      'Calibration & sensing'],
]

const FAULTS = [
  { kind: 'detector-dropout', junction: 'J2', direction: 'east', label: 'Detector dropout (J2 east)' },
  { kind: 'detector-stuck',   junction: 'J1', direction: 'north', label: 'Stuck detector (J1 north)' },
  { kind: 'comms-loss',       junction: 'J3', label: 'Comms loss (J3)' },
  { kind: 'signal-fault',     junction: 'J4', label: 'Signal head failure (J4)' },
]

const WEATHER = ['clear', 'rain', 'heavy-rain', 'fog']

const MODE_LABEL = {
  'adaptive': 'Adaptive',
  'detector-degraded': 'Detector degraded',
  'local-fallback': 'Local fallback',
  'all-red-flash': 'Fail-safe all-red',
}

const num = (v, d = 0) => (typeof v === 'number' ? v.toFixed(d) : '—')
const inr = v => {
  if (typeof v !== 'number') return '—'
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(2)} cr`
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`
  return `₹${Math.round(v).toLocaleString('en-IN')}`
}

async function api(path, options) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { detail = (await res.json()).detail || detail } catch { /* not json */ }
    throw new Error(detail)
  }
  return res.json()
}

function Panel({ title, blurb, children, actions }) {
  return (
    <section className="ops-panel">
      <div className="ops-panel-head">
        <div>
          <h3>{title}</h3>
          {blurb && <p>{blurb}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  )
}

function Stat({ label, value, hint, tone }) {
  return (
    <div className={`ops-stat ${tone || ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  )
}

function Loading({ error, busy, empty }) {
  if (error) return <p className="ops-error">{error}</p>
  if (busy) return <p className="ops-muted">Running…</p>
  if (empty) return <p className="ops-muted">No data yet.</p>
  return null
}

/* ------------------------------------------------------------------ health */

function HealthTab() {
  const [state, setState] = useState(null)
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    api('/api/state').then(setState).catch(e => setError(e.message))
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 1500)
    return () => clearInterval(id)
  }, [refresh])

  const act = (path, body) =>
    api(path, { method: 'POST', body: JSON.stringify(body || {}) })
      .then(setState)
      .catch(e => setError(e.message))

  const metrics = state?.metrics || {}

  return (
    <>
      {state?.degraded && (
        <div className="ops-banner">
          Degraded operation — {state.faults.length} active fault
          {state.faults.length === 1 ? '' : 's'}. Affected junctions have fallen back to a
          safe plan; the controller is no longer in full adaptive control.
        </div>
      )}

      <Panel
        title="Live network"
        blurb="Per-junction operating mode. A junction only reports 'Adaptive' when its detection and comms are healthy."
        actions={<button onClick={() => act('/api/step')}>Step once</button>}
      >
        <Loading error={error} empty={!state} />
        <div className="ops-junctions">
          {(state?.junctions || []).map(j => (
            <div key={j.id} className={`ops-junction ${j.healthy ? '' : 'bad'}`}>
              <header><strong>{j.id}</strong><span>{j.phase}</span></header>
              <div className="ops-mode">{MODE_LABEL[j.mode] || j.mode}</div>
              <dl>
                <div><dt>Queue</dt><dd>{j.queue}</dd></div>
                <div><dt>People</dt><dd>{num(j.person_queue, 0)}</dd></div>
                <div><dt>Buses</dt><dd>{Object.values(j.buses || {}).reduce((s, n) => s + n, 0)}</dd></div>
                <div><dt>Pedestrians</dt><dd>{j.pedestrian} <em>({j.ped_wait}t)</em></dd></div>
              </dl>
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Fairness and delay distribution"
        blurb="An average queue hides a starved approach. These are the numbers that expose one."
      >
        <div className="ops-stats">
          <Stat label="Mean vehicle delay" value={`${num(metrics.mean_vehicle_delay, 1)} ticks`} />
          <Stat label="95th percentile delay" value={`${num(metrics.p95_vehicle_delay, 0)} ticks`}
                hint="the unlucky one in twenty" />
          <Stat label="Worst approach wait" value={`${num(metrics.worst_approach_wait, 0)} ticks`}
                hint={metrics.worst_approach || '—'} tone="warn" />
          <Stat label="Mean person delay" value={`${num(metrics.mean_person_delay, 1)} ticks`}
                hint="weighted by occupancy" />
          <Stat label="Mean pedestrian wait" value={`${num(metrics.mean_pedestrian_delay, 1)} ticks`} />
          <Stat label="Worst pedestrian wait" value={`${num(metrics.max_pedestrian_delay, 0)} ticks`}
                hint="capped by the safety shield" />
        </div>
      </Panel>

      <Panel
        title="Break it on purpose"
        blurb="Every deployment review asks what happens when a detector dies. Find out here rather than on the road."
      >
        <div className="ops-buttons">
          {FAULTS.map(f => (
            <button key={f.label} onClick={() => act('/api/fault', f)}>{f.label}</button>
          ))}
          <button className="ops-clear" onClick={() => act('/api/faults/clear')}>Clear all faults</button>
        </div>
        <div className="ops-buttons">
          {WEATHER.map(w => (
            <button key={w} className={state?.weather === w ? 'sel' : ''}
                    onClick={() => act('/api/weather', { condition: w })}>{w}</button>
          ))}
        </div>
        {state?.faults?.length > 0 && (
          <ul className="ops-faults">
            {state.faults.map(f => (
              <li key={f.id}><code>{f.kind}</code> on {f.junction}{f.direction ? ` ${f.direction}` : ''} since tick {f.since_tick}</li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------ explainability */

function WhyTab() {
  const [report, setReport] = useState(null)
  const [junction, setJunction] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    const q = junction ? `&junction=${junction}` : ''
    api(`/api/safety/audit?limit=40${q}`).then(setReport).catch(e => setError(e.message))
  }, [junction])

  useEffect(() => { load() }, [load])

  const counts = report?.summary?.counts || {}

  return (
    <Panel
      title="Decision audit"
      blurb="Every phase change, the pressures behind it, and the constraint that overrode the optimiser. This is what an engineer reads after an incident."
      actions={
        <span className="ops-inline">
          <select value={junction} onChange={e => setJunction(e.target.value)}>
            <option value="">All junctions</option>
            {['J1', 'J2', 'J3', 'J4'].map(j => <option key={j} value={j}>{j}</option>)}
          </select>
          <button onClick={load}>Refresh</button>
        </span>
      }
    >
      <Loading error={error} empty={!report} />
      {report && !report.shielded && <p className="ops-muted">{report.note}</p>}
      {report?.shielded && (
        <>
          <div className="ops-stats">
            <Stat label="Decisions logged" value={report.summary.decisions_logged} />
            <Stat label="Optimiser overridden" value={`${num(report.summary.override_rate_pct, 1)}%`}
                  hint="by a safety or fairness rule" />
            <Stat label="Min green" value={`${report.constraints.min_green} ticks`} />
            <Stat label="Max pedestrian wait" value={`${report.constraints.max_pedestrian_wait} ticks`} />
          </div>

          <div className="ops-reasons">
            {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([reason, n]) => (
              <span key={reason} className={`ops-tag ${reason === 'accepted' ? 'ok' : ''}`}>{reason} · {n}</span>
            ))}
          </div>

          <div className="ops-table-wrap">
            <table className="ops-table">
              <thead>
                <tr>
                  <th>Tick</th><th>Junction</th><th>Proposed</th><th>Applied</th>
                  <th>NS / EW pressure</th><th>Peds</th><th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {report.decisions.slice().reverse().map((d, i) => (
                  <tr key={i} className={d.overridden ? 'overridden' : ''}>
                    <td>{d.tick}</td>
                    <td>{d.junction}</td>
                    <td>{d.proposed}</td>
                    <td><strong>{d.applied}</strong></td>
                    <td>{d.pressure_ns} / {d.pressure_ew}</td>
                    <td>{d.pedestrians_waiting} <em>({d.pedestrian_wait}t)</em></td>
                    <td title={d.explanation}>{d.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ impact */

function ImpactTab() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [scenario, setScenario] = useState('normal')

  const run = () => {
    setBusy(true); setError('')
    api('/api/impact/compare', {
      method: 'POST',
      body: JSON.stringify({
        baseline: 'fixed-time', candidate: 'mpc-lite-v1',
        steps: 180, seeds: [3, 7, 11, 19, 29], scenario,
      }),
    }).then(setData).catch(e => setError(e.message)).finally(() => setBusy(false))
  }

  useEffect(() => { run() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const saved = data?.saved_per_year
  const a = data?.baseline?.assumptions

  return (
    <Panel
      title="What it is worth to the city"
      blurb="The same delay reduction, expressed in the units a transport department budgets in, pooled over five seeds. Every constant is an assumption you can challenge."
      actions={
        <span className="ops-inline">
          <select value={scenario} onChange={e => setScenario(e.target.value)}>
            <option value="normal">Normal demand</option>
            <option value="rush">Rush hour</option>
          </select>
          <button onClick={run} disabled={busy}>Recalculate</button>
        </span>
      }
    >
      <Loading error={error} busy={busy} empty={!data} />
      {data && (
        <>
          <div className="ops-stats">
            <Stat label="Saved per year" value={inr(saved.total_cost_inr)}
                  hint="fuel plus value of time, 4 junctions"
                  tone={saved.total_cost_inr >= 0 ? 'good' : 'warn'} />
            <Stat label="CO₂ avoided" value={`${num(saved.co2_tonnes, 1)} t/yr`}
                  tone={saved.co2_tonnes >= 0 ? 'good' : 'warn'} />
            <Stat label="Idle fuel saved" value={`${Math.round(saved.idle_fuel_litres).toLocaleString('en-IN')} L/yr`} />
            <Stat label="Person-hours returned" value={`${num(data.reduction_pct.person_hours, 1)}%`}
                  hint="reduction vs fixed-time" />
          </div>

          <details className="ops-assumptions">
            <summary>Assumptions behind these numbers</summary>
            <ul>
              <li>1 tick = {a.tick_seconds} s of real time</li>
              <li>Idling: car {a.car_idle_litres_per_hour} L/h, bus {a.bus_idle_litres_per_hour} L/h</li>
              <li>Fuel: ₹{a.petrol_price_inr}/L petrol, ₹{a.diesel_price_inr}/L diesel</li>
              <li>Emissions: {a.petrol_kg_co2_per_litre} kg CO₂/L petrol, {a.diesel_kg_co2_per_litre} kg/L diesel</li>
              <li>Value of time: ₹{a.value_of_time_inr_per_person_hour} per person-hour</li>
              <li>Annualised over {a.peak_hours_per_day} h/day × {a.operating_days_per_year} days</li>
            </ul>
            <p className="ops-muted">{data.scope.note}</p>
            {saved.total_cost_inr < 0 && (
              <p className="ops-muted">
                Negative here means the adaptive controller is <em>losing</em> to the fixed clock in
                this regime. Under heavy oversaturation every approach is saturated at once, so
                queue-chasing wins nothing and an even round-robin is hard to beat. See
                docs/BENCHMARKS.md.
              </p>
            )}
          </details>
        </>
      )}
    </Panel>
  )
}

/* --------------------------------------------------------------- benchmark */

function BenchTab() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = () => {
    setBusy(true); setError('')
    api('/api/benchmark/suite?steps=60')
      .then(setData).catch(e => setError(e.message)).finally(() => setBusy(false))
  }

  return (
    <Panel
      title="Controller comparison"
      blurb="Every controller, every seed, every disturbance — ranked. Averages alone would flatter a controller that starves one approach, so p95 and worst-case sit beside them."
      actions={<button onClick={run} disabled={busy}>{busy ? 'Running… (~10s)' : 'Run benchmark'}</button>}
    >
      <Loading error={error} busy={busy} empty={!data} />
      {data && (
        <>
          <p className="ops-muted">
            Best: <strong>{data.best_controller}</strong> · {data.seeds.length} seeds ×{' '}
            {data.scenarios.length} scenarios · {data.shielded ? 'safety shield active' : 'unshielded ablation'}
          </p>
          <div className="ops-table-wrap">
            <table className="ops-table">
              <thead>
                <tr>
                  <th>Controller</th><th>Avg queue</th><th>vs fixed</th><th>Mean delay</th>
                  <th>p95 delay</th><th>Worst wait</th><th>Person delay</th><th>Bus delay</th><th>Ped wait</th>
                </tr>
              </thead>
              <tbody>
                {data.summary.map(r => (
                  <tr key={r.controller}>
                    <td><strong>{r.controller}</strong></td>
                    <td>{num(r.mean_average_queue, 1)}</td>
                    <td className={r.queue_improvement_vs_fixed_pct > 0 ? 'good' : ''}>
                      {r.queue_improvement_vs_fixed_pct > 0 ? '−' : '+'}
                      {Math.abs(r.queue_improvement_vs_fixed_pct).toFixed(1)}%
                    </td>
                    <td>{num(r.mean_vehicle_delay, 1)}</td>
                    <td>{num(r.mean_p95_vehicle_delay, 1)}</td>
                    <td>{num(r.mean_worst_approach_wait, 0)}</td>
                    <td>{num(r.mean_person_delay, 1)}</td>
                    <td>{num(r.mean_bus_delay, 1)}</td>
                    <td>{num(r.mean_pedestrian_delay, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="ops-muted">
            Ranked by vehicle queue. <code>transit-priority-v1</code> optimises person delay instead,
            so read its person and bus columns rather than its rank. {data.note}
          </p>
        </>
      )}
    </Panel>
  )
}

/* -------------------------------------------------------------- green wave */

function WaveTab() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [cycle, setCycle] = useState(16)
  const [green, setGreen] = useState(8)

  const load = useCallback(() => {
    api(`/api/greenwave?corridor=J1,J2,J4&cycle=${cycle}&green=${green}`)
      .then(setData).catch(e => setError(e.message))
  }, [cycle, green])

  useEffect(() => { load() }, [load])

  // Time-space diagram: time across, distance along the corridor down.
  const W = 720, H = 300, PAD = 54
  const span = data ? data.cycle_ticks * 4 : 1
  const maxX = data ? Math.max(...data.junctions.map(j => j.position_m)) || 1 : 1
  const tx = t => PAD + (t / span) * (W - PAD - 20)
  const ty = x => PAD + (x / maxX) * (H - PAD - 30)

  return (
    <Panel
      title="Corridor coordination"
      blurb="Green bars are when each junction is open; diagonals are a platoon travelling the corridor. A working green wave shows as a clear diagonal channel through the bars."
      actions={
        <span className="ops-inline">
          <label>Cycle<input type="number" min="8" max="40" value={cycle}
                 onChange={e => setCycle(Number(e.target.value))} /></label>
          <label>Green<input type="number" min="2" max="30" value={green}
                 onChange={e => setGreen(Number(e.target.value))} /></label>
        </span>
      }
    >
      <Loading error={error} empty={!data} />
      {data && (
        <>
          <div className="ops-stats">
            <Stat label="Through band" value={`${num(data.band.coordinated_seconds, 0)} s`}
                  hint="departure window that clears every junction" tone="good" />
            <Stat label="Band efficiency" value={`${num(data.band.efficiency_pct, 0)}%`}
                  hint={`uncoordinated: ${num(data.band.uncoordinated_efficiency_pct, 0)}%`} />
            <Stat label="Stops avoided" value={data.band.stops_avoided_per_platoon}
                  hint="per platoon, per pass" />
            <Stat label="Progression speed" value={`${data.speed_kmph} km/h`} />
          </div>

          <svg className="ops-tsd" viewBox={`0 0 ${W} ${H}`} role="img"
               aria-label="Time-space diagram of the coordinated corridor">
            <line x1={PAD} y1={PAD - 14} x2={PAD} y2={H - 20} className="tsd-axis" />
            <line x1={PAD} y1={H - 20} x2={W - 20} y2={H - 20} className="tsd-axis" />
            <text x={W - 20} y={H - 6} textAnchor="end" className="tsd-label">time →</text>
            <text x={6} y={PAD - 20} className="tsd-label">distance along corridor ↓</text>

            {data.junctions.map(j => (
              <g key={j.id}>
                <text x={PAD - 10} y={ty(j.position_m) + 4} textAnchor="end" className="tsd-label">{j.id}</text>
                <line x1={PAD} y1={ty(j.position_m)} x2={W - 20} y2={ty(j.position_m)} className="tsd-grid" />
                {j.green_windows.filter(w => w[0] < span).map((w, i) => (
                  <rect key={i} x={tx(w[0])} y={ty(j.position_m) - 7}
                        width={Math.max(2, tx(Math.min(w[1], span)) - tx(w[0]))} height={14}
                        className="tsd-green" />
                ))}
              </g>
            ))}

            {data.trajectories.map((line, i) => (
              <polyline key={i} className="tsd-traj"
                        points={line.filter(p => p.t <= span).map(p => `${tx(p.t)},${ty(p.x)}`).join(' ')} />
            ))}
          </svg>
          <p className="ops-muted">{data.note}</p>
        </>
      )}
    </Panel>
  )
}

/* --------------------------------------------------------------- emergency */

function EmergencyTab() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = () => {
    setBusy(true); setError('')
    api('/api/emergency/comparison?steps=140&seed=7&scenario=rush')
      .then(setData).catch(e => setError(e.message)).finally(() => setBusy(false))
  }

  return (
    <Panel
      title="Ambulance through the corridor"
      blurb="The same ambulance, the same traffic, the same seed — with and without signal preemption."
      actions={<button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Run comparison'}</button>}
    >
      <Loading error={error} busy={busy} empty={!data} />
      {data && (
        <>
          <div className="ops-stats">
            <Stat label="Without preemption"
                  value={`${num(data.without_preemption.emergency.travel_ticks * 5, 0)} s`}
                  hint={`${data.without_preemption.emergency.delay_ticks} ticks stopped at red`} tone="warn" />
            <Stat label="With preemption"
                  value={`${num(data.with_preemption.emergency.travel_ticks * 5, 0)} s`}
                  hint={`${data.with_preemption.emergency.delay_ticks} ticks stopped at red`} tone="good" />
            <Stat label="Time saved" value={`${num(data.saved_seconds, 0)} s`}
                  hint={`${num(data.improvement_pct, 1)}% faster`} tone="good" />
            <Stat label="Red lights avoided" value={data.red_light_waits_avoided} />
          </div>

          <h4>What the rest of the traffic paid</h4>
          <p className="ops-muted">
            Measured against the same controller on the same seed with no ambulance dispatched,
            so this is the cost of priority itself and not a difference between controllers.
          </p>
          <div className="ops-stats">
            <Stat label="Extra mean delay" value={`${num(data.cost_of_priority.extra_mean_vehicle_delay, 2)} ticks`} />
            <Stat label="Throughput given up" value={data.cost_of_priority.throughput_given_up} />
          </div>
          <p className="ops-muted">{data.note}</p>
        </>
      )}
    </Panel>
  )
}

/* ----------------------------------------------------------------- what-if */

function WhatIfTab() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    demand_multiplier: 1.0, weather: 'clear', pedestrian_rate: 1.0, closure: 'none',
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const run = () => {
    setBusy(true); setError('')
    const closure = form.closure === 'none' ? null
      : { kind: form.closure, junction: 'J3', direction: form.closure.startsWith('detector') ? 'west' : null }
    api('/api/whatif', {
      method: 'POST',
      body: JSON.stringify({
        controllers: ['fixed-time', 'predictive-pressure-v2', 'transit-priority-v1'],
        baseline: 'fixed-time', seeds: [3, 7, 11, 19, 29], steps: 120,
        demand_multiplier: Number(form.demand_multiplier),
        weather: form.weather,
        pedestrian_rate: Number(form.pedestrian_rate),
        lane_closure: closure,
      }),
    }).then(setData).catch(e => setError(e.message)).finally(() => setBusy(false))
  }

  return (
    <Panel
      title="What if conditions change?"
      blurb="One run is an anecdote. Each question is replayed across several seeds under both controllers, so the answer comes with an interval instead of a single number."
    >
      <div className="ops-form">
        <label>Demand
          <input type="range" min="0.5" max="2.5" step="0.1" value={form.demand_multiplier}
                 onChange={e => set('demand_multiplier', e.target.value)} />
          <span>{Number(form.demand_multiplier).toFixed(1)}×</span>
        </label>
        <label>Footfall
          <input type="range" min="0" max="5" step="0.5" value={form.pedestrian_rate}
                 onChange={e => set('pedestrian_rate', e.target.value)} />
          <span>{Number(form.pedestrian_rate).toFixed(1)}×</span>
        </label>
        <label>Weather
          <select value={form.weather} onChange={e => set('weather', e.target.value)}>
            {WEATHER.map(w => <option key={w} value={w}>{w}</option>)}
          </select>
        </label>
        <label>Infrastructure
          <select value={form.closure} onChange={e => set('closure', e.target.value)}>
            <option value="none">All healthy</option>
            <option value="detector-dropout">Detector failed at J3</option>
            <option value="comms-loss">Comms lost at J3</option>
            <option value="signal-fault">Signal head failed at J3</option>
          </select>
        </label>
        <button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Answer this'}</button>
      </div>

      <Loading error={error} busy={busy} empty={!data} />
      {data && (
        <>
          <div className="ops-table-wrap">
            <table className="ops-table">
              <thead>
                <tr><th>Controller</th><th>Avg queue (95% CI)</th><th>p95 delay</th>
                    <th>Person delay</th><th>Change vs fixed-time</th></tr>
              </thead>
              <tbody>
                {data.results.map(r => {
                  const q = r.metrics.average_network_queue
                  const d = r.vs_baseline?.average_network_queue
                  return (
                    <tr key={r.controller}>
                      <td><strong>{r.controller}</strong></td>
                      <td>{num(q.mean, 1)} <em>[{num(q.ci_low, 1)}, {num(q.ci_high, 1)}]</em></td>
                      <td>{num(r.metrics.p95_vehicle_delay.mean, 1)}</td>
                      <td>{num(r.metrics.mean_person_delay.mean, 1)}</td>
                      <td>
                        {d ? (
                          <span className={d.significant ? (d.mean > 0 ? 'good' : 'bad') : 'ops-muted'}>
                            {d.mean > 0 ? '−' : '+'}{Math.abs(d.improvement_pct).toFixed(1)}%
                            {d.significant ? '' : ' (within noise)'}
                          </span>
                        ) : <span className="ops-muted">baseline</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="ops-muted">{data.reading}</p>
        </>
      )}
    </Panel>
  )
}

/* --------------------------------------------------------- calibration/data */

function DataTab() {
  const [csv, setCsv] = useState(
    'junction,direction,vehicles_per_hour,buses_per_hour\n' +
    'J1,north,1450,90\nJ1,west,980,40\nJ2,north,1100,55\nJ2,east,1250,60\n'
  )
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [vision, setVision] = useState(null)
  const [hil, setHil] = useState('')

  useEffect(() => {
    api('/api/vision/status').then(setVision).catch(() => {})
    fetch(`${API}/api/hil/state?format=wire`).then(r => r.text()).then(setHil).catch(() => {})
  }, [])

  const run = () => {
    setBusy(true); setError(''); setReport(null)
    api('/api/calibrate', { method: 'POST', body: JSON.stringify({ csv_text: csv, verify_steps: 240 }) })
      .then(setReport).catch(e => setError(e.message)).finally(() => setBusy(false))
  }

  return (
    <>
      <Panel
        title="Calibrate to real counts"
        blurb="Paste counts from a traffic survey or an ATCS export. Demand is fitted per approach, then replayed to check the fit reproduces what was measured."
        actions={<button onClick={run} disabled={busy}>{busy ? 'Fitting…' : 'Fit and verify'}</button>}
      >
        <textarea className="ops-csv" rows={6} value={csv} onChange={e => setCsv(e.target.value)} spellCheck={false} />
        <Loading error={error} busy={busy} />
        {report && (
          <>
            <div className="ops-stats">
              <Stat label="Approaches fitted" value={report.approaches_fitted} />
              <Stat label="Mean absolute error" value={`${num(report.mean_absolute_error_pct, 1)}%`}
                    tone={report.mean_absolute_error_pct < 15 ? 'good' : 'warn'} />
              <Stat label="Bus share" value={report.bus_share === null ? '—' : `${(report.bus_share * 100).toFixed(1)}%`} />
              <Stat label="Base flow" value={`${report.base_vehicles_per_hour} veh/h`}
                    hint="unscaled arrival process" />
            </div>
            <div className="ops-table-wrap">
              <table className="ops-table">
                <thead><tr><th>Approach</th><th>Observed</th><th>Simulated</th><th>Error</th><th>Scale</th></tr></thead>
                <tbody>
                  {report.verification.map((r, i) => (
                    <tr key={i}>
                      <td>{r.junction} {r.direction}</td>
                      <td>{r.observed_vph}</td>
                      <td>{r.calibratable ? r.simulated_vph : <em>upstream-fed</em>}</td>
                      <td>{r.calibratable ? `${r.error_pct}%` : '—'}</td>
                      <td>{r.calibratable ? r.scale : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="ops-muted">{report.note}</p>
          </>
        )}
      </Panel>

      <Panel title="Sensing and hardware"
             blurb="Camera-based state estimation, and the live feed a physical model junction consumes.">
        <div className="ops-stats">
          <Stat label="Vision detector"
                value={vision?.available ? 'Ready' : 'Not installed'}
                hint={vision?.weights || 'install ultralytics for offline use'}
                tone={vision?.available ? 'good' : 'warn'} />
          <Stat label="Signal-head feed" value={hil ? 'Live' : '—'}
                hint="polled by the ESP32 every 500 ms" />
        </div>
        <p className="ops-muted">
          Wire format currently on the line: <code>{hil || '—'}</code><br />
          Aspects are NS, EW, PED — G green, A amber, R red. Uploading a frame to{' '}
          <code>/api/vision/analyse</code> returns per-lane counts with a confidence score;
          low-confidence lanes must be corrected by an operator before they can seed the controller.
        </p>
      </Panel>
    </>
  )
}

/* -------------------------------------------------------------------- shell */

const TAB_VIEWS = {
  health: HealthTab, why: WhyTab, impact: ImpactTab, bench: BenchTab,
  wave: WaveTab, ev: EmergencyTab, whatif: WhatIfTab, data: DataTab,
}

export default function OpsConsole() {
  const [tab, setTab] = useState('health')
  const View = TAB_VIEWS[tab]

  return (
    <section className="ops">
      <div className="ops-head">
        <h2>Operations console</h2>
        <p>
          The questions a city asks after "does it work?" — what it is worth, whether it is fair,
          what happens when it breaks, why it decided that, and what happens if demand grows.
        </p>
      </div>
      <nav className="ops-tabs">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? 'sel' : ''} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>
      <div className="ops-body"><View /></div>
    </section>
  )
}
