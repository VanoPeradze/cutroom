const test = require('node:test');
const assert = require('node:assert/strict');
const search = () => import('../web/transcript-search.js');
const prompt = () => import('../web/prompt-edit.js');

const w = (start, end, text) => ({ start, end, text });
const words = [
  w(0.5, 0.9, 'So'), w(0.95, 1.3, 'pricing'), w(1.35, 1.8, 'matters.'),
  w(2.0, 2.3, 'Then'), w(2.35, 2.8, 'we'), w(2.85, 3.2, 'shipped'),
  w(5.0, 5.4, 'Pricing'), w(5.45, 6.0, 'again!'), w(6.1, 6.5, 'Bye'),
];

test('sentenceSpan widens to the sentence, stopping at punctuation and long pauses', async () => {
  const { sentenceSpan } = await search();
  assert.deepEqual(sentenceSpan(words, 1, 1), [0, 2]);
  assert.deepEqual(sentenceSpan(words, 4, 4), [3, 5]); // 1.8 s pause after "shipped"
  assert.deepEqual(sentenceSpan(words, 6, 6), [6, 7]);
  assert.deepEqual(sentenceSpan(words, 4, 4, { reach: 0 }), [4, 4]);
});

test('keepOnlyRanges removes everything outside the kept spans', async () => {
  const { keepOnlyRanges } = await search();
  const cuts = keepOnlyRanges(words, [[0, 2], [6, 7]], 10);
  assert.deepEqual(cuts, [{ start: 0, end: 0.3 }, { start: 2, end: 4.8 }, { start: 6.1, end: 10 }]);
  assert.deepEqual(keepOnlyRanges(words, [], 10), []);
  assert.deepEqual(keepOnlyRanges(words, [[0, 8]], 6.6), [{ start: 0, end: 0.3 }]);
  assert.deepEqual(keepOnlyRanges(words, [[0, 2]], NaN), []);
});

test('typed supercut keeps the sentences that mention a word, in English and Hebrew', async () => {
  const { planPrompt } = await prompt();
  const project = {
    editor_sequence: { duration: 20 },
    editor_captions: [
      { id: 'a', start: 0.5, words: [[0.5, 0.9, 'So'], [0.95, 1.3, 'pricing'], [1.35, 1.8, 'matters.']] },
      { id: 'b', start: 4, words: [[4, 4.3, 'We'], [4.35, 4.8, 'shipped.']] },
      { id: 'c', start: 8, words: [[8, 8.4, 'Pricing'], [8.45, 9, 'again!']] },
    ],
  };
  const plan = planPrompt('Keep only the parts about pricing', project);
  assert.equal(plan.kind, 'remove');
  assert.equal(plan.query, 'pricing');
  assert.deepEqual(plan.ranges, [{ start: 0, end: 0.3 }, { start: 2.1, end: 7.8 }, { start: 9.3, end: 20 }]);
  assert.match(plan.summary, /Supercut: keep the 2 sentences/);
  assert.equal(planPrompt('supercut pricing', project).kind, 'remove');
  assert.equal(planPrompt('השאר רק את החלקים על pricing', project).kind, 'remove');
  assert.equal(planPrompt('keep only banana', project).kind, 'none');
});
