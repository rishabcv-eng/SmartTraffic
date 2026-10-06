/*
 * SmartTraffic — Design of Smart Cities presentation deck.
 *
 * Every figure here is produced by the repository, not written by hand:
 * `python scripts/reproduce_results.py` regenerates each one and fails if it
 * has stopped being true. If a number on a slide and a number in the code ever
 * disagree, the code is right and this file is stale.
 */

const path = require('path')
const pptxgen = require('pptxgenjs')
const { applyTheme } = require(path.join(
  'C:', 'Users', 'LENOVO', 'AppData', 'Roaming', 'Claude',
  'local-agent-mode-sessions', 'skills-plugin',
  'dba9ee21-2cac-4a98-a997-79d2ef5c4fdd', '92f5ba76-f399-4531-96cc-076284e5cfd1',
  'skills', 'pptx', 'scripts', 'apply_theme.js',
))

/* Signal-box palette: night asphalt, signal amber, go-green, stop-red. Chosen
   for this subject rather than a generic corporate blue. */
const THEME = {
  name: 'SmartTraffic Signal',
  headFontFace: 'Cambria',
  bodyFontFace: 'Calibri',
  colors: {
    dk1: '0E1620',  // night asphalt
    lt1: 'FFFFFF',
    dk2: '1B2A3A',  // raised panel
    lt2: 'EEF3F7',
    accent1: 'FFB347',  // signal amber — the dominant accent
    accent2: '3CE87C',  // go green
    accent3: 'FF5A5A',  // stop red
    accent4: '8FD8FF',  // ice blue
    accent5: '94A7B8',  // muted label
    accent6: 'C9A227',  // lane paint
    hlink: '8FD8FF',
    folHlink: '94A7B8',
  },
}

const pres = new pptxgen()
pres.layout = 'LAYOUT_WIDE'           // 13.3 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace }
pres.author = 'Rishab CV, Martin Wills'
pres.company = 'SmartTraffic'
pres.title = 'SmartTraffic — adaptive signal control for lane-less traffic'

const C = pres.SchemeColor
const W = 13.3
const M = 0.7                          // slide margin

/* ------------------------------------------------------------------ layouts */

pres.defineSlideMaster({
  title: 'DARK_TITLE',
  background: { color: THEME.colors.dk1 },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: M, y: 2.5, w: W - 2 * M, h: 1.5,
      fontSize: 44, bold: true, color: C.background1 }, text: '' } },
    { placeholder: { options: { name: 'body', type: 'body', x: M, y: 4.1, w: W - 2 * M, h: 1.5,
      fontSize: 17, color: THEME.colors.accent5 }, text: '' } },
  ],
})

pres.defineSlideMaster({
  title: 'DARK_DIVIDER',
  background: { color: THEME.colors.dk2 },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: M, y: 2.9, w: W - 2 * M, h: 1.2,
      fontSize: 38, bold: true, color: THEME.colors.accent1 }, text: '' } },
    { placeholder: { options: { name: 'body', type: 'body', x: M, y: 4.1, w: W - 2 * M, h: 1.2,
      fontSize: 17, color: C.background1 }, text: '' } },
  ],
})

/* Content frame: title parked at a fixed height on every content slide. */
pres.defineSlideMaster({
  title: 'LIGHT_CONTENT',
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: M, y: 0.5, w: W - 2 * M, h: 0.95,
      fontSize: 36, bold: true, color: C.text1 }, text: '' } },
    { text: { text: 'SmartTraffic · Design of Smart Cities', options: { x: M, y: 6.85, w: 5, h: 0.3,
      fontSize: 10, color: THEME.colors.accent5, isTextBox: true, margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.5, y: 6.85, w: 0.5, h: 0.3, fontSize: 10,
    color: THEME.colors.accent5, align: 'right' },
})

