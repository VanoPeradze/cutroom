const test = require('node:test');
const assert = require('node:assert/strict');

test('every pack uses a real caption style and colour look', async () => {
  const { LOOK_PACKS } = await import('../web/look-packs.js');
  const { LOOKS } = await import('../web/color-motion.js');
  const looks = new Set(LOOKS.map(([id]) => id));
  const captions = new Set(['clean', 'bold', 'boxed', 'highlight', 'pop', 'box', 'neon', 'word', 'emphasis']);
  for (const pack of LOOK_PACKS) { assert.ok(looks.has(pack.look), pack.id); assert.ok(captions.has(pack.caption), pack.id); }
});

test('a pack keeps the other colour values and adds zooms only when it zooms', async () => {
  const { LOOK_PACKS, packManualPatch } = await import('../web/look-packs.js');
  const project = { manual: { color: { look: 'none', exposure: 0.2 } }, editor_captions: [{ words: [[2, 2.4, 'incredible']] }] };
  const social = packManualPatch(LOOK_PACKS.find((p) => p.id === 'social'), project);
  assert.equal(social.color.look, 'punchy'); assert.equal(social.color.exposure, 0.2); assert.equal(social.keyframes.length, 4);
  assert.equal(packManualPatch(LOOK_PACKS.find((p) => p.id === 'clean'), project).keyframes, undefined);
});
