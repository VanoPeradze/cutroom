// Actual host functions with a small DOM/transport harness. The protocol and
// receipt modules are the shipped modules; no backend or browser is started.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('web/app.js', 'utf8');
const start = source.indexOf('function transcriptBatchOwner(');
const end = source.indexOf('const projectLibrary =', start);
assert.ok(start >= 0 && end > start, 'The transcript host block must exist');
const hostCode = source.slice(start, end);
function shippedFunction(name) {
  const at = source.indexOf(`function ${name}(`);
  assert.ok(at >= 0, `Missing shipped ${name}`);
  return source.slice(source.slice(at - 6, at) === 'async ' ? at - 6 : at, source.indexOf('\n}', at) + 2);
}
const passageControls = shippedFunction('renderManualControls').split('\n')
  .filter(line => /elements\.transcript(Remove|Restore)\.disabled/.test(line)).join('\n');
assert.ok(passageControls.includes('transcriptRecoveryActive'));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const copy = value => structuredClone(value);
const plain = value => JSON.parse(JSON.stringify(value));

class Element {
  constructor(tag = 'div', document = null) {
    this.tag = tag; this.document = document; this.children = []; this.dataset = {};
    this.attributes = {}; this.listeners = new Map(); this.textContent = ''; this.value = '';
    this.hidden = false; this.disabled = false; this.readOnly = false; this.isConnected = true;
    this.scrollTop = 0; this.className = '';
    const values = new Set();
    this.classList = {
      contains: value => values.has(value),
      toggle(value, force) { const on = force ?? !values.has(value); on ? values.add(value) : values.delete(value); return on; },
    };
  }
  set innerHTML(value) {
    this.children = [];
    if (value.includes('transcript-seek')) {
      const seek = new Element('button', this.document); seek.className = 'transcript-seek';
      const time = new Element('time'), text = new Element('span'), status = new Element('b');
      text.className = 'transcript-text'; seek.append(time, text, status);
      const edit = new Element('button', this.document); edit.className = 'transcript-edit';
      this.append(seek, edit);
    }
  }
  append(...children) { for (const child of children) { child.parentElement = this; this.children.push(child); } }
  insertBefore(child, before) {
    const index = this.children.indexOf(before); assert.ok(index >= 0);
    child.parentElement = this; this.children.splice(index, 0, child);
  }
  matches(selector) {
    return selector.startsWith('.') ? this.className.split(' ').includes(selector.slice(1))
      : selector.startsWith('#') ? this.id === selector.slice(1) : this.tag === selector;
  }
  querySelectorAll(selector) {
    const found = [];
    for (const child of this.children) {
      if (child.matches(selector)) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }
  removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
  dispatch(type, event = {}) { for (const listener of [...(this.listeners.get(type) || [])]) listener({ target: this, ...event }); }
  getClientRects() { return this.hidden || this.parentElement && !this.parentElement.getClientRects().length ? [] : [{}]; }
  focus() { if (!this.disabled) { this.document.activeElement = this; this.document.dispatch('focusin', { target: this }); } }
  scrollIntoView() {}
}

function project(count = 2) {
  const segments = Array.from({ length: count }, (_, i) => ({ id: `s${i}`, start: i, end: i + .75, text: `original ${i}` }));
  return {
    id: 'project_transcript_host', revision: 7, name: 'Saved synthetic edit', updated_at: 'before',
    sources: { A: { generation: 1, duration: count + 1, has_audio: true } }, settings: { fps: 30, captions: true },
    analysis: { audio_source: 'A', audio_timeline_offset: 0, transcript: { language: 'en', model: 'synthetic', text: segments.map(x => x.text).join(' '), segments } },
    manual: { caption_corrections: {}, history: { undo_count: 2, redo_count: 1 } },
    draft: { cuts: [], edited_at: 'before' }, caption_alternative_status: { active_id: 'original' },
    editor_captions: [], caption_preview: { version: 1, project_id: 'project_transcript_host', revision: 7, clock: 'edited', available: true, issue: '', width: 1280, height: 720, fps: 30, settings: {} },
  };
}

function setup({ count = 2, buffered = count } = {}) {
  const calls = [], raf = [];
  const document = new Element('document');
  document.body = new Element('body', document); document.documentElement = new Element('html', document);
  document.createElement = tag => new Element(tag, document); document.getElementById = () => null;
  document.activeElement = document.body;
  const window = new Element('window', document);
  const elements = Object.fromEntries([
    'transcriptEditForm', 'transcriptEditText', 'transcriptEditTime', 'transcriptEditStatus',
    'transcriptSave', 'transcriptDiscard', 'transcriptSaveAll', 'transcriptPrevious', 'transcriptNext',
    'transcriptList', 'transcriptSearch', 'transcriptFilter', 'transcriptLanguage', 'transcriptResults',
    'transcriptRemove', 'transcriptRestore', 'advancedPanel',
  ].map(id => { const element = new Element(id, document); element.id = id; return [id, element]; }));
  const card = new Element('section', document), disclosure = new Element('details', document);
  card.append(elements.transcriptList); disclosure.append(card, elements.transcriptEditForm);
  elements.transcriptEditForm.append(elements.transcriptEditText, elements.transcriptSave, elements.transcriptDiscard, elements.transcriptSaveAll);
  elements.transcriptFilter.value = 'all';
  const before = project(count);
  const state = {
    project: before, projectViewToken: 3, transcriptBatches: new Map(), transcriptBuffers: new Map(),
    transcriptReviewBuffers: new WeakSet(), transcriptRecoveryActive: null,
    transcriptActive: { projectId: before.id, id: 's0' }, transcriptSaving: false,
    saveQueues: new Map(), activeUploads: new Set(), jobStartLocks: new Set(),
    mediaStudio: { pending: new Map() }, textStudio: { pending: new Map(), dirty: () => false },
    chromaStudio: {}, embeddedEditor: {}, studio: { open: true },
    manualSelection: { start: 10, end: 11 },
    timeline: { scheduleDraw: () => calls.push('draw'), selectRange: (...args) => calls.push({ range: args }), clearSelection: () => calls.push('clear-selection') },
  };
  const x = { calls, raf, document, window, elements, card, disclosure, state, before, pane: 'transcript', cursor: 4.125 };
  const c = {
    state, elements, document, window, structuredClone, TextEncoder, console,
    requestAnimationFrame: callback => { raf.push(callback); return raf.length; },
    explicitPendingDraft: () => null, savedLayerTrackIssue: () => '', retainedEditIssue: () => '',
    previewRepairBusy: () => false, projectCopySourceBusy: () => false,
    previewRepairSettling: () => null, projectCopyForSource: () => null,
    liveEmbeddedCameraRequest: () => null, captionPreviewIssue: () => '',
    layerGroupDuplicateContext: () => x.pane, pauseAllMedia: () => calls.push('pause'),
    updatePreviewCaption: () => calls.push('caption'), previewPlaybackTime: () => x.cursor,
    rememberProjectRevision: value => calls.push({ remember: value.revision }),
    renderProjectSaveState: () => calls.push('save-status'),
    renderReadiness: () => { calls.push('readiness'); x.onReadiness?.(); },
    renderLanguageDetectionStatus() {}, editorProject: () => state.project,
    hydrateProject: () => { calls.push('hydrate'); x.onHydrate?.(); },
    toast: text => calls.push({ toast: text }),
    openStudioTab: pane => { x.pane = pane; disclosure.hidden = false; calls.push({ pane }); return true; },
    formatTime: time => String(time), languageName: () => 'English', uiCopy: (_he, en) => en,
    hasSourceTracks: () => false, sourceMixerSettings: () => ({}),
    seekSourcePreview: time => calls.push({ seek: time }), setManualSelection: selection => { state.manualSelection = selection; calls.push('selection'); },
    setEditTarget: value => calls.push({ editTarget: value }),
    manualRangeState: () => ({ canRemove: true, canRestore: true }), rangeDeleteIssue: () => '',
    $: (selector, root) => root.querySelector(selector), $$: (selector, root) => root.querySelectorAll(selector),
    applyManualEdit: async (action, detail) => { calls.push({ manualAction: action, detail }); return copy(state.project); },
    api: (url, options) => { calls.push({ url, method: options?.method || 'GET', body: options?.body }); return x.transport(url, options); },
  };
  vm.createContext(c);
  for (const path of ['web/transcript-batch.js', 'web/transcript-batch-receipt.js']) {
    const text = fs.readFileSync(path, 'utf8');
    const exports = [...text.matchAll(/^export (?:function|const) (\w+)/gm)].map(match => match[1]);
    const compiled = text.replace(/^import .*;\r?\n/gm, '').replace(/^export /gm, '');
    Object.assign(c, vm.runInContext(`(function(){\n${compiled}\nreturn {${exports.join(',')}};})()`, c));
  }
  vm.runInContext(hostCode + '\n' + shippedFunction('projectSaveStatus') + '\n' + shippedFunction('foregroundBusy')
    + '\n' + shippedFunction('revealPendingSave') + `\nfunction renderManualControls(){ const available=true, selection=state.manualSelection, busy=foregroundBusy(); ${passageControls} }`, c);
  x.c = c;
  for (const row of before.analysis.transcript.segments.slice(0, buffered)) {
    state.transcriptBuffers.set(`${before.id}:${row.id}`, { projectId: before.id, id: row.id, base: row.text, text: `corrected ${row.id}`, start: row.start, end: row.end, provenance: c.transcriptBufferProvenance() });
  }
  x.transport = async () => ({ project: x.accepted() });
  x.accepted = () => {
    const owner = c.transcriptBatchOwner(); assert.ok(owner, 'A batch owner is reserved before transport');
    const plan = owner.plan, after = copy(owner.before);
    if (!plan.changed.length) return after;
    after.revision++; after.updated_at = 'after'; after.draft.edited_at = 'after';
    after.manual.caption_corrections = plain(plan.corrections);
    after.manual.history = { undo_count: Math.min(20, after.manual.history.undo_count + 1), redo_count: 0 };
    after.caption_preview.revision = after.revision;
    for (const item of plan.binding.items) after.analysis.transcript.segments.find(row => String(row.id) === item.segment_id).text = c.pythonStrip(item.text);
    after.analysis.transcript.text = after.analysis.transcript.segments.map(row => c.pythonStrip(row.text)).join(' ');
    return after;
  };
  x.posts = () => calls.filter(item => item?.method === 'POST');
  x.gets = () => calls.filter(item => item?.method === 'GET');
  x.finish = () => { for (const callback of raf.splice(0)) callback(); };
  x.listenerCount = () => [...document.listeners.values(), ...window.listeners.values()].reduce((sum, set) => sum + set.size, 0);
  x.run = focus => c.activateTranscriptSaveAll({ focusOwner: focus || null });
  x.buffers = [...state.transcriptBuffers.values()];
  return x;
}

async function unknown(x) {
  x.transport = async () => { throw Error('Lost response'); };
  assert.equal(await x.run(), false);
  assert.equal(x.c.transcriptBatchOwner().protocol.snapshot().status, 'unknown');
}
async function newerConflict(x, mutate = () => {}) {
  await unknown(x);
  const latest = copy(x.before); latest.revision += 2; latest.caption_preview.revision = latest.revision;
  latest.analysis.transcript.segments[0].text = 'Third saved text'; mutate(latest);
  x.transport = async () => ({ project: copy(latest) });
  assert.equal(await x.run(), false);
  assert.equal(x.c.transcriptBatchOwner().protocol.snapshot().canLoadNewer, true);
  return latest;
}

function installActualApi(x) {
  const at = source.indexOf('class ApiError extends Error');
  assert.ok(at >= 0);
  x.c.FormData = class FormData {};
  x.c.recoverProjectCopies = () => Promise.resolve();
  x.c.fetch = async (path, options) => {
    x.calls.push({ fetchPath: path, fetchOptions: options });
    if (x.fetchTransport) return x.fetchTransport(path, options);
    return { ok: true, headers: { get: () => 'application/json' }, json: async () => ({}), text: async () => '' };
  };
  vm.runInContext(source.slice(at, source.indexOf('\n}', at) + 2) + '\n' + shippedFunction('api'), x.c);
  x.fetches = () => x.calls.filter(item => item?.fetchPath);
}

test('21 changed buffers use one real protocol/receipt, one revision and one Undo entry', async () => {
  const x = setup({ count: 21 }); const selection = x.state.manualSelection;
  assert.equal(await x.run(), true);
  assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 0);
  const payload = JSON.parse(x.posts()[0].body);
  assert.equal(payload.action, 'transcript_text_batch'); assert.equal(payload.items.length, 21); assert.equal(payload.expected_revision, 7);
  assert.equal(x.state.project.revision, 8); assert.equal(x.state.project.manual.history.undo_count, 3);
  assert.equal(x.state.project.manual.history.redo_count, 0); assert.equal(x.state.transcriptBuffers.size, 0);
  assert.equal(x.state.manualSelection, selection); assert.equal(x.calls.filter(item => item === 'pause').length, 1);
  assert.equal(x.calls.some(item => item?.seek || item?.range || item === 'hydrate'), false);
  assert.match(x.elements.transcriptEditStatus.textContent, /One Undo restores/);
});

