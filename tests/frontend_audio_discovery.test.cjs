const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const web = name => fs.readFileSync(path.join(__dirname, '../web', name), 'utf8');
const appSource = web('app.js').replace(/^import .*;\r?\n/gm, '')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');
const mediaSource = web('media-studio.js').replace(/^export /gm, '');
const plain = value => JSON.parse(JSON.stringify(value));
const dataKey = key => key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());

// Only the DOM operations used by the shipped constructors and delegated
// control handlers are doubled. Moving a node also moves its event ancestry.
class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.parentElement = null;
    this.dataset = {}; this.attrs = {}; this.listeners = {}; this.hidden = false;
    this.style = {setProperty() {}}; this.focusCount = 0; this.scrolls = [];
    this.classList = {
      contains: name => (this.className || '').split(/\s+/).includes(name),
      toggle: (name, active) => {
        const names = new Set((this.className || '').split(/\s+/).filter(Boolean));
        if (active ?? !names.has(name)) names.add(name); else names.delete(name);
        this.className = [...names].join(' ');
      }, add: name => this.classList.toggle(name, true), remove: name => this.classList.toggle(name, false),
    };
  }
  setAttribute(key, value) {
    this.attrs[key] = String(value);
    if (key.startsWith('data-')) this.dataset[dataKey(key)] = String(value);
    else if (key === 'class') this.className = String(value);
    else if (['id', 'type', 'value'].includes(key)) this[key] = String(value);
    else if (key === 'hidden') this.hidden = true;
  }
  getAttribute(key) { return this.attrs[key] ?? null; }
  hasAttribute(key) { return key.startsWith('data-') ? dataKey(key) in this.dataset : key in this.attrs; }
  removeAttribute(key) { delete this.attrs[key]; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  append(...nodes) {
    for (const node of nodes) {
      if (node.parentElement) node.parentElement.children = node.parentElement.children.filter(child => child !== node);
      this.children.push(node); node.parentElement = this;
    }
  }
  prepend(node) { this.append(node); this.children.pop(); this.children.unshift(node); }
  appendChild(node) { this.append(node); return node; }
  after(node) { this.parentElement?.append(node); }
  replaceChildren(...nodes) { for (const child of this.children) child.parentElement = null; this.children = []; this.append(...nodes); }
  matches(selector) {
    return selector.split(',').some(part => {
      const query = part.trim(), tag = query.match(/^[a-z]+/i)?.[0];
      if (tag && this.tagName !== tag.toUpperCase()) return false;
      for (const [, name] of query.matchAll(/\.([\w-]+)/g)) if (!this.classList.contains(name)) return false;
      for (const [, key, expected] of query.matchAll(/\[([\w-]+)(?:=['"]?([^\]'"]+)['"]?)?\]/g)) {
        const value = key.startsWith('data-') ? this.dataset[dataKey(key)] : this[key] ?? this.attrs[key];
        if (expected === undefined ? !this.hasAttribute(key) : String(value) !== expected) return false;
      }
      return true;
    });
  }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  focus() { this.focusCount++; }
  scrollIntoView(options) { this.scrolls.push(options); }
  checkValidity() { return true; }
  set innerHTML(markup) {
    this.replaceChildren(); const stack = [this];
    for (const token of markup.matchAll(/<\/?([a-z][\w-]*)([^>]*)>/gi)) {
      if (token[0].startsWith('</')) { stack.pop(); continue; }
      const node = new Element(token[1]);
      for (const [, key, double, single, bare] of token[2].matchAll(/([\w-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) node.setAttribute(key, double ?? single ?? bare ?? '');
      stack.at(-1).append(node);
      if (!['input', 'img', 'br', 'hr', 'meta', 'link'].includes(token[1]) && !token[0].endsWith('/>')) stack.push(node);
    }
  }
}

function dispatch(type, target) {
  const event = {type, target};
  for (let node = target; node; node = node.parentElement) for (const listener of node.listeners[type] || []) listener(event);
}

function fixture({mediaReady = true} = {}) {
  const nodes = new Map(), tabs = [], panels = [];
  const html = web('index.html');
  for (const match of html.matchAll(/<(button|div)\b[^>]*(?:data-tab|data-panel)="[^"]+"[^>]*>/g)) {
    const holder = new Element(); holder.innerHTML = `${match[0]}</${match[1]}>`;
    const node = holder.children[0]; nodes.set(node.id, node);
    if (node.dataset.tab) tabs.push(node); else panels.push(node);
  }
  const shortcutMarkup = html.match(/<button\b[^>]*id="openStabilizationStudio"[^>]*>/)?.[0];
  if (shortcutMarkup) {
    const holder = new Element(); holder.innerHTML = `${shortcutMarkup}</button>`;
    nodes.set('openStabilizationStudio', holder.children[0]);
  }
  // Media is the existing dynamically appended tab, following all static tabs.
  if (mediaReady) {
    const mediaTab = new Element('button'); mediaTab.id = 'studioTabMedia'; mediaTab.dataset.tab = 'media';
    mediaTab.setAttribute('role', 'tab'); mediaTab.setAttribute('aria-controls', 'studioPanelMedia'); tabs.push(mediaTab);
  }
  const get = id => { if (!nodes.has(id)) { const node = new Element(); node.id = id; nodes.set(id, node); } return nodes.get(id); };
  const rail = new Element(); rail.className = 'advanced-tabs';
  rail.append = function(...children) { Element.prototype.append.apply(this, children); tabs.push(...children); };
  get('advancedPanel').append(rail);
  const document = {
    activeElement: null, documentElement: {dir: 'ltr'}, getElementById: get, createElement: tag => new Element(tag),
    addEventListener() {}, querySelectorAll(selector) {
      if (selector === '.tab-panel') return panels;
      if (selector === '.advanced-tabs button' || selector === ".advanced-tabs [role='tab']") return tabs;
      return [];
    }, querySelector(selector) {
      const tab = selector.match(/\.advanced-tabs button\[data-tab="([^"]+)"\]/)?.[1];
      return tab ? tabs.find(node => node.dataset.tab === tab) || null : this.querySelectorAll(selector)[0] || null;
    },
  };
  const context = vm.createContext({document, console, dictionaries: {en: {}},
    setTimeout: () => 1, clearTimeout() {}, performance: {now: () => 1000},
    window: {addEventListener() {}, setTimeout(callback) { callback(); }, matchMedia: () => ({matches: false})},
    requestAnimationFrame: callback => callback(),
  });
  const run = code => vm.runInContext(code, context);
  run(mediaSource); run(appSource);
  run(`cacheElements();
    state.project = {id:'discovery',revision:7,sources:{A:{duration:20},B:{duration:20}},
      settings:{audio_source:'A'},manual:{audio_mixer:{music_db:-12,music_muted:true}},draft:{output_duration:20}};
    state.studio.open = true; state.preview.mode = 'source'; state.preview.playing = true;
    state.manualSelection = {start:2,end:5}; state.markIn = {projectId:'discovery',time:1};
    globalThis.previewCalls = []; globalThis.requests = []; globalThis.mutations = [];
    globalThis.pauses = 0; globalThis.draws = 0; globalThis.opens = [];
    state.timeline = {playhead:3,zoom:2,selection:{start:2,end:5},draw(){draws++;},scheduleDraw(){draws++;},setProject(){mutations.push('timeline reset');}};
    pauseAllMedia = () => {pauses++;}; setAdvanced = value => opens.push(value);
    api = async (...args) => {requests.push(args); throw new Error('Discovery must not start an API request');};
    toast = () => {};
    ${mediaReady ? `state.mediaStudio = new MediaStudio(document.getElementById('studioPanelMedia'),document.getElementById('previewStage'),{
      audioPanel: document.getElementById('studioPanelAudio'),project:()=>state.project,audioSlot:()=> 'B',
      busy:()=>false,preview:()=>previewCalls.push('preview'),edit:async(action,patch)=>{mutations.push({action,patch});return state.project;},
    });` : ''}
    state.stabilizationStudio = {node:document.getElementById('existingStabilization'),source:document.getElementById('existingStabilizationSource'),render(){}};
    elements.cropSourceSelect.value = 'B';
  `);
  return {run, nodes, tabs, panels, document};
}

test('Audio is an accessible primary tab opening the actual existing mixer without changing the edit', () => {
  const {run, nodes, tabs} = fixture();
  const audio = tabs.find(tab => tab.dataset.tab === 'audio');
  assert.ok(audio, 'Audio must be directly discoverable in the primary tool rail');
  assert.equal(audio.getAttribute('role'), 'tab');
  assert.equal(audio.getAttribute('aria-controls'), 'studioPanelAudio');
  const panel = nodes.get('studioPanelAudio');
  assert.equal(panel.getAttribute('aria-labelledby'), audio.id);
  assert.equal(panel.getAttribute('role'), 'tabpanel');
  const before = run('JSON.stringify({project:state.project,selection:state.manualSelection,mark:state.markIn,preview:state.preview,playhead:state.timeline.playhead,zoom:state.timeline.zoom})');
  run(`globalThis.originalMixer = document.getElementById('studioPanelAudio').querySelector('.audio-mixer'); selectAdvancedTab('audio');`);
  assert.equal(panel.hidden, false);
  assert.equal(audio.getAttribute('aria-selected'), 'true'); assert.equal(audio.tabIndex, 0);
  assert.equal(run('originalMixer.open'), true);
  assert.equal(panel.querySelector('.audio-mixer'), run('originalMixer'));
  assert.equal(nodes.get('studioPanelMedia').querySelector('.audio-mixer'), null, 'the mixer must move, not duplicate');
  assert.equal(run('JSON.stringify({project:state.project,selection:state.manualSelection,mark:state.markIn,preview:state.preview,playhead:state.timeline.playhead,zoom:state.timeline.zoom})'), before);
  assert.deepEqual(plain(run('requests')), []); assert.deepEqual(plain(run('mutations')), []); assert.deepEqual(plain(run('previewCalls')), []);
});

test('choosing a primary tool restores the display inspector without changing the project', () => {
  const {run,nodes}=fixture(); let opened=0;
  nodes.get('advancedPanel').workspaceController={setWorkspace(){},showInspector(){opened++;}};
  const before=run('JSON.stringify(state.project)');
  run("selectAdvancedTab('audio');selectAdvancedTab('timeline');");
  assert.equal(opened,2); assert.equal(run('JSON.stringify(state.project)'),before);
  assert.deepEqual(plain(run('requests')),[]); assert.deepEqual(plain(run('mutations')),[]);
});

test('keyboard tab navigation includes Audio, exposes only its panel and preserves preview and selection', () => {
  const {run, tabs, panels, document} = fixture();
  const audioIndex = tabs.findIndex(tab => tab.dataset.tab === 'audio'); assert.ok(audioIndex > 0);
  let prevented = 0;
  const before = run('JSON.stringify({selection:state.manualSelection,preview:state.preview,timeline:state.timeline.selection,project:state.project})');
  run(`globalThis.keyEvent = null;`);
  const event = {key:'ArrowDown',currentTarget:tabs[audioIndex - 1],preventDefault(){prevented++;}};
  // Pass a real tab node as event.currentTarget; no stub of navigation itself.
  document.keyEvent = event; run('handleStudioTabKeydown(document.keyEvent);');
  assert.equal(prevented, 1); assert.equal(tabs[audioIndex].focusCount, 1);
  assert.equal(tabs.filter(tab => tab.tabIndex === 0).length, 1);
  assert.deepEqual(panels.filter(panel => !panel.hidden).map(panel => panel.dataset.panel), ['audio']);
  assert.equal(run('JSON.stringify({selection:state.manualSelection,preview:state.preview,timeline:state.timeline.selection,project:state.project})'), before);
  assert.equal(run('pauses'), 0); assert.deepEqual(plain(run('requests')), []); assert.deepEqual(plain(run('mutations')), []);
  document.documentElement.dir = 'rtl'; event.key = 'ArrowLeft'; event.currentTarget = tabs[audioIndex - 1];
  run('handleStudioTabKeydown(document.keyEvent);'); assert.equal(tabs[audioIndex].focusCount, 2);
});

test('Audio and Media quick navigation use existing busy and draft guards', () => {
  const {run, tabs} = fixture();
  for (const name of ['audio', 'media']) {
    assert.equal(run(`openStudioTab('${name}')`), true);
    assert.equal(tabs.find(tab => tab.dataset.tab === name).focusCount, 1);
  }
  const pauses = run('pauses');
  run(`state.activeJob='running';`);
  assert.equal(run(`openStudioTab('audio')`), false); assert.equal(run(`openStudioTab('media')`), false);
  run(`state.activeJob=null;state.project.draft=null;`);
  assert.equal(run(`openStudioTab('audio')`), false);
  assert.equal(run('pauses'), pauses); assert.deepEqual(plain(run('requests')), []);
});

test('Layout stabilization shortcut reveals and focuses the existing tool for the chosen source without starting work', () => {
  const {run, nodes, tabs} = fixture();
  const before = run('JSON.stringify(state.project)');
  assert.equal(run('openStabilizationTools()'), true);
  assert.equal(nodes.get('existingStabilization').open, true);
  assert.equal(nodes.get('existingStabilization').scrolls.length, 1);
  assert.equal(nodes.get('existingStabilizationSource').value, 'B');
  assert.equal(nodes.get('existingStabilizationSource').focusCount, 1);
  assert.equal(tabs.find(tab => tab.dataset.tab === 'media').getAttribute('aria-selected'), 'true');
  assert.equal(run('JSON.stringify(state.project)'), before);
  assert.deepEqual(plain(run('requests')), []); assert.deepEqual(plain(run('mutations')), []);
  run(`delete state.project.sources.B;state.stabilizationStudio.source.value='A';`);
  assert.equal(run('openStabilizationTools()'), true);
  assert.equal(nodes.get('existingStabilizationSource').value, 'A', 'a stale Layout source must not select unavailable footage');
  run(`state.activeJob='running';`); assert.equal(run('openStabilizationTools()'), false);
  assert.equal(nodes.get('existingStabilizationSource').focusCount, 2);
});

test('primary Audio tab and Layout stabilization button are connected to their actual click handlers', () => {
  const {run, nodes, tabs} = fixture({mediaReady:false});
  assert.ok(/<button\b[^>]*id="openStabilizationStudio"[^>]*>/.test(web('index.html')), 'Layout must expose the stabilization shortcut');
  const audio = tabs.find(tab => tab.dataset.tab === 'audio'); assert.ok(audio);
  // The rest of bindEvents is unrelated to discovering these two tools.
  for (const slot of ['A', 'B']) {
    const remove = new Element('button'); remove.className = 'remove-source'; nodes.get(`sourceSlot${slot}`).append(remove);
  }
  run(`bindKeyboardControls=bindEmbeddedCameraEditorEvents=()=>{};bindEvents();
    // Capability processing belongs to stabilization's dedicated tests; here
    // keep its already-created tool node and exercise actual app wiring.
    globalThis.StabilizationStudio=class {constructor(root){this.node=document.getElementById('existingStabilization');this.source=document.getElementById('existingStabilizationSource');root.append(this.node);}render(){}};
    initializeMediaStudio();`);
  dispatch('click', audio);
  assert.equal(nodes.get('studioPanelAudio').hidden, false);
  assert.equal(nodes.get('studioPanelAudio').querySelector('.audio-mixer').open, true);
  dispatch('click', nodes.get('openStabilizationStudio'));
  assert.equal(nodes.get('existingStabilization').open, true);
  assert.equal(nodes.get('existingStabilizationSource').focusCount, 1);
  assert.deepEqual(plain(run('requests')), []); assert.deepEqual(plain(run('mutations')), []);
});

test('relocated mixer faders, mute, solo and ducking still reach their original handlers exactly once', () => {
  const {run, nodes} = fixture(); const audio = nodes.get('studioPanelAudio');
  const fader = audio.querySelector('[data-mix=music_db]'); assert.ok(fader);
  fader.value = '-18'; dispatch('input', fader);
  assert.equal(run('state.mediaStudio.pending.get("mixer").music_db'), -18);
  assert.equal(run('previewCalls.length'), 1);
  const mute = audio.querySelector('[data-mute=music]'); dispatch('click', mute);
  assert.equal(run('state.mediaStudio.pending.get("mixer").music_muted'), false);
  assert.equal(mute.getAttribute('aria-pressed'), 'false'); assert.equal(run('previewCalls.length'), 2);
  const solo = audio.querySelector('[data-solo=voice]'); dispatch('click', solo);
  assert.equal(run('state.mediaStudio.solo'), 'voice'); assert.equal(solo.getAttribute('aria-pressed'), 'true');
  assert.equal(run('previewCalls.length'), 3); assert.equal(run('state.mediaStudio.pending.get("mixer").solo'), undefined);
  const ducking = audio.querySelector('[data-ducking]'); ducking.checked = true; dispatch('change', ducking);
  assert.equal(run('state.mediaStudio.pending.get("mixer").ducking'), true); assert.equal(run('previewCalls.length'), 4);
  assert.equal(nodes.get('studioPanelMedia').querySelector('[data-mix]'), null);
  assert.deepEqual(plain(run('requests')), []);
});

test('Master is a separate real output row while all relocated channel controls remain connected', () => {
  const {run,nodes}=fixture(),audio=nodes.get('studioPanelAudio');
  const channels=audio.querySelector('.mixer-channels'),master=audio.querySelector('.mixer-master');
  const roles=['source','music','voice','effects','master'];
  assert.deepEqual(channels.children.map(row=>row.dataset.channel),roles.slice(0,4),'the four input channels keep their order without Master occupying their grid');
  assert.ok(master,'Master has its own output section');
  assert.equal(master.parentElement,channels.parentElement);
  assert.equal(channels.parentElement.children[channels.parentElement.children.indexOf(channels)+1],master,'Master follows the input channels in reading and keyboard order');
  assert.deepEqual(master.children.map(row=>row.dataset.channel),['master']);
  assert.deepEqual(channels.children.map(row=>row.querySelector('[data-channel-name]').textContent),['Original','Music','Voiceover','Effects']);
  assert.equal(master.children[0].querySelector('[data-channel-name]').textContent,'Master');
  assert.deepEqual(audio.querySelectorAll('[data-mix]').map(range=>range.dataset.mix),roles.map(role=>`${role}_db`));
  assert.equal(audio.querySelectorAll('.mixer-channel-meter').length,5);
  assert.equal(nodes.get('studioPanelMedia').querySelector('[data-mix]'),null,'the single mixer stays in the primary Audio panel');
  for(const [index,role] of roles.entries()) {
    const row=audio.querySelector(`[data-channel=${role}]`),range=row.querySelector('[data-mix]'),meter=row.querySelector('meter');
    assert.equal(row,run(`state.mediaStudio.channelMeters.get('${role}').row`));
    assert.equal(meter,run(`state.mediaStudio.channelMeters.get('${role}').meter`),'the visible meter is the actual measured channel output');
    assert.equal(range.dataset.mix,`${role}_db`);
    range.value=String(-5-index);dispatch('input',range);
    assert.equal(run(`state.mediaStudio.pending.get('mixer').${role}_db`),-5-index);
    assert.equal(run('previewCalls.length'),index+1,'each relocated fader dispatches exactly once');
  }
  for(const [index,role] of roles.slice(0,4).entries()) {
    const mute=audio.querySelector(`[data-mute=${role}]`),solo=audio.querySelector(`[data-solo=${role}]`);
    dispatch('click',mute);assert.equal(run(`state.mediaStudio.mixer().${role}_muted`),role!=='music');
    dispatch('click',solo);assert.equal(run('state.mediaStudio.solo'),role);
    assert.equal(run('previewCalls.length'),5+(index+1)*2);
  }
  assert.equal(master.querySelector('[data-mute]'),null);assert.equal(master.querySelector('[data-solo]'),null);
  assert.equal(run("Object.keys(state.mediaStudio.pending.get('mixer')).some(key=>key.includes('solo'))"),false,'Solo remains preview-only');
  run(`state.mediaStudio.solo=null;
    state.mediaStudio.analyser={fftSize:4,getFloatTimeDomainData(samples){samples.fill(.75);}};
    state.mediaStudio.audioBuses=new Map(['source','music','voice','effects'].map((role,index)=>[role,{analyser:{fftSize:4,getFloatTimeDomainData(samples){samples.fill(.5/(index+1));}}}]));
    for(const role of ['source','music','voice','effects'])state.mediaStudio.players.set(role,{role,wanted:true,element:{paused:false},gain:{gain:{value:1}}});
    state.mediaStudio.updateMeters(true);`);
  for(const role of roles) assert.ok(audio.querySelector(`[data-channel=${role}]`).querySelector('meter').value>0,`${role} renders its measured signal`);
  assert.match(master.querySelector('meter').getAttribute('aria-valuetext'),/-2\.5 dBFS/);
  run('state.mediaStudio.pause();');for(const meter of audio.querySelectorAll('.mixer-channel-meter'))assert.equal(meter.value,0);
  assert.deepEqual(plain(run('requests')),[]);assert.deepEqual(plain(run('mutations')),[]);
});

test('relocated mixer restores saved gain, selected source label and measured master output on the visible panel', () => {
  const {run, nodes} = fixture(); const audio = nodes.get('studioPanelAudio');
  run(`state.mediaStudio.renderMixer(); state.mediaStudio.analyser={fftSize:4,getFloatTimeDomainData(samples){samples.fill(.5);}};state.mediaStudio.updateMeters(true);`);
  assert.equal(Number(audio.querySelector('[data-mix=music_db]').value), -12);
  assert.equal(audio.querySelector('[data-mute=music]').getAttribute('aria-pressed'), 'true');
  assert.match(audio.querySelector('[data-channel-name=source]').textContent, /B$/);
  assert.ok(audio.querySelector('.mixer-meter').value > .8);
  assert.match(audio.querySelector('.mixer-summary-level').textContent, /-6\.0 dBFS/);
  assert.match(audio.querySelector('.mixer-level-text').textContent, /Live browser mix/);
  run('state.mediaStudio.pause();'); assert.equal(audio.querySelector('.mixer-meter').value, 0);
  assert.match(audio.querySelector('.mixer-summary-level').textContent, /Paused/);
});
