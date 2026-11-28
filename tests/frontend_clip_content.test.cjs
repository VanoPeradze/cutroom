const test = require('node:test');
const assert = require('node:assert/strict');

test('content rows keep the order, clamp scores and skip missing data', async () => {
  const { contentRows } = await import('../web/clip-board.js');
  assert.deepEqual(contentRows(null), []);
  const rows = contentRows({ clarity: { score: 120, note: 'clear' }, hook: { score: 42.4, note: 'a number' }, complete: { note: 'no score' } });
  assert.deepEqual(rows.map((r) => [r.key, r.score]), [['hook', 42], ['clarity', 100]]);
  assert.equal(rows[0].label, 'Hook');
});
