const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/color-motion.js');
const cap = (words) => ({ hidden: false, estimated_words: false, words });

test('key words: numbers, long content words and exclamations', async () => {
  const { isEmphasisWord } = await load();
  assert.deepEqual(['12000', 'dollars', 'wow!', 'really', 'actually', 'the', 'מדהימים'].map(isEmphasisWord), [true, true, true, false, false, false, true]);
});

test('each punch is four keyframes, spaced apart, inside the 32 limit', async () => {
  const { autoZoomKeyframes } = await load();
  const words = Array.from({ length: 40 }, (_, i) => [1 + i, 1.3 + i, i % 2 ? 'amazing' : 'so']);
  const rows = autoZoomKeyframes([cap(words)]);
  assert.equal(rows.length % 4, 0);
  assert.ok(rows.length <= 32);
  assert.deepEqual(rows.slice(0, 4).map((r) => [r.time, r.zoom]), [[1.75, 1], [2, 1.15], [3, 1.15], [3.35, 1]]);
  assert.ok(rows[4].time - rows[0].time >= 4);
});

test('existing keyframes are kept and never overlapped', async () => {
  const { autoZoomKeyframes } = await load();
  const existing = [{ time: 2.2, zoom: 1.5, x: 0.5, y: 0.5 }];
  const rows = autoZoomKeyframes([cap([[2, 2.4, 'incredible'], [9, 9.4, 'fantastic']])], existing);
  assert.deepEqual(rows.map((r) => r.time), [2.2, 8.75, 9, 10, 10.35]);
});
