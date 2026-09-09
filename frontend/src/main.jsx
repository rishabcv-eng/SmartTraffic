import React, { useEffect, useRef, useState } from 'react'
import OpsConsole from './OpsConsole.jsx'
import { createRoot } from 'react-dom/client'
import * as THREE from 'three'
import './styles.css'

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

/* ------------------------------------------------------------------ */
/* Emergency vehicle catalogue                                         */
/* Falls back to these if /api/priority/types is unreachable.          */
/* ------------------------------------------------------------------ */
const EV_FALLBACK = {
  ambulance: { priority: 100, lead_seconds: 12, hold_seconds: 20, max_delay_seconds: 0 },
  fire: { priority: 95, lead_seconds: 14, hold_seconds: 22, max_delay_seconds: 0 },
  'disaster-response': { priority: 90, lead_seconds: 12, hold_seconds: 20, max_delay_seconds: 2 },
  police: { priority: 80, lead_seconds: 10, hold_seconds: 16, max_delay_seconds: 3 },
  vip: { priority: 55, lead_seconds: 8, hold_seconds: 12, max_delay_seconds: 8 },
}

const EV_META = {
  ambulance: { label: 'Ambulance', icon: '🚑', body: 0xf2f4f6, beacon: 0xff3b3b },
  fire: { label: 'Fire service', icon: '🚒', body: 0xd62828, beacon: 0xff6b2c },
  'disaster-response': { label: 'Disaster response', icon: '🛟', body: 0xf59e0b, beacon: 0xffd166 },
  police: { label: 'Police', icon: '🚓', body: 0x1d4ed8, beacon: 0x4cc9f0 },
  vip: { label: 'VIP convoy', icon: '🚔', body: 0x111827, beacon: 0x9d4edd },
}

const APPROACHES = [
  ['north', 'From North', 'NS'],
  ['south', 'From South', 'NS'],
  ['east', 'From East', 'EW'],
  ['west', 'From West', 'EW'],
]

const DEMOS = [
  { id:'surge', n:1, title:'Peak-hour surge',
    line:'One arm floods. The clock keeps serving an empty road; we follow the demand.',
    scenario:'north-surge', incident:'none', ev:null,
    watch:'Watch the fixed side hold green for an empty east–west road while north backs up.' },
  { id:'accident', n:2, title:'Accident blocks an approach',
    line:'East discharge collapses to 1 vehicle per tick for 55 ticks. Capacity, not demand, is the problem.',
    scenario:'north-surge', incident:'accident-east', ev:null,
    watch:'The clock keeps allocating green to a lane that cannot move. We reallocate it.' },
  { id:'ambulance', n:3, title:'Ambulance through a flooded junction',
    line:'Waterlogging halves discharge everywhere, then an ambulance is dispatched into it.',
    scenario:'north-surge', incident:'waterlogging', ev:{type:'ambulance',approach:'south'},
    watch:'Preemption clears a corridor; the fixed signal makes the ambulance wait at red.' },
]

const VEHICLES = {
  bike:  { label:'Two-wheeler', pcu:0.5, occ:1.4,  share:.46, len:2.6,  color:0x8fa3b5, w:.85, h:.62, d:1.9 },
  auto:  { label:'Auto-rickshaw', pcu:0.8, occ:2.5, share:.16, len:3.4, color:0xd8c65a, w:1.45, h:1.35, d:2.5 },
  car:   { label:'Car / van', pcu:1.0, occ:2.2, share:.28, len:5.4,     color:0x7f8b96, w:2.0, h:.85, d:4.0 },
  bus:   { label:'Bus / lorry', pcu:3.0, occ:32, share:.10, len:10.5,   color:0xc98b4b, w:2.45, h:2.6, d:9.0 },
}
const VKEYS = Object.keys(VEHICLES)
const pcuOf    = list => (list||[]).reduce((s,t)=>s+VEHICLES[t].pcu,0)
/* A bus is 3 PCU of road but carries ~32 people. Optimising vehicle delay quietly
   penalises the mode that moves the most people — so we weigh occupancy too. */
const peopleOf = list => (list||[]).reduce((s,t)=>s+VEHICLES[t].occ,0)

/* ------------------------------------------------------------------ */
/* Chennai baseline — TomTom Traffic Index 2025                        */
/* tomtom.com/traffic-index/chennai-traffic/                           */
/* Used to calibrate demand profiles and to state the real-world       */
/* baseline our simulated delay is measured against.                   */
/* ------------------------------------------------------------------ */
const CHENNAI = {
  source: 'TomTom Traffic Index 2025 — Chennai',
  travelTime10km: '31 min 15 s',
  avgCongestion: 58.6,
  morningCongestion: 69.4,
  eveningCongestion: 100.9,
  morningSpeed: 17.7,
  eveningSpeed: 14.6,
  rushSpeed: 16,
  hoursLostPerYear: 132,
  worstDay: '17 Oct 2025 — 95% average, 154% at 6 pm',
  kmIn15min: 4.8,
}

/* Demand multiplier derived from the measured congestion level:
   a 100.9% congestion level means a trip takes ~2x the free-flow time. */
const PROFILES = {
  'off-peak':      { label:'Off-peak · 58.6% congestion',        mult:0.62, cong:CHENNAI.avgCongestion },
  'morning-peak':  { label:'Morning peak · 69.4% · 17.7 km/h',   mult:0.85, cong:CHENNAI.morningCongestion },
  'evening-peak':  { label:'Evening peak · 100.9% · 14.6 km/h',  mult:1.15, cong:CHENNAI.eveningCongestion },
  'worst-day':     { label:'Worst day 17 Oct 2025 · 154% at 6pm', mult:1.55, cong:154 },
}

const EV_START_DIST = 110      // distance units behind the stop line at dispatch
const EV_SPEED = 7.5           // units per tick

function Metric({ label, value, hint }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>
}

function phaseLabel(phase) {
  if (phase === 'NS') return 'N/S GREEN'
  if (phase === 'EW') return 'E/W GREEN'
  if (phase === 'AMBER') return 'AMBER · ALL RED NEXT'
  return phase || 'UNKNOWN'
}

function SignalHead({ phase, axis }) {
  const green = phase === axis
  const amber = phase === 'AMBER'
  return <div className="signal-head" aria-label={`${axis} signal`}>
    <span className={!green && !amber ? 'lamp red on' : 'lamp red'} />
    <span className={amber ? 'lamp amber on' : 'lamp amber'} />
    <span className={green ? 'lamp green on' : 'lamp green'} />
  </div>
}

/* ------------------------------------------------------------------ */
/* Scene dressing helpers.                                             */
/* A junction reads as a place, not a diagram, when it has depth cues: */
/* lit windows, street lighting, kerbs and people. These build the     */
/* textures and sprites for that once, then everything reuses them.    */
/* ------------------------------------------------------------------ */

/* Surface noise. Flat untextured asphalt is the single biggest reason a
   3D scene reads as a diagram: real surfaces are never one uniform colour.
   Cheap canvas noise breaks that up and gives the light something to catch. */
const _noiseCache = {}
function noiseTexture(baseHex, spread, repeat){
  const key = `${baseHex}-${spread}-${repeat}`
  if(_noiseCache[key]) return _noiseCache[key]
  const S = 128
  const c = document.createElement('canvas'); c.width = c.height = S
  const g = c.getContext('2d')
  const base = new THREE.Color(baseHex)
  g.fillStyle = `#${base.getHexString()}`; g.fillRect(0,0,S,S)
  for(let i=0;i<5200;i++){
    const l = (Math.random()-.5) * spread
    const col = base.clone().offsetHSL(0,0,l)
    g.fillStyle = `#${col.getHexString()}`
    g.fillRect(Math.random()*S, Math.random()*S, 1+Math.random()*2.4, 1+Math.random()*2.4)
  }
  const t = new THREE.CanvasTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.repeat.set(repeat, repeat)
  _noiseCache[key] = t
  return t
}

/* Soft radial glow. Used for signal bulbs and lamp spill — far cheaper
   than a post-processing bloom pass and works on weak GPUs. */
let _glowTex = null
function glowTexture(){
  if(_glowTex) return _glowTex
  const c = document.createElement('canvas'); c.width = c.height = 64
  const g = c.getContext('2d')
  const grad = g.createRadialGradient(32,32,0,32,32,32)
  grad.addColorStop(0,'rgba(255,255,255,1)')
  grad.addColorStop(.35,'rgba(255,255,255,.55)')
  grad.addColorStop(1,'rgba(255,255,255,0)')
  g.fillStyle = grad; g.fillRect(0,0,64,64)
  _glowTex = new THREE.CanvasTexture(c)
  return _glowTex
}

function makeGlow(color, scale){
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTexture(), color, transparent:true, opacity:0,
    blending: THREE.AdditiveBlending, depthWrite:false,
  }))
  s.scale.set(scale,scale,1)
  return s
}

/* Facade texture with a window grid. Returns a colour map plus a matching
   emissive map so only the lit windows glow after dark. */
function makeFacade(baseHex, litHex, seed){
  const W = 64, H = 128, cols = 6, rows = 12
  const mk = () => { const c = document.createElement('canvas'); c.width=W; c.height=H; return c }
  const cMap = mk(), eMap = mk()
  const cg = cMap.getContext('2d'), eg = eMap.getContext('2d')
  const base = new THREE.Color(baseHex), lit = new THREE.Color(litHex)

  cg.fillStyle = `#${base.getHexString()}`; cg.fillRect(0,0,W,H)
  eg.fillStyle = '#000000'; eg.fillRect(0,0,W,H)

  /* Deterministic per-building so a facade does not reshuffle every frame. */
  let n = seed * 9301 + 49297
  const rnd = () => { n = (n * 9301 + 49297) % 233280; return n / 233280 }

  const pw = W/cols*.56, ph = H/rows*.42
  for(let r=0;r<rows;r++){
    for(let col=0;col<cols;col++){
      const x = (col + .5) * (W/cols) - pw/2
      const y = (r + .5) * (H/rows) - ph/2
      const on = rnd() > .42
      cg.fillStyle = on ? `#${lit.getHexString()}` : `#${base.clone().offsetHSL(0,0,-.06).getHexString()}`
      cg.fillRect(x,y,pw,ph)
      if(on){
        eg.fillStyle = `#${lit.getHexString()}`
        eg.fillRect(x,y,pw,ph)
      }
    }
  }
  const t1 = new THREE.CanvasTexture(cMap), t2 = new THREE.CanvasTexture(eMap)
  return { map:t1, emissiveMap:t2 }
}

/* Crosswalks. A pedestrian may only cross an arm while the traffic on that
   arm is stopped, so the people on screen are a readable signal of what the
   controller is doing rather than decoration. */
const CROSSWALKS = [
  { id:'n', axis:'x', fixed:-15, from:-12, to:12, safeOn:'EW' },
  { id:'s', axis:'x', fixed: 15, from:-12, to:12, safeOn:'EW' },
  { id:'w', axis:'z', fixed:-15, from:-12, to:12, safeOn:'NS' },
  { id:'e', axis:'z', fixed: 15, from:-12, to:12, safeOn:'NS' },
]

const SHIRTS = [0xe06c5a,0x4f9dd6,0xe8b64c,0x6fbf8a,0xb98fd1,0xe0e3e6,0xd97fa8,0x5fc7c2]

