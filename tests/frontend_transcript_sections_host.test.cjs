// Actual Transcript sections host, form and admission functions. The shipped
// pure planner/navigation adapter and retained-draft helper run in a small DOM
// harness. Native select activation, media decoding and layout remain browser QA.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('web/app.js', 'utf8');
const html = fs.readFileSync('web/index.html', 'utf8');
const start = source.indexOf('function initializeTranscriptSections(');
const end = source.indexOf('function transcriptBatchOwner(', start);
assert.ok(start >= 0 && end > start, 'The actual sections host block must exist');
const host = source.slice(start, end);
function shippedFunction(name) {
  const at = source.indexOf(`function ${name}(`);
  assert.ok(at >= 0, `Missing shipped ${name}`);
  const lineEnd = source.indexOf('\n', at);
  const stop = source.slice(at, lineEnd).trimEnd().endsWith('}') ? lineEnd : source.indexOf('\n}', at) + 2;
  return source.slice(source.slice(at - 6, at) === 'async ' ? at - 6 : at, stop);
}
const actualFunctions = [
  'transcriptBatchOwner', 'transcriptBatchIssue', 'transcriptBatchOtherIssue',
  'transcriptBufferProvenance', 'transcriptDraftReview', 'selectedTranscriptRecoveryDraft',
  'selectedTranscriptSegment', 'transcriptBufferKey', 'pendingTranscriptBuffers',
  'bufferTranscriptText', 'renderTranscriptDetail', 'transcriptBatchStatus',
  'explicitPendingDraft', 'workspaceResizeIssue', 'setPreviewMode', 'setManualSelection',
].map(shippedFunction).join('\n');
const timelineSource = fs.readFileSync('web/timeline.js', 'utf8');
const cutAt = timelineSource.indexOf('  cancelPendingCut() {');
assert.ok(cutAt >= 0);
const cancelCut = vm.runInNewContext(`({${timelineSource.slice(cutAt, timelineSource.indexOf('\n  }', cutAt) + 4)}}).cancelPendingCut`);
const plain = value => JSON.parse(JSON.stringify(value));

class Element {
  constructor(tag, document) {
    this.tag = tag; this.document = document; this.children = []; this.listeners = new Map();
    this.dataset = {}; this.attributes = {}; this.value = ''; this.textContent = '';
    this.hidden = false; this.disabled = false; this.readOnly = false; this.isConnected = true;
    this.replaceCount = 0; this.className = '';
    const values = new Set();
    this.classList = { contains: x => values.has(x), toggle(x, force) {
      const yes = force ?? !values.has(x); yes ? values.add(x) : values.delete(x); return yes;
    } };
  }
  append(...children) { for (const child of children) { child.parentElement = this; this.children.push(child); } }
  replaceChildren(...children) { this.replaceCount++; this.children = []; this.append(...children); }
  insertBefore(child, before) { const i = this.children.indexOf(before); assert.ok(i >= 0); child.parentElement = this; this.children.splice(i, 0, child); }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  querySelector(selector) {
    return this.children.find(child => selector.startsWith('.') ? child.className.split(' ').includes(selector.slice(1)) : child.tag === selector)
      || this.children.map(child => child.querySelector(selector)).find(Boolean) || null;
  }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  hasAttribute(key) { return key === 'hidden' ? this.hidden : key === 'inert' ? Boolean(this.inert) : Object.hasOwn(this.attributes, key); }
  closest(selector) {
    if (selector.split(',').some(part => /^\[(hidden|inert)\]$/.test(part.trim()) && this.hasAttribute(part.trim().slice(1, -1)))) return this;
    return this.parentElement?.closest(selector) || null;
  }
  addEventListener(type, listener) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(listener); }
  dispatch(type, values = {}) {
    const event = { target: this, defaultPrevented: false, propagationStopped: false,
      preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.propagationStopped = true; }, ...values };
    for (const listener of this.listeners.get(type) || []) listener(event);
    return event;
  }
  focus() { if (!this.disabled) this.document.activeElement = this; }
  getClientRects() {
    if (this.rects) return this.rects;
    return this.hidden || !this.isConnected || this.parentElement && !this.parentElement.getClientRects().length ? [] : [{}];
  }
}

function fixture() {
  return { id: 'project_0123456789ab', revision: 7, name: 'Saved speech', settings: { fps: 30 },
    sources: { A: { duration: 8, has_audio: true, generation: 'sourceA', path: 'syntheticA.mp4' },
      B: { duration: 8, has_audio: true, generation: 'sourceB', path: 'syntheticB.mp4' } },
    analysis: { audio_source: 'A', audio_timeline_offset: 0, transcript: { model: 'synthetic', language: 'mixed',
      segments: [{ id: 's1', start: .1, end: .34, text: 'Speech \u05e9\u05dc\u05d5\u05dd' },
        { id: 's2', start: 1, end: 1.5, text: 'Another saved line' }] } },
    manual: { source_mixer: { audio_slot: 'A' }, history: { undo_count: 3, redo_count: 1 } },
    draft: { cuts: [], edited_at: 'unchanged' },
    editor_sequence: { active: false, duration: 24, sequence: { version: 1, duration: 24, camera_plan: [] },
      source_tracks: { A: [0, 8, 16].map((start, i) => ({ id: `A:context:${i}`, start, end: start + 8, source_start: 0 })), B: [] } } };
}

