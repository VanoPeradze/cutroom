const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/timeline.js'), 'utf8').replace(/^export /gm, '');
const plain = value => JSON.parse(JSON.stringify(value));

function fixture(kind = 'video', enabled = false) {
  const calls = [], stack = [], state = { globalAlpha: 1, dash: [] }, actions = [], captures = new Set();
  const ctx = new Proxy(state, { get(target, name) {
    if (name in target) return target[name];
    if (name === 'measureText') return text => ({ width: String(text).length * 6 });
    if (name === 'createLinearGradient') return () => ({ addColorStop() {} });
    return (...args) => {
      calls.push({ name, args: plain(args), alpha: state.globalAlpha, fill: state.fillStyle, dash: [...state.dash] });
      if (name === 'save') stack.push({ ...state, dash: [...state.dash] });
      if (name === 'restore') { for (const key of Object.keys(state)) delete state[key]; Object.assign(state, stack.pop()); }
      if (name === 'setLineDash') state.dash = [...args[0]];
    };
  } });
  const canvas = { style: {}, attrs: {}, id: 'timelineCanvas', getContext: () => ctx,
    setAttribute(key, value) { this.attrs[key] = value; }, addEventListener() {}, focus() {},
    getBoundingClientRect: () => ({ left: 10, top: 20, width: 600 }),
    setPointerCapture(id) { captures.add(id); }, hasPointerCapture: id => captures.has(id), releasePointerCapture(id) { captures.delete(id); } };
  const scroll = { clientWidth: 600, clientHeight: 300, scrollLeft: 0, scrollTop: 0,
    closest: selector => selector === '.studio-timeline-dock' ? {} : null, addEventListener() {} };
  const scope = vm.createContext({ window: { devicePixelRatio: 1 }, ResizeObserver: class { observe() {} }, requestAnimationFrame: () => 1, cancelAnimationFrame() {} });
  vm.runInContext(source + '\nglobalThis.api={TimelineView,timelineIndexEntries,createTimelineNavigation,sequenceGaps,timelineRangeDeleteImpact};', scope);
  const isText = ['title', 'caption'].includes(kind), clip = { id: isText ? 'text_test' : 'media_test', start: 2, end: 6, enabled,
    ...(isText ? { kind, text: 'Synthetic layer' } : { asset_id: 'asset', source_start: 1, video_source_start: 1, speed: 1, role: 'music', muted: false, audio_enabled: true }) };
  const project = { id: 'disabled-fixture', settings: { fps: 30 }, sources: { A: { duration: 12 } },
    draft: { keep_ranges: [{ start: 0, end: 12 }] }, assets: { asset: { kind, name: 'Synthetic media', status: 'ready', duration: 20,
      thumbnail_url: 'synthetic-thumb', waveform: kind === 'audio' ? [.1, .8, .4] : [] } },
    manual: { sequence: { duration: 12 }, source_tracks: { A: [{ id: 'a1', start: 0, end: 2 }, { id: 'a2', start: 6, end: 12 }], B: [] },
      media_clips: isText ? [] : [clip], text_clips: isText ? [clip] : [] } };
  const getTracks = (p, slot) => p.manual.source_tracks[slot] || [];
  const timeline = new scope.api.TimelineView(canvas, scroll, time => timeline.playhead = time, null,
    () => { throw Error('No source edit expected'); }, { getTrackClips: getTracks });
  timeline.project = project; timeline.mediaImages = new Map([['synthetic-thumb', { width: 60, height: 38 }]]);
  timeline.onMediaAction = (action, payload) => { actions.push({ action, ...plain(payload) }); return Promise.resolve(project); };
  const point = (time, edge) => ({ button: 0, pointerId: 1, clientX: 10 + time * timeline.geometry().px,
    clientY: 20 + timeline.mediaRows()[0].top + (edge || 20), preventDefault() {}, stopPropagation() {} });
  return { timeline, project, clip, canvas, scroll, ctx, calls, actions, api: scope.api, getTracks, point };
}

for (const kind of ['video', 'image', 'audio', 'title', 'caption']) test(`disabled ${kind} stays painted, labeled and hit-testable`, () => {
  const h = fixture(kind), before = JSON.stringify(h.project), row = h.timeline.mediaRows()[0];
  h.timeline.drawMedia(h.ctx, h.timeline.geometry().px, 600);
  assert.equal(row.clips[0].id, h.clip.id);
  assert.ok(h.calls.some(call => call.name === 'fillText' && call.args[0].startsWith('Disabled · ')));
  assert.ok(h.calls.some(call => call.name === 'strokeRect' && call.dash.join(',') === '4,3'));
  assert.equal(h.timeline.mediaAtEvent(h.point(4)).clip.id, h.clip.id);
  assert.equal(h.timeline.mediaAtEvent(h.point(2.01)).clip.id, h.clip.id);
  assert.equal(JSON.stringify(h.project), before, 'drawing cannot change saved content');
  if (kind !== 'audio' && !['title', 'caption'].includes(kind)) assert.ok(h.calls.some(call => call.name === 'drawImage' && call.alpha === .28));
  if (kind === 'audio') assert.ok(h.calls.some(call => call.name === 'stroke' && call.alpha === .35));
  assert.equal(h.ctx.globalAlpha, 1); assert.deepEqual(h.ctx.dash, []);
});