test('no-op gets exact server receipt without pausing or inventing an Undo', async () => {
  const x = setup(); for (const buffer of x.buffers) buffer.text = ` ${buffer.base} `;
  assert.equal(await x.run(), true); assert.equal(x.posts().length, 1);
  assert.deepEqual(x.state.project, x.before); assert.equal(x.state.transcriptBuffers.size, 0);
  assert.equal(x.calls.includes('pause'), false); assert.match(x.elements.transcriptEditStatus.textContent, /No Undo step/);
});

test('synchronous reservation prevents repeated Save all while a POST is held', async () => {
  const x = setup(), d = deferred(); x.transport = () => d.promise;
  const pending = x.run(); assert.equal(x.posts().length, 1); assert.equal(x.state.transcriptSaving, true);
  assert.equal(await x.run(), false); assert.equal(await x.c.saveTranscriptBuffers(true), false);
  assert.equal(x.posts().length, 1); d.resolve({ project: x.accepted() }); await pending;
  assert.equal(x.state.transcriptSaving, false);
});

const blockers = {
  explicit: x => x.c.explicitPendingDraft = () => ({ detail: 'Keep my explicit draft' }),
  tracks: x => x.c.savedLayerTrackIssue = () => 'Unsupported tracks',
  retained: x => x.c.retainedEditIssue = () => 'Retained edit',
  manual: x => x.state.manualEditBusy = true,
  manualPromise: x => x.state.manualEditPromise = Promise.resolve(),
  caption: x => x.state.captionContextSave = {},
  repair: x => x.c.previewRepairBusy = () => true,
  copy: x => x.c.projectCopySourceBusy = () => true,
  job: x => x.state.activeJob = {}, upload: x => x.state.activeUploads.add('file'),
  admission: x => x.state.jobStartLocks.add('job'), mediaPending: x => x.state.mediaStudio.pending.set('m', {}),
  mediaSaving: x => x.state.mediaStudio.saving = Promise.resolve(), textDraft: x => x.state.textStudio.dirty = () => true,
  textPending: x => x.state.textStudio.pending.set('t', {}), chroma: x => x.state.chromaStudio.saving = true,
  settings: x => x.state.saveQueues.set(x.before.id, { pending: {} }),
  settingsError: x => x.state.saveQueues.set(x.before.id, { error: 'unsaved' }),
  timelineGesture: x => x.state.timeline.gesture = {}, scrubbing: x => x.state.timeline.scrubbing = true,
  timelinePending: x => x.state.timeline.editPending = true, drop: x => x.state.timeline.libraryDragActive = true,
  sourceGesture: x => x.state.sourceReview = { timeline: { gesture: {} } },
  sourcePending: x => x.state.mediaStudio.shotReview = { pending: true },
  frame: x => x.state.mediaStudio.frameEditor = { active: true },
  numeric: x => x.document.documentElement.classList.toggle('numeric-scrubbing', true),
};
for (const [name, mutate] of Object.entries(blockers)) test(`other ${name} refuses without save, pause or draft loss`, async () => {
  const x = setup(); mutate(x); assert.equal(await x.run(), false);
  assert.equal(x.posts().length, 0); assert.equal(x.calls.includes('pause'), false);
  assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
});