function setup({ mutate = () => {}, initialize = true } = {}) {
  const calls = [], document = new Element('document');
  document.body = new Element('body', document); document.documentElement = new Element('html', document);
  document.activeElement = document.body;
  const elements = Object.fromEntries([
    'transcriptEditForm', 'transcriptEditText', 'transcriptEditTime', 'transcriptEditStatus',
    'transcriptSave', 'transcriptDiscard', 'transcriptSaveAll', 'transcriptPrevious', 'transcriptNext',
    'transcriptSearch', 'transcriptFilter', 'advancedPanel',
  ].map(id => { const e = new Element(id === 'transcriptEditText' ? 'textarea' : 'div', document); e.id = id; return [id, e]; }));
  const nodes = Object.fromEntries(['transcriptSections', 'transcriptSectionChoice', 'transcriptSectionGo', 'transcriptSectionsStatus']
    .map(id => { const e = new Element(id.includes('Choice') ? 'select' : id.includes('Go') ? 'button' : 'div', document); e.id = id; return [id, e]; }));
  const root = nodes.transcriptSections; root.append(nodes.transcriptSectionChoice, nodes.transcriptSectionGo, nodes.transcriptSectionsStatus);
  elements.transcriptEditForm.append(root, elements.transcriptEditText, elements.transcriptSave, elements.transcriptDiscard, elements.transcriptSaveAll);
  document.createElement = tag => new Element(tag, document);
  document.getElementById = id => nodes[id] || elements[id] || null;
  elements.transcriptFilter.value = 'all';
  const project = fixture(); mutate(project);
  const state = { project, projectViewToken: 3, studio: { open: true }, preview: { mode: 'edit', playing: true },
    transcriptActive: { projectId: project.id, id: 's1' }, transcriptRecoveryActive: null,
    transcriptBuffers: new Map(), transcriptBatches: new Map(), transcriptReviewBuffers: new WeakSet(),
    saveQueues: new Map(), activeUploads: new Set(), jobStartLocks: new Set(),
    mediaStudio: { pending: new Map(), selected: 'media-kept', shotReview: { pending: false, markIn: 1.2, markOut: 2.3 } },
    textStudio: { pending: new Map(), dirty: () => false }, chromaStudio: {}, embeddedEditor: {},
    sourceReview: { marks: { in: 2, out: 4 }, timeline: {} },
    manualSelection: { start: 2, end: 3 }, captionSelection: 'caption-kept', inspectorSelectionEpoch: 9,
    timeline: { playhead: 4.25, cutAnchor: null, mediaSelection: 'media-kept', selection: { start: 2, end: 3 }, selectionIsRange: true },
  };
  const x = { calls, document, elements, nodes, state, project, pane: 'transcript', dialog: null,
    pendingChroma: [], trackUnfinished: false, savedTrackIssue: '', retainedIssue: '', repairBusy: false, copyBusy: false };
  document.querySelector = selector => selector === 'dialog[open]' ? x.dialog
    : selector.includes('advanced-tabs') ? { dataset: { tab: x.pane } } : null;
  state.timeline.cancelPendingCut = function() { calls.push('cancelCut'); const result = cancelCut.call(this); x.onCancel?.(); return result; };
  state.timeline.onToolStateChange = () => { calls.push('tool-state'); x.onToolState?.(); };
  state.timeline.scheduleDraw = () => calls.push('draw');
  const c = { state, elements, document, structuredClone, TextEncoder, console,
    formatTime: n => Number(n).toFixed(3),
    pendingChromaDrafts: () => { x.onChromaRead?.(); return x.pendingChroma; },
    trackLevelUnfinished: () => x.trackUnfinished,
    savedLayerTrackIssue: () => x.savedTrackIssue, retainedEditIssue: () => x.retainedIssue,
    previewRepairBusy: () => x.repairBusy, projectCopySourceBusy: () => x.copyBusy,
    liveEmbeddedCameraRequest: () => x.liveEmbedded || null,
    renderProjectSaveState: () => { calls.push('save-status'); state.transcriptSectionsUI?.refresh(); },
    transcriptTimelineMapping: () => ({ ranges: [], independent: true }), transcriptMappingLabel: () => 'Saved mapping label',
    previewTimelineTime: () => state.timeline.playhead, renderPreviewAvailability: () => calls.push('preview-availability'),
    hydrateSourceMixerLayout: () => calls.push('source-layout'), renderManualControls: () => calls.push('manual-controls'),
    renderSourceMixer: () => calls.push('source-mixer'), highlightTranscriptSelection: () => calls.push('highlight'),
    pauseAllMedia: () => { calls.push('pause'); state.preview.playing = false; x.onPause?.(); },
    seekSourcePreview: time => { calls.push({ seek: time }); state.timeline.playhead = time; x.onSeek?.(); },
    saveTranscriptBuffers: all => { calls.push({ save: all }); return 'save-result'; },
  };
  vm.createContext(c);
  for (const path of ['web/transcript-batch.js', 'web/transcript-sections.js']) {
    const text = fs.readFileSync(path, 'utf8');
    const exports = [...text.matchAll(/^export (?:function|const) (\w+)/gm)].map(m => m[1]);
    Object.assign(c, vm.runInContext(`(function(){${text.replace(/^export /gm, '')}\nreturn {${exports.join(',')}};})()`, c));
  }
  c.navigateTranscriptSection = c.navigateSection;
  vm.runInContext(host + '\n' + actualFunctions, c);
  x.c = c;
  x.buffer = id => {
    const row = state.project.analysis.transcript.segments.find(row => String(row.id) === String(id));
    const b = { projectId: state.project.id, id: row.id, base: row.text, text: `Corrected ${row.text}`,
      start: row.start, end: row.end, provenance: c.transcriptBufferProvenance() };
    state.transcriptBuffers.set(`${state.project.id}:${id}`, b); return b;
  };
  x.choose = (index = 1) => { const ui = state.transcriptSectionsUI; ui.choice.value = ui.plan.sections[index].key; ui.choice.dispatch('change'); return ui; };
  x.effects = () => calls.filter(call => ['cancelCut', 'pause'].includes(call) || call?.seek !== undefined || call?.save !== undefined);
  if (initialize) { c.initializeTranscriptSections(); c.renderTranscriptSections(); calls.length = 0; }
  return x;
}

