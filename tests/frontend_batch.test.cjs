const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/batch.js');

test('batch settings keep the look of the open project and fit the goal', async () => {
  const { batchSettings } = await load();
  assert.deepEqual(batchSettings('nope'), { goal: 'clean' });
  assert.deepEqual(batchSettings('short'), { goal: 'short', aspect: '9:16' });
  const current = { goal: 'short', edit_style: 'expert_tip', aspect: '9:16', caption_style: 'bold', caption_accent: '#ff0000', instruction: 'private' };
  assert.deepEqual(batchSettings('short', current), { goal: 'short', aspect: '9:16', caption_style: 'bold', caption_accent: '#ff0000', edit_style: 'expert_tip' });
  const long = batchSettings('youtube', current);
  assert.equal(long.aspect, '16:9');
  assert.equal(long.edit_style, undefined);
  assert.equal(long.instruction, undefined);
});

test('project names come from file names', async () => {
  const { projectName, summary } = await load();
  assert.equal(projectName('Interview_take  2.mp4'), 'Interview take 2');
  assert.equal(projectName('.mov'), 'Recording');
  assert.equal(summary([{ state: 'done' }, { state: 'failed' }, { state: 'waiting' }, { state: 'running' }]), '1 ready · 1 need attention · 2 waiting');
});

function fakeHost({ prepareFails = false, deferred = false } = {}) {
  const calls = [];
  const jobs = { p1: ['running', 'completed'], d1: ['queued', 'running', prepareFails ? 'failed' : 'completed'] };
  return {
    calls,
    async api(path, options = {}) {
      calls.push([options.method || 'GET', path, options.body]);
      if (path === '/api/projects') return { project: { id: 'proj1' } };
      if (path.endsWith('/sources/A/prepare')) return { job: { id: 'p1', status: 'queued' } };
      if (path.endsWith('/director')) return { job: { id: 'd1', status: 'queued' } };
      if (path === '/api/projects/proj1') return { project: { analysis: { segments: [{}, {}] } } };
      const id = path.split('/').at(-1);
      const status = jobs[id].shift();
      return { job: { id, status, progress: 0.5, error: status === 'failed' ? 'Story AI is not ready' : null } };
    },
    async uploadSourceTo(projectId, file, onProgress) {
      calls.push(['UPLOAD', projectId, file.name]);
      onProgress(0.5); onProgress(1);
      return deferred ? { job: null, preparation_deferred: true } : { job: { id: 'p1', status: 'queued' } };
    },
  };
}

test('runOne creates, imports, prepares and edits one recording', async () => {
  const { runOne } = await load();
  const host = fakeHost();
  const seen = [];
  const row = { file: { name: 'Talk.mp4' }, state: 'waiting', detail: '', report: (r) => seen.push(r.detail) };
  await runOne(host, row, { settings: { goal: 'clean' }, poll: 0 });
  assert.equal(row.state, 'done');
  assert.equal(row.projectId, 'proj1');
  assert.deepEqual(JSON.parse(host.calls[0][2]), { name: 'Talk', initial_settings: { goal: 'clean' } });
  assert.deepEqual(host.calls[1], ['UPLOAD', 'proj1', 'Talk.mp4']);
  assert.ok(host.calls.some(([m, p]) => m === 'POST' && p === '/api/projects/proj1/director'));
  assert.ok(seen.includes('Importing 50%'));
  assert.equal(row.detail, 'Transcript (2 lines), edit and Clips ready');
});

test('a failed edit is reported and a deferred preparation is retried', async () => {
  const { runOne } = await load();
  const host = fakeHost({ prepareFails: true, deferred: true });
  const row = { file: { name: 'b.mov' }, state: 'waiting', detail: '' };
  await runOne(host, row, { settings: {}, poll: 0 });
  assert.equal(row.state, 'failed');
  assert.equal(row.detail, 'Story AI is not ready');
  assert.ok(host.calls.some(([m, p]) => m === 'POST' && p.endsWith('/sources/A/prepare')));
  const plain = fakeHost();
  const only = { file: { name: 'c.mp4' }, state: 'waiting', detail: '' };
  await runOne(plain, only, { settings: {}, draft: false, poll: 0 });
  assert.equal(only.state, 'done');
  assert.ok(!plain.calls.some(([, p]) => p.endsWith('/director')));
});