pres.defineSlideMaster({
  title: 'DARK_CONTENT',
  background: { color: THEME.colors.dk1 },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: M, y: 0.5, w: W - 2 * M, h: 0.95,
      fontSize: 36, bold: true, color: C.background1 }, text: '' } },
    { text: { text: 'SmartTraffic · Design of Smart Cities', options: { x: M, y: 6.85, w: 5, h: 0.3,
      fontSize: 10, color: THEME.colors.accent5, isTextBox: true, margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.5, y: 6.85, w: 0.5, h: 0.3, fontSize: 10,
    color: THEME.colors.accent5, align: 'right' },
})

/* ------------------------------------------------------------------ helpers */

/* A signal-head motif: three stacked lamps, one lit. Repeated across the deck. */
function signalHead(slide, x, y, lit, scale = 1) {
  const d = 0.26 * scale
  const gap = 0.33 * scale
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w: d + 0.22 * scale, h: gap * 3 + 0.16 * scale,
    fill: { color: '09111A' }, line: { color: '24323F', width: 1 },
    rectRadius: 0.06, objectName: 'signal housing',
  })
  const colors = [THEME.colors.accent3, THEME.colors.accent1, THEME.colors.accent2]
  colors.forEach((col, i) => {
    slide.addShape(pres.ShapeType.ellipse, {
      x: x + 0.11 * scale, y: y + 0.08 * scale + i * gap, w: d, h: d,
      fill: { color: i === lit ? col : '1B2730' },
      line: { color: i === lit ? col : '22303C', width: 1 },
      objectName: `lamp ${i}`,
    })
  })
}

/* Big number with a label underneath. */
function stat(slide, x, y, w, value, label, color, sub) {
  slide.addText(value, { x, y, w, h: 0.85, fontSize: 48, bold: true, color,
    align: 'center', isTextBox: true, margin: 0, objectName: `stat ${label}` })
  slide.addText(label, { x, y: y + 0.85, w, h: 0.4, fontSize: 13, color: C.text2,
    align: 'center', isTextBox: true, margin: 0 })
  if (sub) {
    slide.addText(sub, { x, y: y + 1.3, w, h: 0.35, fontSize: 10, italic: true,
      color: THEME.colors.accent5, align: 'center', isTextBox: true, margin: 0 })
  }
}

/* Card with a tinted background — never an edge stripe. */
function card(slide, x, y, w, h, fill, name) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, fill: { color: fill }, line: { color: fill, width: 0 },
    rectRadius: 0.08, objectName: name,
  })
}

const chartBase = {
  showLegend: false,
  catAxisLabelColor: THEME.colors.accent5,
  valAxisLabelColor: THEME.colors.accent5,
  catAxisLabelFontSize: 11,
  valAxisLabelFontSize: 11,
  catAxisLabelFontFace: '+mn-lt',
  valAxisLabelFontFace: '+mn-lt',
  dataLabelFontFace: '+mn-lt',
  dataLabelFontSize: 11,
  catGridLine: { style: 'none' },
  valGridLine: { color: 'DCE4EB', size: 1 },
}

/* ============================================================== 1. title === */
pres.addSection({ title: 'Opening' })
let s = pres.addSlide({ masterName: 'DARK_TITLE', sectionTitle: 'Opening' })
s.addText('SmartTraffic', { placeholder: 'title' })
s.addText([
  { text: 'Adaptive signal control built for lane-less Indian traffic', options: { breakLine: true } },
  { text: 'Design of Smart Cities   ·   15 controllers   ·   119 tests   ·   every claim reproducible',
    options: { fontSize: 13, color: THEME.colors.accent1 } },
], { placeholder: 'body' })
card(s, M, 5.75, 6.6, 1.15, THEME.colors.dk2, 'team card')
s.addText([
  { text: 'Rishab CV', options: { bold: true, color: 'FFFFFF' } },
  { text: '   24BCE5296', options: { color: THEME.colors.accent1 } },
], { x: M + 0.35, y: 5.9, w: 6.0, h: 0.4, fontSize: 15, isTextBox: true, margin: 0 })
s.addText([
  { text: 'Martin Wills', options: { bold: true, color: 'FFFFFF' } },
  { text: '   24BCE5255', options: { color: THEME.colors.accent1 } },
], { x: M + 0.35, y: 6.33, w: 6.0, h: 0.4, fontSize: 15, isTextBox: true, margin: 0 })
signalHead(s, W - 2.2, 2.3, 2, 1.6)
s.addNotes(
  'One line: we built an adaptive traffic signal controller, and the part that is ' +
  'genuinely new is that it is designed for traffic without lane discipline. ' +
  'Everything I show you can be re-run from the repository with one command.')

