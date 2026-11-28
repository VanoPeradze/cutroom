const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/hook.js');
const cap = (words, extra = {}) => ({ hidden: false, words, end: words.at(-1)[1] + 0.2, ...extra });

test('ranks numbers, questions and key words above plain sentences', async () => {
  const { rankHooks } = await load();
  const rows = rankHooks([
    cap([[1, 1.4, 'we'], [1.4, 1.8, 'went'], [1.8, 2.4, 'home']]),
    cap([[3, 3.4, 'Did'], [3.4, 3.8, 'you'], [3.8, 4.2, 'know'], [4.2, 4.8, 'this?']]),
    cap([[6, 6.4, 'We'], [6.4, 6.8, 'made'], [6.8, 7.4, '12000'], [7.4, 8, 'dollars']]),
  ]);
  assert.deepEqual(rows.map((r) => r.start), [6, 3]);
  assert.match(rows[0].reasons.join(), /number/);
  assert.match(rows[1].reasons.join(), /question/);
});

test('skips the existing opening, hidden captions and very long sentences', async () => {
  const { rankHooks } = await load();
  const long = Array.from({ length: 30 }, (_, i) => [10 + i * .3, 10.25 + i * .3, 'incredible']);
  assert.deepEqual(rankHooks([
    cap([[0.1, .4, 'Amazing'], [.4, .8, 'results'], [.8, 1.6, 'today!']]),
    cap([[2, 2.4, 'Amazing'], [2.4, 2.8, 'results'], [2.8, 3.6, 'today!']], { hidden: true }),
    cap(long),
  ]), []);
});