function makePerson(i){
  const g = new THREE.Group()
  const shirt = SHIRTS[i % SHIRTS.length]
  const legs = new THREE.Mesh(new THREE.BoxGeometry(.34,.62,.26),
    new THREE.MeshStandardMaterial({ color:0x2f3a45, roughness:.9 }))
  legs.position.y = .31
  const torso = new THREE.Mesh(new THREE.BoxGeometry(.42,.62,.3),
    new THREE.MeshStandardMaterial({ color:shirt, roughness:.85 }))
  torso.position.y = .93
  const head = new THREE.Mesh(new THREE.SphereGeometry(.17,12,12),
    new THREE.MeshStandardMaterial({ color:0x9a6b4f, roughness:.8 }))
  head.position.y = 1.36
  ;[legs,torso,head].forEach(m=>{ m.castShadow = true })
  g.add(legs,torso,head)
  g.userData = { legs, torso, phase: Math.random()*Math.PI*2 }
  return g
}

/* ------------------------------------------------------------------ */
/* Vehicle model kit.                                                  */
/* Four classes share a road here and the whole PCU argument depends   */
/* on telling them apart at a glance, so each gets its own silhouette  */
/* and its own palette rather than a tinted box:                       */
/*   two-wheeler  small, dark, visible rider                           */
/*   auto         three wheels, yellow body, black canopy              */
/*   car          low, four wheels, glasshouse, mixed colours          */
/*   bus          tall and long, window band, six wheels               */
/* Geometry and materials are built once and shared by every instance; */
/* with ~400 pooled vehicles per scene, per-instance materials would   */
/* dominate both memory and draw-call setup.                           */
/* ------------------------------------------------------------------ */
const BODY_TONES = {
  bike: [0x2d3742, 0x6b2f33, 0x27424a],
  auto: [0xe3b505, 0xd9a904, 0xeabf20],
  car:  [0xdfe3e6, 0x39506b, 0x8d3f3f, 0x4a5560, 0xb9bec2],
  bus:  [0x2f6fb5, 0xd06a2a, 0x3f7d5a],
}

let _vkit = null
function vehicleKit(){
  if(_vkit) return _vkit
  const M = (o) => new THREE.MeshStandardMaterial(o)
  const wheel = new THREE.CylinderGeometry(.34,.34,.26,14)
  wheel.rotateZ(Math.PI/2)
  const wheelSm = new THREE.CylinderGeometry(.3,.3,.18,12)
  wheelSm.rotateZ(Math.PI/2)

  _vkit = {
    geo: { wheel, wheelSm, box: new THREE.BoxGeometry(1,1,1) },
    mat: {
      tyre:  M({ color:0x15181b, roughness:.95 }),
      glass: M({ color:0x1d2c38, roughness:.18, metalness:.55 }),
      trim:  M({ color:0x20262b, roughness:.8 }),
      canopy:M({ color:0x14181c, roughness:.85 }),
      head:  M({ color:0xfff6e0, emissive:0xffe8b8, emissiveIntensity:1.5, roughness:.4 }),
      tail:  M({ color:0x5a1414, emissive:0xff2a2a, emissiveIntensity:1.2, roughness:.5 }),
      rider: M({ color:0x394654, roughness:.9 }),
      helmet:M({ color:0xd8dde1, roughness:.5 }),
      body: Object.fromEntries(Object.entries(BODY_TONES).map(([k, tones]) =>
        [k, tones.map(c => M({ color:c, roughness:.55, metalness:.15 }))])),
    },
  }
  return _vkit
}

/* Box helper on the shared unit cube, so nothing allocates new geometry. */
function part(kit, mat, w, h, d, x, y, z, shadow){
  const m = new THREE.Mesh(kit.geo.box, mat)
  m.scale.set(w,h,d); m.position.set(x,y,z)
  if(shadow) m.castShadow = true
  return m
}

function buildVehicle(kind, variantIdx){
  const kit = vehicleKit()
  const v = VEHICLES[kind]
  const g = new THREE.Group()
  const tones = kit.mat.body[kind]
  const body = tones[variantIdx % tones.length]
  const addWheel = (geo, x, y, z) => {
    const w = new THREE.Mesh(geo, kit.mat.tyre)
    w.position.set(x,y,z); g.add(w)
  }

  if(kind === 'bike'){
    addWheel(kit.geo.wheelSm, 0, .3, -v.d*.34)
    addWheel(kit.geo.wheelSm, 0, .3,  v.d*.34)
    g.add(part(kit, body, v.w*.5, .34, v.d*.55, 0, .62, 0, true))
    g.add(part(kit, kit.mat.trim, v.w*.95, .1, .5, 0, .92, -v.d*.3, false))   // handlebar
    g.add(part(kit, kit.mat.rider, .46, .72, .38, 0, 1.12, v.d*.06, true))    // rider
    const helmet = new THREE.Mesh(new THREE.SphereGeometry(.19,10,10), kit.mat.helmet)
    helmet.position.set(0,1.6,v.d*.04); helmet.castShadow = true; g.add(helmet)
    g.add(part(kit, kit.mat.head, .16, .12, .1, 0, .78, -v.d*.46, false))
  }

  else if(kind === 'auto'){
    addWheel(kit.geo.wheelSm, 0, .3, -v.d*.36)                                // single front
    addWheel(kit.geo.wheelSm, -v.w*.42, .3, v.d*.3)
    addWheel(kit.geo.wheelSm,  v.w*.42, .3, v.d*.3)
    g.add(part(kit, body, v.w, .78, v.d*.9, 0, .74, 0, true))                 // yellow tub
    g.add(part(kit, kit.mat.canopy, v.w*1.02, .5, v.d*.78, 0, 1.4, .12, true))// black canopy
    g.add(part(kit, kit.mat.glass, v.w*.8, .42, .1, 0, 1.26, -v.d*.44, false))// windscreen
    g.add(part(kit, kit.mat.canopy, .1, .62, .1, -v.w*.46, 1.35, -v.d*.34, false))
    g.add(part(kit, kit.mat.canopy, .1, .62, .1,  v.w*.46, 1.35, -v.d*.34, false))
    g.add(part(kit, kit.mat.head, .18, .14, .08, 0, .82, -v.d*.47, false))
    g.add(part(kit, kit.mat.tail, .5, .12, .08, 0, .9, v.d*.46, false))
  }

  else if(kind === 'car'){
    const y = .38
    addWheel(kit.geo.wheel, -v.w*.44, .34, -v.d*.31)
    addWheel(kit.geo.wheel,  v.w*.44, .34, -v.d*.31)
    addWheel(kit.geo.wheel, -v.w*.44, .34,  v.d*.31)
    addWheel(kit.geo.wheel,  v.w*.44, .34,  v.d*.31)
    g.add(part(kit, body, v.w, .62, v.d, 0, y+.28, 0, true))                  // lower body
    g.add(part(kit, body, v.w*.9, .46, v.d*.5, 0, y+.78, .18, true))          // cabin
    g.add(part(kit, kit.mat.glass, v.w*.92, .34, v.d*.46, 0, y+.8, .16, false))
    g.add(part(kit, kit.mat.head, .34, .14, .08, -v.w*.3, y+.3, -v.d*.5, false))
    g.add(part(kit, kit.mat.head, .34, .14, .08,  v.w*.3, y+.3, -v.d*.5, false))
    g.add(part(kit, kit.mat.tail, .34, .14, .08, -v.w*.3, y+.34, v.d*.5, false))
    g.add(part(kit, kit.mat.tail, .34, .14, .08,  v.w*.3, y+.34, v.d*.5, false))
  }

  else { // bus
    const h = v.h
    ;[-v.d*.34, v.d*.02, v.d*.36].forEach(z=>{
      addWheel(kit.geo.wheel, -v.w*.44, .34, z)
      addWheel(kit.geo.wheel,  v.w*.44, .34, z)
    })
    g.add(part(kit, body, v.w, h, v.d, 0, h/2 + .34, 0, true))
    /* window band all the way down the flank: the clearest bus cue */
    g.add(part(kit, kit.mat.glass, v.w*1.01, .86, v.d*.9, 0, h*.78, .1, false))
    g.add(part(kit, kit.mat.glass, v.w*.9, .9, .12, 0, h*.72, -v.d*.5, false))
    g.add(part(kit, kit.mat.trim, v.w*1.02, .16, v.d*.96, 0, h*.5, 0, false))
    g.add(part(kit, kit.mat.head, .7, .18, .1, 0, h*.98, -v.d*.49, false))    // route board
    g.add(part(kit, kit.mat.head, .36, .16, .08, -v.w*.3, .62, -v.d*.5, false))
    g.add(part(kit, kit.mat.head, .36, .16, .08,  v.w*.3, .62, -v.d*.5, false))
    g.add(part(kit, kit.mat.tail, .36, .16, .08, -v.w*.3, .7, v.d*.5, false))
    g.add(part(kit, kit.mat.tail, .36, .16, .08,  v.w*.3, .7, v.d*.5, false))
  }

  g.visible = false
  return g
}

