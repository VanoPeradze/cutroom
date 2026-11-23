const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/viewer-transform.js'), 'utf8').replace(/^export /gm, '');
const plain = value => JSON.parse(JSON.stringify(value));
const scope = vm.createContext({});
vm.runInContext(source + '\nglobalThis.api={initMediaFrameEditor,dragMediaFrame,validMediaFrame};', scope);
const {initMediaFrameEditor, dragMediaFrame, validMediaFrame} = scope.api;
const rect = {x:.2, y:.2, w:.5, h:.5};
const tick = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };

class Node {
  constructor(doc) {
    this.ownerDocument = doc; this.listeners = new Map(); this.children = []; this.dataset = {}; this.style = {}; this.attrs = {};
    this.isConnected = true; this.classes = new Set(); this.captures = new Set();
    this.classList = {add: key => this.classes.add(key), remove: key => this.classes.delete(key), contains: key => this.classes.has(key)};
  }
  append(...nodes) { for (const node of nodes) { node.parent = this; this.children.push(node); } }
  remove() { this.isConnected = false; this.parent.children = this.parent.children.filter(node => node !== this); }
  setAttribute(key, value) { this.attrs[key] = value; }
  addEventListener(type, fn) { const list = this.listeners.get(type) || []; list.push(fn); this.listeners.set(type, list); }
  removeEventListener(type, fn) { this.listeners.set(type, (this.listeners.get(type) || []).filter(item => item !== fn)); }
  emit(type, props = {}) {
    const event = {target:this, preventDefault(){this.prevented=true;}, stopPropagation(){this.stopped=true;}, ...props};
    for (const listener of this.listeners.get(type) || []) listener(event);
    return event;
  }
  closest(selector) {
    if (selector === '[data-frame-handle]') return this.dataset.frameHandle ? this : this.parent?.closest(selector);
    return this.protected ? this : null;
  }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  focus() { this.ownerDocument.activeElement = this; }
  setPointerCapture(id) { this.captures.add(id); }
  hasPointerCapture(id) { return this.captures.has(id); }
  releasePointerCapture(id) { this.captures.delete(id); this.emit('lostpointercapture', {pointerId:id}); }
}

function fixture(options = {}) {
  const doc = {createElement: () => new Node(doc)}, win = new Node(doc);
  let observer;
  win.ResizeObserver = class { constructor(callback) { this.callback = callback; observer = this; } observe() {} disconnect() { this.disconnected = true; } };
  doc.defaultView = win;
  const origin = new Node(doc); origin.focus();
  const stage = new Node(doc), bounds = {left:10, top:20, width:1002, height:502};
  Object.assign(stage, {clientWidth:1000, clientHeight:500, clientLeft:1, clientTop:1, getBoundingClientRect:() => ({...bounds})});
  const saved = {projectId:'p', clipId:'m', token:'revision1', rect:{...rect}, busy:false, issue:''};
  const previews = [], commits = [], notices = [];
  let previewImpl, commitImpl, editor;
  previewImpl = (id, value) => {
    if (value && options.canonical) value = options.canonical(value);
    if (options.reentrant) editor.sync();
    return {issue:'', rect:value};
  };
  commitImpl = async (id, value) => { saved.rect = {...value}; saved.token += '+'; editor.sync(); return {id:'p'}; };
  editor = initMediaFrameEditor(stage, {
    snapshot:() => saved,
    preview:(id, value) => { previews.push({id, rect:plain(value)}); return previewImpl(id, value); },
    commit:(id, value, token) => { commits.push({id, rect:plain(value), token}); return commitImpl(id, value, token); },
    changed:value => { notices.push(plain(value)); if (options.reentrant) editor?.sync(); },
  });
  const root = stage.children[0], box = root.children[0];
  const handle = edge => edge === 'move' ? box : box.children.find(node => node.dataset.frameHandle === edge);
  const event = (x,y,extra = {}) => ({pointerId:1, button:0, clientX:x, clientY:y, ...extra});
  const down = (edge='move', x=500, y=250, extra={}) => box.emit('pointerdown', event(x,y,{target:handle(edge),...extra}));
  const move = (x=550,y=275,extra={}) => box.emit('pointermove', event(x,y,extra));
  const up = (x=550,y=275,extra={}) => box.emit('pointerup', event(x,y,extra));
  return {doc, win, origin, stage, bounds, saved, root, box, handle, editor, previews, commits, notices, down, move, up,
    observer:() => observer, setPreview:fn => previewImpl=fn, setCommit:fn => commitImpl=fn};
}

