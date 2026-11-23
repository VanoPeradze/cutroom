const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../web/timeline.js'), 'utf8').replace(/^export /gm, '');
const font = 'Geist, "Noto Sans Hebrew", "Segoe UI", sans-serif';
const plain = value => JSON.parse(JSON.stringify(value));

function fixture({ browser = true, palette = {}, firstFrameId = 0 } = {}) {
  const frames = new Map(), observers = [], views = [];
  const root = { dataset: { theme: 'dark' } };
  let nextFrame = firstFrameId, styleReads = 0, resolveFonts, rejectFonts;
  const ready = new Promise((resolve, reject) => { resolveFonts = resolve; rejectFonts = reject; });
  const window = { devicePixelRatio: 1 };
  const document = { documentElement: root, defaultView: window, fonts: { ready } };
  if (browser) {
    window.MutationObserver = class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe(target, options) { this.target = target; this.options = options; }
    };
    window.CSS = { supports: (property, value) => property === 'color' && !/var\(|gradient\(/.test(value) };
    window.getComputedStyle = canvas => {
      styleReads++;
      assert.ok(views.some(view => view.canvas === canvas), 'resolve inherited styles on each canvas');
      return { getPropertyValue: name => palette[root.dataset.theme]?.[name] || '' };
    };
  }
  const scope = vm.createContext({
    window, ...(browser ? { document } : {}),
    ResizeObserver: class { observe() {} },
    requestAnimationFrame(callback) { const id = nextFrame++; frames.set(id, callback); return id; },
    cancelAnimationFrame(id) { frames.delete(id); },
  });
  vm.runInContext(source + '\nglobalThis.TimelineView = TimelineView;', scope);
  function create(sourceReview = false) {
    const calls = [], stack = [], state = { globalAlpha: 1, direction: 'ltr' };
    const ctx = new Proxy(state, {
      get(target, key) {
        if (key in target) return target[key];
        if (key === 'measureText') return text => ({ width: String(text).length * 6 });
        if (key === 'createLinearGradient') return () => ({ addColorStop() {} });
        return (...args) => {
          calls.push({ name: key, args, fill: state.fillStyle, stroke: state.strokeStyle,
            font: state.font, alpha: state.globalAlpha, direction: state.direction });
          if (key === 'save') stack.push({ ...state });
          if (key === 'restore') { for (const key of Object.keys(state)) delete state[key]; Object.assign(state, stack.pop()); }
        };
      },
    });
    const canvas = { style: {}, ...(browser ? { ownerDocument: document } : {}),
      getContext: () => ctx, setAttribute() {}, addEventListener() {} };
    const scroll = { clientWidth: 600, scrollLeft: 0, scrollTop: 0, closest: () => null, addEventListener() {} };
    const timeline = new scope.TimelineView(canvas, scroll, () => {}, null, null, {
      sourceReview, getTrackClips: (project, slot) => project.manual.source_tracks[slot] || [],
    });
    const view = { timeline, canvas, scroll, ctx, calls };
    views.push(view);
    timeline.project = {
      id: 'theme-fixture', sources: { A: { duration: 12, has_audio: true }, B: { duration: 12, has_audio: false } },
      settings: { fps: 30 }, assets: {},
      manual: { sequence: { duration: 12 }, source_tracks: {
        A: [{ start: 0, end: 5, source_start: 0 }, { start: 6, end: 12, source_start: 6 }],
        B: [{ start: 0, end: 12, source_start: 0 }],
      } },
      draft: { keep_ranges: [{ start: 0, end: 5 }, { start: 6, end: 12 }],
        cuts: [{ start: 5, end: 6 }], camera_plan: [{ start: 0, end: 5, camera: 'A' }, { start: 6, end: 12, camera: 'pip' }] },
      pre_analysis: { audio: { A: { waveform: [{ start: 0, end: 1, rms_dbfs: -20, peak_dbfs: -5 }] } } },
    };
    timeline.mediaLayout = () => ({ height: 300, rows: [], caption: null });
    timeline.syncTrackHeaders = () => false;
    return view;
  }
  function changeTheme(theme) {
    root.dataset.theme = theme;
    observers.forEach(observer => observer.callback([{ type: 'attributes', attributeName: 'data-theme', target: root }]));
  }
  function flush() { const pending = [...frames.values()]; frames.clear(); pending.forEach(callback => callback(0)); }
  return { create, root, observers, frames, flush, changeTheme, resolveFonts, rejectFonts, styleReads: () => styleReads };
}

const palette = {
  dark: { '--timeline-bg': '#191b1f', '--timeline-ruler': '#24272c', '--timeline-text': '#c6c9cf',
    '--timeline-grid': '#3e434c', '--timeline-selected': '#efb28d', '--timeline-clip': '#365564',
    '--timeline-clip-b': '#5e4e77', '--timeline-label': '#f1f3f6', '--timeline-wave': '#aac8c3' },
  light: { '--timeline-bg': '#b5b9bf', '--timeline-ruler': '#c9cdd2', '--timeline-text': '#333c48',
    '--timeline-grid': '#979faa', '--timeline-selected': '#82462a', '--timeline-clip': '#577486',
    '--timeline-clip-b': '#77648e', '--timeline-label': '#ffffff', '--timeline-wave': '#2e5252' },
};

test('standalone timeline keeps deterministic colors without DOM appearance APIs', () => {
  const h = fixture({ browser: false }), { timeline, ctx } = h.create();
  assert.doesNotThrow(() => timeline.draw());
  assert.equal(timeline.color('bg', '#10181e'), '#10181e');
  assert.equal(timeline.themeObserver, undefined);
  assert.equal(ctx.strokeStyle, '#1bd9ce');
  assert.equal(h.frames.size, 0);
  assert.equal(timeline.font(10), '10px ' + font);
  assert.equal(timeline.font(9, 700), '700 9px ' + font);
});

test('canvas custom colors resolve once per invalidation and reject non-color tokens', () => {
  const h = fixture({ palette: { dark: { '--timeline-bg': '  #191b1f  ', '--timeline-ruler': 'linear-gradient(red, blue)',
    '--timeline-grid': 'var(--missing)' } } });
  const { timeline } = h.create();
  for (let i = 0; i < 100; i++) assert.equal(timeline.color('bg', '#000'), '#191b1f');
  assert.equal(timeline.color('ruler', '#151e25'), '#151e25');
  assert.equal(timeline.color('grid', '#454545'), '#454545');
  assert.equal(h.styleReads(), 1, 'no computed-style lookup per clip or unchanged paint');
  h.changeTheme('light');
  assert.equal(timeline.color('bg', '#10181e'), '#10181e', 'missing token cannot retain the previous theme');
  assert.equal(h.styleReads(), 2);
});

test('data-theme changes repaint both timelines once, including RAF id zero', () => {
  const h = fixture({ palette }), editor = h.create(), source = h.create(true);
  editor.timeline.draw(); source.timeline.draw();
  assert.equal(h.observers.length, 2);
  for (const observer of h.observers) {
    assert.equal(observer.target, h.root);
    assert.deepEqual(plain(observer.options), { attributes: true, attributeFilter: ['data-theme'] });
  }
  h.changeTheme('light'); h.changeTheme('light');
  assert.equal(h.frames.size, 2, 'one pending frame per instance, not per mutation');
  h.flush();
  assert.equal(h.frames.size, 0, 'no perpetual animation loop');
  assert.equal(h.styleReads(), 4, 'each canvas resolves once before and once after the change');
  for (const { timeline, ctx, calls } of [editor, source]) {
    assert.equal(timeline.color('bg', ''), '#b5b9bf');
    assert.equal(ctx.strokeStyle, '#82462a');
    assert.ok(calls.some(call => call.name === 'fillRect' && call.fill === '#b5b9bf'));
  }
});

test('font readiness redraws both paused canvases and shares an already pending frame', async () => {
  const h = fixture({ palette }), a = h.create(), b = h.create(true);
  a.timeline.draw(); b.timeline.draw();
  a.timeline.scheduleDraw();
  h.resolveFonts(); await Promise.resolve();
  assert.equal(h.frames.size, 2);
  h.flush();
  assert.equal(h.frames.size, 0);
  assert.equal(h.styleReads(), 4);
});

test('font readiness failure is contained and does not schedule work', async () => {
  const h = fixture({ palette }); h.create();
  h.rejectFonts(new Error('synthetic font failure')); await Promise.resolve();
  assert.equal(h.frames.size, 0);
});

test('theme repaints preserve media sampling, alpha, geometry and project data', () => {
  const h = fixture({ palette }), { timeline, calls } = h.create();
  timeline.images = [{ width: 160, height: 90, name: 'original-frame' }];
  timeline.selection = { start: 1, end: 3 };
  timeline.hoverTime = 2; timeline.playhead = 1.5;
  timeline.snapGuide = { time: 3, label: 'Clip edge' };
  const saved = JSON.stringify(timeline.project);
  timeline.draw();
  const dark = calls.splice(0);
  h.changeTheme('light'); h.flush();
  const light = calls.splice(0);
  const geometry = rows => plain(rows.map(({ name, args, alpha, direction }) => ({ name, args, alpha, direction })));
  assert.deepEqual(geometry(light), geometry(dark));
  const images = light.filter(call => call.name === 'drawImage');
  assert.ok(images.length > 0);
  assert.ok(images.every(call => call.alpha === .85));
  assert.equal(JSON.stringify(timeline.project), saved);
  assert.equal(h.frames.size, 0);
});

test('caption direction, edited/hidden semantics and proportional font metrics survive theming', () => {
  const h = fixture({ palette }), { timeline, ctx, calls } = h.create();
  const items = [{ id: 'he', start: 0, end: 3, text: 'שלום עולם', direction: 'rtl', corrected: true },
    { id: 'hidden', start: 4, end: 7, text: 'Hidden original', hidden: true }];
  timeline.captionItems = () => items;
  timeline.captionPlacement = values => values.map(item => ({ item, row: 0 }));
  timeline.captionSelection = 'he';
  timeline.drawCaptionItems(ctx, 60, 600, { top: 220, height: 28 }, 0, 600);
  assert.ok(calls.some(call => call.name === 'fillText' && call.direction === 'rtl' && call.args[0].includes('שלום')));
  assert.ok(calls.some(call => call.name === 'setLineDash' && JSON.stringify(call.args[0]) === '[4,3]'));
  assert.ok(calls.filter(call => call.name === 'fillText').every(call => call.font === '11px ' + font));
  assert.deepEqual(items.map(item => item.text), ['שלום עולם', 'Hidden original']);
});

test('every explicit canvas font uses the proportional theme font helper', () => {
  assert.doesNotMatch(source, /ui-monospace|SFMono-Regular|Consolas|Liberation Mono/);
  assert.doesNotMatch(source, /ctx\.font\s*=\s*["']/);
  assert.equal((source.match(/ctx\.font\s*=\s*this\.font\(/g) || []).length, 16);
});


test('prototype-only timeline initializes its palette lazily without the constructor', () => {
  for (const browser of [false, true]) {
    const h = fixture({ browser, palette }), base = h.create();
    const timeline = Object.create(Object.getPrototypeOf(base.timeline));
    assert.equal(timeline.themeColors, undefined);
    // The workflow fixture supplies only its rendering fields, not constructor state.
    Object.assign(timeline, {
      canvas: base.canvas, context: base.ctx, scroll: base.scroll, project: base.timeline.project,
      zoom: 1, images: [], playhead: 0, selection: null, hoverTime: null,
      getTrackClips: base.timeline.getTrackClips, mediaLayout: base.timeline.mediaLayout,
      syncTrackHeaders: base.timeline.syncTrackHeaders,
    });
    assert.doesNotThrow(() => timeline.draw());
    assert.equal(timeline.color('bg', '#10181e'), browser ? '#191b1f' : '#10181e');
    timeline.draw();
    assert.equal(h.styleReads(), browser ? 1 : 0, 'lazy initialization still caches resolved styles');
  }
});