function IntersectionTwin({ frame, mode, title, accent, phase, ev, preempting, frames, tick, winning, peers }) {
  const mount = useRef(null)
  const ctx = useRef(null)

  useEffect(() => {
    const host = mount.current
    if (!host) return

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0e141a)
    scene.fog = new THREE.Fog(0x0e141a, 62, 168)
    const camera = new THREE.PerspectiveCamera(55, 1.6, 0.1, 250)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    /* Filmic tone mapping and a correct output colour space. Without these,
       three.js renders linear values straight to screen, which is what makes
       an untouched scene look flat and plasticky. */
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.15
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    host.innerHTML = ''
    host.appendChild(renderer.domElement)

    /* Dusk lighting: cool skylight bounced off the ground, one warm key that
       casts the shadows, and a dim cool fill so shadowed faces keep some
       shape instead of going flat black. */
    scene.add(new THREE.HemisphereLight(0x93b4d6, 0x35302c, .85))
    scene.add(new THREE.AmbientLight(0x4a5a68, .18))
    const sun = new THREE.DirectionalLight(0xffd9b0, 1.45)
    sun.position.set(42, 58, 26)
    sun.castShadow = true
    sun.shadow.mapSize.set(1024, 1024)
    sun.shadow.camera.near = 10
    sun.shadow.camera.far = 190
    sun.shadow.camera.left = -70; sun.shadow.camera.right = 70
    sun.shadow.camera.top = 70;   sun.shadow.camera.bottom = -70
    sun.shadow.bias = -0.0012
    sun.shadow.normalBias = 0.03
    scene.add(sun)
    const fill = new THREE.DirectionalLight(0x8fb0d8, .35)
    fill.position.set(-35, 26, -30)
    scene.add(fill)

    const ground = new THREE.Mesh(new THREE.PlaneGeometry(180, 180),
      new THREE.MeshStandardMaterial({ map: noiseTexture(0x22282d, .10, 14), roughness: 1 }))
    ground.rotation.x = -Math.PI / 2
    ground.receiveShadow = true
    scene.add(ground)

    const roadMat = new THREE.MeshStandardMaterial({
      map: noiseTexture(0x3a4045, .07, 9), roughness: .92, metalness: .02 })
    const ns = new THREE.Mesh(new THREE.PlaneGeometry(24, 150), roadMat)
    ns.rotation.x = -Math.PI / 2; ns.position.y = .01; ns.receiveShadow = true; scene.add(ns)
    const ew = new THREE.Mesh(new THREE.PlaneGeometry(150, 24), roadMat)
    ew.rotation.x = -Math.PI / 2; ew.position.y = .012; ew.receiveShadow = true; scene.add(ew)

    /* Road paint is worn and lit by the scene, not self-illuminated. */
    const markMat = new THREE.MeshStandardMaterial({ color: 0xb9bdbd, roughness: .8 })
    const stripe = (x, z, w, d) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), markMat)
      m.rotation.x = -Math.PI / 2; m.position.set(x, .026, z); scene.add(m)
    }
    for (let z = -68; z <= 68; z += 10) if(Math.abs(z) > 18) stripe(0, z, .16, 4.5)
    for (let x = -68; x <= 68; x += 10) if(Math.abs(x) > 18) stripe(x, 0, 4.5, .16)
    stripe(0, -16.3, 19, .45); stripe(0, 16.3, 19, .45)
    stripe(-16.3, 0, .45, 19); stripe(16.3, 0, .45, 19)

    /* ---------- kerbs and footpaths ---------- */
    const kerbMat = new THREE.MeshStandardMaterial({ color: 0x6b7278, roughness: .9 })
    const pathMat = new THREE.MeshStandardMaterial({
      map: noiseTexture(0x4e555c, .09, 10), roughness: 1 })
    ;[[-1,-1],[1,-1],[-1,1],[1,1]].forEach(([sx,sz])=>{
      const foot = new THREE.Mesh(new THREE.BoxGeometry(53,.5,53), pathMat)
      foot.position.set(sx*38.5, .25, sz*38.5); foot.receiveShadow = true; scene.add(foot)
      const k1 = new THREE.Mesh(new THREE.BoxGeometry(53,.62,.7), kerbMat)
      k1.position.set(sx*38.5, .31, sz*12.35); scene.add(k1)
      const k2 = new THREE.Mesh(new THREE.BoxGeometry(.7,.62,53), kerbMat)
      k2.position.set(sx*12.35, .31, sz*38.5); scene.add(k2)
    })

    /* ---------- zebra crossings on all four arms ---------- */
    /* Zebra crossings.
       Wide, bright bars with a faint emissive lift so they stay readable at
       dusk, plus a soft light panel beneath the crossing. The crossing is the
       thing a viewer needs to find first to understand where people walk, so
       it is deliberately the brightest paint on the road. */
    const zebraMat = new THREE.MeshStandardMaterial({
      color: 0xf4f7f8, roughness: .55, emissive: 0xdfe8ee, emissiveIntensity: .32 })
    const zebraGlowMat = new THREE.MeshBasicMaterial({
      map: glowTexture(), color: 0xbfd8ea, transparent: true, opacity: .13,
      blending: THREE.AdditiveBlending, depthWrite: false })
    const zebra = (x,z,horizontal) => {
      /* wash of light marking the crossing zone */
      const pad = new THREE.Mesh(
        horizontal ? new THREE.PlaneGeometry(30,11) : new THREE.PlaneGeometry(11,30), zebraGlowMat)
      pad.rotation.x = -Math.PI/2; pad.position.set(x,.028,z); scene.add(pad)
      for(let o=-10.4;o<=10.4;o+=2.6){
        const g = horizontal ? new THREE.PlaneGeometry(1.5,5.2) : new THREE.PlaneGeometry(5.2,1.5)
        const m = new THREE.Mesh(g, zebraMat)
        m.rotation.x = -Math.PI/2
        m.position.set(horizontal ? x+o : x, .042, horizontal ? z : z+o)
        m.receiveShadow = true
        scene.add(m)
      }
    }
    zebra(0,-15,true); zebra(0,15,true); zebra(-15,0,false); zebra(15,0,false)

    /* ---------- city block: varied heights, colours and lit windows ---------- */
    const BUILDING_TONES = [
      [0x4a5560,0xffd9a0],[0x565060,0xffcf8a],[0x3f5157,0xdfeaff],
      [0x60544a,0xffe0b0],[0x475a55,0xcfeee0],[0x54495c,0xffd4e6],
    ]
    const blocks = [
      [-40,-40,26,26],[ 40,-40,26,26],[-40, 40,26,26],[ 40, 40,26,26],
      [-72,-30,22,20],[ 72,-30,22,20],[-72, 34,22,20],[ 72, 34,22,20],
      [-30,-74,20,22],[ 34,-74,20,22],[-30, 74,20,22],[ 34, 74,20,22],
    ]
    blocks.forEach(([x,z,w,d], i) => {
      const h = 9 + ((i * 7) % 5) * 6
      const [base, lit] = BUILDING_TONES[i % BUILDING_TONES.length]
      const { map, emissiveMap } = makeFacade(base, lit, i + 1)
      map.wrapS = map.wrapT = emissiveMap.wrapS = emissiveMap.wrapT = THREE.RepeatWrapping
      map.repeat.set(Math.max(1,Math.round(w/9)), Math.max(1,Math.round(h/7)))
      emissiveMap.repeat.copy(map.repeat)
      const b = new THREE.Mesh(new THREE.BoxGeometry(w,h,d), new THREE.MeshStandardMaterial({
        map, emissiveMap, emissive: 0xffffff, emissiveIntensity: .85, roughness: .9,
      }))
      b.position.set(x, h/2 + .5, z); b.castShadow = true; b.receiveShadow = true; scene.add(b)
      /* roof slab reads as a parapet and stops the facade texture wrapping oddly */
      const roof = new THREE.Mesh(new THREE.BoxGeometry(w+.6,.8,d+.6),
        new THREE.MeshStandardMaterial({ color: 0x2f363d, roughness:1 }))
      roof.position.set(x, h + .9, z); scene.add(roof)
    })

    /* ---------- street trees on the footpaths ---------- */
    const trunkMat = new THREE.MeshStandardMaterial({ color:0x4a3a2c, roughness:1 })
    const leafMat  = new THREE.MeshStandardMaterial({ color:0x2f6d45, roughness:.95 })
    ;[[-17,-22],[-17,22],[17,-22],[17,22],[-22,-17],[22,-17],[-22,17],[22,17]].forEach(([x,z])=>{
      const tr = new THREE.Mesh(new THREE.CylinderGeometry(.2,.26,2.2), trunkMat)
      tr.position.set(x,1.6,z); scene.add(tr)
      const cr = new THREE.Mesh(new THREE.SphereGeometry(1.5,10,8), leafMat)
      cr.position.set(x,3.4,z); cr.scale.y = .82; cr.castShadow = true; scene.add(cr)
    })

    /* ---------- street lighting ---------- */
    const streetLamps = []
    const poleMat = new THREE.MeshStandardMaterial({ color:0x555d64, roughness:.8 })
    const addStreetLamp = (x,z,rotY) => {
      const g = new THREE.Group()
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(.15,.2,9), poleMat)
      pole.position.y = 4.5; g.add(pole)
      const arm = new THREE.Mesh(new THREE.BoxGeometry(2.6,.16,.16), poleMat)
      arm.position.set(1.3,8.9,0); g.add(arm)
      const headMat = new THREE.MeshStandardMaterial({
        color:0xfff0cf, emissive:0xffcf7a, emissiveIntensity:1.6, roughness:.5 })
      const head = new THREE.Mesh(new THREE.BoxGeometry(1.5,.3,.7), headMat)
      head.position.set(2.5,8.75,0); g.add(head)
      const glow = makeGlow(0xffc879, 7); glow.position.set(2.5,8.6,0); glow.material.opacity = .55
      g.add(glow)
      /* warm pool of light on the road surface */
      const pool = new THREE.Mesh(new THREE.PlaneGeometry(13,13),
        new THREE.MeshBasicMaterial({ map: glowTexture(), color:0xffc879, transparent:true,
          opacity:.20, blending: THREE.AdditiveBlending, depthWrite:false }))
      pool.rotation.x = -Math.PI/2; pool.position.set(2.5,.05,0); g.add(pool)
      g.position.set(x,0,z); g.rotation.y = rotY
      scene.add(g)
      streetLamps.push({ head, glow, pool })
    }
    ;[-30,-52,-74].forEach(z=>{ addStreetLamp(-14.5,z,0); addStreetLamp(14.5,z,Math.PI) })
    ;[30,52,74].forEach(z=>{ addStreetLamp(-14.5,z,0); addStreetLamp(14.5,z,Math.PI) })
    ;[-30,-52,-74].forEach(x=>{ addStreetLamp(x,-14.5,Math.PI/2); addStreetLamp(x,14.5,-Math.PI/2) })
    ;[30,52,74].forEach(x=>{ addStreetLamp(x,-14.5,Math.PI/2); addStreetLamp(x,14.5,-Math.PI/2) })

    /* A few real lights so the scene has genuine falloff, rather than
       relying on emissive materials alone. Kept to four for weak GPUs. */
    ;[[-26,-26],[26,-26],[-26,26],[26,26]].forEach(([x,z])=>{
      const l = new THREE.PointLight(0xffc879, 26, 60, 2)
      l.position.set(x,9,z); scene.add(l)
    })

    /* ---------- traffic signals ----------
       Bigger heads, a hood over each lamp, an emissive lens and an additive
       glow sprite. The active aspect should be unmistakable at a glance from
       across the room, which the old flat-coloured spheres were not. */
    const lampMeshes = []
    const pedSignals = []
    const addSignal = (x, z, axis, facing) => {
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(.18,.22,6.2),
        new THREE.MeshStandardMaterial({ color: 0x6f777c, roughness:.7 }))
      pole.position.set(x,3.1,z); scene.add(pole)

      const head = new THREE.Group()
      head.position.set(x,5.9,z); head.rotation.y = facing
      const box = new THREE.Mesh(new THREE.BoxGeometry(1.5,3.5,.85),
        new THREE.MeshStandardMaterial({ color: 0x11161a, roughness:.85 }))
      head.add(box)
      const backplate = new THREE.Mesh(new THREE.BoxGeometry(2.2,4.2,.12),
        new THREE.MeshStandardMaterial({ color: 0x0d1114, roughness:1 }))
      backplate.position.z = -.5; head.add(backplate)

      const colors = [0xff4b4b,0xffc23d,0x3ce87c]
      colors.forEach((c, idx) => {
        const y = 1.12 - idx*1.12
        const lens = new THREE.Mesh(new THREE.CircleGeometry(.42,20),
          new THREE.MeshStandardMaterial({ color:0x1b2126, emissive:c, emissiveIntensity:0, roughness:.35 }))
        lens.position.set(0,y,.44); head.add(lens)
        /* hood, so an unlit lamp still reads as a lamp */
        const hood = new THREE.Mesh(new THREE.CylinderGeometry(.5,.5,.42,16,1,true,0,Math.PI),
          new THREE.MeshStandardMaterial({ color:0x0b0e11, roughness:1, side:THREE.DoubleSide }))
        hood.rotation.set(Math.PI/2,0,0); hood.position.set(0,y+.12,.58); head.add(hood)
        const glow = makeGlow(c, 3.1); glow.position.set(0,y,.75); head.add(glow)
        lampMeshes.push({ lens, glow, axis, idx, color:c })
      })
      scene.add(head)

      /* pedestrian head on the same pole: the green figure shows exactly when
         the parallel crossing is safe, which is what the walkers obey */
      const ped = new THREE.Group()
      ped.position.set(x,3.3,z); ped.rotation.y = facing
      const pbox = new THREE.Mesh(new THREE.BoxGeometry(.9,1.5,.5),
        new THREE.MeshStandardMaterial({ color:0x11161a, roughness:.9 }))
      ped.add(pbox)
      const plens = new THREE.Mesh(new THREE.CircleGeometry(.3,16),
        new THREE.MeshStandardMaterial({ color:0x1b2126, emissive:0xff4b4b, emissiveIntensity:.9, roughness:.4 }))
      plens.position.z = .27; ped.add(plens)
      const pglow = makeGlow(0xffffff, 1.9); pglow.position.z = .45; ped.add(pglow)
      scene.add(ped)
      pedSignals.push({ lens:plens, glow:pglow, axis })
    }
    addSignal(-13.5,-13.5,'NS',Math.PI/4); addSignal(13.5,13.5,'NS',Math.PI*1.25)
    addSignal(-13.5,13.5,'EW',Math.PI*.75); addSignal(13.5,-13.5,'EW',Math.PI*1.75)

    /* ---------- pedestrians ----------
       They wait on the kerb and only step out when their crossing is safe, so
       the crowd is a live readout of the signal plan rather than set dressing. */
    const people = []
    CROSSWALKS.forEach((cw, ci) => {
      for(let i=0;i<5;i++){
        const g = makePerson(ci*5+i)
        const dir = i % 2 === 0 ? 1 : -1
        g.userData.cw = cw
        g.userData.dir = dir
        g.userData.t = dir > 0 ? -0.06 - i*0.05 : 1.06 + i*0.05
        g.userData.speed = 0.16 + (i % 3) * 0.035
        g.userData.lane = (i - 2) * 0.9
        scene.add(g)
        people.push(g)
      }
    })

    const pools = {}
    const dirConfig = {
      north: { lane:-4, axis:'z', sign:1, start:-17.2, rot:0 },
      south: { lane:4, axis:'z', sign:-1, start:17.2, rot:Math.PI },
      east:  { lane:4, axis:'x', sign:-1, start:17.2, rot:Math.PI/2 },
      west:  { lane:-4, axis:'x', sign:1, start:-17.2, rot:-Math.PI/2 },
    }

    const createCar = (dir, i) => {
      const c = new THREE.Group()
      const variants = {}
      VKEYS.forEach(k=>{
        const g = buildVehicle(k, i)
        c.add(g); variants[k] = g
      })
      c.visible=false
      c.userData={dir,target:new THREE.Vector3(),variants}
      scene.add(c)
      return c
    }
    Object.keys(dirConfig).forEach(dir => pools[dir] = Array.from({length:24},(_,i)=>createCar(dir,i)))

    /* ---------- departing vehicles: they drive through, not vanish ---------- */
    const departPool = Array.from({length:40}, (_,i)=>{
      const c = new THREE.Group()
      const variants = {}
      VKEYS.forEach(k=>{
        const g = buildVehicle(k, i)
        c.add(g); variants[k] = g
      })
      c.visible=false
      c.userData={active:false,dir:'north',kind:'car',dist:0,speed:0,variants}
      scene.add(c)
      return c
    })

    /* ---------- emergency vehicle mesh ---------- */
    const evGroup = new THREE.Group()
    const evBody = new THREE.Mesh(new THREE.BoxGeometry(2.3,1.6,5.2),
      new THREE.MeshStandardMaterial({ color: 0xf2f4f6, roughness:.5 }))
    evBody.position.y = 1.0
    evBody.castShadow = true
    evGroup.add(evBody)
    const evCab = new THREE.Mesh(new THREE.BoxGeometry(2.1,1.0,1.6),
      new THREE.MeshStandardMaterial({ color: 0x2b3440, roughness:.4 }))
    evCab.position.set(0,1.2,-1.9)
    evGroup.add(evCab)
    const evBeacon = new THREE.Mesh(new THREE.BoxGeometry(1.7,.34,.6),
      new THREE.MeshBasicMaterial({ color: 0xff3b3b }))
    evBeacon.position.y = 1.95
    evGroup.add(evBeacon)
    const evGlow = new THREE.PointLight(0xff3b3b, 0, 26)
    evGlow.position.y = 2.4
    evGroup.add(evGlow)
    evGroup.visible = false
    scene.add(evGroup)

    const resize = () => {
      const width = host.clientWidth || 600
      const height = Math.max(330, width * .64)
      renderer.setSize(width,height,false)
      camera.aspect = width/height
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize); ro.observe(host)

    ctx.current={scene,camera,renderer,pools,dirConfig,lampMeshes,phase:'NS',
      queues:{north:0,south:0,east:0,west:0},types:null,departPool,departQueue:[],
      evGroup,evBody,evBeacon,evGlow,ev:null,people,pedSignals,streetLamps}

    const clock = new THREE.Clock(); let raf=0
    const animate=()=>{
      raf=requestAnimationFrame(animate)
      const dt=Math.min(clock.getDelta(),.05)
      const t=clock.getElapsedTime()
      const c=ctx.current
      if(!c) return

      Object.entries(c.pools).forEach(([dir,cars])=>{
        const cfg=c.dirConfig[dir]
        const list = (c.types && c.types[dir]) || null
        const q=Math.min(list ? list.length : (c.queues[dir]||0), cars.length)
        let cursor = 0
        cars.forEach((car,i)=>{
          car.visible=i<q
          if(!car.visible) return
          const kind = list ? (list[i]||'car') : 'car'
          Object.entries(car.userData.variants).forEach(([k,g])=>{ g.visible = (k===kind) })
          const len = VEHICLES[kind].len
          cursor += len
          const along=cfg.start-cfg.sign*(cursor-len/2)
          if(cfg.axis==='z') car.userData.target.set(cfg.lane,0,along)
          else car.userData.target.set(along,0,cfg.lane)
          car.position.lerp(car.userData.target,Math.min(1,dt*7))
          car.rotation.y=cfg.rot
        })
      })

      /* release queued departures with start-up lost time, then drive them out */
      while(c.departQueue.length){
        const job = c.departQueue[0]
        if(job.delay > 0){ job.delay -= dt; break }
        const slot = c.departPool.find(v=>!v.userData.active)
        if(!slot) { c.departQueue.shift(); continue }
        c.departQueue.shift()
        slot.userData.active = true
        slot.userData.dir = job.dir
        slot.userData.kind = job.kind
        slot.userData.dist = 0
        slot.userData.speed = 4
        Object.entries(slot.userData.variants).forEach(([k,g])=>{ g.visible = (k===job.kind) })
        slot.visible = true
      }
      c.departPool.forEach(v=>{
        if(!v.userData.active) return
        const cfg = c.dirConfig[v.userData.dir]
        /* accelerate away from the stop line, as a real discharge wave does */
        v.userData.speed = Math.min(26, v.userData.speed + 34*dt)
        v.userData.dist += v.userData.speed*dt
        const along = cfg.start - cfg.sign*(-v.userData.dist)
        if(cfg.axis==='z') v.position.set(cfg.lane,0,along)
        else v.position.set(along,0,cfg.lane)
        v.rotation.y = cfg.rot
        if(v.userData.dist > 78){ v.userData.active=false; v.visible=false }
      })

      /* emergency vehicle placement + flashing beacon */
      const ev = c.ev
      if (ev && ev.active) {
        const cfg = c.dirConfig[ev.approach]
        const along = cfg.start - cfg.sign * ev.dist
        // sit one lane over so it is visibly overtaking the queue
        const offset = cfg.lane > 0 ? -2.4 : 2.4
        if (cfg.axis === 'z') c.evGroup.position.set(cfg.lane + offset, 0, along)
        else c.evGroup.position.set(along, 0, cfg.lane + offset)
        c.evGroup.rotation.y = cfg.rot
        c.evGroup.visible = true
        const flash = Math.sin(t * 14) > 0
        c.evBeacon.material.color.setHex(flash ? ev.beacon : 0x2a2f36)
        c.evGlow.color.setHex(ev.beacon)
        c.evGlow.intensity = flash ? 5.5 : 0.4
        c.evBody.material.color.setHex(ev.body)
      } else {
        c.evGroup.visible = false
        c.evGlow.intensity = 0
      }

      /* congestion glow — the scene itself reddens as the junction chokes */
      /* A gentle warm haze as the junction chokes. The old version drove the
         whole sky to red, which read as a video game rather than a street. */
      const load = Math.min(1, (c.totalQueue||0) / 26)
      const tint = new THREE.Color(0x0e141a).lerp(new THREE.Color(0x241a1c), load * .75)
      c.scene.background.copy(tint); c.scene.fog.color.copy(tint)

      c.lampMeshes.forEach(({lens,glow,axis,idx,color})=>{
        const isAmber = c.phase === 'AMBER' && idx === 1
        const isGreen = c.phase === axis && idx === 2
        const isRed = c.phase !== 'AMBER' && c.phase !== axis && idx === 0
        const on = isAmber || isGreen || isRed
        lens.material.emissiveIntensity = on ? 2.4 : 0.04
        lens.material.color.setHex(on ? color : 0x1b2126)
        /* ease the glow instead of snapping it, so a change of phase reads as
           an event rather than a flicker */
        glow.material.opacity += ((on ? .95 : 0) - glow.material.opacity) * Math.min(1, dt*12)
      })

      /* pedestrian aspect: walk when the parallel traffic is stopped */
      c.pedSignals.forEach(({lens,glow,axis})=>{
        const walk = c.phase !== 'AMBER' && c.phase !== axis
        lens.material.emissive.setHex(walk ? 0x8affc0 : 0xff4b4b)
        lens.material.emissiveIntensity = walk ? 2.0 : 1.0
        glow.material.color.setHex(walk ? 0x8affc0 : 0xff4b4b)
        glow.material.opacity += ((walk ? .5 : .22) - glow.material.opacity) * Math.min(1, dt*10)
      })

      /* people: cross only while their arm is stopped, otherwise hold the kerb */
      c.people.forEach(pr=>{
        const u = pr.userData, cw = u.cw
        const safe = c.phase === cw.safeOn
        const inRoad = u.t > 0.02 && u.t < 0.98
        /* someone already in the carriageway finishes crossing rather than
           freezing mid-road when the phase changes */
        const moving = safe || inRoad
        if(moving) u.t += u.dir * u.speed * dt
        if(u.t > 1.12){ u.t = -0.06; u.dir = 1 }
        if(u.t < -0.12){ u.t = 1.06; u.dir = -1 }

        const clamped = Math.min(1.14, Math.max(-0.14, u.t))
        const along = cw.from + (cw.to - cw.from) * clamped
        if(cw.axis === 'x') pr.position.set(along, .5, cw.fixed + u.lane*0.55)
        else pr.position.set(cw.fixed + u.lane*0.55, .5, along)
        pr.rotation.y = cw.axis === 'x'
          ? (u.dir > 0 ? Math.PI/2 : -Math.PI/2)
          : (u.dir > 0 ? 0 : Math.PI)

        const swing = moving ? Math.sin(t*7 + u.phase) : 0
        u.legs.rotation.x = swing * .5
        u.torso.position.y = .93 + (moving ? Math.abs(Math.sin(t*7 + u.phase))*.04 : 0)
      })
      c.renderer.render(c.scene,c.camera)
    }
    animate()
    return()=>{cancelAnimationFrame(raf);ro.disconnect();renderer.dispose();host.innerHTML='';ctx.current=null}
  },[])

  useEffect(()=>{
    if(!ctx.current||!frame) return
    ctx.current.queues={north:frame.north,south:frame.south,east:frame.east,west:frame.west}
    const prev = ctx.current.prevQueues
    if(prev){
      /* a queue that shrank means those vehicles crossed — animate them through */
      ;['north','south','east','west'].forEach(d=>{
        const gone = Math.max(0, (prev[d]||0) - (frame[d]||0))
        const kinds = (prev.types && prev.types[d]) || []
        for(let i=0;i<Math.min(gone,6);i++){
          ctx.current.departQueue.push({ dir:d, kind:kinds[i] || 'car', delay:i*0.16 })
        }
      })
    }
    ctx.current.prevQueues = {north:frame.north,south:frame.south,east:frame.east,west:frame.west,types:frame.types}
    ctx.current.types = frame.types || null
    ctx.current.totalQueue = frame.total_queue || 0
  },[frame])

  useEffect(()=>{
    if(!ctx.current) return
    ctx.current.phase = phase || frame?.phase || 'NS'
  },[phase, frame])

  useEffect(()=>{
    if(!ctx.current) return
    ctx.current.ev = ev || null
  },[ev])

  useEffect(()=>{
    if(!ctx.current) return
    if(mode==='bird'){ctx.current.camera.position.set(48,58,50);ctx.current.camera.lookAt(0,0,0)}
    else {ctx.current.camera.position.set(7,4,-48);ctx.current.camera.lookAt(0,2,4)}
  },[mode])

  const shownPhase = phase || frame?.phase
  return <section className={`sim-card ${accent}`}>
    <div className="sim-title-row">
      <div><h2>{title}</h2><p>{title.includes('Fixed') ? 'Conventional clock-timed cycle' : 'Queue-aware predictive control'}</p></div>
      <div className="phase-readout"><SignalHead phase={shownPhase||'NS'} axis="NS"/><span>{phaseLabel(shownPhase)}</span></div>
    </div>
    {winning===true && <div className="lead-ribbon">LEADING</div>}
    {preempting && <div className="preempt-banner">PREEMPTION ACTIVE · emergency corridor held</div>}
    {ev && ev.active && !preempting && ev.waiting &&
      <div className="preempt-banner blocked">EMERGENCY VEHICLE HELD AT RED · {ev.waitTicks} ticks lost</div>}
    <div className="twin" ref={mount}/>
    <div className="qbars">
      {['north','south','east','west'].map(d=>{
        const v=frame?.[d]??0, p=Math.min(100,100*v/Math.max(8,peers||8))
        const cls = p>72?'crit':p>42?'hot':''
        return <div className="qrow" key={d}>
          <i>{d[0].toUpperCase()}</i>
          <div className="qtrack"><span className={cls} style={{width:p+'%'}}/></div>
          <b>{v}</b>
        </div>
      })}
    </div>
    {frame?.byType && <div className="fleet">
      {VKEYS.map(k=>(
        <span key={k} className={`fchip ${k}`} title={`${VEHICLES[k].label} · ${VEHICLES[k].pcu} PCU each`}>
          <i className={`vdot ${k}`}/>{VEHICLES[k].label.split(' ')[0]} <b>{frame.byType[k]}</b>
        </span>
      ))}
    </div>}
    <div className="card-foot">
      <div className={`ctot ${winning===true?'win':winning===false?'lose':''}`}>
        <span>vehicles</span><strong>{frame?.total_queue ?? 0}</strong>
      </div>
      {frame?.total_pcu!==undefined && <div className="ctot pcu">
        <span>PCU load</span><strong>{frame.total_pcu}</strong>
      </div>}
      {frame?.total_people!==undefined && <div className="ctot ppl">
        <span>people waiting</span><strong>{frame.total_people}</strong>
      </div>}
      <Spark frames={frames} upto={tick} color={accent==='smart'?'#62cffb':'#8190a0'}/>
    </div>
  </section>
}


