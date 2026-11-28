const test = require('node:test');
const assert = require('node:assert/strict');
const load = () => import('../web/broll.js');
const cap = (start, text) => ({ words: text.split(' ').map((w, i) => [start + i * 0.4, start + i * 0.4 + 0.35, w]) });

test('suggests cutaways where things are named, pointed at or counted, and keeps them apart', async () => {
  const { suggestBroll } = await load();
  const ideas = suggestBroll([
    cap(0.2, 'Look at this beautiful mountain'),            // too early: the speaker opens
    cap(3, 'So I was there and it was'),                    // nothing to show
    cap(6, 'Imagine the mountain lake at sunrise'),
    cap(8, 'We spent 300 dollars on the cabin'),            // within 6 s of the previous idea
    cap(15, 'For example the cabin kitchen'),
    { hidden: true, ...cap(22, 'Look at the secret door') },
  ]);
  assert.deepEqual(ideas.map((i) => i.start), [6, 15]);
  assert.deepEqual(ideas[0].terms, ['mountain', 'lake', 'sunrise']);
  assert.ok(ideas[0].end <= 6 + 3 + 1e-9);
  assert.match(ideas[1].reasons.join(), /points at something/);
});

test('an imported shot whose name matches what is said is offered first', async () => {
  const { suggestBroll, matchAsset } = await load();
  const assets = [{ id: 'a1', name: 'cabin-kitchen.jpg', kind: 'image' }, { id: 'a2', name: 'IMG_0042.MOV', kind: 'video' }];
  const ideas = suggestBroll([cap(4, 'and then we cooked in the kitchen'), cap(12, 'I love you so much')], assets);
  assert.equal(ideas.length, 1);
  assert.equal(ideas[0].match.id, 'a1');
  assert.match(ideas[0].reasons[0], /cabin-kitchen/);
  assert.equal(matchAsset(['nothing', 'here'], assets), null);
  assert.equal(matchAsset(['the', 'mountains'], [{ id: 'm', name: 'Mountain view.png' }]).id, 'm');
});

test('visual terms skip filler and keep Hebrew content words and numbers', async () => {
  const { visualTerms } = await load();
  assert.deepEqual(visualTerms(['basically', 'the', 'red', 'Ferrari', '2024', 'really', 'Ferrari']), ['Ferrari', '2024']);
  assert.deepEqual(visualTerms(['אני', 'אוהב', 'את', 'הים', 'בתל', 'אביב']), ['אוהב', 'הים', 'בתל', 'אביב']);
});
