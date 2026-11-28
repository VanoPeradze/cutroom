const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/script-view.js');

test('builds paragraphs in time order with one running word index', async () => {
  const { scriptParagraphs } = await load();
  const paras = scriptParagraphs([
    { id: 'b', start: 3, words: [[3, 3.4, 'שלום'], [3.4, 3.9, 'לכם']], direction: 'rtl' },
    { id: 'a', start: 1, words: [[1, 1.3, ' Hello '], [1.3, 1.5, ' '], [1.5, 2, 'there']], estimated_words: true },
    { id: 'h', start: 2, hidden: true, words: [[2, 2.5, 'gone']] },
    { id: 'e', start: 2.5, words: [] },
  ]);
  assert.deepEqual(paras.map((p) => p.id), ['a', 'b']);
  assert.equal(paras[0].estimated, true);
  assert.equal(paras[1].dir, 'rtl');
  assert.equal(paras[0].dir, 'auto');
  assert.deepEqual(paras[0].words.map((w) => w.text), ['Hello', 'there']);
  assert.deepEqual(paras.flatMap((p) => p.words).map((w) => w.i), [0, 1, 2, 3]);
});

test('selection range pads into pauses but never into neighbouring words', async () => {
  const { selectionRange } = await load();
  const words = [{ start: 0.02, end: 0.5 }, { start: 0.51, end: 1 }, { start: 1.5, end: 2 }, { start: 2.01, end: 2.4 }];
  assert.deepEqual(selectionRange(words, 0, 0), { start: 0, end: 0.51 });
  assert.deepEqual(selectionRange(words, 2, 1), { start: 0.5, end: 2.01 });
  assert.deepEqual(selectionRange(words, 3, 3), { start: 2, end: 2.44 });
  assert.equal(selectionRange(words, 9, 9), null);
  assert.equal(selectionRange([{ start: 1, end: 1 }, { start: 1, end: 1 }, { start: 1, end: 1 }], 1, 1), null);
});