/* ------------------------------------------------------------------ */
/* Deterministic incident lab (client-side).                           */
/* Both policies receive byte-identical arrivals and the identical     */
/* incident, so every difference comes from the signal decision.       */
/* ------------------------------------------------------------------ */
const INCIDENTS = {
  none:            { label: 'No incident',                 note: 'backend A/B replay' },
  'accident-east': { label: 'Accident — east approach',    note: 'east discharge cut to 1 veh/tick, ticks 25–80' },
  waterlogging:    { label: 'Waterlogging — all lanes',    note: 'every approach discharges at 2 veh/tick from tick 30' },
  'school-exit':   { label: 'Event discharge — north',     note: 'sudden north surge, ticks 30–60' },
}

function mulberry32(a){ return function(){ a|=0; a=a+0x6D2B79F5|0; let t=Math.imul(a^a>>>15,1|a);
  t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296 } }

function simulate(scenario, incident, steps, seed, mix, profile){
  const base = { 'north-surge':{north:1.5,south:1.1,east:.5,west:.4},
                 'east-surge' :{north:.5,south:.4,east:1.5,west:1.1},
                 'balanced'   :{north:.9,south:.9,east:.9,west:.9} }[scenario]
  const pm = (PROFILES[profile] || PROFILES['morning-peak']).mult
  const rnd = mulberry32(seed*7919)
  const pickType = ()=>{ let r=rnd(), acc=0
    for(const k of VKEYS){ acc+=VEHICLES[k].share; if(r<=acc) return k }
    return 'car' }
  const arrivals = []
  for(let t=0;t<steps;t++){
    const boost = (incident==='school-exit' && t>=30 && t<60) ? 3.2 : 1
    const row={}
    ;['north','south','east','west'].forEach(d=>{
      const n = Math.floor(rnd()*base[d]*(d==='north'?boost:1)*1.9*pm)
      row[d] = Array.from({length:n}, ()=> mix ? pickType() : 'car')
    })
    arrivals.push(row)
  }
  /* discharge budget is in PCU per tick — a bus costs 3, a two-wheeler 0.5 */
  const capacity = (t,dir)=>{
    if(incident==='accident-east' && dir==='east' && t>=25 && t<80) return 1.2
    if(incident==='waterlogging' && t>=30) return 2.4
    return 4.5
  }
  /* control constants — the safety envelope the optimiser may never violate */
  const AMBER_TICKS = 2      // fixed clearance, never shortened
  const MIN_GREEN   = 6      // stops phase flapping
  const MAX_GREEN   = 26     // no approach may monopolise
  const MAX_RED     = 30     // hard starvation guard
  const FAIR        = 0.09   // ageing weight: waiting approaches gain priority over time
  const PERSON_W    = 0.05   // passenger-occupancy weight (people delayed, not just vehicles)
  const HYST        = 0.25   // must be clearly better before paying the switch cost

  const run = (policy)=>{
    let q={north:['car','car'],south:['car','car'],east:['car','car'],west:['car','car']}
    let phase='NS', timer=0, amber=0, throughput=0, wait=0, pcuCleared=0, peopleCleared=0
    let credit={north:0,south:0,east:0,west:0}   // part-discharged PCU carried between ticks
    let lastGreen={NS:0,EW:0}, switches=0
    const frames=[]
    for(let t=0;t<steps;t++){
      const pNS=pcuOf(q.north)+pcuOf(q.south), pEW=pcuOf(q.east)+pcuOf(q.west)

      /* Clearable work = how much PCU this approach could actually discharge over a
         short green window. Capping by capacity stops us wasting green on a blocked
         lane; keeping the window means a slow lane still earns a LONG green rather
         than a short useless one. Instantaneous rate alone starves blocked lanes. */
      const GREEN_WINDOW = 8
      const clearable = d => Math.min(pcuOf(q[d]), capacity(t,d)*GREEN_WINDOW)
      const rateNS = clearable('north')+clearable('south')
      const rateEW = clearable('east')+clearable('west')

      if(amber>0){
        amber--
        if(amber===0){ phase = phase==='NS'?'EW':'NS'; timer=0; lastGreen[phase]=t; switches++ }
      } else if(policy==='fixed'){
        if(timer>=14) amber=AMBER_TICKS
      } else {
        /* score = what this axis can actually discharge now, PLUS an ageing term so
           an approach that has waited long enough is served even if it discharges
           slowly. Without this a blocked lane starves indefinitely. */
        const age = ax => FAIR * (t - lastGreen[ax]) * Math.sqrt(ax==='NS'?pNS:pEW)
        /* person-delay term: an approach holding a full bus is holding 32 people */
        const ppl = ax => PERSON_W * (ax==='NS'
          ? peopleOf(q.north)+peopleOf(q.south) : peopleOf(q.east)+peopleOf(q.west))
        const scoreNS = rateNS + age('NS') + ppl('NS')
        const scoreEW = rateEW + age('EW') + ppl('EW')
        const curAxis = phase, oppAxis = phase==='NS'?'EW':'NS'
        const cur = curAxis==='NS'?scoreNS:scoreEW
        const opp = oppAxis==='NS'?scoreNS:scoreEW
        const oppQueue = oppAxis==='NS'?pNS:pEW
        const starved = (t - lastGreen[oppAxis]) >= MAX_RED && oppQueue > 0
        const worthSwitching = opp > cur*(1+HYST) && oppQueue > 0
        if(starved) amber=AMBER_TICKS
        else if(timer>=MIN_GREEN && (worthSwitching || timer>=MAX_GREEN)) amber=AMBER_TICKS
      }

      const shown = amber>0 ? 'AMBER' : phase
      const counts = { north:q.north.length, south:q.south.length, east:q.east.length, west:q.west.length }
      const byType = {}
      VKEYS.forEach(k=>byType[k]=['north','south','east','west'].reduce((n,d)=>n+q[d].filter(x=>x===k).length,0))
      frames.push({ ...counts, phase:shown,
        total_queue: counts.north+counts.south+counts.east+counts.west,
        total_pcu: Math.round((pNS+pEW)*10)/10,
        total_people: Math.round(['north','south','east','west'].reduce((n,d)=>n+peopleOf(q[d]),0)),
        types: { north:[...q.north], south:[...q.south], east:[...q.east], west:[...q.west] },
        byType })

      if(amber===0){
        const served = phase==='NS'?['north','south']:['east','west']
        ;['north','south','east','west'].forEach(d=>{
          if(!served.includes(d)){ credit[d]=0; return }
          /* A bus is 3 PCU. If a tick only affords 1.2 PCU it must take three ticks to
             clear — not block the lane forever. Unspent capacity is carried over. */
          credit[d] = Math.min(credit[d] + capacity(t,d), capacity(t,d)*4)
          while(q[d].length && VEHICLES[q[d][0]].pcu <= credit[d] + 1e-9){
           credit[d] -= VEHICLES[q[d][0]].pcu
            pcuCleared += VEHICLES[q[d][0]].pcu
            peopleCleared += VEHICLES[q[d][0]].occ
            q[d].shift(); throughput++
          }
        })
      }
      const a=arrivals[t]
      ;['north','south','east','west'].forEach(d=>{ q[d]=q[d].concat(a[d]) })
      wait += q.north.length+q.south.length+q.east.length+q.west.length
      timer++
    }
    const avgQ = frames.reduce((s,f)=>s+f.total_queue,0)/frames.length
    return { frames, summary:{ average_queue:avgQ, average_wait_per_tick:wait/steps,
             throughput, switches, pcu_cleared:Math.round(pcuCleared),
             people_cleared:Math.round(peopleCleared) } }
  }
  return { steps, seed, scenario, incident, mix, profile, fixed:run('fixed'), adaptive:run('adaptive'), clientSim:true }
}