test('initial rendering is inert and repeated source clips get exact separate options', () => {
  const x = setup(), ui = x.state.transcriptSectionsUI;
  assert.equal(ui.plan.ok, true); assert.equal(ui.plan.sections.length, 3);
  assert.equal(ui.choice.children.length, 4); assert.equal(ui.key, ''); assert.equal(ui.go.disabled, true);
  assert.deepEqual(ui.choice.children.slice(1).map(n => n.textContent), [0, 8, 16].map((t, i) => `${i + 1}. Edit ${(t + .1).toFixed(3)} - ${(t + .34).toFixed(3)} | Source A 0.100 - 0.340`));
  assert.match(ui.status.textContent, /Selected range remains 2\.000 - 3\.000/);
  assert.deepEqual(x.effects(), []);
});

test('choosing an option is local only, including during normal Program playback', () => {
  const x = setup(), range = x.state.manualSelection; const ui = x.choose(2);
  assert.equal(ui.key, ui.plan.sections[2].key); assert.equal(ui.go.disabled, false);
  assert.equal(x.state.preview.playing, true); assert.equal(x.state.manualSelection, range);
  assert.match(ui.status.textContent, /Section 3: edit 16\.100000/); assert.match(ui.status.title, /A:context:2/);
  assert.deepEqual(x.effects(), []);
});

test('single section may preselect but never navigates without explicit Go', () => {
  const x = setup({ mutate: p => p.editor_sequence.source_tracks.A.splice(1) });
  assert.equal(x.state.transcriptSectionsUI.key, x.state.transcriptSectionsUI.plan.sections[0].key);
  assert.equal(x.state.transcriptSectionsUI.go.disabled, false); assert.deepEqual(x.effects(), []);
});

test('partial sections are clearly labelled and never merged into a gap or full-line claim', () => {
  const x = setup({ mutate: p => {
    Object.assign(p.analysis.transcript.segments[0], { start: 1, end: 4 });
    p.editor_sequence.source_tracks.A = [{ id: 'left', start: 0, end: .5, source_start: 1 }, { id: 'right', start: 10, end: 10.5, source_start: 3.5 }];
  } });
  const ui = x.choose(1); assert.equal(ui.plan.sections.length, 2);
  assert.match(ui.choice.children[2].textContent, /partial line/); assert.match(ui.status.textContent, /partial line/);
  assert.equal(x.c.goToTranscriptSection(), true); assert.equal(x.state.timeline.playhead, 10);
});

test('successful Go cancels only the armed cut, pauses once and seeks; buffers, nodes and selections remain exact', () => {
  const x = setup(), b1 = x.buffer('s1'), b2 = x.buffer('s2'), saved = JSON.stringify(x.project);
  const range = x.state.manualSelection, timelineRange = x.state.timeline.selection, sourceReview = x.state.sourceReview, shotReview = x.state.mediaStudio.shotReview;
  x.state.timeline.cutAnchor = 6; const ui = x.choose(1); ui.go.focus();
  assert.equal(x.c.goToTranscriptSection(), true);
  assert.deepEqual(x.effects(), ['cancelCut', 'pause', { seek: 8.1 }]);
  assert.equal(x.state.timeline.cutAnchor, null); assert.equal(x.state.preview.playing, false); assert.equal(x.state.preview.mode, 'edit');
  assert.equal(x.state.manualSelection, range); assert.equal(x.state.timeline.selection, timelineRange); assert.equal(x.state.timeline.selectionIsRange, true);
  assert.equal(x.state.mediaStudio.selected, 'media-kept'); assert.equal(x.state.captionSelection, 'caption-kept');
  assert.equal(x.state.sourceReview, sourceReview); assert.equal(x.state.mediaStudio.shotReview, shotReview);
  assert.equal(x.state.transcriptBuffers.get(`${x.project.id}:s1`), b1); assert.equal(x.state.transcriptBuffers.get(`${x.project.id}:s2`), b2);
  assert.equal(JSON.stringify(x.project), saved); assert.equal(x.document.activeElement, ui.go);
  assert.match(ui.status.textContent, /Playhead moved.*Playback is paused.*Selected range remains/);
});

