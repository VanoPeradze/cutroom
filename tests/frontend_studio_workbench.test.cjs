const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.js'), 'utf8').replace(/^export /gm, '');
const context = vm.createContext({});
vm.runInContext(source + '\nglobalThis.initWorkbench = initWorkbench;', context);

class Element {
  constructor(tag, doc) {
    this.tagName = tag; this.doc = doc; this.children = []; this.attrs = new Map(); this.events = new Map();
    this.dataset = {}; this.classes = new Set(); this.hidden = false; this.inert = false; this.open = false; this.disabled = false; this.scrollTop = 0;
    this.classList = { add: v => this.classes.add(v), remove: v => this.classes.delete(v), contains: v => this.classes.has(v), toggle: (v, on) => on ? this.classes.add(v) : this.classes.delete(v) };
  }
  set id(value) { this._id = value; this.doc.ids.set(value, this); }
  get id() { return this._id || ''; }
  set className(value) { this.classes = new Set(value.split(' ')); }
  set textContent(value) { this.text = value; }
  get textContent() { return [this.text || '', ...this.children.map(e => e.textContent)].join(''); }
  get parentNode() { return this.parentElement; }
  get firstChild() { return this.children[0] || null; }
  get nextSibling() { return this.parentElement?.children[this.parentElement.children.indexOf(this) + 1] || null; }
  append(...items) { for (const el of items) { el.remove(); this.children.push(el); el.parentElement = this; } }
  insertBefore(el, next) { el.remove(); const index = this.children.indexOf(next); if (index < 0) this.append(el); else { this.children.splice(index, 0, el); el.parentElement = this; } }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(e => e !== this); this.parentElement = null; }
  setAttribute(key, value) { this.attrs.set(key, String(value)); }
  getAttribute(key) { return this.attrs.get(key) ?? null; }
  removeAttribute(key) { this.attrs.delete(key); }
  addEventListener(type, callback) { this.events.set(type, [...(this.events.get(type) || []), callback]); }
  removeEventListener(type, callback) { this.events.set(type, (this.events.get(type) || []).filter(fn => fn !== callback)); }
  emit(type, event = {}) { for (const fn of this.events.get(type) || []) fn(event); }
  click() { if (!this.disabled) this.emit('click', { target: this }); }
  focus() { this.doc.activeElement = this; }
  descendants() { return this.children.flatMap(el => [el, ...el.descendants()]); }
  contains(el) { return this === el || this.descendants().includes(el); }
  querySelector(selector) { return this.descendants().find(el => selector.startsWith('.') && el.classes.has(selector.slice(1))) || null; }
  querySelectorAll(selector) { return selector === ':scope > .tab-panel' ? this.children.filter(el => el.classes.has('tab-panel')) : []; }
  closest(selector) { return selector === '[data-tab]' && this.dataset.tab ? this : this.parentElement?.closest(selector) || null; }
}
function harness({ blocked = false, stored = null } = {}) {
  const doc = { ids: new Map(), activeElement: null, createElement(tag) { return new Element(tag, this); }, getElementById(id) { return this.ids.get(id) || null; } };
  const node = (id, cls = '', tag = 'div') => { const el = doc.createElement(tag); el.id = id; el.className = cls; return el; };
  const panel = node('advancedPanel'), header = node('header', 'studio-header'), inspector = node('studioInspector'), shelf = node('studioShelf');
  const toolsToggle = node('workspaceToolsToggle'), tools = node('studioPanelTimeline', 'tab-panel'), otherTools = node('studioPanelMedia', 'tab-panel');
  const suggestions = node('suggestions', 'editor-ai-suggestions', 'details'), dock = node('studioDirectorDock'), after = node('after');
  const nav = node('nav', 'advanced-tabs'), edit = node('studioTabTimeline'); edit.dataset.tab = 'timeline'; nav.append(edit);
  const aiConnection = node('aiConnectionButton'), transcription = node('transcriptionButton');
  header.append(toolsToggle); tools.append(suggestions, after); suggestions.append(dock); inspector.append(tools, otherTools); panel.append(header, inspector, shelf, nav);
  const store = new Map(stored === null ? [] : [['cutroom-media-pool-visible-v1', stored]]), writes = [], observers = [], events = [], calls = [];
  aiConnection.addEventListener('click', () => calls.push('connection')); transcription.addEventListener('click', () => calls.push('transcription'));
  const win = {
    localStorage: { getItem(key) { if (blocked) throw Error('blocked'); return store.get(key) ?? null; }, setItem(key, value) { if (blocked) throw Error('blocked'); writes.push([key, value]); store.set(key, value); } },
    Event: class { constructor(type) { this.type = type; } }, dispatchEvent: event => events.push(event.type),
    MutationObserver: class { constructor(callback) { this.callback = callback; observers.push(this); } observe(target, options) { this.target = target; this.options = options; } disconnect() { this.disconnected = true; } },
  };
  const init = () => context.initWorkbench({ document: doc, window: win });
  const mutate = (target, attributeName) => observers.filter(o => o.target === target && !o.disconnected).forEach(o => o.callback([{ attributeName }]));
  return { doc, win, panel, header, inspector, shelf, tools, otherTools, suggestions, dock, after, nav, edit, aiConnection, transcription, store, writes, events, calls, observers, init, mutate, get: id => doc.getElementById(id) };
}