/* ================================================================== */
/* TWO-JUNCTION CORRIDOR                                              */
/* Guindy Junction  →  1.4 km link  →  Kathipara Junction             */
/* Clearing the upstream junction is worthless if the link it feeds is */
/* already full. Fixed clocks cannot see this; we meter the release.   */
/* ================================================================== */
const CORRIDOR = {
  name: 'Anna Salai corridor, Chennai',
  up:   { id:'J1', name:'Guindy Junction',   cross:'Race Course Road' },
  down: { id:'J2', name:'Kathipara Junction', cross:'Mount–Poonamallee Rd' },
  linkKm: 1.4,
  LINK_CAP: 15,        // PCU the 1.4 km link can hold before it backs up
  TRAVEL: 6,           // ticks to traverse the link at free flow
}

function simulateCorridor(scenario, incident, steps, seed, mix, profile){
  const demand = { 'north-surge':{main:3.2,crossA:.9,crossB:.8},
                   'east-surge' :{main:2.9,crossA:1.5,crossB:1.3},
                   'balanced'   :{main:2.8,crossA:1.1,crossB:1.0} }[scenario]
  const pm = (PROFILES[profile] || PROFILES['morning-peak']).mult
  const rnd = mulberry32(seed*104729)
  const pickType = ()=>{ let r=rnd(), acc=0
    for(const k of VKEYS){ acc+=VEHICLES[k].share; if(r<=acc) return k }
    return 'car' }
  const arrivals=[]
  for(let t=0;t<steps;t++){
    const boost = (incident==='school-exit' && t>=30 && t<60) ? 2.8 : 1
    const mk = rate => Array.from({length:Math.floor(rnd()*rate*1.9*pm)}, ()=> mix?pickType():'car')
    arrivals.push({ main:mk(demand.main*boost), crossA:mk(demand.crossA), crossB:mk(demand.crossB) })
  }
  const cap = (t,where)=>{
    if(incident==='accident-east' && where==='downMain' && t>=25 && t<80) return 1.4
    if(incident==='waterlogging' && t>=30) return 2.6
    return 4.5
  }

  const AMBER=2, MIN_G=6, MAX_G=26, MAX_RED=30

  const run = (policy)=>{
    let qUpMain=[], qUpCross=[], link=[], qDownMain=[], qDownCross=[]
    let phA='THROUGH', phB='THROUGH', tA=0, tB=0, amA=0, amB=0
    let lastA={THROUGH:0,CROSS:0}, lastB={THROUGH:0,CROSS:0}
    let credit={upMain:0,upCross:0,downMain:0,downCross:0}
    let exited=0, spillTicks=0, meteredTicks=0, wait=0
    const frames=[]

    const linkLoad = ()=> pcuOf(link.map(v=>v.k)) + pcuOf(qDownMain)

    for(let t=0;t<steps;t++){
      const load = linkLoad()
      const full = load >= CORRIDOR.LINK_CAP * 0.88

      /* ---------------- junction B (downstream) ---------------- */
      const bMain = Math.min(pcuOf(qDownMain), cap(t,'downMain')*8)
      const bCross= Math.min(pcuOf(qDownCross), cap(t,'downCross')*8)
      if(amB>0){ amB--; if(amB===0){ phB = phB==='THROUGH'?'CROSS':'THROUGH'; tB=0; lastB[phB]=t } }
      else if(policy==='fixed'){ if(tB>=14) amB=AMBER }
      else {
        const cur = phB==='THROUGH'?bMain:bCross
        const opp = phB==='THROUGH'?bCross:bMain
        const oppAxis = phB==='THROUGH'?'CROSS':'THROUGH'
        const oppQ = phB==='THROUGH'?pcuOf(qDownCross):pcuOf(qDownMain)
        /* draining a congested link is worth extra to the whole corridor */
        const relief = (phB==='THROUGH'&&full) ? 9 : (oppAxis==='THROUGH'&&full ? -9 : 0)
        const starved = (t-lastB[oppAxis])>=MAX_RED && oppQ>0
        if(starved) amB=AMBER
        else if(tB>=MIN_G && ((opp > (cur+relief)*1.25 && oppQ>0) || tB>=MAX_G)) amB=AMBER
      }

      /* ---------------- junction A (upstream) ------------------ */
      const aMain = Math.min(pcuOf(qUpMain), cap(t,'upMain')*8)
      const aCross= Math.min(pcuOf(qUpCross), cap(t,'upCross')*8)
      if(amA>0){ amA--; if(amA===0){ phA = phA==='THROUGH'?'CROSS':'THROUGH'; tA=0; lastA[phA]=t } }
      else if(policy==='fixed'){ if(tA>=14) amA=AMBER }
      else {
        /* THE NETWORK-AWARE TERM: releasing into a filling link is penalised */
        const headroom = Math.max(0, CORRIDOR.LINK_CAP - load)
        const penalty = 0.40 * Math.max(0, load - CORRIDOR.LINK_CAP*0.62)
        const mainScore = Math.min(aMain, headroom*1.4) - penalty
        const cur = phA==='THROUGH'?mainScore:aCross
        const opp = phA==='THROUGH'?aCross:mainScore
        const oppAxis = phA==='THROUGH'?'CROSS':'THROUGH'
        const oppQ = phA==='THROUGH'?pcuOf(qUpCross):pcuOf(qUpMain)
        const starved = (t-lastA[oppAxis])>=MAX_RED && oppQ>0
        if(starved) amA=AMBER
        else if(tA>=MIN_G && ((opp > cur*1.25 && oppQ>0) || tA>=MAX_G)) amA=AMBER
        if(phA==='THROUGH' && penalty>0) meteredTicks++
      }

      const phAs = amA>0?'AMBER':phA, phBs = amB>0?'AMBER':phB

      frames.push({
        upMain:qUpMain.length, upCross:qUpCross.length,
        downMain:qDownMain.length, downCross:qDownCross.length,
        linkCount:link.length, linkPcu:Math.round(load*10)/10,
        linkPct:Math.round(100*load/CORRIDOR.LINK_CAP),
        phaseA:phAs, phaseB:phBs,
        spill: full,
        types:{ upMain:[...qUpMain], upCross:[...qUpCross],
                downMain:[...qDownMain], downCross:[...qDownCross],
                link: link.map(v=>({k:v.k,p:1-v.eta/CORRIDOR.TRAVEL})) },
        total_queue: qUpMain.length+qUpCross.length+qDownMain.length+qDownCross.length+link.length,
        exited, spillTicks, meteredTicks,
      })

      /* ---------------- discharge ---------------- */
      const serve = (arr, key, t2, sink)=>{
        credit[key] = Math.min(credit[key] + cap(t2,key), cap(t2,key)*4)
        while(arr.length && VEHICLES[arr[0]].pcu <= credit[key]+1e-9){
          if(sink && sink(arr[0])===false) break
          credit[key]-=VEHICLES[arr[0]].pcu
          arr.shift()
        }
      }
      if(amA===0){
        if(phA==='THROUGH'){
          serve(qUpMain,'upMain',t,(k)=>{
            if(linkLoad()+VEHICLES[k].pcu > CORRIDOR.LINK_CAP){ spillTicks++; return false }
            link.push({k, eta:CORRIDOR.TRAVEL}); return true
          })
        } else { credit.upMain=0; serve(qUpCross,'upCross',t,()=>true) }
      }
      if(amB===0){
        if(phB==='THROUGH'){ serve(qDownMain,'downMain',t,()=>{ exited++; return true }) }
        else { credit.downMain=0; serve(qDownCross,'downCross',t,()=>true) }
      }

      /* link travel */
      link.forEach(v=>v.eta--)
      while(link.length && link[0].eta<=0){ qDownMain.push(link.shift().k) }

      const a=arrivals[t]
      qUpMain=qUpMain.concat(a.main); qUpCross=qUpCross.concat(a.crossA); qDownCross=qDownCross.concat(a.crossB)
      wait += qUpMain.length+qUpCross.length+qDownMain.length+qDownCross.length+link.length
      tA++; tB++
    }
    const avgQ = frames.reduce((s,f)=>s+f.total_queue,0)/frames.length
    return { frames, summary:{ average_queue:avgQ, average_wait_per_tick:wait/steps,
      exited, spillTicks, meteredTicks } }
  }
  return { steps, seed, scenario, incident, fixed:run('fixed'), smart:run('smart') }
}