test('actual typing/detail path preserves option nodes, choice, focus and all unrelated buffers', () => {
  const x = setup(), other = x.buffer('s2'), ui = x.choose(2), children = [...ui.choice.children], count = ui.choice.replaceCount;
  const before = JSON.stringify(x.project); x.elements.transcriptEditText.focus();
  for (const text of ['First draft', 'Second draft \u05e9\u05dc\u05d5\u05dd', 'Third draft']) {
    x.elements.transcriptEditText.value = text; x.c.bufferTranscriptText();
    assert.equal(ui.key, ui.plan.sections[2].key); assert.equal(ui.choice.replaceCount, count);
    assert.deepEqual(ui.choice.children, children); assert.equal(x.document.activeElement, x.elements.transcriptEditText);
    assert.equal(x.state.transcriptBuffers.get(`${x.project.id}:s1`).text, text); assert.equal(ui.go.disabled, false);
  }
  assert.equal(x.state.transcriptBuffers.get(`${x.project.id}:s2`), other); assert.equal(JSON.stringify(x.project), before);
  assert.deepEqual(x.effects(), []);
});

test('an unchanged render while select has focus preserves its exact native option objects', () => {
  const x = setup(), ui = x.choose(), children = [...ui.choice.children], count = ui.choice.replaceCount;
  ui.choice.focus(); x.c.renderTranscriptSections();
  assert.deepEqual(ui.choice.children, children); assert.equal(ui.choice.replaceCount, count);
  assert.equal(x.document.activeElement, ui.choice); assert.equal(ui.choice.value, ui.key);
});

test('B section uses its analyzed audio offset and exact edited start, not Full source A or current sync', () => {
  const x = setup({ mutate: p => {
    p.analysis.audio_source = 'B'; p.analysis.audio_timeline_offset = 5; p.manual.source_mixer = { audio_slot: 'B', sync_offset: -17 };
    Object.assign(p.analysis.transcript.segments[0], { start: 10, end: 13 });
    p.editor_sequence.source_tracks.B = [{ id: 'B:section', start: 12, end: 13, source_start: 6, video_speed: .25 }];
  } });
  assert.equal(x.c.goToTranscriptSection(), true); assert.deepEqual(x.effects(), ['cancelCut', 'pause', { seek: 12 }]);
});

test('tiny positive section navigates without manufacturing a Range or rounding the seek', () => {
  const x = setup({ mutate: p => Object.assign(p.analysis.transcript.segments[0], { start: .100000001, end: .100000002 }) });
  x.choose(0); assert.equal(x.c.goToTranscriptSection(), true); assert.equal(x.state.timeline.playhead, .100000001);
  assert.deepEqual(x.state.manualSelection, { start: 2, end: 3 });
});

for (const [name, mutate] of Object.entries({
  'empty lane': p => { p.editor_sequence.source_tracks.A = []; },
  'missing projection': p => { delete p.editor_sequence; },
  'ambiguous line': p => { p.analysis.transcript.segments.push({ ...p.analysis.transcript.segments[0] }); },
  'changed selected source': p => { p.manual.source_mixer.audio_slot = 'B'; },
})) test(`unavailable ${name} explains the refusal and never navigates`, () => {
  const x = setup({ mutate }), ui = x.state.transcriptSectionsUI;
  assert.equal(ui.go.disabled, true); assert.equal(ui.choice.disabled, true); assert.ok(ui.status.textContent.length > 25);
  assert.equal(x.c.goToTranscriptSection(), false); assert.deepEqual(x.effects(), []);
});