test('strict geometry rejects unknown, strings, nonfinite, undersized and out-of-canvas frames', () => {
  assert.equal(validMediaFrame(rect), true);
  for (const value of [null, {}, {...rect,x:'0.2'}, {...rect,y:NaN}, {...rect,w:.009}, {...rect,h:0}, {...rect,x:-.1}, {...rect,x:.8}, {...rect,y:.8}]) assert.equal(validMediaFrame(value), false);
  assert.equal(dragMediaFrame(rect,'rotation',0,0), null);
  assert.equal(dragMediaFrame(rect,'move',Infinity,0), null);
});

test('body move clamps whole frame while retaining exact width/height', () => {
  assert.deepEqual(plain(dragMediaFrame(rect,'move',2,-2)),{x:.5,y:0,w:.5,h:.5});
  assert.deepEqual(plain(dragMediaFrame({x:0,y:0,w:1,h:1},'move',.3,.2)),{x:0,y:0,w:1,h:1});
});

test('saved edge tolerance matches native bounds but never permits a dimension above one', () => {
  assert.equal(validMediaFrame({x:.300000005,y:.300000005,w:.7,h:.7}),true);
  assert.equal(validMediaFrame({x:.30000002,y:.3,w:.7,h:.7}),false);
  assert.equal(validMediaFrame({x:0,y:0,w:1.000000001,h:1}),false);
  assert.equal(validMediaFrame({x:0,y:0,w:1,h:1.000000001}),false);
});

for (const edge of ['nw','n','ne','e','se','s','sw','w']) test(`${edge} grip preserves opposite edges, bounds and minimum size without aspect lock`, () => {
  for (const dx of [-5,-.04,.031,5]) for (const dy of [-5,-.07,.023,5]) {
    const result = dragMediaFrame(rect,edge,dx,dy);
    assert.ok(validMediaFrame(result));
    if (!edge.includes('w')) assert.equal(result.x,rect.x);
    if (!edge.includes('n')) assert.equal(result.y,rect.y);
    if (!edge.includes('e')) assert.ok(Math.abs(result.x+result.w-.7)<1e-9);
    if (!edge.includes('s')) assert.ok(Math.abs(result.y+result.h-.7)<1e-9);
  }
});

test('explicit open attaches eight grips, exact saved percentages and focus; close restores origin', () => {
  const h=fixture(); assert.equal(h.root.hidden,true); assert.equal(h.editor.open(),true);
  assert.equal(h.editor.active,true); assert.equal(h.root.hidden,false); assert.equal(h.doc.activeElement,h.root);
  assert.equal(h.box.children.filter(node=>node.dataset.frameHandle).length,8);
  assert.equal(h.box.style.left,'20%'); assert.equal(h.box.style.width,'50%');
  assert.equal(h.stage.classList.contains('media-frame-editing'),true);
  assert.match(h.root.attrs['aria-label'],/percentage fields for keyboard/);
  assert.equal(h.editor.close(),true); assert.equal(h.doc.activeElement,h.origin); assert.equal(h.root.hidden,true);
});

test('busy, inactive/unsupported and zero-sized viewer never open or write', () => {
  for (const change of [{busy:true},{issue:'Full source'}, {clipId:''}, {rect:{...rect,w:0}}, {token:undefined}]) {
    const h=fixture(); Object.assign(h.saved,change); assert.equal(h.editor.open(),false); assert.equal(h.commits.length,0);
  }
  const h=fixture(); h.stage.clientWidth=0; assert.equal(h.editor.open(),false);
});

test('body drag previews only and release commits the canonical rectangle/token exactly once', async () => {
  const h=fixture({canonical:value=>({...value,x:Number(value.x.toFixed(3))})}); h.editor.open();
  h.down(); h.move(533.3333,275); assert.deepEqual(h.saved.rect,rect); assert.equal(h.commits.length,0);
  h.up(533.3333,275); h.up(533.3333,275); await tick();
  assert.deepEqual(h.commits,[{id:'m',rect:{x:.233,y:.25,w:.5,h:.5},token:'revision1'}]);
  assert.equal(h.editor.active,true); assert.equal(h.editor.pending,false); assert.equal(h.box.style.left,'23.3%');
  assert.equal(h.previews.at(-1).rect,null);
});