test('workbench is idempotent and moves the original AI dock without cloning editing controls', () => {
  const h = harness(), controller = h.init();
  assert.equal(h.init(), controller);
  assert.equal(h.get('workbenchAIPanel').children.filter(el => el === h.suggestions).length, 1);
  assert.equal(h.dock.parentElement, h.suggestions);
  assert.equal(h.suggestions.open, true);
  assert.equal(h.header.children.filter(e => e.id === 'workbenchMediaToggle').length, 1);
  assert.equal(h.get('workbenchInspectorButton').getAttribute('aria-pressed'), 'true');
  assert.deepEqual(h.writes, []);
  assert.deepEqual(h.calls, []);
});

test('AI view restores Inspector scroll and prior inert states without editing or invoking AI', () => {
  const h = harness(), controller = h.init();
  h.inspector.scrollTop = 91; h.otherTools.inert = true;
  h.tools.focus(); controller.setPane('ai');
  assert.equal(h.get('workbenchAIPanel').hidden, false);
  assert.equal(h.tools.inert, true);
  assert.equal(h.doc.activeElement, h.get('workbenchAIButton'));
  assert.equal(h.inspector.scrollTop, 0);
  h.get('workbenchAIConnection').focus(); controller.setPane('inspector');
  assert.equal(h.get('workbenchAIPanel').hidden, true);
  assert.equal(h.tools.inert, false); assert.equal(h.otherTools.inert, true);
  assert.equal(h.doc.activeElement, h.get('workbenchInspectorButton'));
  assert.equal(h.inspector.scrollTop, 91);
  h.inspector.scrollTop = 44; controller.setPane('inspector'); assert.equal(h.inspector.scrollTop, 44);
  assert.deepEqual(h.writes, []); assert.deepEqual(h.calls, []);
});

test('workspace navigation including reselecting Edit reveals tools, without stale scroll restoration', () => {
  const h = harness(), controller = h.init();
  h.inspector.scrollTop = 120; controller.setPane('ai');
  h.nav.emit('click', { target: h.edit });
  assert.equal(h.inspector.dataset.workbenchPane, 'inspector'); assert.equal(h.inspector.scrollTop, 0);
  controller.setPane('ai'); h.mutate(h.panel, 'data-workspace');
  assert.equal(h.inspector.dataset.workbenchPane, 'inspector');
  controller.setPane('ai'); h.panel.hidden = true; h.mutate(h.panel, 'hidden');
  assert.equal(h.inspector.dataset.workbenchPane, 'inspector');
});

test('media-pool visibility is display-only, focus-safe, persistent and storage-denial tolerant', () => {
  for (const blocked of [false, true]) {
    const h = harness({ blocked }), controller = h.init(); h.shelf.focus();
    controller.setMediaPoolVisible(false);
    assert.equal(h.shelf.inert, true); assert.equal(h.shelf.getAttribute('aria-hidden'), 'true');
    assert.equal(h.doc.activeElement, h.get('workbenchMediaToggle'));
    assert.equal(h.panel.classList.contains('media-pool-collapsed'), true);
    assert.equal(h.get('workbenchMediaToggle').getAttribute('aria-expanded'), 'false');
    controller.setMediaPoolVisible(true);
    assert.equal(h.shelf.inert, false); assert.equal(h.get('workbenchMediaToggle').getAttribute('aria-expanded'), 'true');
    assert.ok(h.events.every(e => e === 'resize')); assert.deepEqual(h.calls, []);
    assert.ok(h.writes.every(([key]) => key === 'cutroom-media-pool-visible-v1'));
  }
  const h = harness({ stored: 'false' }); h.init(); assert.equal(h.shelf.inert, true); assert.deepEqual(h.writes, []);
});

test('AI entry points proxy original controls and track disabled states', () => {
  const h = harness(); h.init();
  h.get('workbenchAIConnection').click(); h.get('workbenchTranscription').click();
  assert.deepEqual(h.calls, ['connection', 'transcription']);
  h.aiConnection.disabled = true; h.mutate(h.aiConnection, 'disabled');
  assert.equal(h.get('workbenchAIConnection').disabled, true); h.get('workbenchAIConnection').click();
  assert.deepEqual(h.calls, ['connection', 'transcription']);
  h.aiConnection.disabled = false; h.mutate(h.aiConnection, 'disabled'); assert.equal(h.get('workbenchAIConnection').disabled, false);
});