const guards = {
  'closed Studio': x => { x.state.studio.open = false; },
  'Full source mode': x => { x.state.preview.mode = 'source'; },
  'caption draft': x => { x.state.captionDirty = true; },
  'Chroma draft': x => { x.pendingChroma = [{ slot: 'A', issue: 'Apply or Discard Chroma' }]; },
  'track numeric draft': x => { x.trackUnfinished = true; },
  'track gesture': x => { x.trackUnfinished = true; x.state.mediaStudio.trackLevelGesture = {}; },
  'invalid layer track model': x => { x.savedTrackIssue = 'Invalid saved model'; },
  'retained edit': x => { x.retainedIssue = 'Resume retained edit'; },
  'transcript save': x => { x.state.transcriptSaving = true; },
  'manual edit': x => { x.state.manualEditBusy = true; },
  'manual edit promise': x => { x.state.manualEditPromise = Promise.resolve(); },
  'caption context save': x => { x.state.captionContextSave = {}; },
  'preview repair': x => { x.repairBusy = true; },
  'copy': x => { x.copyBusy = true; },
  'active job': x => { x.state.activeJob = 'job'; },
  'upload': x => { x.state.activeUploads.add('upload'); },
  'job admission': x => { x.state.jobStartLocks.add('job'); },
  'media upload': x => { x.state.mediaStudio.uploading = true; },
  'media placement': x => { x.state.mediaStudio.placing = true; },
  'import queue': x => { x.state.mediaStudio.importQueue = { running: true }; },
  'media pending': x => { x.state.mediaStudio.pending.set('clip', {}); },
  'media saving': x => { x.state.mediaStudio.saving = true; },
  'media save error': x => { x.state.mediaStudio.saveError = 'unknown'; },
  'text dirty': x => { x.state.textStudio.dirty = () => true; },
  'text pending': x => { x.state.textStudio.pending.set('text', {}); },
  'text saving': x => { x.state.textStudio.saving = true; },
  'text save error': x => { x.state.textStudio.saveError = 'unknown'; },
  'Chroma save': x => { x.state.chromaStudio.saving = true; },
  'stabilization upload': x => { x.state.stabilizationStudio = { uploading: true }; },
  'source mix save': x => { x.state.sourceMixerSavePending = true; },
  'source sync save': x => { x.state.sourceSyncPending = true; },
  'embedded request': x => { x.liveEmbedded = {}; },
  'embedded dirty': x => { x.state.embeddedEditor.dirty = true; },
  'embedded save': x => { x.state.embeddedEditor.saving = true; },
  'timeline gesture': x => { x.state.timeline.gesture = {}; },
  'timeline scrub': x => { x.state.timeline.scrubbing = true; },
  'timeline edit': x => { x.state.timeline.editPending = true; },
  'library drag': x => { x.state.timeline.libraryDragActive = true; },
  'selection pending': x => { x.state.timeline.mediaSelectionPending = true; },
  'Source opening': x => { x.state.timeline.mediaSourceOpening = true; },
  'lock pending': x => { x.state.timeline.trackLockPending = true; },
  'Source review busy': x => { x.state.sourceReview.busy = true; },
  'Source review gesture': x => { x.state.sourceReview.timeline.gesture = {}; },
  'Source review scrub': x => { x.state.sourceReview.timeline.scrubbing = true; },
  'imported Source pending': x => { x.state.mediaStudio.shotReview.pending = true; },
  'frame editor active': x => { x.state.mediaStudio.frameEditor = { active: true }; },
  'frame editor pending': x => { x.state.mediaStudio.frameEditor = { pending: true }; },
  'frame adjustment drag': x => { x.state.mediaStudio.frameEditorState = { dragging: true }; },
  'frame adjustment pending': x => { x.state.mediaStudio.frameEditorState = { pending: true }; },
  'embedded drag': x => { x.state.embeddedEditor.dragging = true; },
  'numeric scrub': x => { x.document.documentElement.classList.toggle('numeric-scrubbing', true); },
  'Source timeline': x => { x.state.timeline.sourceReview = true; },
  'pending zoom focus': x => { x.state.timeline.zoomFocusPending = {}; },
  'pending afterDraw': x => { x.state.timeline.afterDraw = () => {}; },
  'editing position loading': x => { x.state.editingPositions = { loading: true }; },
  'editing position applying': x => { x.state.editingPositions = { applying: true }; },
  'open dialog': x => { x.dialog = new Element('dialog', x.document); },
};
for (const key of ['pending', 'inFlight', 'timer', 'error']) guards[`settings queue ${key}`] = x => { x.state.saveQueues.set(x.project.id, { [key]: true }); };
for (const [name, block] of Object.entries(guards)) test(`actual admission refuses ${name} without pause, seek, save or cut cancellation`, () => {
  const x = setup(), ui = x.choose(); x.state.timeline.cutAnchor = 6; block(x); ui.refresh();
  assert.equal(ui.go.disabled, true); assert.notEqual(x.c.transcriptSectionNavigationIssue(), '');
  assert.equal(x.c.goToTranscriptSection(), false); assert.equal(x.state.timeline.cutAnchor, 6);
  assert.deepEqual(x.effects(), []);
});

for (const [name, status] of Object.entries({ unknown: { canCheck: true, issue: 'Check saved changes' }, pending: { pending: true }, loading: {}, 'saved newer': {} })) {
  test(`actual batch ${name} remains fenced even with otherwise ordinary buffers`, () => {
    const x = setup(); x.buffer('s1'); const ui = x.choose();
    x.state.transcriptBatches.set(x.project.id, { protocol: { snapshot: () => status }, loading: name === 'loading', savedReload: name === 'saved newer' ? 8 : undefined });
    ui.refresh(); assert.equal(ui.go.disabled, true); assert.equal(x.c.goToTranscriptSection(), false); assert.deepEqual(x.effects(), []);
  });
}

const reviewMutations = {
  'explicit retained identity': (x, b) => x.state.transcriptReviewBuffers.add(b),
  'different saved base': (x, b) => { b.base = 'Old saved text'; },
  'changed timing': (x, b) => { b.start += .1; },
  'unverified provenance': (x, b) => { delete b.provenance; },
  'missing saved ID': (x, b) => { b.id = 'orphan'; },
  'ambiguous saved ID': x => { x.project.analysis.transcript.segments.push({ ...x.project.analysis.transcript.segments[1] }); },
};
for (const [name, change] of Object.entries(reviewMutations)) test(`nonselected ${name} draft blocks Go and remains copyable/untouched`, () => {
  const x = setup(), b = x.buffer('s2'); change(x, b); const before = JSON.stringify(b), ui = x.choose();
  ui.refresh(); assert.equal(ui.go.disabled, true); assert.equal(x.c.goToTranscriptSection(), false);
  assert.equal(JSON.stringify(b), before); assert.equal(x.state.transcriptBuffers.get(`${x.project.id}:s2`), b); assert.deepEqual(x.effects(), []);
});

