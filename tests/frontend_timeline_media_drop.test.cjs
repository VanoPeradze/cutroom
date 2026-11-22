const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const timelineSource = fs.readFileSync(path.join(__dirname, '../web/timeline.js'), 'utf8').replace(/^export /gm, '');
const source = fs.readFileSync(path.join(__dirname, '../web/timeline-media-drop.js'), 'utf8').replace(/^import .*\n/gm, '').replace(/^export /gm, '');
const scope = vm.createContext({});
vm.runInContext(timelineSource + '\n' + source + '\nglobalThis.api={libraryDragIdentity,libraryDropPlacement,readLibraryDrag,initTimelineMediaDrop,LIBRARY_DRAG_TYPE,TimelineView};', scope);
const { libraryDragIdentity: identity, libraryDropPlacement: plan, readLibraryDrag: read, initTimelineMediaDrop: init, LIBRARY_DRAG_TYPE: MIME, TimelineView } = scope.api;
const plain = value => JSON.parse(JSON.stringify(value));
function project() {
  return { id: 'project-test', revision: 4, draft: {}, settings: { fps: 30 }, manual: { sequence: { duration: 10 }, media_clips: [] },
    assets: { video: { id: 'video', name: 'Clip.mp4', kind: 'video', status: 'ready', duration: 4, width: 1920, height: 1080, has_audio: true, url: '/local/video' },
      audio: { id: 'audio', name: 'Tone.wav', kind: 'audio', status: 'ready', duration: 2 },
      image: { id: 'image', name: 'Image.png', kind: 'image', status: 'ready' }, failed: { id: 'failed', kind: 'video', status: 'failed', duration: 4 } } };
}
class Node {
  constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.attrs = new Map(); this.classes = new Set(); this.children = []; this.events = new Map(); this.dataset = {}; this.hidden = false;
    this.classList = { add: name => this.classes.add(name), remove: name => this.classes.delete(name), contains: name => this.classes.has(name), toggle: (name, yes) => yes ? this.classes.add(name) : this.classes.delete(name) }; }
  set className(value) { this.classes = new Set(value.split(' ')); }
  set draggable(value) { this.setAttribute('draggable', String(value)); } get draggable() { return this.getAttribute('draggable') === 'true'; }
  set title(value) { this.setAttribute('title', value); } get title() { return this.getAttribute('title') || ''; }
  setAttribute(key, value) { this.attrs.set(key, String(value)); } getAttribute(key) { return this.attrs.get(key) ?? null; } removeAttribute(key) { this.attrs.delete(key); }
  append(...children) { children.forEach(node => { node.parent = this; this.children.push(node); }); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(node => node !== this); this.parent = null; }
  descendants() { return this.children.flatMap(node => [node, ...node.descendants()]); }
  contains(node) { return this === node || this.descendants().includes(node); }
  matches(selector) { if (selector === '[data-source-drag]') return Object.hasOwn(this.dataset,'sourceDrag'); return selector.startsWith('.') ? this.classes.has(selector.slice(1)) : selector === 'button[data-asset]' ? this.tagName === 'BUTTON' && Boolean(this.dataset.asset) : selector.toUpperCase() === this.tagName; }
  closest(selector) { return selector.split(',').some(item => this.matches(item)) ? this : this.parent?.closest(selector) || null; }
  querySelector(selector) { return this.descendants().find(node => node.matches(selector)) || null; }
  querySelectorAll(selector) { return this.descendants().filter(node => node.matches(selector)); }
  addEventListener(type, handler) { this.events.set(type, [...(this.events.get(type) || []), handler]); }
  removeEventListener(type, handler) { this.events.set(type, (this.events.get(type) || []).filter(item => item !== handler)); }
  async emit(type, event = {}) { for (const handler of this.events.get(type) || []) await handler(event); }
}
function harness({ place, canPlace, insertionIssue, placementPreview, sourceSelection } = {}) {
  const doc = new Node('document'), library = new Node(), dock = new Node(), scroll = new Node(), canvas = new Node('canvas');
  library.className = 'media-library'; dock.className = 'studio-timeline-dock'; dock.append(scroll); scroll.append(canvas); doc.append(library, dock);
  const cards = {};
  for (const id of ['video', 'audio', 'image', 'failed']) {
    const card = new Node(), label = new Node('span'), button = new Node('button'); card.className = 'media-asset'; button.dataset.asset = id; card.append(label, button); library.append(card); cards[id] = { card, label, button };
  }
  cards.video.card.title = 'Original title';
  const timers = new Map(), observers = [];
  doc.createElement = tag => new Node(tag);
  doc.defaultView = { setTimeout(fn) { const id = timers.size + 1; timers.set(id, fn); return id; }, clearTimeout(id) { timers.delete(id); },
    MutationObserver: class { constructor(fn) { this.fn = fn; observers.push(this); } observe() {} disconnect() { this.disconnected = true; } } };
  canvas.ownerDocument = doc;
  const calls = [], selected = [], timeline = { canvas, scroll, project: project(), editPending: false, cutAnchor: 2, draws: 0,
    canNavigate() { return !this.busy && !this.editPending; }, timeFromEvent: event => event.time,
    splitTime: time => Math.round(time * 30) / 30, snappedTime(time, event) { return this.snapping && !event.altKey ? this.snapTarget : time; },
    color: (_, fallback) => fallback, scheduleDraw() { this.draws++; }, cancelPendingCut() { this.cutAnchor = null; }, onToolStateChange() {},
    selectIndexEntry(key) { selected.push(key); return true; } };
  const placeFn = place || (async (assetId, time, options) => {
    calls.push({ assetId, time, options: plain(options) });
    const result = structuredClone(timeline.project); result.revision++; result.manual.media_clips.push({ id: 'media-new', asset_id: assetId, start: time, end: options.sourceEnd === undefined ? time + 2 : options.append || options.insert ? time + options.sourceEnd-options.sourceStart : Math.min(timeline.project.manual.sequence.duration,time + options.sourceEnd-options.sourceStart), ...(options.sourceStart === undefined ? {} : {source_start:options.sourceStart,speed:1}), ...(options.trackId ? { track_id: options.trackId } : {}) }); timeline.project = result; return result;
  });
  const controller = init(timeline, { document: doc, place: placeFn, canPlace, insertionIssue, placementPreview, sourceSelection, sourceRoot: () => dock });
  const data = new Map(), transfer = { clearData: () => data.clear(), setData: (type, value) => data.set(type, value), getData: type => data.get(type) || '' };
  const event = (target, time = 2, options = {}) => ({ target, time, dataTransfer: transfer, prevented: false, preventDefault() { this.prevented = true; }, stopPropagation() {}, ...options });
  const start = async (id = 'video') => { const e = event(cards[id].label); await doc.emit('dragstart', e); return e; };
  const feedback = () => dock.querySelector('.timeline-drop-feedback');
  return { doc, library, dock, scroll, canvas, cards, timeline, controller, calls, selected, transfer, event, start, feedback, observers, timers };
}