test('each resize grip saves geometry only; source clocks and effects are not invented', async () => {
  for (const edge of ['nw','n','ne','e','se','s','sw','w']) {
    const h=fixture(); h.editor.open(); h.down(edge); h.up(530,270); await tick();
    assert.equal(h.commits.length,1); assert.deepEqual(Object.keys(h.commits[0].rect).sort(),['h','w','x','y']);
  }
});

test('click, subthreshold movement, return to original and fully clamped move write nothing', async () => {
  for (const route of ['click','small','return','clamp']) {
    const h=fixture(); if(route==='clamp')h.saved.rect={x:0,y:0,w:1,h:1}; h.editor.open();h.down();
    if(route==='return'){h.move();h.up(500,250);} else if(route==='small')h.up(501,251); else if(route==='click')h.up(500,250);else h.up(600,300);
    await tick();assert.equal(h.commits.length,0);assert.equal(h.box.captures.size,0);
  }
});

for (const change of ['revision','selection','project','cursor','viewport-size','viewport-position','busy','inactive']) test(`${change} during a drag discards transient geometry without a stale save`, async () => {
  const h=fixture();h.editor.open();h.down();h.move();
  if(change==='revision'||change==='cursor')h.saved.token+='changed';
  if(change==='selection')h.saved.clipId='other';
  if(change==='project')h.saved.projectId='other';
  if(change==='viewport-size')h.stage.clientWidth=900;
  if(change==='viewport-position')h.bounds.left+=10;
  if(change==='busy')h.saved.busy=true;
  if(change==='inactive')h.saved.issue='Move inside this clip';
  h.editor.sync();h.up();await tick();assert.equal(h.commits.length,0);assert.equal(h.previews.at(-1).rect,null);
  assert.deepEqual(h.saved.rect,rect);
  assert.equal(h.editor.active,!['selection','project','inactive'].includes(change));
});

test('ordinary saved changes follow Undo/new rect outside gestures; busy alone preserves mode', () => {
  const h=fixture();h.editor.open();h.saved.rect={...rect,x:.3};h.saved.token='undo';h.editor.sync();
  assert.equal(h.box.style.left,'30%');assert.equal(h.editor.active,true);
  h.saved.busy=true;h.editor.sync();h.down();h.up();assert.equal(h.commits.length,0);assert.equal(h.root.dataset.state,'busy');
  h.saved.busy=false;h.editor.sync();assert.equal(h.root.dataset.state,'ready');
});

for (const route of ['Escape','pointercancel','lostpointercapture','blur']) test(`${route} cancels preview without writing and allows another gesture`, async () => {
  const h=fixture();h.editor.open();h.down();h.move();
  if(route==='Escape')h.win.emit('keydown',{key:'Escape',target:h.root});
  else if(route==='blur')h.win.emit('blur');else h.box.emit(route,{pointerId:1});
  h.up();await tick();assert.equal(h.commits.length,0);assert.equal(h.previews.at(-1).rect,null);assert.equal(h.editor.active,true);
  h.down();h.up();await tick();assert.equal(h.commits.length,1);
});

test('Escape on a field/dialog is left to that control; otherwise it closes idle frame mode', () => {
  const h=fixture();h.editor.open();const input=new Node(h.doc);input.protected=true;
  const event=h.win.emit('keydown',{key:'Escape',target:input});assert.equal(event.prevented,undefined);assert.equal(h.editor.active,true);
  h.win.emit('keydown',{key:'Escape',target:h.root});assert.equal(h.editor.active,false);
});

test('canonical preview rejection or exception clears transient slot and communicates reason', async () => {
  for(const route of ['reason','throw','invalid']){
    const h=fixture();h.editor.open();h.setPreview((id,value)=>{if(!value)return{rect:null};if(route==='throw')throw Error('preview');return route==='reason'?{issue:'Geometry is locked',rect:null}:{issue:'',rect:{...rect,w:2}};});
    h.down();h.move();h.up();await tick();assert.equal(h.commits.length,0);assert.equal(h.previews.at(-1).rect,null);
    assert.ok(h.notices.at(-1).issue);assert.deepEqual(h.saved.rect,rect);
  }
});