function CorridorView({ frame, title, tone }){
  const ref = useRef(null)
  useEffect(()=>{
    const c = ref.current; if(!c || !frame) return
    const dpr = Math.min(window.devicePixelRatio||1, 2)
    const W = c.clientWidth, H = 190
    c.width = W*dpr; c.height = H*dpr
    const x = c.getContext('2d'); x.setTransform(dpr,0,0,dpr,0,0)
    x.clearRect(0,0,W,H)

    const jA = W*0.30, jB = W*0.74, midY = H*0.56, roadH = 26
    /* corridor road */
    x.fillStyle = '#2b333b'; x.fillRect(0, midY-roadH/2, W, roadH)
    /* cross roads */
    ;[jA,jB].forEach(jx=>{ x.fillStyle='#2b333b'; x.fillRect(jx-roadH/2, 12, roadH, H-24) })
    /* lane dashes */
    x.strokeStyle='#4c565f'; x.setLineDash([9,9]); x.lineWidth=1.4
    x.beginPath(); x.moveTo(0,midY); x.lineTo(W,midY); x.stroke(); x.setLineDash([])

    /* link fill indicator */
    const pct = Math.min(100, frame.linkPct)
    const lx0 = jA+roadH/2, lx1 = jB-roadH/2
    x.fillStyle = pct>92 ? 'rgba(239,94,94,.22)' : pct>65 ? 'rgba(240,189,88,.16)' : 'rgba(98,207,251,.10)'
    x.fillRect(lx0, midY-roadH/2, (lx1-lx0)*pct/100, roadH)

    const draw = (list, x0, y0, dx, dy) => {
      let cur = 0
      list.slice(0,26).forEach(t=>{
        const k = typeof t === 'string' ? t : t.k
        const v = VEHICLES[k]; const len = v.len*1.5
        cur += len
        const px = x0 + dx*(cur-len/2), py = y0 + dy*(cur-len/2)
        x.fillStyle = '#'+v.color.toString(16).padStart(6,'0')
        if(dx) x.fillRect(px-len/2, py-4.5, len, 9)
        else   x.fillRect(px-4.5, py-len/2, 9, len)
      })
    }
    /* queues */
    draw(frame.types.upMain,   jA-roadH/2, midY-7, -1, 0)
    draw(frame.types.downMain, jB-roadH/2, midY-7, -1, 0)
    draw(frame.types.upCross,  jA, 14, 0, 1)
    draw(frame.types.downCross,jB, 14, 0, 1)
    /* link vehicles positioned by progress */
    frame.types.link.forEach(v=>{
      const vv = VEHICLES[v.k], len = vv.len*1.5
      const px = lx0 + (lx1-lx0)*Math.min(1,Math.max(0,v.p))
      x.fillStyle = '#'+vv.color.toString(16).padStart(6,'0')
      x.fillRect(px-len/2, midY+2, len, 9)
    })
    /* signals */
    const lamp=(cx,cy,on,col)=>{ x.beginPath(); x.arc(cx,cy,4.6,0,7); x.fillStyle=on?col:'#232b32'; x.fill() }
    ;[[jA,frame.phaseA],[jB,frame.phaseB]].forEach(([jx,ph])=>{
      lamp(jx-roadH/2-11, midY-15, ph==='THROUGH', '#43cf7c')
      lamp(jx-roadH/2-11, midY-3,  ph==='AMBER',   '#e5b94d')
      lamp(jx-roadH/2-11, midY+9,  ph==='CROSS',   '#e34f4f')
    })
    /* labels */
    x.fillStyle='#93a8ba'; x.font='600 11px system-ui'; x.textAlign='center'
    x.fillText(CORRIDOR.up.name,   jA, H-6)
    x.fillText(CORRIDOR.down.name, jB, H-6)
    x.fillStyle= pct>92?'#ff8f8f':'#7f93a5'; x.font='10px system-ui'
    x.fillText(`link ${CORRIDOR.linkKm} km · ${frame.linkPcu} PCU · ${pct}% full${frame.spill?'  ⚠ SPILLBACK':''}`,
      (lx0+lx1)/2, midY-roadH/2-7)
  },[frame])
  return <div className={`corr ${tone}`}>
    <div className="corr-head"><strong>{title}</strong>
      <span>{frame?.spill ? <b className="spill">spillback — upstream green is wasted</b>
        : frame?.meteredTicks>0 && tone==='smart' ? <b className="meter">metering release into the link</b> : ''}</span>
    </div>
    <canvas ref={ref} className="corr-canvas"/>
  </div>
}

