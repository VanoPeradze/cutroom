const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/cleanup.js');

const cap = (id, words) => ({ id, start: words[0][0], end: words.at(-1)[1], hidden: false, estimated_words: false, words });

test('finds long pauses but keeps a short breath on each side', async () => {
  const { findCleanup } = await load();
  const rows = findCleanup([cap('a', [[0.2, 0.5, 'Hello'], [2.5, 2.9, 'there']])], 3.2);
  const pause = rows.find((r) => r.kind === 'pause');
  assert.deepEqual([pause.start, pause.end], [0.625, 2.375]);
  assert.equal(pause.checked, true);
});

test('lead and tail silence are found; short gaps are not', async () => {
  const { findCleanup } = await load();
  const rows = findCleanup([cap('a', [[1.5, 1.8, 'Hi'], [2.0, 2.3, 'all']])], 5);
  assert.deepEqual(rows.filter((r) => r.kind === 'pause').map((r) => [r.start, r.end]), [[0, 1.25], [2.55, 5]]);
});

test('isolated hesitations are ticked, soft fillers listed but unticked, joined ones skipped', async () => {
  const { findCleanup } = await load();
  const rows = findCleanup([cap('a', [[0, .3, 'So'], [.5, .8, 'umm'], [1.0, 1.3, 'like,'], [1.5, 1.8, 'this'], [1.8, 2.0, 'uh'], [2.0, 2.4, 'works']])], 2.4);
  assert.deepEqual(rows.filter((r) => r.kind !== 'pause').map((r) => [r.kind, r.checked]), [['hesitation', true], ['filler', false]]);
});

test('a repeated opening marks the earlier attempt as a retake', async () => {
  const { findCleanup } = await load();
  const rows = findCleanup([
    cap('a', [[0, .3, 'The'], [.3, .6, 'best'], [.6, .9, 'part']]),
    cap('b', [[1.2, 1.5, 'The'], [1.5, 1.8, 'best'], [1.8, 2.1, 'part'], [2.1, 2.5, 'is']]),
  ], 2.5);
  const retake = rows.find((r) => r.kind === 'retake');
  assert.deepEqual([retake.start, retake.end, retake.checked], [0, 1.15, true]);
});

test('captions without trustworthy word timing are ignored', async () => {
  const { findCleanup } = await load();
  assert.deepEqual(findCleanup([{ ...cap('a', [[0, .3, 'umm'], [3, 3.3, 'ok']]), estimated_words: true }], 4), []);
});

test('approved items merge into non-overlapping ranges', async () => {
  const { removalRanges } = await load();
  assert.deepEqual(removalRanges([
    { start: 1, end: 2, checked: true }, { start: 1.5, end: 2.5, checked: true },
    { start: 3, end: 3.05, checked: true }, { start: 4, end: 5, checked: false },
  ]), [{ start: 1, end: 2.5 }]);
});