/* ========================================================== 2. the problem === */
pres.addSection({ title: 'Problem' })
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'Problem' })
s.addText('Chennai loses 132 hours per commuter, per year', { placeholder: 'title' })
stat(s, M, 1.7, 3.6, '31:15', 'to travel 10 km', THEME.colors.accent3, 'TomTom Traffic Index 2025')
stat(s, M + 3.9, 1.7, 3.6, '100.9%', 'evening congestion', THEME.colors.accent3, 'a trip takes twice free-flow')
stat(s, M + 7.8, 1.7, 3.6, '16 km/h', 'peak speed', THEME.colors.accent3, 'slower than a bicycle downhill')

card(s, M, 3.9, W - 2 * M, 1.95, THEME.colors.lt2, 'problem card')
s.addText('Signals are the cheapest lever a city has', {
  x: M + 0.35, y: 4.1, w: W - 2 * M - 0.7, h: 0.4, fontSize: 20, bold: true,
  color: C.text1, isTextBox: true, margin: 0 })
s.addText(
  'New roads take years and land nobody has. Retiming the signals on a corridor is ' +
  'software. The catch is that the control theory every adaptive system is built on ' +
  'was written for traffic that queues in lanes — and Indian traffic does not.',
  { x: M + 0.35, y: 4.6, w: W - 2 * M - 0.7, h: 1.1, fontSize: 15, color: C.text2,
    isTextBox: true, margin: 0 })
s.addNotes('Set up why signals matter, and plant the assumption that the whole deck turns on.')

/* ====================================================== 3. honest framing === */
s = pres.addSlide({ masterName: 'DARK_CONTENT', sectionTitle: 'Problem' })
s.addText('What is standard, and what is ours', { placeholder: 'title' })

card(s, M, 1.55, 5.8, 4.6, THEME.colors.dk2, 'standard card')
s.addText('Established work — implemented, not claimed', {
  x: M + 0.3, y: 1.8, w: 5.4, h: 0.4, fontSize: 16, bold: true,
  color: THEME.colors.accent5, isTextBox: true, margin: 0 })
s.addText([
  { text: 'Max-pressure control', options: { bullet: true, breakLine: true } },
  { text: 'Green-wave coordination', options: { bullet: true, breakLine: true } },
  { text: 'Emergency vehicle preemption', options: { bullet: true, breakLine: true } },
  { text: 'Transit signal priority', options: { bullet: true, breakLine: true } },
  { text: 'Reinforcement learning for signals', options: { bullet: true, breakLine: true } },
  { text: 'YOLO vehicle counting', options: { bullet: true } },
], { x: M + 0.3, y: 2.35, w: 5.2, h: 3.5, fontSize: 15, color: C.background1,
  paraSpaceAfter: 10, isTextBox: true, margin: 0 })

card(s, M + 6.1, 1.55, 5.8, 4.6, '2A2015', 'ours card')
s.addText('Ours', {
  x: M + 6.6, y: 1.8, w: 5.4, h: 0.4, fontSize: 16, bold: true,
  color: THEME.colors.accent1, isTextBox: true, margin: 0 })
s.addText([
  { text: 'A discharge model for lane-less mixed traffic, built from physical width and headway',
    options: { bullet: true, breakLine: true } },
  { text: 'Signal pressure measured in people per second of green, not vehicles or PCU',
    options: { bullet: true, breakLine: true } },
  { text: 'Two widely used evaluation metrics shown to be gameable — with the demonstration',
    options: { bullet: true } },
], { x: M + 6.4, y: 2.35, w: 5.2, h: 3.5, fontSize: 15, color: C.background1,
  paraSpaceAfter: 14, isTextBox: true, margin: 0 })