test('reentrant readiness change after reservation refuses before POST', async () => {
  const x = setup(); x.onReadiness = () => { x.state.project = { ...x.state.project, name: 'Newer local choice' }; };
  assert.equal(await x.run(), false); assert.equal(x.posts().length, 0); assert.equal(x.calls.includes('pause'), false);
});
test('pause callback invalidation is rechecked before the sole POST', async () => {
  const x = setup(); x.c.pauseAllMedia = () => { x.state.projectViewToken++; };
  assert.equal(await x.run(), false); assert.equal(x.posts().length, 0); assert.equal(x.state.transcriptBuffers.size, 2);
});

for (const kind of ['network', 'malformed', '409']) test(`unknown ${kind} retains all drafts and offers GET-only Check`, async () => {
  const x = setup(); x.transport = async () => {
    if (kind === 'malformed') return {};
    throw Object.assign(Error('Unconfirmed'), kind === '409' ? { status: 409 } : {});
  };
  assert.equal(await x.run(), false); assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 0);
  assert.equal(x.state.project, x.before); assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes'); assert.equal(x.elements.transcriptSaveAll.disabled, false);
  assert.equal(x.c.projectSaveStatus().kind, 'error'); assert.equal(x.c.projectSaveStatus().target, 'transcript');
  assert.ok(x.c.foregroundBusy());
});

test('baseline Check permits only explicit identical-body original-revision Retry', async () => {
  const x = setup(); await unknown(x); const body = x.posts()[0].body;
  x.transport = async () => ({ project: copy(x.before) });
  assert.equal(await x.run(), false); assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 1);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Retry same save');
  x.transport = async () => ({ project: x.accepted() });
  assert.equal(await x.run(), true); assert.equal(x.posts().length, 2); assert.equal(x.posts()[1].body, body);
  assert.equal(x.state.project.manual.history.undo_count, 3);
});

test('a rejected explicit retry leaves Check reachable for the uncertain original', async () => {
  const x = setup(); await unknown(x); x.transport = async () => ({ project: copy(x.before) }); await x.run();
  x.transport = async () => { throw Object.assign(Error('Retry refused'), { status: 400 }); };
  assert.equal(await x.run(), false); assert.equal(x.posts().length, 2);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes'); assert.equal(x.elements.transcriptSaveAll.disabled, false);
  assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
});

test('programmatically newer buffer after baseline Check revokes Retry without losing the old uncertain owner', async () => {
  const x = setup(); await unknown(x); x.transport = async () => ({ project: copy(x.before) }); await x.run();
  const key = `${x.before.id}:s0`, updated = { ...x.buffers[0], text: 'A newer draft' };
  x.state.transcriptBuffers.set(key, updated); x.c.renderTranscriptDetail(false);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes');
  await x.run(); assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 2); assert.equal(x.state.transcriptBuffers.get(key), updated);
});

test('verified Check clears only unchanged captured objects, preserving a newer buffer and other project', async () => {
  const x = setup(); await unknown(x); const accepted = x.accepted();
  const key = `${x.before.id}:s0`, newer = { ...x.buffers[0], text: 'Typed after sending' }, other = { projectId: 'other', id: 's0', text: 'Keep' };
  x.state.transcriptBuffers.set(key, newer); x.state.transcriptBuffers.set('other:s0', other);
  x.transport = async () => ({ project: accepted }); assert.equal(await x.run(), true);
  assert.equal(x.posts().length, 1); assert.equal(x.state.transcriptBuffers.get(key), newer);
  assert.equal(x.state.transcriptBuffers.get('other:s0'), other); assert.equal(x.state.transcriptBuffers.has(`${x.before.id}:s1`), false);
});