test('retained active draft has no chooser, while another project buffer does not fence this project', () => {
  const x = setup(), b = x.buffer('s1'); x.state.transcriptReviewBuffers.add(b);
  x.state.transcriptRecoveryActive = { projectId: x.project.id, key: `${x.project.id}:s1` };
  x.c.renderTranscriptSections(); assert.equal(x.state.transcriptSectionsUI.root.hidden, true);
  assert.equal(x.c.goToTranscriptSection(), false); assert.deepEqual(x.effects(), []);
  const y = setup(); y.state.transcriptBuffers.set('foreign:s', { projectId: 'foreign', id: 's', text: 'Retained elsewhere' });
  y.choose(); assert.equal(y.c.goToTranscriptSection(), true);
});

test('Full source reason names Edited video and does not silently switch modes', () => {
  const x = setup(), ui = x.choose(); x.state.preview.mode = 'source'; ui.refresh();
  assert.match(ui.status.textContent, /Choose Edited video/); assert.equal(x.c.goToTranscriptSection(), false);
  assert.equal(x.state.preview.mode, 'source'); assert.deepEqual(x.effects(), []);
});

test('actual mode switch refreshes Go immediately and preserves the section, Range and focus', () => {
  const x = setup(), ui = x.choose(2), range = x.state.manualSelection, children = [...ui.choice.children], key = ui.key;
  ui.choice.focus(); x.c.setPreviewMode('source');
  assert.equal(x.state.preview.mode, 'source'); assert.equal(ui.go.disabled, true); assert.match(ui.status.textContent, /Choose Edited video/);
  assert.equal(ui.key, key); assert.equal(x.state.manualSelection, range); assert.deepEqual(ui.choice.children, children); assert.equal(x.document.activeElement, ui.choice);
  x.c.setPreviewMode('edit');
  assert.equal(x.state.preview.mode, 'edit'); assert.equal(ui.go.disabled, false); assert.equal(ui.key, key);
  assert.equal(x.state.manualSelection, range); assert.equal(x.document.activeElement, ui.choice);
  assert.deepEqual(x.effects(), ['pause', { seek: 4.25 }, 'pause', { seek: 4.25 }]);
});

test('actual Range change updates the visible preserved-selection warning without changing section choice', () => {
  const x = setup(), ui = x.choose(1), key = ui.key;
  x.c.setManualSelection({ start: 5, end: 6 });
  assert.equal(ui.key, key); assert.match(ui.status.textContent, /Selected range remains 5\.000 - 6\.000/);
  assert.deepEqual(x.effects(), []);
  x.c.setManualSelection(null); assert.match(ui.status.textContent, /Timeline selection is unchanged/); assert.equal(ui.key, key);
});

const replacements = {
  'new project object': x => { x.state.project = structuredClone(x.project); },
  'new view': x => { x.state.projectViewToken++; },
  'new revision': x => { x.project.revision++; },
  'new active line': x => { x.state.transcriptActive.id = 's2'; },
  'source generation changed': x => { x.project.sources.A.generation = 'replacement'; },
  'canonical clock changed': x => { x.project.editor_sequence.source_tracks.A[1].source_start = .01; },
  'selected option changed': x => { x.choose(2); },
  'select value alone changed': x => { x.state.transcriptSectionsUI.choice.value = 'tampered'; },
  'new range': x => { x.state.manualSelection = { start: 5, end: 6 }; },
  'new seek': x => { x.state.timeline.playhead = 9; },
  'new inspector epoch': x => { x.state.inspectorSelectionEpoch++; },
  'new query': x => { x.elements.transcriptSearch.value = 'new search'; },
  'new filter': x => { x.elements.transcriptFilter.value = 'removed'; },
  'new pane': x => { x.pane = 'audio'; },
  'hidden region': x => { x.state.transcriptSectionsUI.root.hidden = true; },
  'detached region': x => { x.state.transcriptSectionsUI.root.isConnected = false; },
  'replaced controller': x => { x.state.transcriptSectionsUI = {}; },
  'Full source entered': x => { x.state.preview.mode = 'source'; },
  'new caption draft': x => { x.state.captionDirty = true; },
};
for (const [name, replace] of Object.entries(replacements)) test(`reentrant actual cut callback cancels navigation after ${name}`, () => {
  const x = setup(), ui = x.choose(); x.state.timeline.cutAnchor = 6; x.onToolState = () => replace(x);
  assert.equal(x.c.goToTranscriptSection(), false); assert.equal(x.state.timeline.cutAnchor, null);
  assert.equal(x.calls.includes('pause'), false); assert.equal(x.calls.some(v => v?.seek !== undefined), false);
  // A current readiness refusal or the newer choice's own local handler may
  // legitimately refresh status. Neither may claim the old Go succeeded.
  assert.doesNotMatch(ui.status.textContent, /Playhead moved to the saved section/);
});

