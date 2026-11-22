const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/timeline.js'), 'utf8').replace(/^export /gm, '');
const scope = vm.createContext({ window: { devicePixelRatio: 1 }, ResizeObserver: class { observe() {} }, requestAnimationFrame: () => 1 });
vm.runInContext(source + '\nglobalThis.Timeline = TimelineView;', scope);
const ids = ['media_' + 'a'.repeat(32), 'text_' + 'b'.repeat(32)];
function fixture(options = {}) {
  const events = [];
  const canvas = { title: '', style: {}, dataset: {}, getContext: () => ({}), setAttribute() {}, addEventListener() {}, focus() {} };
  const scroll = { clientWidth: 1200, clientHeight: 200, scrollLeft: 0, scrollTop: 0, closest: () => null, addEventListener() {} };
  const timeline = new scope.Timeline(canvas, scroll, () => events.push('seek'), () => events.push('range'), () => events.push('source'), {
    getTrackClips: () => [], onMediaAction: (...args) => events.push(args), ...options,
  });
  timeline.project = { id: 'p', revision: 3, draft: { output_duration: 24 }, settings: { fps: 30 }, manual: {
    media_clips: [{ id: ids[0], asset_id: 'v', start: 1, end: 3 }], text_clips: [{ id: ids[1], start: 1.5, end: 3, text: 'Title' }],
  } };
  timeline.loadImages = () => {};
  timeline.setMediaSelection(ids, ids[1]);
  return { timeline, canvas, events };
}
const available = () => '';
for (const duplicate of [false, true]) for (const remove of [false, true]) {
  test(`group help accurately describes duplicate=${duplicate}, remove=${remove}`, () => {
    const { timeline } = fixture({ mediaGroupDuplicateIssue: duplicate ? available : undefined, mediaGroupRemoveIssue: remove ? available : undefined });
    const hint = timeline.mediaGroupActionHint();
    assert.match(hint, /[Mm]ov/);
    assert.equal(/duplicate/i.test(hint), duplicate);
    assert.equal(/remove|Removal/.test(hint), remove);
    if (duplicate) {
      assert.match(hint, /Duplicate at playhead/);
      assert.match(hint, /whole arrangement/);
      assert.match(hint, /timing offsets.*timeline duration/);
      assert.match(hint, /Originals stay unchanged/);
    }
    assert.match(hint, /Select one (?:clip|layer) for other edits/);
  });
}
for (const callback of [null, true, {}, 'ready']) test(`nonfunction duplicate readiness ${JSON.stringify(callback)} is not advertised`, () => {
  const { timeline } = fixture({ mediaGroupDuplicateIssue: callback });
  assert.doesNotMatch(timeline.mediaGroupActionHint(), /duplicate/i);
});
test('help reads only capability and never calls readiness or dispatches a mutation', () => {
  const { timeline, events } = fixture({ mediaGroupDuplicateIssue: () => { throw Error('must not run while describing capability'); }, mediaGroupRemoveIssue: available });
  const before = JSON.stringify(timeline.project);
  assert.match(timeline.mediaGroupActionHint(), /Duplicate at playhead/);
  assert.deepEqual(events, []);
  assert.equal(JSON.stringify(timeline.project), before);
});
test('group Enter explains existing button path without duplicating, seeking or touching selection', () => {
  const { timeline, canvas, events } = fixture({ mediaGroupDuplicateIssue: available });
  let prevented = 0, stopped = 0;
  timeline.keyDown({ key: 'Enter', preventDefault: () => prevented++, stopPropagation: () => stopped++ });
  assert.equal(prevented, 1); assert.equal(stopped, 1);
  assert.match(canvas.title, /Duplicate at playhead/);
  assert.deepEqual(events, []);
  assert.deepEqual(Array.from(timeline.selectedMediaIds()), ids);
});
test('no new canvas duplicate shortcut or fallback is introduced', () => {
  const { timeline, events } = fixture({ mediaGroupDuplicateIssue: available });
  for (const event of [{ key: 'd' }, { key: 'D' }, { key: 'd', ctrlKey: true }, { key: 'd', metaKey: true }]) {
    timeline.keyDown({ preventDefault() {}, stopPropagation() {}, ...event });
  }
  assert.deepEqual(events, []);
  assert.doesNotMatch(source, /onMediaAction\(\s*["']layers_duplicate["']/);
});
test('Index uses the same capability-aware help without changing checkbox selection meaning', () => {
  assert.match(source, /Select \$\{entry\.name\} with other clips/);
  assert.match(source, /label\.title=`Select imported media or custom text\. \$\{timeline\.mediaGroupActionHint\(\)\} Closing the Index retains this selection\./);
});

test('existing group Duplicate shares themed compact and touch-sized buttons without a new tool or layout', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  const group = css.slice(css.indexOf('#studioInspector .layer-group-controls {'), css.indexOf('/* Source assembly reuses'));
  assert.match(group, /\[data-group-duplicate\] \{ min-height:32px;[\s\S]*?color:var\(--paper\); background:var\(--surface-chrome\)/);
  assert.match(group, /@media \(max-width:899px\)[\s\S]*?\[data-group-duplicate\] \{ min-height:42px;/);
  assert.match(group, /button:focus-visible \{ outline:2px solid var\(--focus-ring\)/);
  assert.match(group, /button:disabled \{ opacity:\.45/);
  assert.doesNotMatch(group, /position:fixed|z-index|display:none.*data-group-duplicate/);
});