test('drop preview uses existing bounded overlay/add and full-video append semantics without mutation', () => {
  const p = project(), before = JSON.stringify(p);
  assert.deepEqual(plain(plan(p, 'video', 8)), { assetId: 'video', kind: 'video', append: false, start: 8, end: 10, label: 'Overlay video' });
  assert.deepEqual(plain(plan(p, 'video', 10.8)), { assetId: 'video', kind: 'video', append: true, start: 10, end: 14, label: 'Append video' });
  assert.equal(plan(p, 'video', 9.95).append, true, 'a sub-0.08s video sliver is explicitly previewed as append instead');
  assert.equal(plan(p, 'audio', 9.92).end, 10); assert.match(plan(p, 'audio', 9.95).error, /inside the edit/);
  assert.equal(plan(p, 'image', 1).end, 6); assert.match(plan(p, 'image', 10).error, /inside the edit/);
  assert.equal(JSON.stringify(p), before);
});
test('placement rejects incomplete drafts, unknown/unready assets and invalid positions', () => {
  const p = project();
  for (const id of ['missing', 'failed']) assert.ok(plan(p, id, 1).error);
  for (const time of [NaN, Infinity, -1, '2']) assert.ok(plan(p, 'video', time).error);
  p.assets.video.duration = .01; assert.ok(plan(p, 'video', 1).error);
  p.draft = null; assert.ok(plan(p, 'image', 1).error);
  p.draft = {}; p.manual.sequence.duration = 0; assert.ok(plan(p, 'image', 0).error);
});
test('drag payload requires an existing in-memory origin and exact project/asset match', () => {
  const origin = { project_id: 'project-test', asset_id: 'video' }, raw = JSON.stringify({ version: 1, ...origin });
  assert.deepEqual(plain(read(raw, origin)), { version: 1, ...origin });
  for (const value of ['{}', '{invalid', 'x'.repeat(1025), JSON.stringify({ version: 1, project_id: 'other', asset_id: 'video' })]) assert.equal(read(value, origin), null);
  assert.equal(read(raw, null), null); assert.equal(identity(project(), 'failed'), null);
});
test('only real ready imported asset cards become draggable and setup is idempotent', () => {
  const h = harness(); assert.equal(h.cards.video.card.draggable, true); assert.equal(h.cards.failed.card.draggable, false);
  assert.equal(h.library.children.length, 4); assert.equal(h.cards.video.button.dataset.asset, 'video');
  assert.equal(init(h.timeline, { document: h.doc, place() {} }), h.controller);
  assert.equal(h.dock.querySelectorAll('.timeline-drop-feedback').length, 1); assert.deepEqual(h.calls, []);
});
test('drag hover previews a frame-aligned copy and does not edit, seek or clear a pending cut', async () => {
  const h = harness(), before = JSON.stringify(h.timeline.project); await h.start();
  assert.equal(h.transfer.effectAllowed, 'copy'); assert.equal(h.timeline.libraryDragActive, true);
  const over = h.event(h.canvas, 2.015); await h.scroll.emit('dragover', over);
  assert.equal(over.prevented, true); assert.equal(h.transfer.dropEffect, 'copy'); assert.match(h.feedback().textContent, /Overlay video at 00:00:02:00/);
  assert.deepEqual(h.calls, []); assert.equal(h.timeline.cutAnchor, 2); assert.equal(JSON.stringify(h.timeline.project), before);
  const draws = [], ctx = new Proxy({}, { get: (_, key) => (...args) => draws.push([key, ...args]), set: () => true }); h.controller.draw(ctx, 10, 110, 200);
  assert.ok(draws.some(row => row[0] === 'fillRect' && row[1] === 20));
});
test('drop uses the existing edit callback exactly once and reveals the new occurrence', async () => {
  const h = harness(); await h.start(); await h.scroll.emit('drop', h.event(h.canvas, 2.015));
  assert.deepEqual(h.calls, [{ assetId: 'video', time: 2, options: { append: false } }]);
  assert.deepEqual(h.selected, ['media::media-new']); assert.equal(h.timeline.editPending, false); assert.equal(h.timeline.libraryDragActive, false); assert.equal(h.timeline.cutAnchor, null);
  assert.match(h.feedback().textContent, /Undo is available/); await h.doc.emit('dragend'); assert.match(h.feedback().textContent, /Undo is available/, 'native dragend must not erase a result');
});
test('tail video drop appends, while audio tail drop is explicitly rejected with no edit', async () => {
  const h = harness(); await h.start(); await h.scroll.emit('drop', h.event(h.canvas, 10.5)); assert.equal(h.calls[0].time, 10); assert.equal(h.calls[0].options.append, true);
  const audio = harness(); await audio.start('audio'); await audio.scroll.emit('drop', audio.event(audio.canvas, 10.5));
  assert.deepEqual(audio.calls, []); assert.match(audio.feedback().textContent, /inside the edit/); await audio.doc.emit('dragend'); assert.equal(audio.feedback().hidden, false);
});
test('snapping and Alt bypass use the real timeline snapping policy', async () => {
  const h = harness(); h.timeline.snapping = true; h.timeline.snapTarget = 3; await h.start(); await h.scroll.emit('drop', h.event(h.canvas, 2.95)); assert.equal(h.calls[0].time, 3);
  const bypass = harness(); bypass.timeline.snapping = true; bypass.timeline.snapTarget = 3; await bypass.start(); await bypass.scroll.emit('drop', bypass.event(bypass.canvas, 2.8, { altKey: true })); assert.equal(bypass.calls[0].time, 2.8);
});
test('leaving and cancelling a drag creates no edit and restores normal playback following', async () => {
  const h = harness(); await h.start(); await h.scroll.emit('dragover', h.event(h.canvas)); await h.scroll.emit('dragleave', h.event(h.canvas, 2, { relatedTarget: h.doc }));
  assert.equal(h.feedback().hidden, true); assert.equal(h.timeline.libraryDragActive, true, 'leaving allows re-entry');
  await h.doc.emit('keydown', { key: 'Escape' }); assert.equal(h.timeline.libraryDragActive, false); assert.deepEqual(h.calls, []);
  const fake = { project: project(), playhead: 0, scroll: { scrollLeft: 100, clientWidth: 100 }, geometry: () => ({ px: 10 }), libraryDragActive: true };
  TimelineView.prototype.followPlayhead.call(fake); assert.equal(fake.scroll.scrollLeft, 100); fake.libraryDragActive = false; TimelineView.prototype.followPlayhead.call(fake); assert.equal(fake.scroll.scrollLeft, 0);
});
test('project revision and asset identity changes invalidate a drag rather than placing stale media', async () => {
  for (const change of [p => p.revision++, p => p.id = 'new-project', p => p.assets.video.url = '/replaced']) {
    const h = harness(); await h.start(); change(h.timeline.project); h.controller.refresh();
    assert.equal(h.timeline.libraryDragActive, false); assert.match(h.feedback().textContent, /project or source selection changed/);
    await h.scroll.emit('drop', h.event(h.canvas)); assert.deepEqual(h.calls, []);
  }
});
test('busy/import guards, button drags and external payloads never place or upload anything', async () => {
  const busy = harness({ canPlace: () => false }); assert.equal((await busy.start()).prevented, true);
  const h = harness(), button = h.event(h.cards.video.button); await h.doc.emit('dragstart', button); assert.equal(button.prevented, true);
  h.transfer.setData(MIME, JSON.stringify({ version: 1, project_id: 'project-test', asset_id: 'video' })); await h.scroll.emit('drop', h.event(h.canvas));
  assert.deepEqual(h.calls, []); assert.match(h.feedback().textContent, /Import external files first/);
  await h.start(); h.timeline.busy = true; await h.scroll.emit('drop', h.event(h.canvas)); assert.deepEqual(h.calls, []); assert.match(h.feedback().textContent, /Finish the current edit/);
});
test('duplicate drops are blocked while a placement is pending and failure is never presented as success', async () => {
  let finish, count = 0; const h = harness({ place: () => { count++; return new Promise(resolve => { finish = resolve; }); } });
  await h.start(); const pending = h.scroll.emit('drop', h.event(h.canvas)); assert.equal(h.timeline.editPending, true);
  await h.scroll.emit('drop', h.event(h.canvas)); assert.equal(count, 1); finish(null); await pending;
  assert.equal(h.timeline.editPending, false); assert.match(h.feedback().textContent, /not confirmed/); assert.deepEqual(h.selected, []);
});
test('completing a placement after switching projects cannot select an item in the new project', async () => {
  let finish; const h = harness({ place: () => new Promise(resolve => { finish = resolve; }) }); await h.start(); const pending = h.scroll.emit('drop', h.event(h.canvas));
  const result = project(); result.manual.media_clips = [{ id: 'media-late', asset_id: 'video' }]; h.timeline.project = { ...project(), id: 'different' }; finish(result); await pending;
  assert.deepEqual(h.selected, []); assert.equal(h.feedback().hidden, true); assert.equal(h.timeline.editPending, false);
});
test('a revision retry reveals the final occurrence appended by this placement, not an earlier concurrent one', async () => {
  const h = harness({ place: async assetId => {
    const result = project(); result.manual.media_clips = [{ id: 'media-other-window', asset_id: assetId }, { id: 'media-own-drop', asset_id: assetId }];
    h.timeline.project = result; return result;
  } });
  await h.start(); await h.scroll.emit('drop', h.event(h.canvas)); assert.deepEqual(h.selected, ['media::media-own-drop']);
});
test('destroy restores original card attributes, observers and listeners without changing project data', async () => {
  const h = harness(), before = JSON.stringify(h.timeline.project); await h.start(); h.controller.destroy();
  assert.equal(h.cards.video.card.title, 'Original title'); assert.equal(h.cards.video.card.getAttribute('draggable'), null); assert.equal(h.dock.querySelector('.timeline-drop-feedback'), null);
  assert.equal(h.observers[0].disconnected, true); assert.equal(h.timeline.libraryDrop, null); assert.equal(h.timeline.libraryDragActive, false); assert.equal(JSON.stringify(h.timeline.project), before);
  await h.doc.emit('dragstart', h.event(h.cards.video.label)); assert.deepEqual(h.calls, []);
});