for (const [name, replace] of Object.entries(replacements)) test(`pause callback cannot seek or replace a newer context after ${name}`, () => {
  const x = setup(); x.choose(); x.onPause = () => replace(x);
  assert.equal(x.c.goToTranscriptSection(), false); assert.equal(x.calls.filter(v => v === 'pause').length, 1);
  assert.equal(x.calls.some(v => v?.seek !== undefined || v?.save !== undefined), false);
});

test('a readiness callback that synchronously replaces project is refused before all transport effects', () => {
  const x = setup(); x.choose(); x.onChromaRead = () => { x.onChromaRead = null; x.state.project = structuredClone(x.project); };
  assert.equal(x.c.goToTranscriptSection(), false); assert.deepEqual(x.effects(), []);
});

test('new focus/context triggered by seek receives no later notice or refocus', () => {
  const x = setup(), ui = x.choose(), outsider = new Element('button', x.document), oldStatus = ui.status.textContent;
  ui.go.focus(); x.onSeek = () => { outsider.focus(); x.pane = 'audio'; };
  assert.equal(x.c.goToTranscriptSection(), false); assert.equal(x.document.activeElement, outsider);
  assert.equal(ui.status.textContent, oldStatus); assert.deepEqual(x.effects(), ['cancelCut', 'pause', { seek: 8.1 }]);
});

test('stale plan and view refuse before cut cancellation even when a button was previously enabled', () => {
  const x = setup(), ui = x.choose(); x.state.timeline.cutAnchor = 3; x.project.revision++;
  assert.equal(x.c.goToTranscriptSection(), false); assert.equal(x.state.timeline.cutAnchor, 3); assert.deepEqual(x.effects(), []);
  x.c.renderTranscriptSections(); assert.equal(ui.key, ''); assert.equal(ui.go.disabled, true);
});

test('same-ID project/view replacement resets choice rather than transferring it into a copied branch', () => {
  const x = setup(), ui = x.choose(); x.state.project = structuredClone(x.project); x.state.projectViewToken++;
  x.c.renderTranscriptSections(); assert.equal(ui.key, ''); assert.equal(ui.go.disabled, true); assert.equal(ui.choice.value, '');
});

test('changed active line resets local choice but never seeks or selects its first section', () => {
  const x = setup(), ui = x.choose(); x.state.transcriptActive.id = 's2'; x.c.renderTranscriptSections();
  assert.equal(ui.key, ''); assert.equal(ui.segmentId, 's2'); assert.deepEqual(x.effects(), []);
});

test('no Range note never invents a selection', () => {
  const x = setup(); x.state.manualSelection = null; x.choose();
  assert.equal(x.c.goToTranscriptSection(), true); assert.equal(x.state.manualSelection, null);
  assert.match(x.state.transcriptSectionsUI.status.textContent, /Timeline selection is unchanged/);
});

test('native region keyboard handler stops global transport propagation but keeps default button behavior', () => {
  const x = setup(), event = x.nodes.transcriptSections.dispatch('keydown', { key: 'Enter' });
  assert.equal(event.propagationStopped, true); assert.equal(event.defaultPrevented, false); assert.deepEqual(x.effects(), []);
});

for (const target of ['transcriptSectionChoice', 'transcriptSectionGo', 'transcriptSections']) test(`actual form-submit guard cannot save from Enter in ${target}`, () => {
  const x = setup(); x.choose(); x.nodes[target].focus(); let prevented = 0;
  assert.equal(x.document.activeElement, x.nodes[target], 'Enter originates on an enabled owned control');
  assert.equal(x.c.submitTranscriptText({ preventDefault: () => prevented++ }), false);
  assert.equal(prevented, 1); assert.deepEqual(x.effects(), []);
});

test('actual Go click listener navigates once and never invokes transcript Save text', () => {
  const x = setup(), ui = x.choose(); ui.go.focus(); ui.go.dispatch('click');
  assert.deepEqual(x.effects(), ['cancelCut', 'pause', { seek: 8.1 }]);
});

test('ordinary textarea/form save remains the existing individual-save path', () => {
  const x = setup(); x.elements.transcriptEditText.focus(); let prevented = 0;
  assert.equal(x.c.submitTranscriptText({ preventDefault: () => prevented++ }), 'save-result');
  assert.equal(prevented, 1); assert.deepEqual(x.effects(), [{ save: false }]);
});

test('missing DOM fails initialization safely and stale old listeners do nothing', () => {
  const x = setup({ initialize: false }); delete x.nodes.transcriptSectionGo; x.c.initializeTranscriptSections();
  assert.equal(x.state.transcriptSectionsUI, undefined);
  const y = setup(), ui = y.choose(); y.state.transcriptSectionsUI = null;
  ui.choice.value = 'foreign'; ui.choice.dispatch('change'); ui.go.dispatch('click'); assert.deepEqual(y.effects(), []);
});

