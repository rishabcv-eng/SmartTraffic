/*
 * SmartTraffic — 5-minute review presentation.
 *
 * Seven slides at roughly 40 seconds each. The 14-slide version in
 * build_deck.js is the full talk; this one keeps only what survives a
 * five-minute slot: the assumption that is wrong, the measurement, the fix,
 * the result, and the fact that all of it re-runs on demand.
 *
 * Every figure comes from the repository. `python scripts/reproduce_results.py`
 * regenerates each one and fails if it has stopped being true.
 */

const path = require('path')
const pptxgen = require('pptxgenjs')
const { applyTheme } = require(path.join(
  'C:', 'Users', 'LENOVO', 'AppData', 'Roaming', 'Claude',
  'local-agent-mode-sessions', 'skills-plugin',
  'dba9ee21-2cac-4a98-a997-79d2ef5c4fdd', '92f5ba76-f399-4531-96cc-076284e5cfd1',
  'skills', 'pptx', 'scripts', 'apply_theme.js',
))

const THEME = {
  name: 'SmartTraffic Signal',
  headFontFace: 'Cambria',
  bodyFontFace: 'Calibri',
  colors: {
    dk1: '0E1620', lt1: 'FFFFFF', dk2: '1B2A3A', lt2: 'EEF3F7',
    accent1: 'FFB347', accent2: '3CE87C', accent3: 'FF5A5A',
    accent4: '8FD8FF', accent5: '94A7B8', accent6: 'C9A227',
    hlink: '8FD8FF', folHlink: '94A7B8',
  },
}

const pres = new pptxgen()
pres.layout = 'LAYOUT_WIDE'
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace }
pres.author = 'Rishab CV, Martin Wills'
pres.company = 'SmartTraffic'
pres.title = 'SmartTraffic — adaptive signal control for lane-less traffic'

const C = pres.SchemeColor
const W = 13.3
const M = 0.7

pres.defineSlideMaster({
  title: 'DARK_TITLE',
  background: { color: THEME.colors.dk1 },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: M, y: 2.0, w: W - 2 * M, h: 1.4,
      fontSize: 46, bold: true, color: C.background1 }, text: '' } },
    { placeholder: { options: { name: 'body', type: 'body', x: M, y: 3.5, w: W - 2 * M, h: 1.0,
      fontSize: 18, color: THEME.colors.accent5 }, text: '' } },
  ],
})

pres.defineSlideMaster({
  title: 'LIGHT_CONTENT',
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: M, y: 0.5, w: W - 2 * M, h: 0.95,
      fontSize: 36, bold: true, color: C.text1 }, text: '' } },
    { text: { text: 'SmartTraffic · Design of Smart Cities', options: { x: M, y: 6.85, w: 6, h: 0.3,
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
    { text: { text: 'SmartTraffic · Design of Smart Cities', options: { x: M, y: 6.85, w: 6, h: 0.3,
      fontSize: 10, color: THEME.colors.accent5, isTextBox: true, margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.5, y: 6.85, w: 0.5, h: 0.3, fontSize: 10,
    color: THEME.colors.accent5, align: 'right' },
})

function signalHead(slide, x, y, lit, scale = 1) {
  const d = 0.26 * scale, gap = 0.33 * scale
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w: d + 0.22 * scale, h: gap * 3 + 0.16 * scale,
    fill: { color: '09111A' }, line: { color: '24323F', width: 1 },
    rectRadius: 0.06, objectName: 'signal housing',
  })
  ;[THEME.colors.accent3, THEME.colors.accent1, THEME.colors.accent2].forEach((col, i) => {
    slide.addShape(pres.ShapeType.ellipse, {
      x: x + 0.11 * scale, y: y + 0.08 * scale + i * gap, w: d, h: d,
      fill: { color: i === lit ? col : '1B2730' },
      line: { color: i === lit ? col : '22303C', width: 1 },
      objectName: `lamp ${i}`,
    })
  })
}

function card(slide, x, y, w, h, fill, name) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, fill: { color: fill }, line: { color: fill, width: 0 },
    rectRadius: 0.08, objectName: name,
  })
}

