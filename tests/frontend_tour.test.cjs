const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/tour.js');

test('the tour has five stops ending at Export', async () => {
  const { STEPS } = await load();
  assert.equal(STEPS.length, 5);
  assert.match(STEPS.at(-1).target, /RenderButton/);
  assert.ok(STEPS.every((s) => s.title && s.text.length < 140));
});

test('the bubble sits below the target when it fits, above otherwise, inside the screen', async () => {
  const { place } = await load();
  const viewport = { width: 1000, height: 800 };
  const box = { width: 300, height: 150 };
  assert.deepEqual(place({ top: 50, bottom: 80, left: 100, width: 60 }, box, viewport), { top: 92, left: 12, below: true });
  const up = place({ top: 700, bottom: 730, left: 950, width: 40 }, box, viewport);
  assert.equal(up.below, false);
  assert.equal(up.top, 538);
  assert.equal(up.left, 688);
});