test('Shift Insert uses the full video duration and requires the native readiness guard', () => {
  const p = project(), checks = [], insertionIssue = (asset, time) => { checks.push([asset, time]); return ''; };
  assert.deepEqual(plain(plan(p, 'video', 8.5, { insert: true, insertionIssue })), {
    assetId: 'video', kind: 'video', append: false, insert: true, start: 8.5, end: 12.5, label: 'Insert video',
  });
  assert.deepEqual(checks, [['video', 8.5]]);
  assert.match(plan(p, 'video', 2, { insert: true }).error, /unavailable/);
  for (const result of [false, undefined, null, Promise.resolve('')]) assert.match(plan(p, 'video', 2, { insert: true, insertionIssue: () => result }).error, /could not be confirmed/);
  assert.match(plan(p, 'video', 2, { insert: true, insertionIssue() { throw Error('Unavailable'); } }).error, /could not be confirmed/);
});
test('Shift never silently inserts audio/images or changes explicit tail append behavior', () => {
  const p = project(); let checks = 0; const insertionIssue = () => { checks++; return ''; };
  for (const kind of ['audio', 'image']) assert.match(plan(p, kind, 2, { insert: true, insertionIssue }).error, /Only video can insert time/);
  const tail = plan(p, 'video', 10.5, { insert: true, insertionIssue }); assert.equal(tail.append, true); assert.equal(tail.insert, undefined);
  assert.equal(checks, 0, 'tail is honestly Append and never pretends to shift existing time');
});
test('blocked mixed-layer insert reasons are displayed without calling any edit action', async () => {
  for (const reason of ['A source track is locked.', 'The cut crosses an active fade.', 'Animated visual motion cannot be split safely.', 'Review edited captions before inserting.']) {
    const h = harness({ insertionIssue: () => reason }); await h.start(); await h.scroll.emit('dragover', h.event(h.canvas, 2, { shiftKey: true }));
    assert.equal(h.transfer.dropEffect, 'none'); assert.equal(h.feedback().textContent, reason);
    await h.scroll.emit('drop', h.event(h.canvas, 2, { shiftKey: true })); assert.deepEqual(h.calls, []);
  }
});
test('Insert has a distinct boundary/right-shift preview, not an overlay band; hover and cancel are read-only', async () => {
  const h = harness({ insertionIssue: () => '' }), before = JSON.stringify(h.timeline.project); await h.start();
  await h.scroll.emit('dragover', h.event(h.canvas, 2, { shiftKey: true })); assert.match(h.feedback().textContent, /Insert video at.*\+00:00:04:00; moves later clips across tracks/);
  assert.equal(h.feedback().dataset.operation, 'insert');
  const draws = [], ctx = new Proxy({}, { get: (_, key) => (...args) => draws.push([key, ...args]), set: () => true }); h.controller.draw(ctx, 10, 110, 200);
  assert.ok(draws.some(row => row[0] === 'lineTo' && row[1] === 20 && row[2] === 200)); assert.equal(draws.some(row => row[0] === 'fillRect'), false);
  await h.doc.emit('keydown', { key: 'Escape' }); assert.deepEqual(h.calls, []); assert.equal(JSON.stringify(h.timeline.project), before); assert.equal(h.timeline.cutAnchor, 2);
});
test('Shift drop calls true insert once and reveals its result, while ordinary drag stays Overlay', async () => {
  let checks = 0; const h = harness({ insertionIssue: () => { checks++; return ''; } });
  await h.start(); await h.scroll.emit('drop', h.event(h.canvas, 2, { shiftKey: true }));
  assert.deepEqual(h.calls, [{ assetId: 'video', time: 2, options: { append: false, insert: true } }]); assert.equal(checks, 1);
  assert.match(h.feedback().textContent, /Video inserted; all later clips shifted/); assert.deepEqual(h.selected, ['media::media-new']);
  const ordinary = harness({ insertionIssue: () => { throw Error('Plain Overlay must not query Insert readiness'); } }); await ordinary.start(); await ordinary.scroll.emit('drop', ordinary.event(ordinary.canvas, 2));
  assert.deepEqual(ordinary.calls[0].options, { append: false });
});
test('Shift plus Alt bypasses snapping without changing the insert operation', async () => {
  const checks = [], h = harness({ insertionIssue: (asset, time) => { checks.push([asset, time]); return ''; } });
  h.timeline.snapping = true; h.timeline.snapTarget = 3; await h.start(); await h.scroll.emit('drop', h.event(h.canvas, 2.8, { shiftKey: true, altKey: true }));
  assert.deepEqual(checks, [['video', 2.8]]); assert.equal(h.calls[0].time, 2.8); assert.equal(h.calls[0].options.insert, true);
});
test('a backend-declined insert is never announced as inserted', async () => {
  const h = harness({ insertionIssue: () => '', place: async () => null }); await h.start(); await h.scroll.emit('drop', h.event(h.canvas, 2, { shiftKey: true }));
  assert.equal(h.timeline.editPending, false); assert.match(h.feedback().textContent, /not confirmed/); assert.deepEqual(h.selected, []);
});
test('Undo or another project revision clears an obsolete placement-success message', async () => {
  const h = harness({ insertionIssue: () => '' }); await h.start(); await h.scroll.emit('drop', h.event(h.canvas, 2, { shiftKey: true }));
  assert.match(h.feedback().textContent, /Video inserted/); h.timeline.project.revision++; h.controller.refresh(); assert.equal(h.feedback().hidden, true);
});