const chartBase = {
  showLegend: false,
  catAxisLabelColor: THEME.colors.accent5, valAxisLabelColor: THEME.colors.accent5,
  catAxisLabelFontSize: 11, valAxisLabelFontSize: 11,
  catAxisLabelFontFace: '+mn-lt', valAxisLabelFontFace: '+mn-lt',
  dataLabelFontFace: '+mn-lt', dataLabelFontSize: 11,
  catGridLine: { style: 'none' }, valGridLine: { color: 'DCE4EB', size: 1 },
}

/* ====================================================== 1. title (0:00) === */
pres.addSection({ title: 'Deck' })
let s = pres.addSlide({ masterName: 'DARK_TITLE', sectionTitle: 'Deck' })
s.addText('SmartTraffic', { placeholder: 'title' })
s.addText('Adaptive signal control built for lane-less Indian traffic   ·   Design of Smart Cities',
  { placeholder: 'body' })
card(s, M, 4.6, 6.6, 1.35, THEME.colors.dk2, 'team card')
s.addText([
  { text: 'Rishab CV', options: { bold: true, color: 'FFFFFF' } },
  { text: '   24BCE5296', options: { color: THEME.colors.accent1 } },
], { x: M + 0.35, y: 4.78, w: 6.0, h: 0.42, fontSize: 16, isTextBox: true, margin: 0 })
s.addText([
  { text: 'Martin Wills', options: { bold: true, color: 'FFFFFF' } },
  { text: '   24BCE5255', options: { color: THEME.colors.accent1 } },
], { x: M + 0.35, y: 5.25, w: 6.0, h: 0.42, fontSize: 16, isTextBox: true, margin: 0 })
signalHead(s, W - 2.2, 2.0, 2, 1.6)
s.addNotes(
  '[0:00-0:25] We built an adaptive traffic signal controller. The part that is new is ' +
  'that it is designed for traffic without lane discipline. Everything I show you ' +
  're-runs from the repository with one command.')

/* ================================================== 2. the assumption (0:25) */
s = pres.addSlide({ masterName: 'DARK_CONTENT', sectionTitle: 'Deck' })
s.addText('Signal theory assumes lane discipline', { placeholder: 'title' })

card(s, M, 1.7, 5.75, 3.9, THEME.colors.dk2, 'assumption card')
s.addText('What the textbooks assume', { x: M + 0.35, y: 1.95, w: 5.0, h: 0.4,
  fontSize: 17, bold: true, color: THEME.colors.accent5, isTextBox: true, margin: 0 })
s.addText(
  'Vehicles queue single file. One crosses per lane per headway. A fixed factor ' +
  'converts a bus or a scooter into "car equivalents".',
  { x: M + 0.35, y: 2.5, w: 5.0, h: 2.8, fontSize: 15, color: C.background1,
    isTextBox: true, margin: 0 })

card(s, M + 6.15, 1.7, 5.75, 3.9, '2A2015', 'reality card')
s.addText('What an Indian junction does', { x: M + 6.5, y: 1.95, w: 5.0, h: 0.4,
  fontSize: 17, bold: true, color: THEME.colors.accent1, isTextBox: true, margin: 0 })
s.addText(
  'Two-wheelers filter into lateral gaps and cross two or three abreast where one ' +
  'car fits. What limits the stop line is lateral space — not a factor calibrated ' +
  'for moving traffic.',
  { x: M + 6.5, y: 2.5, w: 5.0, h: 2.8, fontSize: 15, color: C.background1,
    isTextBox: true, margin: 0 })

s.addText('Chennai: 132 hours lost per driver per year, 16 km/h at peak  ·  TomTom 2025',
  { x: M, y: 5.85, w: W - 2 * M, h: 0.4, fontSize: 13, italic: true,
    color: THEME.colors.accent5, align: 'center', isTextBox: true, margin: 0 })

s.addNotes(
  '[0:25-1:10] Every adaptive system in the world is built on the left-hand column. ' +
  'Indian traffic is the right-hand column. That gap is the whole project.')

/* ================================================= 3. the measurement (1:10) */
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'Deck' })
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
  titleFontSize: 13, titleFontFace: '+mn-lt', valAxisMaxVal: 3.2,
})

card(s, M + 7.6, 1.6, 4.3, 4.3, THEME.colors.lt2, 'finding card')
s.addText('21.5%', { x: M + 7.9, y: 1.9, w: 3.7, h: 0.9, fontSize: 50, bold: true,
  color: THEME.colors.accent3, isTextBox: true, margin: 0 })