test('mutating a captured object in place prevents its cleanup', async () => {
  const x = setup(), d = deferred(); x.transport = () => d.promise; const pending = x.run(); const accepted = x.accepted();
  x.buffers[0].text = 'Newer in-place text'; d.resolve({ project: accepted }); await pending;
  assert.equal(x.state.transcriptBuffers.get(`${x.before.id}:s0`), x.buffers[0]); assert.equal(x.state.transcriptBuffers.size, 1);
});

test('mixed newer GET clears no subset and only offers explicit Load', async () => {
  const x = setup(); const latest = await newerConflict(x);
  assert.equal(x.state.project, x.before); assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Load newer version'); assert.equal(x.gets().length, 1);
  assert.equal(x.calls.includes('hydrate'), false); assert.ok(latest.revision > x.before.revision);
});

test('explicit newer Load retains every object and marks even matching lines review-only', async () => {
  const x = setup(); const latest = await newerConflict(x);
  assert.equal(await x.run(), true); assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 2);
  assert.equal(x.state.project.revision, latest.revision); assert.equal(x.state.projectViewToken, 4);
  assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
  for (const buffer of x.buffers) { assert.ok(x.state.transcriptReviewBuffers.has(buffer)); assert.ok(x.c.transcriptDraftReview(buffer)); }
  assert.equal(x.elements.transcriptEditText.readOnly, true); assert.equal(x.elements.transcriptEditText.disabled, false);
  assert.equal(x.elements.transcriptSave.disabled, true); assert.equal(x.elements.transcriptSaveAll.disabled, true);
  assert.equal(x.elements.transcriptDiscard.disabled, false); assert.equal(x.c.transcriptBatchIssue(), '');
});

for (const [name, mutate] of Object.entries({
  explicit: x => x.c.explicitPendingDraft = () => ({ detail: 'Other retained draft' }),
  settings: x => x.state.saveQueues.set(x.before.id, { pending: {} }),
  media: x => x.state.mediaStudio.pending.set('clip', {}),
  gesture: x => x.state.timeline.gesture = {},
})) test(`newer Load never bypasses other ${name}`, async () => {
  const x = setup(); await newerConflict(x); mutate(x);
  assert.equal(await x.run(), false); assert.equal(x.gets().length, 1); assert.equal(x.state.project, x.before);
  assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
});

test('failed fresh Load restores Check instead of retrying the load automatically', async () => {
  const x = setup(); await newerConflict(x); x.transport = async () => { throw Error('GET unavailable'); };
  assert.equal(await x.run(), false); assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes');
  assert.equal(x.state.project, x.before); assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 2);
});

for (const [name, mutate] of Object.entries({
  project: x => x.state.project = { ...x.before, id: 'other' },
  view: x => x.state.projectViewToken++, raw: x => x.before.name = 'New local name',
  pointer: x => x.document.dispatch('pointerdown'), key: x => x.document.dispatch('keydown'),
  wheel: x => x.document.dispatch('wheel'), focus: x => x.document.dispatch('focusin', { target: {} }),
})) test(`held newer Load respects later ${name}`, async () => {
  const x = setup(); const latest = await newerConflict(x), d = deferred(); x.transport = () => d.promise;
  const pending = x.run(); mutate(x); const current = x.state.project;
  d.resolve({ project: latest }); assert.equal(await pending, false); assert.equal(x.state.project, current);
  assert.equal(x.calls.includes('hydrate'), false); assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
});

test('saved-now with unrelated newer fields does not install until explicit Load', async () => {
  const x = setup(); await unknown(x); const latest = x.accepted(); latest.revision++; latest.caption_preview.revision++;
  latest.name = 'Name changed elsewhere'; x.transport = async () => ({ project: copy(latest) });
  assert.equal(await x.run(), true); assert.equal(x.state.project, x.before); assert.equal(x.state.transcriptBuffers.size, 0);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Load newer version'); assert.equal(x.elements.transcriptSaveAll.disabled, false);
  assert.ok(x.c.transcriptBatchIssue()); assert.equal(await x.run(), true); assert.equal(x.state.project.name, latest.name);
  assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 2);
});

test('all submitted text saved does not authorize saved-now or Load with a malformed unrelated row', async () => {
  const x = setup({ count: 3, buffered: 2 }); await unknown(x);
  const latest = x.accepted(); latest.revision++; latest.caption_preview.revision++;
  latest.analysis.transcript.segments[2].text = { malformed: true };
  x.transport = async () => ({ project: latest });
  assert.equal(await x.run(), false); assert.equal(x.state.project, x.before);
  assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
  assert.equal(x.c.transcriptBatchOwner().protocol.snapshot().canLoadNewer, false);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes');
});

for (const [name, alter] of Object.entries({
  absent: (x, b) => x.state.project.analysis.transcript.segments = [],
  ambiguous: (x, b) => x.state.project.analysis.transcript.segments.push({ ...x.state.project.analysis.transcript.segments[0] }),
  provenance: x => x.state.project.sources.A.generation++,
  timing: x => x.state.project.analysis.transcript.segments[0].start = -.5,
  reviewed: (x, b) => x.state.transcriptReviewBuffers.add(b),
})) test(`retained ${name} row remains accessible outside search/filter without timeline identity`, async () => {
  const x = setup({ buffered: 1 }), buffer = x.buffers[0], raw = copy(buffer); alter(x, buffer);
  x.elements.transcriptSearch.value = 'nothing matches'; x.elements.transcriptFilter.value = 'removed';
  x.c.renderTranscript(); const rows = x.elements.transcriptList.querySelectorAll('.transcript-retained-draft');
  assert.equal(rows.length, 1); const row = rows[0];
  assert.equal(row.dataset.start, undefined); assert.equal(row.dataset.timelineRanges, undefined);
  assert.match(x.elements.transcriptResults.textContent, /0 of \d+ lines \| 1 retained draft/);
  row.children[0].dispatch('click');
  assert.equal(x.c.selectedTranscriptSegment(), null); assert.equal(x.c.selectedTranscriptRecoveryDraft(), buffer);
  assert.equal(x.elements.transcriptEditText.value, buffer.text); assert.equal(x.elements.transcriptEditText.readOnly, true);
  assert.equal(x.elements.transcriptEditText.disabled, false); assert.equal(x.elements.transcriptSave.disabled, true);
  assert.equal(x.elements.transcriptPrevious.disabled, true); assert.equal(x.elements.transcriptNext.disabled, true);
  assert.equal(x.elements.transcriptRemove.disabled, true); assert.equal(x.elements.transcriptRestore.disabled, true);
  x.c.moveTranscriptLine(1); x.elements.transcriptEditText.value = 'Attempted event injection'; x.c.bufferTranscriptText();
  assert.deepEqual(buffer, raw); assert.equal(await x.c.saveTranscriptBuffers(false), false);
  assert.equal(x.posts().length, 0); assert.equal(x.calls.some(item => item?.seek || item?.range || item === 'pause' || item === 'selection'), false);
});

