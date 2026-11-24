const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const app = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const slice = (start, end) => app.slice(app.indexOf(start), app.indexOf(end));

function control() {
  const handlers = new Map();
  return {
    hidden: false, disabled: false, files: [], value: "",
    addEventListener(event, listener) { handlers.set(event, listener); },
    click() { handlers.get('click')?.(); },
    event(event) { handlers.get(event)?.(); },
  };
}

function fixture() {
  const nodes = new Map(['editorSourceB', 'editorAddSourceB', 'editorSourceBTitle', 'editorSourceBHelp',
    'editorSourceBProgress', 'editorStopSourceB', 'editorSourceBInput'].map(id => [id, control()]));
  const calls = [];
  let upload = null, busy = false;
  const state = { studio: {open: true}, projectViewToken: 10, project: {
    id: 'manual', revision: 3, draft: {}, settings: {workflow: 'manual'}, sources: {A: {generation: 'A'}}} };
  const context = vm.createContext({ state, document: {getElementById: id => nodes.get(id)},
    activeUploadForSlot: () => upload, foregroundBusy: () => busy, uiCopy: (_he, en) => en,
    runUiAction: fn => fn(), uploadSource: (...args) => calls.push(args), cancelUpload: (...args) => calls.push(args),
    uploadStatusText: () => 'Transferring' });
  vm.runInContext(slice('function editorSourceBContext()', 'function applyAttachedBPreview()') + '\nbindEditorSourceB()', context);
  return {nodes, calls, state, render: () => vm.runInContext('renderEditorSourceB()', context),
    setBusy: value => { busy = value; }, setUpload: value => { upload = value; }};
}

test('Layout has one native video attachment trigger independent of the media and Setup inputs', () => {
  assert.match(html, /<button[^>]+id="editorAddSourceB"[^>]+type="button"/);
  assert.match(html, /<input type="file" id="editorSourceBInput" accept="video\/[^"]+" hidden>/);
  assert.ok(html.indexOf('id="editorSourceB"') < html.indexOf('id="sourceMixerBody"'));
});

test('chooser cancel, another view, busy project, and populated B never start another upload', () => {
  const f = fixture(), click = f.nodes.get('editorAddSourceB'), input = f.nodes.get('editorSourceBInput');
  const file = {name:'camera.mp4'};
  f.render();
  assert.equal(click.hidden, false);
  click.click(); input.event('cancel'); input.files = [file]; input.event('change');
  assert.equal(f.calls.length, 0);
  click.click(); f.state.projectViewToken++; input.event('change');
  assert.equal(f.calls.length, 0);
  f.setBusy(true); f.render(); click.click(); input.event('change'); assert.equal(f.calls.length, 0);
  f.setBusy(false); f.render(); click.click(); input.event('change');
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0][0], 'B');
  assert.equal(f.calls[0][1], file);
  assert.equal(f.calls[0][2].attachB, true);
  assert.equal(f.calls[0][2].shouldContinue(), true);
  f.state.project.sources.B = {parallel_a_generation:'A'};
  f.render();
  assert.equal(click.hidden, true);
  assert.equal(f.calls[0][2].shouldContinue(), false);
  assert.match(f.nodes.get('editorSourceBHelp').textContent, /Clip framing.*A or B.*B only/);
});

test('attach progress exposes Stop without mounting a second input or changing the view', () => {
  const f = fixture();
  f.setBusy(true);
  f.setUpload({attachB:true});
  f.render();
  assert.equal(f.nodes.get('editorSourceBProgress').textContent, 'Transferring');
  assert.equal(f.nodes.get('editorAddSourceB').disabled, true);
  const stop = f.nodes.get('editorStopSourceB');
  assert.equal(stop.hidden, false);
  stop.click();
  assert.deepEqual(f.calls, [['B']]);
  f.setUpload({attachB:true, cancelRequested:true}); f.render();
  assert.equal(stop.disabled, true);
});

test('existing transport reserves reviewed attachment, uploads local chunks, finalizes only Source B', async () => {
  const traffic = [];
  const context = vm.createContext({
    state:{}, validateUploadFile:() => "", projectCopyFileBusy:() => false, rememberUploadStorage() {},
    api: async (url, request) => {
      traffic.push({url, request});
      if (url.endsWith('/preflight')) return {upload_token:'token1234', upload_url:'/chunk', cancel_url:'/cancel', chunk_size_bytes:2};
      return {source:{generation:'real-B'}};
    },
    sendUploadChunk: async (route, chunk, offset) => {
      assert.equal(route, '/chunk');
      return {received_bytes: offset + chunk.size};
    }
  });
  vm.runInContext(slice('async function uploadWithProgress(', 'async function uploadMediaAsset('), context);
  const response = await vm.runInContext(
    "uploadWithProgress('/api/projects/test/sources/B',{name:'camera.mp4',size:4,slice:(a,b)=>({size:b-a})},'token1234',null,null," +
    "{purpose:'source',slot:'B',attachB:true,attachRevision:5})", context);
  assert.equal(response.source.generation, 'real-B');
  assert.equal(traffic.length, 2);
  assert.equal(traffic[0].url, '/api/projects/test/uploads/preflight');
  assert.deepEqual(JSON.parse(traffic[0].request.body), {purpose:'source',slot:'B',filename:'camera.mp4',size_bytes:4,
    upload_token:'token1234',attach_b_revision:5});
  assert.equal(traffic[1].url, '/api/projects/test/sources/B');
  assert.equal(traffic[1].request.headers['X-Cutroom-Source-Intent'], 'attach-empty-b');
});