s.addNotes(
  'Say this out loud early. Judges respect a team that knows which parts of its own ' +
  'project are textbook. It buys credibility for the part that is not.')

/* ========================================================= 4. the assumption */
pres.addSection({ title: 'The novelty' })
s = pres.addSlide({ masterName: 'DARK_DIVIDER', sectionTitle: 'The novelty' })
s.addText('Signal theory assumes lane discipline', { placeholder: 'title' })
s.addText('Two-wheelers filter into lateral gaps and cross two or three abreast where one car fits. ' +
  'What limits the stop line is lateral space — not a factor calibrated for moving traffic.',
  { placeholder: 'body' })
s.addNotes('The pivot of the whole deck. Pause here.');

/* ======================================================== 5. the measurement */
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'The novelty' })
s.addText('The conventional factor is 56% too high', { placeholder: 'title' })

s.addChart(pres.ChartType.bar, [
  { name: 'Static PCU (used today)', labels: ['Two-wheeler', 'Auto', 'Car', 'Bus'], values: [0.50, 0.80, 1.00, 3.00] },
  { name: 'Implied by real discharge', labels: ['Two-wheeler', 'Auto', 'Car', 'Bus'], values: [0.32, 0.66, 1.00, 1.80] },
], {
  ...chartBase, x: M, y: 1.6, w: 7.3, h: 4.3,
  barDir: 'col', barGrouping: 'clustered',
  chartColors: [THEME.colors.accent5, THEME.colors.accent1],
  showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: '44525F',
  showLegend: true, legendPos: 'b', legendColor: '44525F', legendFontSize: 11,
  legendFontFace: '+mn-lt',
  showTitle: true, title: 'Car-equivalents per vehicle', titleColor: '44525F',
  titleFontSize: 13, titleFontFace: '+mn-lt',
  valAxisMaxVal: 3.2,
})

card(s, M + 7.6, 1.6, 4.3, 4.3, THEME.colors.lt2, 'finding card')
s.addText('56%', { x: M + 7.9, y: 1.9, w: 3.7, h: 0.9, fontSize: 54, bold: true,
  color: THEME.colors.accent3, isTextBox: true, margin: 0 })
s.addText('too high for a two-wheeler', { x: M + 7.9, y: 2.8, w: 3.7, h: 0.4,
  fontSize: 14, color: C.text2, isTextBox: true, margin: 0 })
s.addText(
  'Static PCU measures space in moving traffic. A junction asks a different question: ' +
  'how long does this queue take to clear?\n\n' +
  'Our model reproduces the textbook figure for cars exactly — 1800 veh/h/lane — so it ' +
  'departs from convention only where lane discipline does.',
  { x: M + 7.9, y: 3.35, w: 3.7, h: 2.3, fontSize: 13, color: C.text2,
    isTextBox: true, margin: 0 })

s.addNotes(
  'The car column being identical is the important detail. It shows we have not just ' +
  'invented numbers that suit us — where the old assumption holds, we agree with it exactly.')

/* ============================================================ 6. the cost === */
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'The novelty' })
s.addText('That error becomes wasted green', { placeholder: 'title' })

s.addChart(pres.ChartType.line, [{
  name: 'Green allocated beyond need',
  labels: ['0%', '15%', '30%', '45%', '60%', '75%'],
  values: [6.0, 9.3, 14.5, 21.5, 29.1, 39.5],
}], {
  ...chartBase, x: M, y: 1.6, w: 7.6, h: 4.2,
  chartColors: [THEME.colors.accent3],
  lineSize: 4, lineSmooth: true,
  showValue: true, dataLabelPosition: 't', dataLabelColor: '44525F',
  showTitle: true, title: 'Two-wheeler share of the queue', titleColor: '44525F',
  titleFontSize: 13, titleFontFace: '+mn-lt',
})

s.addText('Indian urban arterials run at about 45%', {
  x: M + 7.9, y: 1.7, w: 4.0, h: 0.6, fontSize: 17, bold: true, color: C.text1,
  isTextBox: true, margin: 0 })
