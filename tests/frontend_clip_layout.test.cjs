const test = require('node:test');
const assert = require('node:assert/strict');

const mixer = { screenSlot: 'A', cameraSlot: 'B', firstSlot: 'B', primaryRole: 'screen', stackFit: 'cover', screenFit: 'auto' };

test('stacked cards put the camera panel on top, the screen below, as render.py does', async () => {
  const { layoutPanels } = await import('../web/clip-board.js');
  const panels = layoutPanels('stacked', mixer, 270, 480);
  assert.deepEqual(panels.map((p) => p.slot), ['B', 'A']);
  assert.equal(panels[0].rect.h, Math.round(480 * 0.3));
  assert.equal(panels[1].rect.y, panels[0].rect.h);
  assert.equal(panels[0].rect.h + panels[1].rect.h, 480);
  assert.ok(panels.every((p) => p.fit === 'cover'));
  const cameraFirst = layoutPanels('stacked', { ...mixer, primaryRole: 'camera', firstSlot: 'A' }, 270, 480);
  assert.deepEqual(cameraFirst.map((p) => [p.slot, p.rect.h]), [['A', 480 - 336], ['B', 336]]);
});

test('side by side, picture in picture and single-source frames', async () => {
  const { layoutPanels } = await import('../web/clip-board.js');
  const split = layoutPanels('side_by_side', { ...mixer, firstSlot: 'A' }, 385, 216);
  assert.deepEqual(split.map((p) => [p.slot, p.rect.x, p.rect.w, p.fit]), [['A', 0, 192, 'contain'], ['B', 192, 193, 'contain']]);
  const pip = layoutPanels('pip', { ...mixer, pip: { x: .6, y: .7, w: .3, h: .2 } }, 100, 200);
  assert.deepEqual(pip.map((p) => p.slot), ['A', 'B']);
  assert.deepEqual(pip[1].rect, { x: 60, y: 140, w: 30, h: 40 });
  assert.deepEqual(layoutPanels('B', mixer, 10, 20), [{ slot: 'B', rect: { x: 0, y: 0, w: 10, h: 20 }, fit: 'cover' }]);
  assert.equal(layoutPanels('A', { ...mixer, screenFit: 'contain' }, 10, 20)[0].fit, 'contain');
  assert.deepEqual(layoutPanels('black', mixer, 10, 20), []);
});

test('containRect letterboxes a wide source in a tall panel', async () => {
  const { containRect } = await import('../web/clip-board.js');
  assert.deepEqual(containRect(1920, 1080, { x: 0, y: 0, w: 270, h: 480 }), { x: 0, y: (480 - 151.875) / 2, w: 270, h: 151.875 });
});