s.addText('of green wasted at Indian traffic mixes', { x: M + 7.9, y: 2.8, w: 3.7, h: 0.6,
  fontSize: 14, color: C.text2, isTextBox: true, margin: 0 })
s.addText(
  'Held green after the queue has already cleared. Those seconds are taken from the ' +
  'cross street.\n\n' +
  'Our model reproduces the textbook figure for cars exactly, so it departs from ' +
  'convention only where lane discipline does.',
  { x: M + 7.9, y: 3.5, w: 3.7, h: 2.2, fontSize: 13, color: C.text2,
    isTextBox: true, margin: 0 })

s.addNotes(
  '[1:10-2:00] We derived discharge from physical width and headway instead. ' +
  'The car column being identical matters — where the old assumption holds, we agree ' +
  'with it exactly. We are not just picking numbers that suit us.')

/* ========================================================= 4. the fix (2:00) */
s = pres.addSlide({ masterName: 'DARK_CONTENT', sectionTitle: 'Deck' })
s.addText('We found the flaw in our own fix', { placeholder: 'title' })

card(s, M, 1.65, 5.7, 4.3, '2A1518', 'problem card')
s.addText('Correcting the measure was not enough', { x: M + 0.35, y: 1.9, w: 5.0, h: 0.75,
  fontSize: 17, bold: true, color: THEME.colors.accent3, isTextBox: true, margin: 0 })
s.addText(
  'Optimising green-seconds-per-vehicle treats a scooter road as cheap, so it scored ' +
  'badly on the very thing being maximised.\n\n' +
  'It starved that road: 184 ticks of waiting — minutes — falling on the riders least ' +
  'able to absorb it.',
  { x: M + 0.35, y: 2.75, w: 5.0, h: 3.0, fontSize: 14, color: C.background1,
    isTextBox: true, margin: 0 })

card(s, M + 6.2, 1.65, 5.7, 4.3, '13301F', 'fix card')
s.addText('So we changed what we optimise', { x: M + 6.55, y: 1.9, w: 5.0, h: 0.75,
  fontSize: 17, bold: true, color: THEME.colors.accent2, isTextBox: true, margin: 0 })
s.addText(
  'Road efficiency is a constraint, not the goal. The controller now scores each ' +
  'road by people moved per second of green, with a fairness term on accumulated ' +
  'red time.\n\n' +
  'Worst-case waiting fell from 184 ticks to 37 — a five-fold cut.',
  { x: M + 6.55, y: 2.75, w: 5.0, h: 3.0, fontSize: 14, color: C.background1,
    isTextBox: true, margin: 0 })

s.addNotes(
  '[2:00-2:55] This is the slide to dwell on. We found the equity problem in our own ' +
  'result and fixed it, rather than reporting the bigger number and hoping nobody asked.')

/* ========================================================= 5. result (2:55) */
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'Deck' })
s.addText('Scooter feeder meets bus arterial', { placeholder: 'title' })

s.addChart(pres.ChartType.bar, [
  { name: 'People moved',
    labels: ['Static PCU\n(deployed today)', 'Efficiency only', 'People per second\n(ours)'],
    values: [34772, 41099, 36683] },
], {
  ...chartBase, x: M, y: 1.6, w: 6.1, h: 4.1,
  barDir: 'col',
  chartColors: [THEME.colors.accent5, THEME.colors.accent3, THEME.colors.accent2],
  showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: '44525F',
  showTitle: true, title: 'People moved', titleColor: '44525F',
  titleFontSize: 13, titleFontFace: '+mn-lt', valAxisMaxVal: 46000,
})

s.addChart(pres.ChartType.bar, [
  { name: 'Worst approach wait',
    labels: ['Static PCU\n(deployed today)', 'Efficiency only', 'People per second\n(ours)'],
    values: [31.5, 184.5, 37.1] },
], {
  ...chartBase, x: M + 6.4, y: 1.6, w: 5.5, h: 4.1,
  barDir: 'col',
  chartColors: [THEME.colors.accent5, THEME.colors.accent3, THEME.colors.accent2],
  showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: '44525F',
  showTitle: true, title: 'Worst approach wait (ticks) — lower is better',
  titleColor: '44525F', titleFontSize: 13, titleFontFace: '+mn-lt', valAxisMaxVal: 215,
})