function Spark({ frames, upto, color }){
  if(!frames?.length) return null
  const pts = frames.slice(0, Math.max(2,upto+1)).map(f=>f.total_queue)
  const max = Math.max(10, ...frames.map(f=>f.total_queue))
  const d = pts.map((v,i)=>`${(i/(frames.length-1))*100},${28-(v/max)*26}`).join(' ')
  return <svg className="spark" viewBox="0 0 100 28" preserveAspectRatio="none">
    <polyline points={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke"/>
  </svg>
}

function App(){
  const [data,setData]=useState(null)
  const [running,setRunning]=useState(false)
  const [tick,setTick]=useState(0)
  const [view,setView]=useState('pov')
  const [scenario,setScenario]=useState('north-surge')
  const [speed,setSpeed]=useState(1)
  const [error,setError]=useState('')
  const [incident,setIncident]=useState('none')
  const [mix,setMix]=useState(true)
  const [profile,setProfile]=useState('morning-peak')

  /* ---------------- emergency vehicle state ---------------- */
  const [profiles,setProfiles]=useState(EV_FALLBACK)
  const [evType,setEvType]=useState('ambulance')
  const [evApproach,setEvApproach]=useState('north')
  const [ev,setEv]=useState(null)     // {active, approach, axis, distFixed, distSmart, ...}

  const load=async()=>{
    if(incident!=='none' || mix){
      setError(''); setData(simulate(scenario,incident,100,7,mix,profile))
      setCorr(simulateCorridor(scenario,incident,100,7,mix,profile))
      setTick(0); setRunning(false); setEv(null); return
    }
    try{
      setError('')
      const url=`${API}/api/single-junction/comparison?steps=100&seed=7&scenario=${scenario}`
      const res=await fetch(url)
      const contentType=res.headers.get('content-type')||''
      if(!res.ok) throw new Error(`backend returned HTTP ${res.status}`)
      if(!contentType.includes('application/json')) throw new Error(`backend did not return JSON from ${url}`)
      const payload=await res.json()
      setData(payload); setCorr(simulateCorridor(scenario,incident,100,7,mix,profile))
      setTick(0);setRunning(false);setEv(null)
    }catch(e){
      setData(null)
      setRunning(false)
      setError(`Cannot reach SmartTraffic backend at ${API}. Start FastAPI with: cd backend && uvicorn app.main:app --reload --port 8000. (${e.message})`)
    }
  }
  useEffect(()=>{load()},[scenario,incident,mix,profile])

  useEffect(()=>{
    fetch(`${API}/api/priority/types`).then(r=>r.json())
      .then(d=>{ if(d && d.types) setProfiles(d.types) })
      .catch(()=>{})
  },[])

  useEffect(()=>{
    if(!running||!data) return
    const id=setInterval(()=>setTick(t=>t>=data.steps-1?0:t+1),Math.max(70,650/speed))
    return()=>clearInterval(id)
  },[running,data,speed])

  const fixed=data?.fixed.frames?.[tick]
  const adaptive=data?.adaptive.frames?.[tick]

  /* ------- emergency vehicle advances with the timeline ------- */
  useEffect(()=>{
    if(!ev || !ev.active) return
    setEv(prev=>{
      if(!prev || !prev.active) return prev
      const p = profiles[prev.type] || EV_FALLBACK[prev.type]
      const preemptDist = (p.lead_seconds || 12) * 4.2

      /* SMART side: preempts, so it never stops */
      let distSmart = prev.distSmart - EV_SPEED
      let smartCross = prev.smartCross
      if (distSmart <= 0 && smartCross === null) smartCross = prev.age

      /* FIXED side: must wait for its own clock phase */
      let distFixed = prev.distFixed
      let waitTicks = prev.waitTicks
      let fixedCross = prev.fixedCross
      const fixedPhase = data?.fixed.frames?.[tick]?.phase
      if (distFixed > 0) {
        distFixed = Math.max(0, distFixed - EV_SPEED)
      } else if (fixedCross === null) {
        if (fixedPhase === prev.axis) { distFixed = -12; fixedCross = prev.age }
        else waitTicks += 1
      } else {
        distFixed -= EV_SPEED
      }

      const done = smartCross !== null && fixedCross !== null && distSmart < -70
      return {...prev,
        age: prev.age + 1,
        distSmart, distFixed, waitTicks, smartCross, fixedCross,
        preempting: distSmart < preemptDist && distSmart > -30,
        waiting: distFixed === 0 && fixedCross === null,
        active: !done,
      }
    })
  },[tick])

  const [demo,setDemo]=useState(null)

  const runDemo = (d) => {
    setDemo(d.id)
    setEv(null); setTick(0); setRunning(false)
    setScenario(d.scenario); setIncident(d.incident)
    setView('bird')
    if(d.ev){
      setEvType(d.ev.type); setEvApproach(d.ev.approach)
      setTimeout(()=>{
        const axis = APPROACHES.find(a=>a[0]===d.ev.approach)[2]
        const meta = EV_META[d.ev.type]
        setEv({ active:true, type:d.ev.type, approach:d.ev.approach, axis,
          body:meta.body, beacon:meta.beacon,
          distSmart:EV_START_DIST, distFixed:EV_START_DIST,
          waitTicks:0, smartCross:null, fixedCross:null,
          preempting:false, waiting:false, age:0 })
        setRunning(true)
      }, 700)
    } else {
      setTimeout(()=>setRunning(true), 500)
    }
  }

  const [corr,setCorr]=useState(null)
  const [tour,setTour]=useState(false)
  const tourRef = useRef(null)

  const startTour = () => {
    if(tour){ clearTimeout(tourRef.current); setTour(false); return }
    setTour(true)
    const step = (i)=>{
      if(i>=DEMOS.length){ setTour(false); return }
      runDemo(DEMOS[i])
      tourRef.current = setTimeout(()=>step(i+1), 14000)
    }
    step(0)
  }
  useEffect(()=>()=>clearTimeout(tourRef.current),[])

  const dispatchEv = () => {
    const axis = APPROACHES.find(a=>a[0]===evApproach)[2]
    const meta = EV_META[evType]
    setEv({
      active:true, type:evType, approach:evApproach, axis,
      body:meta.body, beacon:meta.beacon,
      distSmart:EV_START_DIST, distFixed:EV_START_DIST,
      waitTicks:0, smartCross:null, fixedCross:null,
      preempting:false, waiting:false, age:0,
    })
    setRunning(true)
  }

  const fs=data?.fixed.summary
  const as=data?.adaptive.summary
  const queueGain=fs&&as?Math.round((1-as.average_queue/fs.average_queue)*100):0
  const waitGain=fs&&as?Math.round((1-as.average_wait_per_tick/fs.average_wait_per_tick)*100):0
  const throughputGain=fs&&as?Math.round((as.throughput/fs.throughput-1)*100):0

  /* Instantaneous queue ratio swings wildly (and is meaningless when both are near
     zero). The headline uses the running mean up to the current tick; the instant
     value is shown small, and only when both sides actually have traffic. */
  const cmp = React.useMemo(()=>{
    if(!data) return null
    const f=data.fixed.frames.slice(0,tick+1), a=data.adaptive.frames.slice(0,tick+1)
    if(!f.length) return null
    const sumF=f.reduce((s,x)=>s+x.total_queue,0), sumA=a.reduce((s,x)=>s+x.total_queue,0)
    const mean = sumF>0 ? Math.round((1-sumA/sumF)*100) : null
    const nowF=f.at(-1).total_queue, nowA=a.at(-1).total_queue
    const inst = (nowF>=3||nowA>=3) && nowF>0 ? Math.round((1-nowA/nowF)*100) : null
    return { mean, inst, nowF, nowA }
  },[data,tick])
  const peerMax = data
    ? Math.max(8, ...[...data.fixed.frames,...data.adaptive.frames]
        .flatMap(f=>[f.north,f.south,f.east,f.west])) : 8
  const impact = React.useMemo(()=>{
    if(!data) return null
    const f=data.fixed.frames.slice(0,tick+1), a=data.adaptive.frames.slice(0,tick+1)
    if(!f.length) return null
    const wF=f.reduce((s,x)=>s+x.total_queue,0), wA=a.reduce((s,x)=>s+x.total_queue,0)
    const saved=Math.max(0,wF-wA)
    const idleSec=saved*4
    return { waitSaved:saved, idleMin:Math.round(idleSec/60),
      co2:(idleSec*1.6/1000).toFixed(1),
      pcuFixed:f.at(-1).total_pcu ?? '—', pcuSmart:a.at(-1).total_pcu ?? '—' }
  },[data,tick])

  const prof = profiles[evType] || EV_FALLBACK[evType]
  const evSmart = ev && ev.active ? {...ev, dist:ev.distSmart} : null
  const evFixed = ev && ev.active ? {...ev, dist:ev.distFixed} : null

  return <main>
    <header className="hero">
      <div><p className="eyebrow">SIH PS90 · single-intersection proof</p><h1>SmartTraffic: same junction, same traffic, two signal policies</h1><p className="sub">Left is conventional fixed-clock timing. Right is our adaptive controller. Both receive the exact same seeded arrivals, so any difference comes from signal decisions—not a different traffic pattern.</p></div>
      <div className="hero-status">{error?'BACKEND OFFLINE':'LOCAL A/B'}</div>
    </header>

    <div className="controls">
      <button onClick={()=>setRunning(r=>!r)} disabled={!data}>{running?'⏸ Pause':'▶ Run comparison'}</button>
      <button onClick={()=>{setTick(0);setRunning(false);setEv(null)}}>Reset</button>
      <button onClick={()=>setView(v=>v==='pov'?'bird':'pov')}>{view==='pov'?'Bird’s-eye':'Intersection POV'}</button>
      <button onClick={load}>Reconnect backend</button>
      <button className="jump-ops"
              onClick={()=>document.querySelector('.ops')?.scrollIntoView({behavior:'smooth'})}>
        ↓ Operations console
      </button>
      <label>Traffic pattern<select value={scenario} onChange={e=>setScenario(e.target.value)}><option value="north-surge">North/south surge</option><option value="east-surge">East/west surge</option><option value="balanced">Balanced traffic</option></select></label>
      <label>Chennai profile<select value={profile} onChange={e=>setProfile(e.target.value)}>
        {Object.keys(PROFILES).map(k=><option key={k} value={k}>{PROFILES[k].label}</option>)}
      </select></label>
      <label>Incident<select value={incident} onChange={e=>setIncident(e.target.value)}>
        {Object.keys(INCIDENTS).map(k=><option key={k} value={k}>{INCIDENTS[k].label}</option>)}
      </select></label>
      <label>Vehicle model<select value={mix?'mix':'plain'} onChange={e=>setMix(e.target.value==='mix')}>
        <option value="mix">Mixed traffic (PCU-weighted)</option>
        <option value="plain">Uniform cars (backend A/B)</option>
      </select></label>
      <label>Speed<select value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value="0.25">0.25× — frame by frame</option><option value="0.5">0.5× — slow</option><option value="1">1× — normal</option><option value="2">2×</option><option value="4">4× — fast</option></select></label>
    </div>

    <section className="demos">
      <div className="demo-head">
        <h2>Judge demo — three scenarios</h2>
        <p>One click each. Every scenario feeds both controllers identical seeded arrivals and the identical disruption.</p>
        <button className={`tour-btn ${tour?'on':''}`} onClick={startTour}>
          {tour?'■ Stop tour':'▶ Auto-run all three'}
        </button>
      </div>
      <div className="demo-row">
        {DEMOS.map(d=>(
          <button key={d.id} className={`demo-card ${demo===d.id?'sel':''}`} onClick={()=>runDemo(d)}>
            <span className="demo-n">{d.n}</span>
            <strong>{d.title}</strong>
            <em>{d.line}</em>
            <small>{d.watch}</small>
          </button>
        ))}
      </div>
    </section>

    {/* ---------------- EMERGENCY PRIORITY BAR ---------------- */}
    <section className="ev-bar">
      <div className="ev-head">
        <h2>Emergency vehicle priority</h2>
        <p>Dispatch a priority vehicle into the same junction on both sides. The adaptive controller
           preempts and holds a green corridor; the fixed-clock signal cannot.</p>
      </div>
      <div className="ev-controls">
        <div className="ev-types">
          {Object.keys(EV_META).map(k=>(
            <button key={k} className={`ev-chip ${evType===k?'sel':''}`} onClick={()=>setEvType(k)}>
              <span className="ev-ic">{EV_META[k].icon}</span>{EV_META[k].label}
            </button>
          ))}
        </div>
        <label>Approach
          <select value={evApproach} onChange={e=>setEvApproach(e.target.value)}>
            {APPROACHES.map(([v,l])=><option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <button className="ev-go" onClick={dispatchEv} disabled={!data}>Dispatch {EV_META[evType].icon}</button>
        {ev && <button onClick={()=>setEv(null)}>Clear</button>}
      </div>
      <div className="ev-profile">
        <span><b>Priority</b> {prof.priority}</span>
        <span><b>Green lead</b> {prof.lead_seconds}s before arrival</span>
        <span><b>Hold</b> {prof.hold_seconds}s</span>
        <span><b>Max acceptable delay</b> {prof.max_delay_seconds}s</span>
      </div>
      {ev && <div className="ev-result">
        <div className={`ev-stat ${ev.smartCross!==null?'good':''}`}>
          <span>SmartTraffic</span>
          <strong>{ev.smartCross!==null?`cleared in ${ev.smartCross} ticks`:'approaching…'}</strong>
          <small>preemption {ev.preempting?'active':'armed'}</small>
        </div>
        <div className={`ev-stat ${ev.waiting?'bad':''}`}>
          <span>Fixed clock</span>
          <strong>{ev.fixedCross!==null?`cleared in ${ev.fixedCross} ticks`:(ev.waiting?`held at red · ${ev.waitTicks}`:'approaching…')}</strong>
          <small>{ev.waitTicks} ticks stopped</small>
        </div>
        <div className="ev-stat hero-stat">
          <span>Delay avoided</span>
          <strong>{ev.fixedCross!==null&&ev.smartCross!==null?`${Math.max(0,ev.fixedCross-ev.smartCross)} ticks`:'—'}</strong>
          <small>golden-hour minutes</small>
        </div>
      </div>}
      <p className="ev-note">Amber and all-red clearance are never shortened for a preemption — the corridor
        is opened <i>early</i> using the lead time, not by cutting a live green.</p>
    </section>

    {error&&<div className="error-box">{error}</div>}

    {corr && <section className="corridor">
      <div className="corr-title">
        <div>
          <h2>City corridor — two junctions, one network</h2>
          <p>{CORRIDOR.name} · {CORRIDOR.up.name} → {CORRIDOR.linkKm} km → {CORRIDOR.down.name}.
             The link between them holds only {CORRIDOR.LINK_CAP} PCU. Emptying the upstream junction
             into a full link does not clear the jam — it moves it.</p>
        </div>
        <div className="corr-kpis">
          <div className="ck bad"><span>Fixed clocks</span>
            <strong>{corr.fixed.frames[tick]?.spillTicks ?? 0}</strong><small>spillback events</small></div>
          <div className="ck good"><span>SmartTraffic</span>
            <strong>{corr.smart.frames[tick]?.spillTicks ?? 0}</strong><small>spillback events</small></div>
          <div className="ck"><span>Cleared through corridor</span>
            <strong>{corr.smart.frames[tick]?.exited ?? 0} <em>vs {corr.fixed.frames[tick]?.exited ?? 0}</em></strong>
            <small>vehicles out the far side</small></div>
        </div>
      </div>
      <CorridorView frame={corr.fixed.frames[tick]}  title="Two independent fixed clocks" tone="baseline"/>
      <CorridorView frame={corr.smart.frames[tick]} title="SmartTraffic — network-aware release" tone="smart"/>
      <p className="corr-note">Both corridors receive identical seeded arrivals and the identical disruption.
        The upstream controller subtracts a penalty proportional to how full the downstream link already is,
        so it holds traffic where there is room to store it instead of pushing it into a queue that has none.</p>
    </section>}

    <div className="delta-strip">
      <div className="d-side lose"><span>Fixed clock</span><strong>{fixed?.total_queue??0}</strong>
        <small>vehicles{fixed?.total_pcu!==undefined?` · ${fixed.total_pcu} PCU`:''}</small></div>
      <div className="d-mid">
        <span className="d-label">{incident==='none'?'live difference':INCIDENTS[incident].label}</span>
        <strong className={cmp?.mean>0?'good':cmp?.mean<0?'bad':''}>
          {cmp?.mean===null||cmp?.mean===undefined ? '—' : `${Math.abs(cmp.mean)}%`}
        </strong>
        <span className="d-verdict">
          {cmp?.mean===null||cmp?.mean===undefined ? 'warming up'
            : cmp.mean>0 ? 'shorter queues with SmartTraffic (mean so far)'
            : cmp.mean<0 ? 'longer queues with SmartTraffic (mean so far)'
            : 'level so far'}
          {cmp?.inst!==null&&cmp?.inst!==undefined &&
            <em> · this tick {cmp.inst>0?`${cmp.inst}% lower`:cmp.inst<0?`${Math.abs(cmp.inst)}% higher`:'level'}</em>}
        </span>
        <small>{INCIDENTS[incident].note}{data?.mix?' · mixed fleet, PCU-weighted control (2W 0.5 · auto 0.8 · car 1.0 · bus/lorry 3.0)':''}</small>
      </div>
      <div className="d-side win"><span>SmartTraffic</span><strong>{adaptive?.total_queue??0}</strong>
        <small>vehicles{adaptive?.total_pcu!==undefined?` · ${adaptive.total_pcu} PCU`:''}</small></div>
    </div>

    <div className="comparison-grid">
      <IntersectionTwin frame={fixed} mode={view} title="Fixed Clock Signal" accent="baseline"
        phase={fixed?.phase} ev={evFixed} preempting={false}
        frames={data?.fixed.frames} tick={tick} peers={peerMax}
        winning={fixed&&adaptive?fixed.total_queue<adaptive.total_queue:null}/>
      <IntersectionTwin frame={adaptive} mode={view} title="SmartTraffic Adaptive" accent="smart"
        phase={ev&&ev.active&&ev.preempting?ev.axis:adaptive?.phase}
        ev={evSmart} preempting={!!(ev&&ev.active&&ev.preempting)}
        frames={data?.adaptive.frames} tick={tick} peers={peerMax}
        winning={fixed&&adaptive?adaptive.total_queue<fixed.total_queue:null}/>
    </div>

    <section className="chennai">
      <div className="chn-head">
        <div>
          <h2>Calibrated against measured Chennai traffic</h2>
          <p>Demand profiles are scaled from published congestion levels, not invented.
             Source: {CHENNAI.source}.</p>
        </div>
        <span className="chn-src">tomtom.com/traffic-index</span>
      </div>
      <div className="chn-grid">
        <div className="chn"><span>Travel time per 10 km</span><strong>{CHENNAI.travelTime10km}</strong>
          <small>annual average, city area</small></div>
        <div className="chn"><span>Average congestion</span><strong>{CHENNAI.avgCongestion}%</strong>
          <small>morning {CHENNAI.morningCongestion}% · evening {CHENNAI.eveningCongestion}%</small></div>
        <div className="chn"><span>Rush-hour speed</span><strong>{CHENNAI.rushSpeed} km/h</strong>
          <small>evening {CHENNAI.eveningSpeed} · morning {CHENNAI.morningSpeed} km/h</small></div>
        <div className="chn accent"><span>Lost per driver per year</span><strong>{CHENNAI.hoursLostPerYear} h</strong>
          <small>5 days 12 hours in rush-hour delay</small></div>
      </div>
      <p className="chn-note">Active profile: <b>{PROFILES[profile].label}</b>. Worst recorded day: {CHENNAI.worstDay}.
        A driver covers only {CHENNAI.kmIn15min} km in 15 minutes at this congestion level.</p>
    </section>

    {impact && <section className="impact">
      <div className="imp-title">Cumulative effect at T+{tick} · <span>identical arrivals, identical disruption</span></div>
      <div className="imp-grid">
        <div className="imp"><span>Vehicle-ticks of waiting avoided</span><strong>{impact.waitSaved.toLocaleString()}</strong>
          <small>queue length summed over every tick so far</small></div>
        <div className="imp"><span>PCU load carried</span><strong>{impact.pcuSmart} <em>vs {impact.pcuFixed}</em></strong>
          <small>passenger-car-unit equivalent right now</small></div>
        <div className="imp"><span>Idling avoided</span><strong>{impact.idleMin} min</strong>
          <small>at 1 tick ≈ 4 s of idling per queued vehicle</small></div>
        <div className="imp accent"><span>CO₂ not emitted</span><strong>{impact.co2} kg</strong>
          <small>assumption: 1.6 g CO₂ per vehicle-second idling</small></div>
      </div>
    </section>}

    <div className="timeline"><span>T+{tick}</span><input type="range" min="0" max={data?data.steps-1:99} value={tick} onChange={e=>setTick(Number(e.target.value))}/><span>{data?.steps??100} ticks</span></div>

    <div className="metric-grid">
      <Metric label="Average queue reduction" value={`${queueGain}%`} hint="adaptive vs fixed-clock"/>
      <Metric label="Average wait reduction" value={`${waitGain}%`} hint="same arrivals"/>
      <Metric label="Throughput change" value={`${throughputGain>=0?'+':''}${throughputGain}%`} hint="vehicles cleared"/>
      <Metric label="Current fixed queue" value={fixed?.total_queue??0} hint={`SmartTraffic: ${adaptive?.total_queue??0}`}/>
    </div>

    <OpsConsole/>

  </main>
}

createRoot(document.getElementById('root')).render(<App/>)