test('DOM uses a labelled native select, explicit non-submit Go and visible selection separation inside the existing form', () => {
  const at = html.indexOf('id="transcriptEditForm"'), tail = html.indexOf('</form>', at), form = html.slice(at, tail);
  assert.ok(at >= 0 && tail > at); assert.match(form, /id="transcriptSections"/);
  assert.match(form, /<label[^>]*for="transcriptSectionChoice"/);
  assert.match(form, /<select[^>]*id="transcriptSectionChoice"/);
  assert.match(form, /<button[^>]*id="transcriptSectionGo"[^>]*type="button"|<button[^>]*type="button"[^>]*id="transcriptSectionGo"/);
  assert.match(form, /timeline selection is unchanged/i); assert.match(form, /select a Range on the timeline/i);
  assert.match(form, /data-editor-shortcuts="off"/);
  assert.match(source, /transcriptEditForm\.addEventListener\("submit", submitTranscriptText\)/);
});

test('new host has no persistence, asynchronous selection, range assignment or alternate playback route', () => {
  assert.doesNotMatch(host, /\b(?:api|fetch|flushCurrentProjectSaves|prepareInspectorSelection|applyManualEdit|saveTranscriptBatch|selectRange|playPreview|setPreviewMode)\s*\(/);
  assert.doesNotMatch(host, /state\.(?:manualSelection|markIn|captionSelection)\s*=/);
  const saveState = shippedFunction('renderProjectSaveState'), manual = shippedFunction('setManualSelection');
  assert.match(saveState, /transcriptSectionsUI\?\.refresh\?\.\(\)/);
  assert.match(manual, /transcriptSectionsUI\?\.refresh\?\.\(\)/);
});

const domReplacements = {};
for (const id of ['transcriptSectionChoice', 'transcriptSectionGo', 'transcriptSectionsStatus']) {
  domReplacements[`registered ${id} replaced`] = x => { x.nodes[id] = new Element('div', x.document); };
  domReplacements[`${id} removed but old registry retained`] = x => {
    const child = x.nodes[id], root = x.nodes.transcriptSections;
    root.children = root.children.filter(node => node !== child); child.parentElement = null;
  };
  domReplacements[`${id} disconnected`] = x => { x.nodes[id].isConnected = false; };
}
domReplacements['registered root replaced'] = x => { x.nodes.transcriptSections = new Element('div', x.document); };
for (const [name, mutate] of Object.entries(domReplacements)) {
  test(`actual DOM ownership rejects ${name} before admission`, () => {
    const x = setup(), ui = x.choose(); mutate(x);
    assert.equal(x.c.goToTranscriptSection(ui), false); assert.deepEqual(x.effects(), []);
    const key = ui.key; ui.choice.value = 'stale'; ui.choice.dispatch('change'); assert.equal(ui.key, key);
  });
  test(`readiness reentrancy cannot use ${name}`, () => {
    const x = setup(), ui = x.choose(); x.onChromaRead = () => { x.onChromaRead = null; mutate(x); };
    assert.equal(x.c.goToTranscriptSection(ui), false); assert.deepEqual(x.effects(), []);
  });
  test(`pause reentrancy cannot use ${name}`, () => {
    const x = setup(), ui = x.choose(); x.onPause = () => mutate(x);
    assert.equal(x.c.goToTranscriptSection(ui), false); assert.deepEqual(x.effects(), ['cancelCut', 'pause']);
  });
}

const invisibleStates = {
  'other active tab': x => { x.pane = 'audio'; },
  'hidden ancestor': x => { x.elements.transcriptEditForm.hidden = true; },
  'inert ancestor': x => { x.elements.transcriptEditForm.inert = true; },
  'inert owned root': x => { x.nodes.transcriptSections.inert = true; },
  'no laid-out client rect': x => { x.nodes.transcriptSections.rects = []; },
};
for (const [name, mutate] of Object.entries(invisibleStates)) {
  test(`visible Transcript ownership rejects ${name} before transport`, () => {
    const x = setup(), ui = x.choose(); mutate(x);
    assert.equal(x.c.goToTranscriptSection(ui), false); assert.deepEqual(x.effects(), []);
  });
  test(`visible Transcript ownership rejects ${name} during readiness`, () => {
    const x = setup(), ui = x.choose(); x.onChromaRead = () => { x.onChromaRead = null; mutate(x); };
    assert.equal(x.c.goToTranscriptSection(ui), false); assert.deepEqual(x.effects(), []);
  });
  test(`visible Transcript ownership rejects ${name} during pause`, () => {
    const x = setup(), ui = x.choose(); x.onPause = () => mutate(x);
    assert.equal(x.c.goToTranscriptSection(ui), false); assert.deepEqual(x.effects(), ['cancelCut', 'pause']);
  });
}

test('an offscreen but laid-out Transcript region remains navigable without scrolling or focus changes', () => {
  const x = setup(), ui = x.choose(); ui.root.rects = [{ top: 5000, bottom: 5100, left: 0, right: 300, width: 300, height: 100 }];
  ui.go.focus(); assert.equal(x.c.goToTranscriptSection(), true); assert.equal(x.document.activeElement, ui.go);
  assert.deepEqual(x.effects(), ['cancelCut', 'pause', { seek: 8.1 }]);
});