const trackId = n => 'track_' + String(n).padStart(32, '0');
function tracked(p = project()) {
  p.manual.layer_tracks = { version: 1, tracks: [
    { id: trackId(1), name: 'Cutaways', kind: 'visual' }, { id: trackId(2), name: 'Sound bed', kind: 'audio' },
    { id: trackId(3), name: 'Titles', kind: 'text' }, { id: trackId(4), name: 'Empty picture', kind: 'visual' },
  ] }; return p;
}
function canonical(p, assetId, time, { append, insert, trackId }) {
  const length = arguments[3].sourceEnd !== undefined ? arguments[3].sourceEnd-arguments[3].sourceStart : assetId === 'image' ? 5 : p.assets[assetId].duration;
  return { issue: '', start: time, end: append || insert ? time + length : Math.min(10, time + length), trackId,
    trackName: p.manual.layer_tracks.tracks.find(t => t.id === trackId)?.name };
}
function trackedHarness(options = {}) {
  const checks = [], h = harness({ placementPreview: (...args) => {
    checks.push(plain(args)); return options.plan ? options.plan(...args) : canonical(h.timeline.project, ...args);
  }, ...options });
  h.timeline.project = tracked(); h.timeline.mediaRowAtEvent = event => event.row === null ? null
    : { trackId: event.row || trackId(1), top: event.row === trackId(2) ? 300 : 200, bottom: event.row === trackId(2) ? 356 : 260 };
  h.controller.refresh(); h.checks = checks; return h;
}
test('tracked full video, sound and image require compatible saved destinations and use canonical times', () => {
  const p = tracked(), before = JSON.stringify(p), calls = [];
  for (const [asset, id] of [['video', trackId(1)], ['audio', trackId(2)], ['image', trackId(4)]]) {
    const result = plan(p, asset, 2, { trackId: id, placementPreview: (...args) => { calls.push(args); return canonical(p, ...args); } });
    assert.equal(result.trackId, id); assert.ok(result.label.includes(p.manual.layer_tracks.tracks.find(t => t.id === id).name));
    assert.equal(result.start, 2); assert.equal(result.end, asset === 'video' ? 6 : asset === 'audio' ? 4 : 7);
  }
  assert.equal(calls.length, 3); assert.equal(JSON.stringify(p), before);
});
for (const row of [null, 'base-A', 'layout', 'auto-captions', trackId(3), trackId(2), 'missing'])
  test('tracked video drag refuses ruler/base/text/wrong-kind/unavailable row ' + row + ' without fallback', async () => {
    const h = trackedHarness(); await h.start(); const e = h.event(h.canvas, 2, { row });
    await h.scroll.emit('dragover', e); assert.equal(h.transfer.dropEffect, 'none'); assert.equal(h.checks.length, 0);
    await h.scroll.emit('drop', e); assert.deepEqual(h.calls, []); assert.deepEqual(h.selected, []);
  });