test('destroy restores original suggestion location and removes listeners and display state', () => {
  const h = harness(), controller = h.init(); controller.setPane('ai'); controller.setMediaPoolVisible(false);
  controller.destroy();
  assert.equal(h.suggestions.parentElement, h.tools); assert.equal(h.suggestions.nextSibling, h.after);
  assert.equal(h.suggestions.open, false); assert.equal(h.tools.inert, false); assert.equal(h.shelf.inert, false);
  assert.equal(h.shelf.getAttribute('aria-hidden'), null); assert.equal(h.panel.workbenchController, undefined);
  assert.equal(h.panel.classList.contains('workbench-ready'), false); assert.equal(h.inspector.dataset.workbenchPane, undefined);
  assert.ok(h.observers.every(o => o.disconnected));
  h.get('workbenchAIConnection').click(); assert.deepEqual(h.calls, []);
});

test('workbench assets load after the established editor without replacing export or media logic', () => {
  const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
  assert.ok(html.indexOf('/assets/studio-workbench.css') > html.indexOf('/assets/studio-finish.css'));
  assert.ok(html.indexOf('/assets/studio-workbench.js') > html.indexOf('/assets/app.js'));
  assert.doesNotMatch(source, /\bfetch\s*\(|\.play\s*\(|\.pause\s*\(|\.load\s*\(|confirmExport|renderButton/);
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /forced-colors:active/);
  assert.match(css, /max-width:899px/);
  // This exact presence query sizes only the workspace row, never the stage.
  // All other stage/viewport selectors and rendering filters remain forbidden.
  const landscapePresence = ':has(#studioPreviewDock #previewStage[data-aspect="16:9"])';
  assert.equal(css.split(landscapePresence).length, 2);
  assert.doesNotMatch(css.replace(landscapePresence, ''), /#previewStage|preview-viewport|filter:.*(?:blur|brightness)|url\(['"]?https?:/);
});

test('native inspector reveals reserve the sticky switch without offsetting the static compact header', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /#studioInspector\s*\{\s*scroll-padding-block-start:48px/);
  assert.match(css, /@media \(max-width:899px\),\(max-height:539px\)\s*\{\s*#studioInspector\s*\{\s*scroll-padding-block-start:0/);
});

test('blocked native layer actions look disabled without hiding their reason or changing the layout', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /\.media-actions button:disabled\s*\{\s*opacity:\.5;\s*cursor:not-allowed;/);
  assert.match(css, /\[data-trim-start\]:disabled,[\s\S]*?\[data-trim-end\]:disabled\s*\{\s*cursor:not-allowed;/);
});

test('Slip has a real compact toolbar icon while retaining its native accessible button name', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /\.timeline-tools \[data-timeline-tool=slip\]\s*\{\s*--chrome-icon:url/);
  assert.match(css, /M4 4v16M20 4v16/);
});

test('blocked custom-text duplicate keeps its native disabled state without implying a running save', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /\.text-actions \[data-duplicate\]:disabled\s*\{\s*cursor:not-allowed;/);
});


test('whole-layer Placement actions stay compact, distinct from source Slip and truthfully disabled', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /\.layer-move-controls :is\(\.media-actions,\.text-actions\)\s*\{\s*display:grid;\s*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /\.layer-move-controls \[data-move=playhead\]\s*\{\s*grid-column:1\/-1/);
  assert.match(css, /\.layer-move-controls \[data-move\]:disabled\s*\{\s*opacity:\.5;\s*cursor:not-allowed/);
  assert.match(css, /:is\(\.media-inspector,\.text-inspector\) input\[data-scrub-step\]\s*\{\s*appearance:textfield/);
  assert.match(css, /input\[data-scrub-step\]::-(?:webkit)-outer-spin-button\s*\{\s*-webkit-appearance:none/);

});


test('visual stacking is a compact inspector disclosure and custom text stays above every supported media overlay', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /\.media-stack-controls \.media-actions\s*\{\s*display:grid;\s*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /\.media-stack-controls \[data-stack\]\s*\{\s*min-width:0;\s*white-space:normal/);
  assert.match(css, /\.media-stack-controls \[data-stack-status\]\s*\{[\s\S]*?color:var\(--muted\)/);
  assert.match(css, /\.studio-workspace \.custom-text-layer\s*\{\s*z-index:240;/);
  const maximum = Number(fs.readFileSync(path.join(__dirname, '../cutroom/media_library.py'), 'utf8').match(/MAX_MEDIA_CLIPS\s*=\s*(\d+)/)[1]);
  assert.ok(240 > 3 + maximum && 240 < 250 && 240 < 260, 'custom text must stay above supported media, below captions and viewer controls');
});
