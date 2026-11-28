const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/prompt-edit.js');
const search = () => import('../web/transcript-search.js');

const project = {
  editor_sequence: { duration: 20 },
  manual: { keyframes: [] },
  editor_captions: [
    { id: 'a', start: 0.5, words: [[0.5, 0.9, 'So'], [0.95, 1.3, 'basically'], [1.35, 1.8, 'pricing'], [1.85, 2.2, 'matters.']] },
    { id: 'b', start: 4, words: [[4, 4.3, 'umm'], [4.6, 5, 'We'], [5.05, 5.4, 'made'], [5.45, 6, '12000'], [6.05, 6.6, 'dollars!']] },
    { id: 'c', start: 8, words: [[8, 8.4, 'Basically,'], [8.45, 9, 'thanks'], [9.05, 9.6, 'everyone']] },
  ],
};

test('removes a time range in English and Hebrew', async () => {
  const { planPrompt } = await load();
  assert.deepEqual(planPrompt('Cut from 0:05 to 0:08', project).ranges, [{ start: 5, end: 8 }]);
  assert.deepEqual(planPrompt('חתוך מ-5 עד 7.5', project).ranges, [{ start: 5, end: 7.5 }]);
  assert.equal(planPrompt('cut from 0:08 to 0:05', project).kind, 'none');
  assert.equal(planPrompt('cut from 0:10 to 0:30', project).kind, 'none');
});

test('removes every exact use of a phrase, never a longer word', async () => {
  const { planPrompt } = await load();
  const plan = planPrompt('Delete every "basically"', project);
  assert.equal(plan.kind, 'remove');
  assert.equal(plan.ranges.length, 2);
  assert.equal(plan.query, 'basically');
  assert.equal(planPrompt('remove pric', project).kind, 'none');
});

test('maps cleanup words to cleanup kinds', async () => {
  const { planPrompt } = await load();
  const pauses = planPrompt('Remove the long pauses', project);
  assert.equal(pauses.kind, 'remove');
  assert.match(pauses.summary, /long pauses/);
  assert.equal(planPrompt('תסיר את השתיקות', project).kind, 'remove');
  const um = planPrompt('remove um and uh', project);
  assert.match(um.summary, /hesitations/);
  assert.ok(um.ranges.every((r) => r.start >= 3.9 && r.end <= 4.6));
});

test('finds, seeks, adds an opener and zooms without removing', async () => {
  const { planPrompt } = await load();
  assert.deepEqual([planPrompt('go to 1:02', { ...project, editor_sequence: { duration: 90 } }).kind, planPrompt('go to 1:02', { ...project, editor_sequence: { duration: 90 } }).time], ['seek', 62]);
  const find = planPrompt('Find pricing', project);
  assert.equal(find.kind, 'find'); assert.equal(find.time, 1.35);
  assert.equal(planPrompt('איפה אמרתי dollars', project).kind, 'find');
  assert.equal(planPrompt('find nothing-here', project).kind, 'none');
  assert.equal(planPrompt('Add an opener', project).kind, 'opener');
  assert.equal(planPrompt('Zoom on key words', project).kind, 'zoom');
  assert.equal(planPrompt('make it pretty', project).kind, 'none');
  assert.equal(planPrompt('', project).summary, '');
});

test('transcript search helpers', async () => {
  const { findMatches, parseTime, mergeRanges, normalizeWord } = await search();
  const words = [{ text: 'Thanks' }, { text: 'for' }, { text: 'watching!' }, { text: 'thanks' }];
  assert.deepEqual(findMatches(words, 'thanks'), [[0, 0], [3, 3]]);
  assert.deepEqual(findMatches(words, 'for wat'), [[1, 2]]);
  assert.deepEqual(findMatches(words, 'for wat', { prefix: false }), []);
  assert.deepEqual(findMatches(words, 'han'), [[0, 0], [3, 3]]);
  assert.deepEqual(findMatches(words, ''), []);
  assert.equal(normalizeWord('“שָׁלוֹם,”'), 'שלום');
  assert.equal(parseTime('1:02:03'), 3723);
  assert.equal(parseTime('12.5s'), 12.5);
  assert.equal(parseTime('soon'), null);
  assert.deepEqual(mergeRanges([{ start: 2, end: 3 }, { start: 1, end: 2.01 }, { start: 5, end: 5.05 }]), [{ start: 1, end: 3 }]);
});

test('shorten to a length removes the lightest cleanup first and is honest when it cannot', async () => {
  const { planPrompt, parseLength } = await load();
  assert.equal(parseLength('8 minutes'), 480);
  assert.equal(parseLength('90 seconds'), 90);
  assert.equal(parseLength('1:30'), 90);
  assert.equal(parseLength('8 דקות'), 480);
  assert.equal(parseLength('8'), 480);
  assert.equal(parseLength('45'), 45);
  assert.equal(parseLength('soon'), null);
  const project = {
    editor_sequence: { duration: 20 },
    editor_captions: [
      { id: 'a', start: 0.5, words: [[0.5, 0.9, 'So'], [0.95, 1.3, 'pricing'], [1.35, 1.8, 'matters.']] },
      { id: 'b', start: 6, words: [[6, 6.3, 'umm'], [6.6, 7, 'We'], [7.05, 7.4, 'made'], [7.45, 8, 'money.']] },
      { id: 'c', start: 14, words: [[14, 14.4, 'Thanks'], [14.45, 15, 'everyone']] },
    ],
  };
  assert.match(planPrompt('shorten to 30 seconds', project).summary, /already/);
  const near = planPrompt('Shorten to 0:17', project);
  assert.equal(near.kind, 'remove');
  assert.match(near.summary, /^Shorten to/);
  assert.ok(20 - near.ranges.reduce((s, r) => s + r.end - r.start, 0) <= 17.05);
  const far = planPrompt('תקצר ל-5 שניות', project);
  assert.equal(far.kind, 'remove');
  assert.match(far.summary, /AI Director/);
});