test('pending commit rejects repeat pointer/open/close/Escape without pretending to cancel dispatched save', async () => {
  const h=fixture();let finish;h.setCommit(()=>new Promise(resolve=>finish=resolve));h.editor.open();h.down();h.up();
  assert.equal(h.editor.pending,true);assert.equal(h.editor.close(),false);assert.equal(h.editor.open(),false);
  h.win.emit('keydown',{key:'Escape',target:h.root});h.down();h.up();assert.equal(h.commits.length,1);
  finish({id:'p'});await tick();assert.equal(h.editor.pending,false);assert.equal(h.editor.active,true);
});

test('failed save restores saved frame and permits retry, no unhandled rejection', async () => {
  const h=fixture();h.setCommit(async()=>{throw Error('Synthetic save failed');});h.editor.open();h.down();h.up();await tick();
  assert.equal(h.editor.pending,false);assert.equal(h.box.style.left,'20%');assert.equal(h.previews.at(-1).rect,null);
  assert.equal(h.notices.at(-1).issue,'Synthetic save failed');assert.equal(h.editor.active,true);
});

test('navigation during save closes overlay and late completion never reopens it', async () => {
  const h=fixture();let finish;h.setCommit(()=>new Promise(resolve=>finish=resolve));h.editor.open();h.down();h.up();
  h.saved.projectId='new';h.editor.sync();assert.equal(h.editor.active,false);
  finish(null);await tick();assert.equal(h.editor.active,false);assert.equal(h.root.hidden,true);assert.equal(h.editor.pending,false);
});

test('synchronous host preview/sync/changed callbacks do not recurse or duplicate commits', async () => {
  const h=fixture({reentrant:true});h.editor.open();h.down();h.move();h.up();await tick();
  assert.equal(h.commits.length,1);assert.equal(h.editor.active,true);assert.ok(h.notices.length<10);
  assert.equal(h.previews.filter(row=>row.rect===null).length,1);
});

test('non-primary/foreign pointer and unrelated keyboard input cannot start or finish a gesture', async () => {
  const h=fixture();h.editor.open();h.down('move',500,250,{button:2});h.up();h.down('move',500,250,{isPrimary:false});h.up();assert.equal(h.commits.length,0);
  h.down();h.up(600,300,{pointerId:2});assert.equal(h.commits.length,0);h.up();await tick();assert.equal(h.commits.length,1);
});

test('ResizeObserver cancels a changed viewport and destroy restores preview/removes all listeners', () => {
  const h=fixture();h.editor.open();h.down();h.move();h.stage.clientHeight=490;h.observer().callback();assert.equal(h.previews.at(-1).rect,null);
  h.down();h.move();h.editor.destroy();h.editor.destroy();assert.equal(h.root.isConnected,false);assert.equal(h.observer().disconnected,true);
  assert.equal(h.stage.classList.contains('media-frame-editing'),false);assert.equal(h.previews.at(-1).rect,null);
  assert.ok([...h.win.listeners.values(),...h.box.listeners.values()].every(list=>!list.length));assert.equal(h.editor.open(),false);
});

test('scoped overlay styles preserve normal playback and existing composition layers', () => {
  const css=fs.readFileSync(path.join(__dirname,'../web/studio-workbench.css'),'utf8');
  assert.match(css,/\.preview-stage\.media-frame-editing #previewPlay\s*\{[^}]*visibility:hidden/);
  assert.match(css,/\.media-frame-editor\s*\{[^}]*z-index:270;[^}]*pointer-events:none/);
  assert.match(css,/\.media-frame-editor\[hidden\]\s*\{\s*display:none/);
  assert.match(css,/\.media-frame-handle\s*\{[^}]*width:20px;[^}]*height:20px/);
  assert.match(css,/\[data-frame-handle=nw\]\s*\{\s*left:0; top:0/);
  assert.match(css,/\[data-frame-handle=se\]\s*\{\s*right:0; bottom:0/);
});