s.addText(
  'At that mix a conventional controller holds the approach green 21.5% longer than ' +
  'the traffic needs. Those seconds are taken from the cross street while the road ' +
  'it was given to stands empty.',
  { x: M + 7.9, y: 2.4, w: 4.0, h: 1.6, fontSize: 14, color: C.text2, isTextBox: true, margin: 0 })

card(s, M + 7.9, 4.1, 4.0, 1.75, THEME.colors.lt2, 'robustness card')
s.addText('Robust to our own assumptions', { x: M + 8.15, y: 4.3, w: 3.5, h: 0.35,
  fontSize: 13, bold: true, color: C.text1, isTextBox: true, margin: 0 })
s.addText(
  'Swept across the full plausible range of widths and headways, the error stays ' +
  'between +4.6% and +34.7%. It survives us being wrong.',
  { x: M + 8.15, y: 4.65, w: 3.5, h: 1.05, fontSize: 12, color: C.text2,
    isTextBox: true, margin: 0 })

s.addNotes('If asked "how do you know your parameters are right" — point at the sweep. ' +
  'We do not need them to be exactly right for the conclusion to hold.')

/* =========================================================== 7. failures === */
pres.addSection({ title: 'Method' })
s = pres.addSlide({ masterName: 'DARK_CONTENT', sectionTitle: 'Method' })
s.addText('It did nothing. Three times.', { placeholder: 'title' })

const attempts = [
  ['1', 'Corrected the measure', 'No effect. The bias applied equally to both roads, so it cancelled.', THEME.colors.accent3],
  ['2', 'Made the two roads differ', 'Still almost nothing. Only blocked arrivals moved, barely.', THEME.colors.accent3],
  ['3', 'Diagnosed it', 'Controllers agreed 85% of the time. Green was not scarce, so allocating it badly cost nothing.', THEME.colors.accent1],
  ['4', 'Allocated green duration', 'It worked. Choosing which road is binary; how long is where a bad measure costs you.', THEME.colors.accent2],
]
attempts.forEach((a, i) => {
  const y = 1.6 + i * 1.22
  card(s, M, y, W - 2 * M, 1.05, i === 3 ? '13301F' : THEME.colors.dk2, `attempt ${a[0]}`)
  s.addShape(pres.ShapeType.ellipse, { x: M + 0.3, y: y + 0.26, w: 0.52, h: 0.52,
    fill: { color: a[3] }, line: { color: a[3], width: 0 }, objectName: `badge ${a[0]}` })
  s.addText(a[0], { x: M + 0.3, y: y + 0.3, w: 0.52, h: 0.45, fontSize: 18, bold: true,
    color: '0E1620', align: 'center', isTextBox: true, margin: 0 })
  s.addText(a[1], { x: M + 1.05, y: y + 0.17, w: 3.3, h: 0.4, fontSize: 16, bold: true,
    color: C.background1, isTextBox: true, margin: 0 })
  s.addText(a[2], { x: M + 4.45, y: y + 0.17, w: W - 2 * M - 4.75, h: 0.75, fontSize: 13,
    color: THEME.colors.accent5, isTextBox: true, margin: 0 })
})

s.addNotes(
  'This slide is deliberately about failure. The third attempt is the one to dwell on: ' +
  'we found our own fix had raised capacity so much that nothing was scarce. ' +
  'That diagnosis is the actual engineering.')

/* ============================================================ 8. result ===== */
pres.addSection({ title: 'Results' })
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'Results' })
s.addText('Scooter feeder meets bus arterial', { placeholder: 'title' })

s.addChart(pres.ChartType.bar, [
  { name: 'People moved', labels: ['Static PCU\n(deployed today)', 'Efficiency only', 'People per second\n(ours)'],
    values: [34772, 41099, 36683] },
], {
  ...chartBase, x: M, y: 1.6, w: 6.1, h: 4.2,
  barDir: 'col',
  chartColors: [THEME.colors.accent5, THEME.colors.accent3, THEME.colors.accent2],
  showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: '44525F',
  showTitle: true, title: 'People moved', titleColor: '44525F',
  titleFontSize: 13, titleFontFace: '+mn-lt',
  valAxisMaxVal: 46000,
})