test('selected disabled layer retains strong solid edges and handles; later enabled draws inherit no faded state', () => {
  const h = fixture(); h.timeline.mediaSelection = h.clip.id;
  h.timeline.drawMedia(h.ctx, 50, 600);
  assert.ok(h.calls.some(call => call.name === 'strokeRect' && call.dash.length === 0));
  assert.ok(h.calls.some(call => call.name === 'fillRect' && call.args[2] === 3 && call.alpha === 1));
  h.clip.enabled = true; h.calls.length = 0; h.timeline.drawMedia(h.ctx, 50, 600);
  assert.ok(!h.calls.some(call => call.name === 'fillText' && call.args[0].startsWith('Disabled')));
  assert.ok(h.calls.some(call => call.name === 'drawImage' && call.alpha === .7));
  assert.equal(h.ctx.globalAlpha, 1);
});

test('only explicit false is disabled; legacy absence remains enabled and sound mute is distinct', () => {
  for (const value of [undefined, true, null, 0]) {
    const h = fixture(); h.clip.enabled = value; h.clip.muted = true; h.clip.audio_enabled = false;
    const item = h.api.timelineIndexEntries(h.project, h.getTracks).find(row => row.id === h.clip.id);
    assert.equal(item.enabled, true);
    h.timeline.drawMedia(h.ctx, 50, 600);
    assert.ok(!h.calls.some(call => call.name === 'fillText' && call.args[0].startsWith('Disabled')));
  }
});

test('disabled geometry, snap boundaries, range impact and gap protection are retained exactly', () => {
  const h = fixture(), beforeRows = plain(h.timeline.mediaRows());
  assert.ok(h.timeline.snapPoints().some(row => row.time === 2));
  assert.ok(h.timeline.snapPoints().some(row => row.time === 6));
  assert.deepEqual(plain(h.api.sequenceGaps(h.project, h.getTracks)), []);
  const impact = h.api.timelineRangeDeleteImpact(h.project, { start: 3, end: 4 }, 'edit', h.getTracks);
  assert.equal(impact.media.split, 1);
  h.clip.enabled = true;
  const afterRows = plain(h.timeline.mediaRows()); delete beforeRows[0].clips[0].enabled; delete afterRows[0].clips[0].enabled;
  assert.deepEqual(afterRows, beforeRows);
});

for (const kind of ['video', 'title']) test(`disabled ${kind} can still use guarded native body Move without enabling`, async () => {
  const h = fixture(kind), before = JSON.stringify(h.project);
  h.timeline.mediaMovePreview = (id, start) => ({ issue: '', patch: start === h.clip.start ? {} : { start, end: start + 4 } });
  h.timeline.snapping = false;
  h.timeline.pointerDown(h.point(4)); h.timeline.pointerUp(h.point(5)); await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(h.actions, [{ action: 'media_move', clip_id: h.clip.id, start: 3 }]);
  assert.equal(JSON.stringify(h.project), before);
});

test('disabled hover explains output state without blocking Move, Trim, Blade or Slip', () => {
  const h = fixture(); h.timeline.mediaMovePreview = () => ({ issue: '', patch: {} });
  h.timeline.updatePointerCursor(h.point(4), 4); assert.match(h.canvas.title, /Disabled in preview and export.*Move/); assert.equal(h.canvas.style.cursor, 'grab');
  h.timeline.mediaTrimPreview = () => ({ issue: '', patch: {} });
  h.timeline.updatePointerCursor(h.point(2.01), 2.01); assert.match(h.canvas.title, /Disabled.*trim/);
  h.timeline.mediaSplitIssue = () => ''; h.timeline.setTool('blade'); h.timeline.updatePointerCursor(h.point(4), 4); assert.match(h.canvas.title, /Disabled.*Split/);
  h.timeline.mediaSlipPreview = () => ({ issue: '', patch: {} }); h.timeline.setTool('slip'); h.timeline.updatePointerCursor(h.point(4), 4); assert.match(h.canvas.title, /Disabled.*Slip/);
  h.clip.enabled = true; h.timeline.updatePointerCursor(h.point(4), 4); assert.doesNotMatch(h.canvas.title, /Disabled/);
});

