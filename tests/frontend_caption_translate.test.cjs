const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/caption-translate.js');

test('defaults to Hebrew for English speech and English otherwise', async () => {
  const { defaultTarget, LANGUAGES } = await load();
  assert.equal(defaultTarget('en'), 'he');
  assert.equal(defaultTarget('he'), 'en');
  assert.equal(defaultTarget(undefined), 'en');
  assert.ok(LANGUAGES.some(([code]) => code === 'he'));
});