s.addChart(pres.ChartType.bar, [
  { name: 'Worst approach wait', labels: ['Static PCU\n(deployed today)', 'Efficiency only', 'People per second\n(ours)'],
    values: [31.5, 184.5, 37.1] },
], {
  ...chartBase, x: M + 6.4, y: 1.6, w: 5.5, h: 4.2,
  barDir: 'col',
  chartColors: [THEME.colors.accent5, THEME.colors.accent3, THEME.colors.accent2],
  showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: '44525F',
  showTitle: true, title: 'Worst approach wait (ticks) — lower is better',
  titleColor: '44525F', titleFontSize: 13, titleFontFace: '+mn-lt',
  valAxisMaxVal: 215,
})

s.addText('+1,911 ± 848 more people moved than what is deployed today — and no road left starving',
  { x: M, y: 5.95, w: W - 2 * M, h: 0.45, fontSize: 15, bold: true, italic: true,
    color: C.text1, align: 'center', isTextBox: true, margin: 0 })

s.addNotes(
  'Point at the red bar on the right. That is our own first attempt, and it is ' +
  'unusable: it leaves one road red for minutes. Showing it is the point.')

/* ========================================================= 9. the equity === */
s = pres.addSlide({ masterName: 'DARK_CONTENT', sectionTitle: 'Results' })
s.addText('We found the flaw in our own fix', { placeholder: 'title' })

card(s, M, 1.6, 5.7, 4.3, '2A1518', 'problem card')
s.addText('The problem', { x: M + 0.35, y: 1.85, w: 5.0, h: 0.4, fontSize: 17, bold: true,
  color: THEME.colors.accent3, isTextBox: true, margin: 0 })
s.addText(
  'Optimising green-seconds-per-vehicle treats a two-wheeler road as cheap — and ' +
  'therefore low value. It scored badly on exactly the thing being maximised.\n\n' +
  'The feeder starved: 184 ticks of waiting. In an Indian city those riders are the ' +
  'least able to absorb it.',
  { x: M + 0.35, y: 2.35, w: 5.0, h: 3.2, fontSize: 14, color: C.background1,
    isTextBox: true, margin: 0 })

card(s, M + 6.2, 1.6, 5.7, 4.3, '13301F', 'fix card')
s.addText('The fix', { x: M + 6.55, y: 1.85, w: 5.0, h: 0.4, fontSize: 17, bold: true,
  color: THEME.colors.accent2, isTextBox: true, margin: 0 })
s.addText(
  'We were optimising a proxy. Road efficiency is a constraint, not the goal.\n\n' +
  'So we score each road by people moved per second of green, with an explicit ' +
  'fairness term on accumulated red time.\n\n' +
  'Worst-case waiting fell from 184 ticks to 37 — a five-fold cut — while still ' +
  'beating what is deployed today.',
  { x: M + 6.55, y: 2.35, w: 5.0, h: 3.2, fontSize: 14, color: C.background1,
    isTextBox: true, margin: 0 })

s.addNotes(
  'If you remember one slide, remember this one. A team that finds the equity problem ' +
  'in its own result, and says so before being asked, is a team worth trusting.')

/* ========================================================= 10. metric traps */
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'Results' })
s.addText('Two standard metrics turned out to be gameable', { placeholder: 'title' })

card(s, M, 1.6, 5.75, 4.4, THEME.colors.lt2, 'trap one')
signalHead(s, M + 0.35, 1.9, 0, 0.85)
s.addText('Average queue rewards refusing traffic', {
  x: M + 1.3, y: 1.95, w: 4.1, h: 0.75, fontSize: 17, bold: true, color: C.text1,
  isTextBox: true, margin: 0 })