test('retained text is textContent, never a new HTML/segment/seek target', () => {
  const x = setup({ buffered: 1 }), buffer = x.buffers[0]; buffer.text = '<img src=x onerror=alert(1)> שלום';
  x.state.transcriptReviewBuffers.add(buffer); x.c.renderTranscript();
  const button = x.elements.transcriptList.querySelector('.transcript-retained-draft').children[0];
  const text = button.querySelector('.transcript-text');
  assert.equal(text.textContent, `Retained draft ${buffer.id}: ${buffer.text}`); assert.equal(text.children.length, 0);
  assert.equal(button.querySelectorAll('img').length, 0);
  assert.equal(x.state.project.analysis.transcript.segments.length, 2);
});

test('Discard retires only the chosen retained object; explicit edit creates a fresh base', async () => {
  const x = setup(); const latest = await newerConflict(x); await x.run();
  const first = x.buffers[0], second = x.buffers[1];
  x.c.discardTranscriptBuffer(); assert.equal(x.state.transcriptBuffers.has(`${first.projectId}:${first.id}`), false);
  assert.equal(x.state.transcriptBuffers.get(`${second.projectId}:${second.id}`), second);
  const current = x.state.project.analysis.transcript.segments[0]; x.c.selectTranscriptLine(current);
  x.elements.transcriptEditText.value = 'Deliberately pasted again'; x.c.bufferTranscriptText();
  const fresh = x.state.transcriptBuffers.get(`${first.projectId}:${first.id}`);
  assert.notEqual(fresh, first); assert.equal(fresh.base, latest.analysis.transcript.segments[0].text);
  assert.equal(fresh.start, current.start); assert.equal(fresh.end, current.end); assert.equal(x.c.transcriptDraftReview(fresh), null);
  assert.ok(x.c.transcriptDraftReview(second)); assert.equal(x.elements.transcriptSaveAll.disabled, true);
});

test('normal single Save remains the existing singular action, not the batch path', async () => {
  const x = setup(); assert.equal(await x.c.saveTranscriptBuffers(false), true);
  assert.equal(x.calls.filter(item => item?.manualAction === 'transcript_text').length, 1);
  assert.equal(x.posts().length, 0); assert.equal(x.state.transcriptBuffers.size, 1);
});

test('closed pane still exposes unresolved batch via existing project save status', async () => {
  const x = setup(); await unknown(x); x.pane = 'audio'; x.disclosure.hidden = true; x.state.transcriptActive = null;
  const status = x.c.projectSaveStatus(); assert.equal(status.target, 'transcript'); assert.equal(status.actionable, true);
  assert.notEqual(status.label, 'Saved'); x.c.revealPendingSave(status);
  assert.equal(x.pane, 'transcript'); assert.equal(x.disclosure.open, true); assert.equal(x.elements.transcriptEditForm.hidden, false);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes');
  assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 0); assert.equal(x.calls.some(item => item?.seek || item?.range), false);
});

for (const [name, change] of Object.entries({
  view: x => x.state.projectViewToken++, project: x => x.state.project = { ...x.before, id: 'other' },
  raw: x => x.before.name = 'New local state', draft: x => x.c.explicitPendingDraft = () => ({ detail: 'New draft' }),
})) test(`late accepted save preserves newer ${name} and never hydrates/seeks/focuses`, async () => {
  const x = setup(), d = deferred(); x.transport = () => d.promise;
  x.document.activeElement = x.elements.transcriptSaveAll;
  const pending = x.run(x.elements.transcriptSaveAll), accepted = x.accepted(); change(x); const current = x.state.project;
  x.document.activeElement = x.document.body; d.resolve({ project: accepted }); await pending; x.finish();
  assert.equal(x.state.project, current); assert.equal(x.calls.includes('hydrate'), false);
  assert.equal(x.calls.some(item => item?.seek || item?.range), false);
  assert.equal(x.document.activeElement === x.document.body, true, 'A newer local intent must not receive batch focus');
});

test('newer accepted server revision leaves old captured text review-only', async () => {
  const x = setup(), d = deferred(); x.transport = () => d.promise; const pending = x.run(), accepted = x.accepted();
  x.state.project = copy(x.before); x.state.project.revision = accepted.revision + 1;
  d.resolve({ project: accepted }); await pending;
  for (const buffer of x.buffers) { assert.equal(x.state.transcriptBuffers.get(`${buffer.projectId}:${buffer.id}`), buffer); assert.ok(x.state.transcriptReviewBuffers.has(buffer)); }
});

test('owned success recovers keyboard focus to the still-visible textarea', async () => {
  const x = setup(); x.document.activeElement = x.elements.transcriptSaveAll;
  x.onReadiness = () => { if (x.state.transcriptSaving) x.document.activeElement = x.document.body; };
  await x.run(x.elements.transcriptSaveAll); x.finish();
  assert.equal(x.document.activeElement, x.elements.transcriptEditText); assert.equal(x.listenerCount(), 0);
});

for (const type of ['pointerdown', 'keydown', 'wheel', 'focusin']) test(`new ${type} wins over pending Save focus`, async () => {
  const x = setup(), d = deferred(); x.transport = () => d.promise; x.document.activeElement = x.elements.transcriptSaveAll;
  const pending = x.run(x.elements.transcriptSaveAll); x.document.activeElement = x.document.body;
  x.document.dispatch(type, type === 'focusin' ? { target: {} } : {});
  d.resolve({ project: x.accepted() }); await pending; x.finish();
  assert.equal(x.document.activeElement, x.document.body); assert.equal(x.listenerCount(), 0);
});

test('new input after Load resolves but before focus RAF must still win', async () => {
  const x = setup(); await newerConflict(x); x.document.activeElement = x.elements.transcriptSaveAll;
  x.onHydrate = () => { x.document.activeElement = x.document.body; };
  assert.equal(await x.run(x.elements.transcriptSaveAll), true);
  assert.ok(x.raf.length); x.document.dispatch('keydown'); x.finish();
  assert.equal(x.document.activeElement, x.document.body); assert.equal(x.listenerCount(), 0);
});

test('new pane during a held recovery Load does not install or restore the old view', async () => {
  const x = setup(); const latest = await newerConflict(x), d = deferred(); x.transport = () => d.promise;
  const pending = x.run(); x.pane = 'audio'; d.resolve({ project: latest });
  assert.equal(await pending, false); assert.equal(x.state.project, x.before); assert.equal(x.calls.includes('hydrate'), false);
});

