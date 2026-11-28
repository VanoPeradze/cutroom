const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/brand-kit.js');

test('logo keeps its shape, stays inside the frame and keeps an even margin', async () => {
  const { logoPlacement } = await load();
  const wide = logoPlacement({ corner: 'top-right', size: 0.14, frameRatio: 16 / 9, imageRatio: 2 });
  assert.ok(Math.abs(wide.h - 0.14 * (16 / 9) / 2) < 1e-3);
  assert.ok(wide.x + wide.w <= 1 && wide.y + wide.h <= 1);
  assert.ok(Math.abs((1 - wide.x - wide.w) - 0.03) < 1e-3);
  const tall = logoPlacement({ corner: 'bottom-left', size: 0.3, frameRatio: 9 / 16, imageRatio: 0.2 });
  assert.ok(tall.h <= 0.4 + 1e-9 && tall.x === 0.03);
  assert.ok(tall.y + tall.h <= 1 && tall.y > 0.5);
  const square = logoPlacement({ corner: 'top-left', size: 0.1, frameRatio: 1, imageRatio: 1 });
  assert.deepEqual(square, { x: 0.03, y: 0.03, w: 0.1, h: 0.1 });
});

test('frame ratio comes from the aspect setting, with a fallback for source aspect', async () => {
  const { frameRatioOf } = await load();
  assert.equal(frameRatioOf({ settings: { aspect: '9:16' } }), 9 / 16);
  assert.equal(frameRatioOf({ settings: { aspect: 'source' } }, 4 / 3), 4 / 3);
});

test('templates capture the look and are stored safely', async () => {
  const { templateFromProject, readTemplates, writeTemplates, upsertTemplate, isAccent } = await load();
  const project = { settings: { caption_style: 'pop', caption_position: 'top', caption_scale: 120, caption_words_per_line: 3, caption_accent: '#ff4d6d' }, manual: { color: { look: 'warm' } } };
  const t = templateFromProject(project, '  Channel  ');
  assert.deepEqual(t, { name: 'Channel', caption_style: 'pop', caption_position: 'top', caption_scale: 120, caption_words_per_line: 3, caption_accent: '#FF4D6D', look: 'warm' });
  assert.equal(templateFromProject({}, '').name, 'My brand');
  assert.equal(templateFromProject({ settings: { caption_accent: 'red' } }).caption_accent, '');
  const memory = new Map();
  const storage = { getItem: (k) => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v) };
  assert.deepEqual(readTemplates(storage), []);
  let rows = upsertTemplate([], t);
  rows = upsertTemplate(rows, { ...t, name: 'Other' });
  rows = upsertTemplate(rows, { ...t, name: 'CHANNEL', caption_style: 'box' });
  assert.deepEqual(rows.map((r) => r.name), ['CHANNEL', 'Other']);
  assert.ok(writeTemplates(storage, rows));
  assert.equal(readTemplates(storage).length, 2);
  memory.set('cutroom-brand-templates', '{broken');
  assert.deepEqual(readTemplates(storage), []);
  assert.equal(writeTemplates({ setItem() { throw new Error('blocked'); } }, rows), false);
  assert.deepEqual(readTemplates(null), []);
  assert.ok(isAccent('#A1b2C3') && !isAccent('#abc') && !isAccent(null));
});