s.addText(
  'A road held at red fills up and then turns arrivals away. Those vehicles never ' +
  'enter the network, so they never appear in the statistic.\n\n' +
  'A plain fixed clock "beat" our controller by blocking about 100 more vehicles ' +
  'per run while serving fewer.',
  { x: M + 0.35, y: 3.0, w: 5.05, h: 2.8, fontSize: 14, color: C.text2,
    isTextBox: true, margin: 0 })

card(s, M + 6.15, 1.6, 5.75, 4.4, THEME.colors.lt2, 'trap two')
signalHead(s, M + 6.5, 1.9, 0, 0.85)
s.addText('Mean delay hides starvation', {
  x: M + 7.45, y: 1.95, w: 4.1, h: 0.75, fontSize: 17, bold: true, color: C.text1,
  isTextBox: true, margin: 0 })
s.addText(
  'Our first RL controller posted the lowest mean queue in the benchmark — by ' +
  'learning to keep some approaches permanently red.\n\n' +
  'Its 95th-percentile delay was 66 ticks against a fixed clock’s 27. ' +
  'Every claim we make now carries p95 and worst-case beside the average.',
  { x: M + 6.5, y: 3.0, w: 5.05, h: 2.8, fontSize: 14, color: C.text2,
    isTextBox: true, margin: 0 })

s.addNotes(
  'These are findings about how the field evaluates itself, not just about our code. ' +
  'Both were caught by our own benchmark, which is the argument for building one properly.')

/* ======================================================= 11. deployability = */
pres.addSection({ title: 'Deployability' })
s = pres.addSlide({ masterName: 'DARK_CONTENT', sectionTitle: 'Deployability' })
s.addText('Built to be installed, not just benchmarked', { placeholder: 'title' })

const pillars = [
  ['Safety shield', 'Minimum green, starvation limits, a guaranteed maximum pedestrian wait. The optimiser proposes; the shield disposes.', THEME.colors.accent2],
  ['Fails safe', 'Kill a detector, drop comms, fail a signal head — each routes to a documented fallback and the UI says which.', THEME.colors.accent1],
  ['Explains itself', 'Every phase change is logged with the pressures behind it and the constraint that overrode the optimiser.', THEME.colors.accent4],
  ['Speaks in city units', 'Idle fuel, CO₂ and rupees per year, with every assumption listed and challengeable.', THEME.colors.accent6],
]
pillars.forEach((p, i) => {
  const x = M + (i % 2) * 6.2
  const y = 1.6 + Math.floor(i / 2) * 2.3
  card(s, x, y, 5.9, 2.0, THEME.colors.dk2, `pillar ${p[0]}`)
  s.addShape(pres.ShapeType.ellipse, { x: x + 0.3, y: y + 0.3, w: 0.42, h: 0.42,
    fill: { color: p[2] }, line: { color: p[2], width: 0 }, objectName: `dot ${i}` })
  s.addText(p[0], { x: x + 0.95, y: y + 0.26, w: 4.6, h: 0.45, fontSize: 18, bold: true,
    color: C.background1, isTextBox: true, margin: 0 })
  s.addText(p[1], { x: x + 0.3, y: y + 0.85, w: 5.3, h: 1.0, fontSize: 13,
    color: THEME.colors.accent5, isTextBox: true, margin: 0 })
})

s.addNotes('Keep this brisk — 30 seconds. It is table stakes, not the headline.')

/* ========================================================= 12. verification */
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'Deployability' })
s.addText('Every number in this deck re-runs on demand', { placeholder: 'title' })

card(s, M, 1.6, W - 2 * M, 1.5, '0E1620', 'command card')
s.addText('python scripts/reproduce_results.py', {
  x: M + 0.4, y: 1.85, w: 8.0, h: 0.5, fontSize: 20, bold: true,
  fontFace: 'Courier New', color: THEME.colors.accent2, isTextBox: true, margin: 0 })
s.addText('Re-measures every documented claim and exits non-zero if one has stopped being true.',
  { x: M + 0.4, y: 2.4, w: 11.0, h: 0.5, fontSize: 14, color: THEME.colors.accent5,
    isTextBox: true, margin: 0 })