test('new seek during a held recovery Load cancels adoption without restoring the old cursor', async () => {
  const x = setup(); const latest = await newerConflict(x), d = deferred(); x.transport = () => d.promise;
  const pauses = x.calls.filter(item => item === 'pause').length;
  const pending = x.run(); assert.equal(x.calls.filter(item => item === 'pause').length, pauses + 1);
  x.cursor = 12.75; d.resolve({ project: latest });
  assert.equal(await pending, false); assert.equal(x.state.project, x.before); assert.equal(x.cursor, 12.75);
  assert.equal(x.calls.includes('hydrate'), false); assert.equal(x.calls.some(item => item?.seek), false);
});

test('new transcript selection during a held Load cancels old recovery installation', async () => {
  const x = setup(); const latest = await newerConflict(x), d = deferred(); x.transport = () => d.promise;
  const pending = x.run(); x.state.transcriptActive = { projectId: x.before.id, id: 's1' };
  d.resolve({ project: latest }); assert.equal(await pending, false); assert.equal(x.state.project, x.before);
  assert.equal(x.state.transcriptActive.id, 's1'); assert.equal(x.state.transcriptRecoveryActive, null);
});

for (const [name, replace] of Object.entries({
  project: x => { x.state.project = { ...x.state.project, id: 'new_project' }; },
  view: x => { x.state.projectViewToken++; },
  owner: x => { x.state.transcriptBatches.set(x.before.id, { notice: 'New owner' }); },
})) test(`hydrate callback replacing ${name} prevents later recovery selection and focus`, async () => {
  const x = setup(); await newerConflict(x); x.document.activeElement = x.elements.transcriptSaveAll;
  x.onHydrate = () => { replace(x); x.document.activeElement = x.document.body; };
  assert.equal(await x.run(x.elements.transcriptSaveAll), false);
  assert.equal(x.state.transcriptRecoveryActive, null);
  x.finish(); assert.equal(x.document.activeElement === x.document.body, true);
  assert.equal(x.listenerCount(), 0);
});

test('protocol acknowledgment reentrancy cannot restore a replaced recovery view', async () => {
  const x = setup(); await newerConflict(x); const owner = x.c.transcriptBatchOwner(), protocol = owner.protocol;
  owner.protocol = { ...protocol, acceptNewerLoad(next) { const result = protocol.acceptNewerLoad(next); x.state.projectViewToken++; return result; } };
  x.document.activeElement = x.elements.transcriptSaveAll;
  x.onHydrate = () => { x.document.activeElement = x.document.body; };
  assert.equal(await x.run(x.elements.transcriptSaveAll), false);
  assert.equal(x.state.transcriptRecoveryActive, null);
  x.finish(); assert.equal(x.document.activeElement === x.document.body, true); assert.equal(x.listenerCount(), 0);
});

test('a failed later Check revokes previous newer-load permission', async () => {
  const x = setup(); await newerConflict(x); const owner = x.c.transcriptBatchOwner();
  x.transport = async () => { throw Error('Later read failed'); };
  await x.c.runTranscriptBatchOperation(owner, 'check');
  assert.equal(owner.protocol.snapshot().canLoadNewer, false);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes');
  assert.equal(await x.c.loadNewerTranscriptVersion(owner), false);
  assert.equal(x.state.project, x.before); assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
});

test('fresh Load refuses a revision older than the previously reviewed newer version', async () => {
  const x = setup(); const latest = await newerConflict(x);
  latest.revision--; latest.caption_preview.revision--;
  x.transport = async () => ({ project: latest });
  assert.equal(await x.run(), false); assert.equal(x.state.project, x.before);
  assert.equal(x.calls.includes('hydrate'), false); assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes');
});

for (const [name, row] of Object.entries({
  null: null,
  string: 'not a saved segment',
  textObject: { id: 's0', start: 0, end: .75, text: { unexpected: true } },
  nonfiniteClock: { id: 's0', start: NaN, end: .75, text: 'Third saved text' },
})) test(`malformed newer ${name} row cannot authorize a recovery Load`, async () => {
  const x = setup(); await unknown(x);
  const latest = copy(x.before); latest.revision += 2; latest.caption_preview.revision = latest.revision;
  latest.analysis.transcript.segments[0] = row;
  x.transport = async () => ({ project: latest });
  assert.equal(await x.run(), false); assert.equal(x.state.project, x.before);
  assert.equal(x.c.transcriptBatchOwner().protocol.snapshot().canLoadNewer, false);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes');
  assert.deepEqual([...x.state.transcriptBuffers.values()], x.buffers);
});

test('all drafts absent from a newer transcript remain reachable and individually discardable', async () => {
  const x = setup(); await newerConflict(x, latest => { delete latest.analysis.transcript; });
  assert.equal(await x.run(), true); x.elements.transcriptSearch.value = 'unmatched'; x.elements.transcriptFilter.value = 'kept';
  x.c.renderTranscript(); assert.match(x.elements.transcriptResults.textContent, /^0 of 0 lines \| 2 retained drafts$/);
  assert.equal(x.elements.transcriptEditText.readOnly, true);
  x.c.discardTranscriptBuffer(); assert.equal(x.state.transcriptBuffers.size, 1);
  const row = x.elements.transcriptList.querySelector('.transcript-retained-draft'); row.children[0].dispatch('click');
  assert.equal(x.elements.transcriptEditText.value, x.buffers[1].text);
  x.c.discardTranscriptBuffer(); assert.equal(x.state.transcriptBuffers.size, 0);
  assert.equal(x.state.project.analysis.transcript, undefined); assert.equal(x.posts().length, 1);
});

test('unknown batch blocks Discard and remains discoverable with no selected line', async () => {
  const x = setup({ count: 1 }); await unknown(x); x.c.discardTranscriptBuffer();
  x.state.transcriptActive = null; x.c.renderTranscriptDetail();
  assert.equal(x.state.transcriptBuffers.size, 1); assert.equal(x.elements.transcriptEditForm.hidden, false);
  assert.equal(x.elements.transcriptSaveAll.textContent, 'Check saved changes'); assert.equal(x.elements.transcriptSaveAll.disabled, false);
  assert.equal(x.c.projectSaveStatus().target, 'transcript'); assert.equal(x.posts().length, 1);
});