test('zero-track saved projects keep drag blocked; keyboard Automatic is not impersonated', async () => {
  const h = trackedHarness(); h.timeline.project.manual.layer_tracks.tracks = []; await h.start();
  await h.scroll.emit('drop', h.event(h.canvas, 2, { row: null })); assert.deepEqual(h.calls, []);
  assert.match(h.feedback().textContent, /Use Destination track.*Automatic/);
});
test('missing, failing or malformed tracked planner cannot fall through to generic placement', async () => {
  for (const response of [undefined, null, {}, { issue: false }, { issue: '', start: 2, end: 6 },
    { issue: '', start: 2, end: 6, trackId: trackId(4) }, { issue: '', start: 3, end: 7, trackId: trackId(1) },
    { issue: '', start: 2, end: Infinity, trackId: trackId(1) }, Promise.resolve({ issue: '' })]) {
    const h = trackedHarness({ plan: () => response }); await h.start(); await h.scroll.emit('drop', h.event(h.canvas)); assert.deepEqual(h.calls, []);
  }
  const h = harness(); h.timeline.project = tracked(); h.timeline.mediaRowAtEvent = () => ({ trackId: trackId(1), top: 200, bottom: 260 });
  await h.start(); await h.scroll.emit('drop', h.event(h.canvas)); assert.deepEqual(h.calls, []); assert.match(h.feedback().textContent, /unavailable/);
});
test('occupied disabled occurrence and mixed-insert blockers remain exact read-only feedback', async () => {
  for (const reason of ['Destination Cutaways is occupied, including disabled clips.', 'Cannot split inside a fade.']) {
    const h = trackedHarness({ plan: () => ({ issue: reason }) }); await h.start(); await h.scroll.emit('dragover', h.event(h.canvas, 2, { shiftKey: true }));
    assert.equal(h.feedback().textContent, reason); await h.scroll.emit('drop', h.event(h.canvas, 2, { shiftKey: true })); assert.deepEqual(h.calls, []);
  }
});
test('tracked hover shades only the selected saved row and Escape changes nothing', async () => {
  const h = trackedHarness(), before = JSON.stringify(h.timeline.project); await h.start(); await h.scroll.emit('dragover', h.event(h.canvas));
  const draws = [], ctx = new Proxy({}, { get: (_, key) => (...args) => draws.push([key, ...args]), set: () => true }); h.controller.draw(ctx, 10, 110, 400);
  assert.deepEqual(draws.filter(r => r[0] === 'fillRect'), [['fillRect', 20, 201, 40, 58]]);
  assert.match(h.feedback().textContent, /Overlay video on Cutaways/); assert.deepEqual(h.calls, []);
  await h.doc.emit('keydown', { key: 'Escape' }); assert.equal(JSON.stringify(h.timeline.project), before); assert.equal(h.timeline.libraryDragActive, false);
});
test('tracked Insert has both global shift boundary and exact destination row, while tail remains Append', async () => {
  const h = trackedHarness(); await h.start(); await h.scroll.emit('dragover', h.event(h.canvas, 2, { shiftKey: true }));
  const draws = [], ctx = new Proxy({}, { get: (_, key) => (...args) => draws.push([key, ...args]), set: () => true }); h.controller.draw(ctx, 10, 110, 400);
  assert.ok(draws.some(r => r[0] === 'lineTo' && r[1] === 20 && r[2] === 400));
  assert.deepEqual(draws.filter(r => r[0] === 'fillRect'), [['fillRect', 20, 201, 40, 58]]);
  await h.scroll.emit('drop', h.event(h.canvas, 2, { shiftKey: true }));
  assert.deepEqual(h.calls[0].options, { append: false, insert: true, trackId: trackId(1) });
  const tail = trackedHarness(); await tail.start(); await tail.scroll.emit('drop', tail.event(tail.canvas, 11, { shiftKey: true }));
  assert.deepEqual(tail.calls[0], { assetId: 'video', time: 10, options: { append: true, trackId: trackId(1) } });
});
test('tracked sound/image commit once to exact row and select actual confirmed occurrence', async () => {
  for (const [asset, row] of [['audio', trackId(2)], ['image', trackId(4)]]) {
    const h = trackedHarness(); await h.start(asset); await h.scroll.emit('drop', h.event(h.canvas, 2, { row }));
    assert.deepEqual(h.calls[0].options, { append: false, trackId: row }); assert.deepEqual(h.selected, ['media::media-new']);
  }
});
for (const change of ['rename', 'order', 'remove', 'membership', 'model', 'duration'])
  test('same-revision ' + change + ' invalidates saved track intent before drop', async () => {
    const h = trackedHarness(); await h.start(); const p = h.timeline.project;
    if (change === 'rename') p.manual.layer_tracks.tracks[0].name = 'Renamed';
    if (change === 'order') p.manual.layer_tracks.tracks.reverse();
    if (change === 'remove') p.manual.layer_tracks.tracks.shift();
    if (change === 'membership') p.manual.media_clips.push({ id: 'other', track_id: trackId(1), start: 2, end: 6 });
    if (change === 'model') delete p.manual.layer_tracks;
    if (change === 'duration') p.manual.sequence.duration = 11;
    await h.scroll.emit('drop', h.event(h.canvas)); assert.deepEqual(h.calls, []); assert.match(h.feedback().textContent, /project or source selection changed/);
  });