s.addText('+1,911 ± 848 more people moved than what is deployed today — and no road left starving',
  { x: M, y: 5.85, w: W - 2 * M, h: 0.45, fontSize: 15, bold: true, italic: true,
    color: C.text1, align: 'center', isTextBox: true, margin: 0 })

s.addNotes(
  '[2:55-3:50] Ten seeds, paired confidence intervals. The red bar is our own first ' +
  'attempt — we show it because it is the reason the final controller is shaped this way.')

/* =================================================== 6. verifiable (3:50) === */
s = pres.addSlide({ masterName: 'LIGHT_CONTENT', sectionTitle: 'Deck' })
s.addText('Every number re-runs on demand', { placeholder: 'title' })

card(s, M, 1.6, W - 2 * M, 1.35, '0E1620', 'command card')
s.addText('python scripts/reproduce_results.py', {
  x: M + 0.4, y: 1.82, w: 8.0, h: 0.5, fontSize: 20, bold: true,
  fontFace: 'Courier New', color: THEME.colors.accent2, isTextBox: true, margin: 0 })
s.addText('Re-measures every documented claim and exits non-zero if one has stopped being true.',
  { x: M + 0.4, y: 2.34, w: 11.0, h: 0.45, fontSize: 14, color: THEME.colors.accent5,
    isTextBox: true, margin: 0 })

const stats = [['10/10', 'claims reproduced', THEME.colors.accent2],
               ['122', 'automated tests', C.text1],
               ['15', 'controllers benchmarked', C.text1]]
stats.forEach((st, i) => {
  const x = M + i * 4.0
  s.addText(st[0], { x, y: 3.25, w: 3.7, h: 0.8, fontSize: 44, bold: true, color: st[2],
    align: 'center', isTextBox: true, margin: 0 })
  s.addText(st[1], { x, y: 4.05, w: 3.7, h: 0.35, fontSize: 13, color: C.text2,
    align: 'center', isTextBox: true, margin: 0 })
})

card(s, M, 4.65, W - 2 * M, 1.5, THEME.colors.lt2, 'limits card')
s.addText('What we are not claiming', { x: M + 0.35, y: 4.82, w: 11.2, h: 0.4,
  fontSize: 15, bold: true, color: C.text1, isTextBox: true, margin: 0 })
s.addText(
  'Discharge parameters are estimates, not measurements from a real junction. It moves ' +
  'more people but fewer vehicles, which is a policy choice. And where every road carries ' +
  'the same traffic it is measurably behind the conventional controller.',
  { x: M + 0.35, y: 5.22, w: 11.2, h: 0.8, fontSize: 13, color: C.text2,
    isTextBox: true, margin: 0 })

s.addNotes(
  '[3:50-4:40] Say the limitations out loud. Volunteering them before being asked is ' +
  'what makes the rest of the numbers believable.')

/* ============================================================ 7. close (4:40) */
s = pres.addSlide({ masterName: 'DARK_TITLE', sectionTitle: 'Deck' })
s.addText('Measure the right thing', { placeholder: 'title' })
s.addText(
  'Control theory imported from the West assumes lane discipline. We modelled lane-less ' +
  'traffic from physics, showed the standard method mis-allocates green by 21%, and fixed ' +
  'the equity problem that correction created.',
  { placeholder: 'body' })
card(s, M, 4.9, 6.6, 1.1, THEME.colors.dk2, 'team card')
s.addText('Rishab CV · 24BCE5296       Martin Wills · 24BCE5255', {
  x: M + 0.35, y: 5.18, w: 6.0, h: 0.45, fontSize: 14, color: THEME.colors.accent1,
  isTextBox: true, margin: 0 })
signalHead(s, W - 2.2, 2.0, 2, 1.6)
s.addNotes(
  '[4:40-5:00] Close on the one-sentence version, then offer the live demo: the Mixed ' +
  'fleet tab runs the whole study on screen, and the control condition is a checkbox.')

const out = path.join(__dirname, 'SmartTraffic-5min.pptx')
pres.writeFile({ fileName: out })
  .then(() => applyTheme(out, THEME))
  .then(() => console.log('wrote', out))
  .catch(err => { console.error(err); process.exit(1) })