for (const phase of ['unknown', 'baseline', 'mixed', 'retry-refused']) test(`uncertain ${phase} keeps text copyable but cannot supersede the immutable save`, async () => {
  const x = setup();
  if (phase === 'mixed') await newerConflict(x);
  else {
    await unknown(x);
    if (phase === 'baseline' || phase === 'retry-refused') {
      x.transport = async () => ({ project: copy(x.before) }); await x.run();
    }
    if (phase === 'retry-refused') {
      x.transport = async () => { throw Object.assign(Error('Retry refused'), { status: 400 }); }; await x.run();
    }
  }
  const captured = [...x.state.transcriptBuffers.values()], fields = copy(captured), posts = x.posts().length;
  assert.equal(x.elements.transcriptEditText.readOnly, true); assert.equal(x.elements.transcriptEditText.disabled, false);
  assert.equal(x.elements.transcriptDiscard.disabled, true); assert.equal(x.elements.transcriptSave.disabled, true);
  assert.equal(x.elements.transcriptSaveAll.disabled, false);
  x.elements.transcriptEditText.value = 'Queued input after the original click'; x.c.bufferTranscriptText();
  x.c.discardTranscriptBuffer();
  assert.deepEqual([...x.state.transcriptBuffers.values()], fields);
  for (const buffer of captured) assert.equal(x.state.transcriptBuffers.get(`${buffer.projectId}:${buffer.id}`), buffer);
  assert.equal(await x.c.saveTranscriptBuffers(false), false); assert.equal(x.posts().length, posts);
  x.elements.transcriptEditText.focus(); assert.equal(x.document.activeElement, x.elements.transcriptEditText);
  if (phase === 'baseline') assert.equal(x.c.transcriptBatchOwner().protocol.snapshot().canRetry, true);
});

test('verified uncertain save releases ordinary local editing only after exact receipt resolution', async () => {
  const x = setup(); await unknown(x); const accepted = x.accepted(); x.transport = async () => ({ project: accepted });
  assert.equal(await x.run(), true); assert.equal(x.elements.transcriptEditText.readOnly, false);
  x.elements.transcriptEditText.value = 'A deliberate edit after confirmation'; x.c.bufferTranscriptText();
  assert.equal(x.state.transcriptBuffers.get(`${x.before.id}:s0`).base, 'corrected s0');
  assert.equal(x.elements.transcriptDiscard.disabled, false); assert.equal(x.elements.transcriptSave.disabled, false);
});

test('definite initial refusal has no uncertain original and permits retained text editing or Discard', async () => {
  const x = setup(); x.transport = async () => { throw Object.assign(Error('Invalid batch'), { status: 400 }); };
  assert.equal(await x.run(), false); assert.equal(x.elements.transcriptEditText.readOnly, false);
  assert.equal(x.elements.transcriptDiscard.disabled, false); x.c.discardTranscriptBuffer();
  assert.equal(x.state.transcriptBuffers.size, 1); assert.equal(x.posts().length, 1);
});

test('changed full source provenance makes same-ID same-time drafts copy-only', () => {
  const x = setup(); x.before.analysis.transcript.model = 'different analysis';
  assert.equal(x.c.transcriptDraftReview(x.buffers[0]).kind, 'orphan');
  x.c.selectTranscriptLine(x.before.analysis.transcript.segments[0]);
  assert.equal(x.elements.transcriptEditText.readOnly, true); assert.equal(x.calls.includes('pause'), false);
  assert.equal(x.calls.some(item => item?.seek || item?.range), false);
});

test('actual central api accepts the exact submitting owner and strips its internal token before fetch', async () => {
  const x = setup(); installActualApi(x);
  x.fetchTransport = async () => ({ ok: true, headers: { get: () => 'application/json' }, json: async () => ({ project: x.accepted() }) });
  assert.equal(await x.run(), true); assert.equal(x.fetches().length, 1);
  const call = x.fetches()[0];
  assert.equal(call.fetchPath, `/api/projects/${encodeURIComponent(x.before.id)}/manual/edit`);
  assert.equal(call.fetchOptions.method, 'POST');
  assert.equal(call.fetchOptions.body, x.c.transcriptBatchOwner().protocol.snapshot().binding.body);
  assert.equal(Object.hasOwn(call.fetchOptions, 'transcriptBatchToken'), false);
  assert.equal(call.fetchOptions.headers['Content-Type'], 'application/json');
});

for (const [name, alter] of Object.entries({
  missingToken: request => { delete request.options.transcriptBatchToken; },
  foreignToken: request => { request.options.transcriptBatchToken = {}; },
  lookalikeOwner: request => { request.options.transcriptBatchToken = { ...request.options.transcriptBatchToken }; },
  changedBody: request => { request.options.body += ' '; },
  newRevision: request => { const body = JSON.parse(request.options.body); body.expected_revision++; request.options.body = JSON.stringify(body); },
  changedText: request => { const body = JSON.parse(request.options.body); body.items[0].text = 'Different intent'; request.options.body = JSON.stringify(body); },
  settingsPath: request => { request.path = request.path.replace('/manual/edit', '/settings'); },
  renamePath: request => { request.path = request.path.replace('/manual/edit', ''); request.options.method = 'PATCH'; },
  deletePath: request => { request.path = request.path.replace('/manual/edit', ''); request.options.method = 'DELETE'; },
  extraQuery: request => { request.path += '?another=1'; },
  nonPost: request => { request.options.method = 'PATCH'; },
})) test(`actual central api refuses ${name} despite an admitted pending batch`, async () => {
  const x = setup(); installActualApi(x); const d = deferred(); x.fetchTransport = () => d.promise;
  const pending = x.run(); const owner = x.c.transcriptBatchOwner();
  assert.equal(owner.protocol.snapshot().status, 'submitting'); assert.equal(x.fetches().length, 1);
  const request = { path: `/api/projects/${encodeURIComponent(x.before.id)}/manual/edit`, options: { method: 'POST', body: owner.protocol.snapshot().binding.body, transcriptBatchToken: owner } };
  alter(request);
  await assert.rejects(x.c.api(request.path, request.options), error => error.code === 'transcript_batch_pending' && error.status === 409);
  assert.equal(x.fetches().length, 1);
  d.resolve({ ok: true, headers: { get: () => 'application/json' }, json: async () => ({ project: x.accepted() }) });
  assert.equal(await pending, true);
});

test('an exact token cannot write while the original outcome is unknown rather than submitting', async () => {
  const x = setup(); await unknown(x); installActualApi(x); const owner = x.c.transcriptBatchOwner();
  await assert.rejects(x.c.api(`/api/projects/${x.before.id}/manual/edit`, { method: 'POST', body: owner.protocol.snapshot().binding.body, transcriptBatchToken: owner }), error => error.code === 'transcript_batch_pending');
  assert.equal(x.fetches().length, 0);
});

for (const method of ['GET', 'HEAD', 'OPTIONS']) test(`central ${method} stays available during unknown recovery without token leakage`, async () => {
  const x = setup(); await unknown(x); installActualApi(x); const owner = x.c.transcriptBatchOwner();
  await x.c.api(`/api/projects/${x.before.id}`, { method, transcriptBatchToken: owner, headers: { 'X-Probe': 'read-only' } });
  assert.equal(x.fetches().length, 1); assert.equal(x.fetches()[0].fetchOptions.method, method);
  assert.equal(Object.hasOwn(x.fetches()[0].fetchOptions, 'transcriptBatchToken'), false);
  assert.equal(x.fetches()[0].fetchOptions.headers['X-Probe'], 'read-only');
});