test('future/orphan models are never interpreted as legacy Automatic placement', () => {
  for (const mutate of [p => p.manual.layer_tracks.version = 99, p => { delete p.manual.layer_tracks; p.manual.media_clips = [{ track_id: trackId(1) }]; }]) {
    const p = tracked(); mutate(p); assert.match(plan(p, 'video', 2, { trackId: trackId(1), placementPreview: () => { throw Error('Never'); } }).error, /incompatible/);
  }
});
test('mismatched saved destination receipt is not selected or claimed as success', async () => {
  const h = trackedHarness({ place: async assetId => {
    const p = tracked(); p.manual.media_clips.push({ id: 'new', asset_id: assetId, track_id: trackId(4) }); h.timeline.project = p; return p;
  } });
  await h.start(); await h.scroll.emit('drop', h.event(h.canvas)); assert.deepEqual(h.selected, []); assert.match(h.feedback().textContent, /not confirmed/);
});
test('track chooser uses a compact native select with visible label, focus and mobile sizing', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8').split('/* Deliberate source-to-track assembly:')[1].split('/* Retained edit recovery:')[0];
  assert.match(css, /media-destination-control \{ display:grid/); assert.match(css, /media-destination-control\[hidden\]/);
  assert.match(css, /select:focus-visible \{ outline:2px solid var\(--focus-ring\)/); assert.match(css, /max-width:899px[\s\S]*min-height:44px/);
  assert.match(css, /media-destination-note[^}]*overflow-wrap:anywhere/); assert.match(css, /library-source-monitor \.media-destination-control \{ grid-column:1\/-1/); assert.match(css, /data-destination-scope=pool[^}]*grid-template-columns:minmax\(0,1fr\)/); assert.match(css, /forced-colors:active/); assert.match(css, /max-width:1100px[\s\S]*library-source-monitor \.media-destination-control[^}]*grid-template-columns:minmax\(0,1fr\)/);
  assert.doesNotMatch(css, /position:fixed|z-index|timeline-toolbar/);
});


test('marked video uses exact selected length for Overlay, Insert and Append, never full duration', () => {
  const p=project();p.assets.video.duration=10;const selected={sourceStart:3,sourceEnd:5},checks=[];
  const overlay=plan(p,'video',2,selected);assert.equal(overlay.end,4);assert.equal(overlay.sourceStart,3);
  const inserted=plan(p,'video',2,{...selected,insert:true,insertionIssue:(...args)=>{checks.push(plain(args));return '';}});
  assert.equal(inserted.end,4);assert.deepEqual(checks,[['video',2,selected]]);
  assert.equal(plan(p,'video',10,selected).end,12);
  for(const bad of [{sourceStart:-1,sourceEnd:2},{sourceStart:3,sourceEnd:2},{sourceStart:0,sourceEnd:10.1},{sourceStart:0},{sourceEnd:2},{sourceStart:NaN,sourceEnd:3},{sourceStart:1,sourceEnd:1.01}])assert.match(plan(p,'video',2,bad).error,/valid source In/);
  assert.match(plan(p,'image',2,selected).error,/valid source In/);
});
test('marked ghost and accessible feedback use the exact source and edit spans without mutation', async()=>{
  const h=harness({sourceSelection:id=>id==='video'?{sourceStart:1,sourceEnd:2.5}:null}),before=JSON.stringify(h.timeline.project);
  await h.start();await h.scroll.emit('dragover',h.event(h.canvas,2));
  const draws=[],ctx=new Proxy({},{get:(_,k)=>(...args)=>draws.push([k,...args]),set:()=>true});h.controller.draw(ctx,10,110,200);
  assert.deepEqual(draws.find(r=>r[0]==='fillRect'),['fillRect',20,30,15,170]);
  assert.match(h.feedback().textContent,/Edit 00:00:02:00–00:00:03:15.*Source 1.000–2.500 s/);
  assert.equal(h.feedback().getAttribute('role'),'status');assert.equal(h.feedback().getAttribute('aria-live'),'polite');
  assert.equal(JSON.stringify(h.timeline.project),before);assert.deepEqual(h.calls,[]);
  await h.scroll.emit('drop',h.event(h.canvas,2));assert.deepEqual(h.calls[0].options,{append:false,sourceStart:1,sourceEnd:2.5});
  assert.deepEqual(h.selected,['media::media-new']);
});
test('marked audio uses its own offset and bounded length, not another source video selection',async()=>{
  const h=harness({sourceSelection:id=>id==='audio'?{sourceStart:.5,sourceEnd:1.25}:null});
  await h.start('audio');await h.scroll.emit('drop',h.event(h.canvas,2));
  assert.deepEqual(h.calls[0].options,{append:false,sourceStart:.5,sourceEnd:1.25});assert.deepEqual(h.selected,['media::media-new']);
  const unmarked=harness({sourceSelection:id=>id==='audio'?{sourceStart:.5,sourceEnd:1.25}:null});
  await unmarked.start();await unmarked.scroll.emit('drop',unmarked.event(unmarked.canvas,2));assert.deepEqual(unmarked.calls[0].options,{append:false});
});
test('bounded marked overlay explicitly previews a shorter Out at edit end',async()=>{
  const h=harness({sourceSelection:()=>({sourceStart:1,sourceEnd:4})});await h.start();await h.scroll.emit('dragover',h.event(h.canvas,9));
  assert.match(h.feedback().textContent,/Source 1.000–2.000 s; shortened at edit end/);
  await h.scroll.emit('drop',h.event(h.canvas,9));assert.equal(h.timeline.project.manual.media_clips.at(-1).end,10);assert.equal(h.timeline.project.manual.media_clips.at(-1).source_start,1);
});
for(const replacement of [null,{sourceStart:1,sourceEnd:3},{issue:'Invalid active In / Out'}])test('changed, cleared or invalid active marks cancel a frozen drag '+JSON.stringify(replacement),async()=>{
  let selected={sourceStart:1,sourceEnd:2};const h=harness({sourceSelection:()=>selected});await h.start();selected=replacement;
  await h.scroll.emit('drop',h.event(h.canvas));assert.deepEqual(h.calls,[]);assert.match(h.feedback().textContent,/source selection changed/);
});
test('invalid active range is not silently replaced with full source; resolver failure also refuses',async()=>{
  for(const sourceSelection of [()=>({issue:'Enter both source In and Out.'}),()=>{throw Error('unavailable')},()=>({sourceStart:1})]){
    const h=harness({sourceSelection});assert.equal((await h.start()).prevented,true);assert.equal(h.timeline.libraryDragActive,undefined);assert.deepEqual(h.calls,[]);
  }
});
test('async placement guard still rejects a source-selection change after drop preflight',async()=>{
  let selected={sourceStart:1,sourceEnd:2};const h=harness({sourceSelection:()=>selected,place:async(_id,_time,_options,context)=>{
    assert.equal(context.isCurrent(),true);selected={sourceStart:2,sourceEnd:3};assert.equal(context.isCurrent(),false);return null;
  }});await h.start();await h.scroll.emit('drop',h.event(h.canvas));assert.match(h.feedback().textContent,/not confirmed/);
});
test('source-monitor summary uses the same native drag path and rejects foreign/disabled owners',async()=>{
  const h=harness({sourceSelection:()=>({sourceStart:1,sourceEnd:2})}),source=new Node(),handle=new Node('p');
  source.className='library-source-monitor';source.dataset.sourceProjectId=h.timeline.project.id;source.dataset.sourceAssetId='video';
  handle.dataset.sourceDrag='true';handle.draggable=true;source.append(handle);h.dock.append(source);
  await h.doc.emit('dragstart',h.event(handle));assert.equal(h.timeline.libraryDragActive,true);
  await h.scroll.emit('drop',h.event(h.canvas));assert.equal(h.calls.length,1);assert.equal(h.calls[0].options.sourceStart,1);
  handle.draggable=false;const blocked=h.event(handle);await h.doc.emit('dragstart',blocked);assert.equal(blocked.prevented,true);
  handle.draggable=true;source.dataset.sourceProjectId='other';const foreign=h.event(handle);await h.doc.emit('dragstart',foreign);assert.equal(foreign.prevented,true);
});
test('marked placement receipt must match offset, timeline span and speed',async()=>{
  for(const patch of [{source_start:0},{start:3},{end:5},{speed:2},{video_source_start:0}]){
    const h=harness({sourceSelection:()=>({sourceStart:1,sourceEnd:2}),place:async()=>{
      const p=project();p.manual.media_clips=[{id:'wrong',asset_id:'video',start:2,end:3,source_start:1,speed:1,...patch}];h.timeline.project=p;return p;
    }});await h.start();await h.scroll.emit('drop',h.event(h.canvas));assert.deepEqual(h.selected,[]);assert.match(h.feedback().textContent,/not confirmed/);
  }
});
const trackScope=vm.createContext({});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/layer-tracks.js'),'utf8').replace(/^export /gm,'')+'\nglobalThis.plan=planLibraryTrackPlacement;',trackScope);
function realTracked(options={}){let h;h=trackedHarness({...options,plan:(...args)=>trackScope.plan(h.timeline.project,...args)});return h;}
for(const kind of ['video','audio'])test('native '+kind+' track planner tests occupancy using marked duration, including the exact end seam',async()=>{
  for(const [start,blocked] of [[3.99,true],[4,false],[4.25,false]]){
    const row=kind==='audio'?trackId(2):trackId(1),h=realTracked({sourceSelection:id=>id===kind?{sourceStart:3,sourceEnd:5}:null});
    h.timeline.project.assets[kind].duration=10;
    h.timeline.project.manual.media_clips=[{id:'media_'+'a'.repeat(32),asset_id:kind,track_id:row,start,end:6,enabled:false}];
    await h.start(kind);await h.scroll.emit('dragover',h.event(h.canvas,2,{row}));
    assert.equal(h.transfer.dropEffect,blocked?'none':'copy');if(blocked)assert.match(h.feedback().textContent,/occupied/);
    await h.scroll.emit('drop',h.event(h.canvas,2,{row}));assert.equal(h.calls.length,blocked?0:1);
  }
});
test('native locked destination and wrong-kind lanes refuse marked hover and drop without rerouting',async()=>{
  for(const wrong of [false,true]){
    const h=realTracked({sourceSelection:()=>({sourceStart:1,sourceEnd:2})});if(!wrong){h.timeline.project.manual.layer_tracks.version=2;h.timeline.project.manual.layer_tracks.tracks.forEach((t,i)=>t.locked=i===0);}
    const row=wrong?trackId(2):trackId(1);await h.start();await h.scroll.emit('dragover',h.event(h.canvas,2,{row}));
    assert.equal(h.transfer.dropEffect,'none');assert.match(h.feedback().textContent,wrong?/visual track/:/locked/i);
    await h.scroll.emit('drop',h.event(h.canvas,2,{row}));assert.deepEqual(h.calls,[]);
  }
});


test('destroying the drag owner during an async preflight revokes its admission guard',async()=>{
 const h=harness({place:async(_id,_time,_options,context)=>{assert.equal(context.isCurrent(),true);h.controller.destroy();assert.equal(context.isCurrent(),false);return null;}});
 await h.start();await h.scroll.emit('drop',h.event(h.canvas));assert.deepEqual(h.selected,[]);
});


for(const [asset,at,options] of [['video',2,{sourceStart:1,sourceEnd:2}],['audio',2,{sourceStart:.5,sourceEnd:1.5}],['video',10,{sourceStart:1,sourceEnd:2}],['video',2,{}]])
 test('legacy native 200-media cap rejects hover and drop for '+asset+' at '+at+' '+JSON.stringify(options),async()=>{
  let h;h=harness({sourceSelection:()=>Object.keys(options).length?options:null,placementPreview:(...args)=>trackScope.plan(h.timeline.project,...args)});
  h.timeline.project.manual.media_clips=Array.from({length:200},(_,i)=>({id:'media_'+i.toString(16).padStart(32,'0'),asset_id:asset,start:0,end:1}));
  const before=JSON.stringify(h.timeline.project);await h.start(asset);await h.scroll.emit('dragover',h.event(h.canvas,at));
  assert.equal(h.transfer.dropEffect,'none');assert.match(h.feedback().textContent,/200 media clips/);
  await h.scroll.emit('drop',h.event(h.canvas,at));assert.deepEqual(h.calls,[]);assert.equal(JSON.stringify(h.timeline.project),before);
 });
test('legacy native readiness errors and inconsistent planner spans cannot paint a valid marked ghost',()=>{
 const p=project();
 for(const at of [2,10]){
  const options={sourceStart:1,sourceEnd:2,placementPreview:()=>({issue:'A source track is locked.'})};
  assert.match(plan(p,'video',at,options).error,/source track is locked/);
  for(const response of [null,{},Promise.resolve({issue:''}),{issue:'',start:at,end:at+4},{issue:'',start:at,end:at+1,trackId:'unexpected'}])
   assert.match(plan(p,'video',at,{...options,placementPreview:()=>response}).error,/could not be verified/);
 }
});