function indexDOM(h) {
  const nodes = [], doc = { activeElement: null };
  class Node {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.events = {}; this.value = ''; this.disabled = false; this.open = false; nodes.push(this); }
    append(...children) { for (const child of children) { child.parent = this; this.children.push(child); if (this.tag === 'select' && this.children.length === 1) this.value = child.value; } }
    insertBefore(node) { this.append(node); }
    replaceChildren(...children) { this.children = []; this.append(...children); }
    setAttribute(key, value) { this.attrs[key] = value; }
    getAttribute(key) { return this.attrs[key]; }
    removeAttribute(key) { delete this.attrs[key]; }
    addEventListener(key, fn) { this.events[key] = fn; }
    fire(key, event = {}) { this.events[key]?.(event); }
    focus() { doc.activeElement = this; }
    setCustomValidity() {}
    showModal() { this.open = true; }
    close() { this.open = false; this.fire('close'); }
    closest() { return this.tag === 'button' && this.dataset.indexKey ? this : this.parent?.closest(); }
  }
  doc.createElement = tag => new Node(tag); doc.body = new Node('body'); const dock = new Node('div');
  h.canvas.ownerDocument = doc; h.scroll.closest = selector => selector === '.studio-timeline-dock' ? dock : null;
  const nav = h.api.createTimelineNavigation(h.timeline), byId = id => nodes.find(node => node.id === id);
  byId('timelineIndexButton').fire('click');
  const list = nodes.find(node => node.className === 'timeline-index-list');
  return { nav, nodes, byId, list, items: () => list.children.map(row => row.children[0]) };
}

test('disabled Index entries remain actionable, explicit and searchable, then select their real inspector', () => {
  const h = fixture('title'), ui = indexDOM(h); let selected;
  h.timeline.onMediaSelect = id => selected = id;
  let item = ui.items().find(node => node.dataset.indexKey === `media::${h.clip.id}`);
  assert.equal(item.disabled, false); assert.equal(item.dataset.layerEnabled, 'false');
  assert.match(item.getAttribute('aria-label'), /disabled/); assert.match(item.title, /Disabled in preview and export/);
  assert.equal(item.children[1].textContent, 'Title (disabled)');
  ui.byId('timelineIndexSearch').value = 'disabled'; ui.byId('timelineIndexSearch').fire('input');
  assert.equal(ui.items().length, 1); item = ui.items()[0];
  ui.list.fire('click', { target: item });
  assert.equal(selected, h.clip.id); assert.equal(h.timeline.mediaSelection, h.clip.id); assert.equal(ui.nav.dialog.open, false);
  assert.equal(h.clip.enabled, false);
});

test('actual navigation busy state remains distinct from occurrence enablement and refresh removes stale labels', () => {
  const h = fixture(), ui = indexDOM(h);
  h.timeline.editPending = true; ui.nav.refresh();
  assert.ok(ui.items().every(item => item.disabled));
  h.timeline.editPending = false; h.clip.enabled = true; ui.nav.refresh();
  const item = ui.items().find(node => node.dataset.indexKey === `media::${h.clip.id}`);
  assert.equal(item.disabled, false); assert.equal(item.dataset.layerEnabled, 'true'); assert.doesNotMatch(item.getAttribute('aria-label'), /disabled/);
  assert.equal(ui.items().find(node => node.dataset.indexKey.startsWith('source:')).dataset.layerEnabled, undefined);
});

test('enabled controls use scoped readable styling without visually disabling the entire inspector or Index item', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /#studioInspector \.layer-enabled-control\s*\{[^}]*display:flex/);
  assert.match(css, /\.layer-enabled-control input\[type=checkbox\][^{]*\{[^}]*width:15px/);
  assert.match(css, /\.timeline-index-item\[data-layer-enabled="false"\] \.timeline-index-track/);
  assert.doesNotMatch(css, /\.timeline-index-item\[data-layer-enabled="false"\]\s*\{[^}]*(pointer-events:none|opacity:)/);
});


test('Index opened during busy loading recovers in place without replacing rows, filters, focus or scroll', () => {
  const h = fixture(); h.timeline.editPending = true;
  const ui = indexDOM(h), item = ui.items().find(row => row.dataset.indexKey === `media::${h.clip.id}`);
  assert.equal(item.disabled, true);
  ui.byId('timelineIndexSearch').value = 'disabled'; ui.byId('timelineIndexSearch').fire('input');
  const filtered = ui.items()[0]; ui.list.scrollTop = 123; filtered.focus();
  h.timeline.editPending = false; ui.nav.sync();
  assert.equal(ui.items()[0], filtered, 'readiness does not replace the focused DOM node');
  assert.equal(filtered.disabled, false); assert.equal(ui.list.scrollTop, 123);
  assert.equal(ui.byId('timelineIndexSearch').value, 'disabled');
  assert.equal(h.canvas.ownerDocument.activeElement, filtered);
  assert.equal(ui.nodes.find(node => node.className === 'timeline-index-status').textContent, '1 of 3 items');
  h.timeline.editPending = true; ui.nav.sync(); assert.equal(filtered.disabled, true);
  h.timeline.editPending = false; ui.nav.sync(); assert.equal(filtered.disabled, false);
  assert.equal(filtered.dataset.layerEnabled, 'false', 'clip remains off, not inaccessible');
});