stat(s, M, 3.4, 3.7, '10/10', 'claims reproduced', THEME.colors.accent2)
stat(s, M + 4.1, 3.4, 3.7, '119', 'automated tests', C.text1)
stat(s, M + 8.2, 3.4, 3.7, 'CI', 'fails on drift', THEME.colors.accent1)

card(s, M, 5.15, W - 2 * M, 1.5, THEME.colors.lt2, 'negatives card')
s.addText('It verifies the results that went against us, too', {
  x: M + 0.35, y: 5.32, w: 11.2, h: 0.4, fontSize: 16, bold: true, color: C.text1,
  isTextBox: true, margin: 0 })
s.addText(
  'The claim that our correction changes nothing when both roads carry the same traffic ' +
  'must keep coming back with a confidence interval spanning zero. If a future change ' +
  'makes that pass for the wrong reason, the build goes red.',
  { x: M + 0.35, y: 5.75, w: 11.2, h: 0.8, fontSize: 13, color: C.text2,
    isTextBox: true, margin: 0 })

s.addNotes(
  'This is the slide that separates us from a demo. Offer to run it live if they want.')

/* ========================================================= 13. limitations = */
s = pres.addSlide({ masterName: 'DARK_CONTENT', sectionTitle: 'Deployability' })
s.addText('What we are not claiming', { placeholder: 'title' })

const limits = [
  ['Parameters are estimates, not measurements', 'Lateral widths and headways are centre estimates. Calibrating them needs stop-line video from a real junction, which we have not done.'],
  ['It trades vehicles for people', 'About 1,800 fewer vehicles move while 1,900 more people do. Whether a city wants that is a policy decision, not a technical result.'],
  ['It loses where traffic is uniform', 'With every road carrying the same mix it is measurably behind the conventional controller. It pays only when roads differ and green is scarce.'],
  ['The engine is not a traffic simulator', 'Final performance claims must be regenerated in SUMO with a heterogeneous vehicle set.'],
]
limits.forEach((l, i) => {
  const y = 1.55 + i * 1.27
  card(s, M, y, W - 2 * M, 1.1, THEME.colors.dk2, `limit ${i}`)
  s.addText(l[0], { x: M + 0.35, y: y + 0.14, w: 4.9, h: 0.8, fontSize: 15, bold: true,
    color: THEME.colors.accent1, isTextBox: true, margin: 0 })
  s.addText(l[1], { x: M + 5.4, y: y + 0.14, w: W - 2 * M - 5.75, h: 0.85, fontSize: 13,
    color: THEME.colors.accent5, isTextBox: true, margin: 0 })
})

s.addNotes(
  'Volunteering limitations before being asked changes how the rest of the deck is heard. ' +
  'It is also the honest position.')

/* ============================================================== 14. close == */
pres.addSection({ title: 'Close' })
s = pres.addSlide({ masterName: 'DARK_TITLE', sectionTitle: 'Close' })
s.addText('Measure the right thing', { placeholder: 'title' })
s.addText([
  { text: 'Control theory imported from the West assumes lane discipline. We modelled ' +
      'lane-less traffic from physics, showed the standard method mis-allocates green ' +
      'by 21%, and fixed the equity problem that correction created.',
    options: { breakLine: true } },
  { text: 'Every figure re-runs with one command — including the ones that went against us.',
    options: { fontSize: 13, color: THEME.colors.accent1 } },
], { placeholder: 'body' })
signalHead(s, W - 2.2, 2.3, 2, 1.6)
s.addNotes(
  'Close on the one-sentence version. Then offer the live demo: the Mixed fleet tab ' +
  'runs the whole study in front of them, and the control condition is a checkbox.')

/* --------------------------------------------------------------- write out */
const out = path.join(__dirname, 'SmartTraffic-full.pptx')
pres.writeFile({ fileName: out })
  .then(() => applyTheme(out, THEME))
  .then(() => console.log('wrote', out))
  .catch(err => { console.error(err); process.exit(1) })