test('unknown project fence does not block a different project write or leak a foreign token', async () => {
  const x = setup(); await unknown(x); installActualApi(x);
  await x.c.api('/api/projects/another_project/settings', { method: 'PATCH', body: '{}', transcriptBatchToken: x.c.transcriptBatchOwner() });
  assert.equal(x.fetches().length, 1); assert.equal(Object.hasOwn(x.fetches()[0].fetchOptions, 'transcriptBatchToken'), false);
});

for (const [name, guard, code] of [['copy', 'projectCopySourceBusy', 'project_copy_active'], ['preview repair', 'previewRepairBusy', 'preview_repair_active']])
  test(`the exact batch token never bypasses the existing ${name} write fence`, async () => {
    const x = setup(); installActualApi(x); const d = deferred(); x.fetchTransport = () => d.promise;
    const pending = x.run(), owner = x.c.transcriptBatchOwner(); x.c[guard] = () => true;
    await assert.rejects(x.c.api(`/api/projects/${x.before.id}/manual/edit`, { method: 'POST', body: owner.protocol.snapshot().binding.body, transcriptBatchToken: owner }), error => error.code === code);
    assert.equal(x.fetches().length, 1); x.c[guard] = () => false;
    d.resolve({ ok: true, headers: { get: () => 'application/json' }, json: async () => ({ project: x.accepted() }) });
    await pending;
  });

test('alignment stylesheet and its approved cache remain unchanged', () => {
  const crypto = require('node:crypto');
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync('web/studio-workbench.css')).digest('hex'), '6e9c8497d286cd2993bfc6b64c1f20d761d5c44f0500d7dc26c2d87057491833');
  assert.match(fs.readFileSync('web/index.html', 'utf8'), /studio-workbench\.css\?v=20261117-urgent-alignment2/);
});

function installActualTabRecovery(x) {
  x.c.retainedEditStatus = () => null;
  x.c.t = value => value;
  x.c.setAdvanced = value => x.calls.push({ advanced: value });
  x.c.selectAdvancedTab = pane => { x.pane = pane; x.calls.push({ selectedPane: pane }); };
  const query = x.c.$;
  x.c.$ = (selector, root) => root ? query(selector, root) : null;
  vm.runInContext(shippedFunction('openStudioTab') + '\n' + shippedFunction('activateSaveStatus'), x.c);
}

test('actual header Check reveals own unknown batch despite its own foreground fence, without save or seek', async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  const buffers = [...x.state.transcriptBuffers.values()];
  assert.equal(x.c.foregroundBusy(), true);
  assert.equal(x.c.openStudioTab('transcript'), false, 'ordinary tab helper still honors foreground busy');
  await x.c.activateSaveStatus();
  assert.equal(x.pane, 'transcript');
  assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 0);
  assert.equal(x.calls.some(row => row?.seek || row?.range), false);
  assert.deepEqual([...x.state.transcriptBuffers.values()], buffers);
  assert.equal(x.elements.transcriptEditText.readOnly, true);
});

for (const blocker of ['manualEditBusy', 'activeJob']) test(`actual header recovery does not bypass unrelated ${blocker}`, async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  x.state[blocker] = blocker === 'activeJob' ? { id: 'other-job' } : true;
  await x.c.activateSaveStatus();
  assert.equal(x.pane, 'audio'); assert.equal(x.posts().length, 1);
  assert.equal(x.calls.some(row => row?.selectedPane), false);
  assert.equal(x.state.transcriptBuffers.size, 2);
});

test('actual header recovery remains unavailable while the batch Load is pending', async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  x.c.transcriptBatchOwner().loading = true;
  await x.c.activateSaveStatus();
  assert.equal(x.pane, 'audio'); assert.equal(x.posts().length, 1);
  assert.equal(x.calls.some(row => row?.selectedPane), false);
});

test('actual tab recovery rejects a foreign owner and an otherwise valid owner on another tab', async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  const owner = x.c.transcriptBatchOwner();
  assert.equal(x.c.openStudioTab('transcript', { transcriptRecoveryOwner: { ...owner } }), false);
  assert.equal(x.c.openStudioTab('framing', { transcriptRecoveryOwner: owner }), false);
  assert.equal(x.pane, 'audio'); assert.equal(x.calls.some(row => row?.selectedPane), false);
});

test('actual tab recovery rejects a stale owner replaced in the current project map', async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  const owner = x.c.transcriptBatchOwner(); x.state.transcriptBatches.set(x.before.id, { ...owner });
  assert.equal(x.c.openStudioTab('transcript', { transcriptRecoveryOwner: owner }), false);
  assert.equal(x.pane, 'audio'); assert.equal(x.calls.some(row => row?.selectedPane), false);
});

test('actual tab recovery cannot bypass the active transcript save flag', async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  x.state.transcriptSaving = true;
  assert.equal(x.c.openStudioTab('transcript', { transcriptRecoveryOwner: x.c.transcriptBatchOwner() }), false);
  assert.equal(x.pane, 'audio'); assert.equal(x.calls.some(row => row?.selectedPane), false);
});

test('actual tab recovery rechecks current view after its synchronous pause callback', async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  x.c.pauseAllMedia = () => { x.calls.push('pause'); x.state.projectViewToken++; };
  assert.equal(x.c.openStudioTab('transcript', { transcriptRecoveryOwner: x.c.transcriptBatchOwner() }), false);
  assert.equal(x.pane, 'audio'); assert.equal(x.calls.some(row => row?.selectedPane), false);
  assert.equal(x.state.transcriptBuffers.size, 2); assert.equal(x.posts().length, 1);
});

for (const callback of ['setAdvanced', 'selectAdvancedTab']) test(`actual tab recovery refuses newer ownership from ${callback}`, async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  x.c[callback] = () => { x.state.projectViewToken++; x.pane = 'settings'; };
  assert.equal(x.c.openStudioTab('transcript', { transcriptRecoveryOwner: x.c.transcriptBatchOwner() }), false);
  assert.equal(x.pane, 'settings'); assert.equal(x.state.transcriptBuffers.size, 2);
  assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 0);
});

test('actual tab recovery returns refusal after a focus callback replaces the view', async () => {
  const x = setup(); await unknown(x); installActualTabRecovery(x); x.pane = 'audio';
  x.c.$ = () => ({ focus: () => { x.state.projectViewToken++; x.pane = 'settings'; } });
  assert.equal(x.c.openStudioTab('transcript', { transcriptRecoveryOwner: x.c.transcriptBatchOwner() }), false);
  assert.equal(x.pane, 'settings'); assert.equal(x.state.transcriptBuffers.size, 2);
  assert.equal(x.posts().length, 1); assert.equal(x.gets().length, 0);
});
