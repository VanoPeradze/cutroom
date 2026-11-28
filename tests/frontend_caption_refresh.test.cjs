const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const app = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
const code = app.slice(app.indexOf('// Captions built from another sound'), app.indexOf('function friendlyRenderError('));

function host(failFirst) {
  const calls = [], state = { project: { id: 'demo', revision: 7 } };
  let renders = 0;
  const ctx = vm.createContext({
    state, calls, setTimeout: (fn) => fn(), uiCopy: (_he, en) => en, toast: () => {},
    setActiveJob: () => {}, clearActiveJob: () => {}, reconcileProjectSnapshot: (p) => p, rememberProjectRevision: () => {},
    editorProject: () => state.project, renderTranscript: () => {}, renderCaptionControls: () => {}, renderCaptionInspector: () => {},
    updatePreviewCaption: () => {}, previewPlaybackTime: () => 0,
    api: async (url, options = {}) => {
      calls.push([url, options.body ? JSON.parse(options.body) : null]);
      if (url.endsWith('/render')) {
        renders += 1;
        if (failFirst && renders === 1) { const e = new Error('Captions no longer match'); e.code = 'captions_out_of_date'; throw e; }
        return { job: { id: 'render' } };
      }
      if (url.endsWith('/caption-refresh')) return { job: { id: 'refresh', status: 'running' } };
      if (url.startsWith('/api/jobs/')) return { job: { id: 'refresh', status: 'completed', progress: 1 } };
      if (url === '/api/projects/demo') return { project: { id: 'demo', revision: 8 } };
      throw new Error('unexpected ' + url);
    },
  });
  vm.runInContext(code, ctx);
  return { ctx, calls, run: (body) => vm.runInContext(`postRender('demo', ${JSON.stringify(body)}, () => {})`, ctx) };
}

test('stale captions are refreshed once, then the marked range is sent on the new revision', async () => {
  const h = host(true);
  await h.run({ range: { start_frame: 21, end_frame: 42, fps: 30, expected_revision: 7 } });
  assert.deepEqual(h.calls.map(([url]) => url), ['/api/projects/demo/render', '/api/projects/demo/caption-refresh',
    '/api/jobs/refresh', '/api/projects/demo', '/api/projects/demo/render']);
  assert.deepEqual(h.calls[1][1], { expected_revision: 7 });
  assert.deepEqual(h.calls[4][1], { range: { start_frame: 21, end_frame: 42, fps: 30, expected_revision: 8 } });
});

test('a render that is accepted never transcribes', async () => {
  const h = host(false);
  await h.run({});
  assert.deepEqual(h.calls, [['/api/projects/demo/render', {}]]);
});
