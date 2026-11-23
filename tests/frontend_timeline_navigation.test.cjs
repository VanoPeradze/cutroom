const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../web/timeline.js'), 'utf8').replace(/^export /gm, '');
const scope = vm.createContext({ window: { devicePixelRatio: 1 }, ResizeObserver: class { observe() {} }, requestAnimationFrame: () => 1 });
vm.runInContext(source + '\nglobalThis.api = { TimelineView, parseTimelineTimecode, formatFrameTime, timelineIndexEntries, adjacentTimelineEdit };', scope);
const { TimelineView, parseTimelineTimecode: parse, formatFrameTime: format, timelineIndexEntries: index, adjacentTimelineEdit: adjacent } = scope.api;
const plain = value => JSON.parse(JSON.stringify(value));
const getTracks = (project, slot) => project.manual?.source_tracks?.[slot] || [];
function project() {
  return { id: 'synthetic', settings: { fps: 24 }, sources: { A: { name: 'Interview.mp4', duration: 10 }, B: { name: 'Camera B.mov', duration: 10 } },
    draft: { keep_ranges: [{ start: 0, end: 10 }] },
    manual: { sequence: { duration: 10 }, track_locks: { B: true }, source_tracks: {
      A: [{ id: 'a1', start: 0, end: 3 }, { id: 'a2', start: 5, end: 10 }], B: [{ id: 'b1', start: 2, end: 7 }],
    }, media_clips: [{ id: 'music', asset_id: 'sound', role: 'music', start: 0, end: 9 }, { id: 'insert', asset_id: 'video', start: 3, end: 4 }],
    text_clips: [{ id: 'text_title', kind: 'title', start: 1, end: 2, text: 'Opening title' }] },
    assets: { sound: { kind: 'audio', name: 'Synthetic tone.wav' }, video: { kind: 'video', name: 'Insert.mp4' } },
    editor_captions: [{ id: 's0:w0', start: 4, end: 4.8, text: 'Actual caption', hidden: true }] };
}
function fixture() {
  const events = [], canvas = { style: {}, getContext: () => ({}), setAttribute() {}, addEventListener() {} },
    scroll = { clientWidth: 600, clientHeight: 160, scrollLeft: 0, scrollTop: 0, closest: () => null, addEventListener() {} };
  const timeline = new TimelineView(canvas, scroll, time => { events.push(['seek', time]); timeline.playhead = time; },
    (selection, context) => events.push(['selection', plain(selection), context]), () => { throw Error('Navigation must never edit'); },
    { getTrackClips: getTracks, onTargetChange: target => events.push(['target', target]),
      onMediaSelect: id => events.push(['media', id]), onCaptionSelect: id => events.push(['caption', id]) });
  timeline.project = project();
  return { timeline, events, scroll };
}

test('timecode accepts output frames at every supported project FPS', () => {
  for (const fps of [24, 25, 30, 50, 60]) {
    for (const frame of [0, 1, fps - 1, fps, fps * 62 + 7, fps * 3661 + 2]) {
      assert.ok(Math.abs(parse(format(frame / fps, fps), fps) - frame / fps) < 1e-9);
    }
    assert.equal(parse(`00:00:00:${fps}`, fps), null);
  }
});
test('timecode supports seconds and clock durations without coercing blank or invalid text to zero', () => {
  for (const [value, expected] of [['0', 0], ['8.125', 8.125], [' 01:02.5 ', 62.5], ['120:02', 7202], ['01:02:03.5', 3723.5]]) assert.equal(parse(value), expected);
  for (const value of ['', ' ', null, undefined, '-1', '+2', '1e3', '00:60', '01:60:00', '00:00:60:00', '1.2:02', '0:0:0:1.5', '00;00;00;01', '1:2:3:4:5', 'NaN', 'Infinity', '1.']) assert.equal(parse(value), null, String(value));
  assert.equal(parse('00:00:01:29', 29.97), 1 + 29 / 30, 'unsupported rates use the existing 30 FPS fallback');
});
test('index reflects actual source tracks, media, custom text and automatic captions in chronological order', () => {
  const p = project(), before = JSON.stringify(p), rows = plain(index(p, getTracks));
  assert.equal(rows.length, 7);
  assert.deepEqual(rows.map(row => row.start), [0, 0, 1, 2, 3, 4, 5]);
  assert.equal(rows.find(row => row.id === 'b1').locked, true);
  assert.equal(rows.find(row => row.id === 'music').track, 'Music');
  assert.equal(rows.find(row => row.id === 'text_title').name, 'Opening title');
  assert.equal(rows.find(row => row.id === 's0:w0').track, 'Caption (hidden)');
  assert.equal(new Set(rows.map(row => row.key)).size, rows.length);
  assert.equal(JSON.stringify(p), before, 'building the index is read-only');
});
test('legacy edit ranges remain discoverable while empty and malformed entries do not become fake clips', () => {
  const p = { sources: { A: { name: 'Legacy.mp4', duration: 8 } }, draft: { keep_ranges: [{ start: 1, end: 7 }], edit_points: [3] } };
  assert.deepEqual(plain(index(p, getTracks)).map(row => [row.slot, row.start, row.end]), [['edit', 1, 3], ['edit', 3, 7]]);
  assert.deepEqual(plain(index(null, getTracks)), []);
  p.manual = { sequence: { duration: 8 }, source_tracks: { A: [] }, media_clips: [{ id: 'missing', asset_id: 'no-asset', start: 0, end: 3 }],
    text_clips: [{ id: 'text_invalid', start: 3, end: NaN }, { id: 'text_outside', start: 10, end: 12 }] };
  assert.deepEqual(plain(index(p, getTracks)), []);
});
test('edit navigation finds actual boundaries, including gaps and endpoints, without jumping to the same boundary', () => {
  const clips = [{ start: 5, end: 10 }, { start: 0, end: 3 }, { start: NaN, end: 50 }];
  assert.equal(adjacent(clips, 0, 10, -1), null);
  assert.equal(adjacent(clips, 0, 10, 1), 3);
  assert.equal(adjacent(clips, 3 + 1e-8, 10, -1), 0);
  assert.equal(adjacent(clips, 3, 10, 1), 5);
  assert.equal(adjacent(clips, 10, 10, 1), null);
  assert.equal(adjacent([], 2, 10, -1), 0);
  assert.equal(adjacent([], 2, 10, 1), 10);
  assert.equal(adjacent(clips, 0, 0, 1), null);
  assert.equal(adjacent(clips, 0, 10, 0), null);
});
test('seek and previous/next navigation use the existing callback and never create an edit or undo item', () => {
  const { timeline, events } = fixture(), before = JSON.stringify(timeline.project);
  timeline.setEditTarget('A'); events.length = 0; timeline.cutAnchor = 1;
  assert.equal(timeline.seekNavigation(1 / 24), true);
  assert.equal(timeline.cutAnchor, null);
  assert.equal(timeline.navigateEdit(1), true);
  assert.equal(timeline.playhead, 3);
  assert.equal(timeline.navigateEdit(1), true);
  assert.equal(timeline.playhead, 5);
  assert.equal(timeline.navigateEdit(-1), true);
  assert.equal(timeline.playhead, 3);
  assert.equal(timeline.seekNavigation(10.001), false);
  assert.equal(timeline.seekNavigation(NaN), false);
  assert.equal(timeline.seekNavigation(-1), false);
  assert.ok(events.every(event => event[0] === 'seek'));
  assert.equal(JSON.stringify(timeline.project), before);
});
test('source index selection targets its real lane and opens the existing clip inspector even when the lane is locked', () => {
  const { timeline, events, scroll } = fixture(), before = JSON.stringify(timeline.project);
  timeline.captionSelection = 's0:w0'; timeline.mediaSelection = 'music'; timeline.cutAnchor = 1;
  assert.equal(timeline.selectIndexEntry('source:B:b1'), true);
  assert.equal(timeline.editTarget, 'B');
  assert.deepEqual(plain(timeline.selection), { start: 2, end: 7 });
  assert.equal(timeline.captionSelection, null); assert.equal(timeline.mediaSelection, null);
  assert.ok(events.some(event => event[0] === 'selection' && event[2]?.kind === 'clip'));
  assert.deepEqual(events.at(-1), ['seek', 2]);
  assert.equal(scroll.scrollTop, 62);
  assert.equal(timeline.cutAnchor, null);
  assert.equal(JSON.stringify(timeline.project), before, 'selection does not change a lock or clip');
});
test('media, text and captions route selection to their existing inspector callbacks', () => {
  const { timeline, events } = fixture();
  for (const [key, id, category] of [['media::music', 'music', 'media'], ['media::text_title', 'text_title', 'media'], ['caption::s0:w0', 's0:w0', 'caption']]) {
    events.length = 0;
    assert.equal(timeline.selectIndexEntry(key), true);
    assert.ok(events.some(event => event[0] === category && event[1] === id));
    assert.equal(timeline.selection, null);
    assert.equal(category === 'caption' ? timeline.captionSelection : timeline.mediaSelection, id);
  }
});
test('index keys are re-resolved against the latest project, so removed or retimed clips cannot select stale ranges', () => {
  const { timeline, events } = fixture();
  timeline.project.manual.source_tracks.A[0].start = 1;
  assert.equal(timeline.selectIndexEntry('source:A:a1'), true);
  assert.equal(timeline.selection.start, 1);
  timeline.project.manual.source_tracks.A.shift(); events.length = 0;
  assert.equal(timeline.selectIndexEntry('source:A:a1'), false);
  assert.deepEqual(events, []);
});
test('busy edits, dirty inspectors and active drags prevent navigation from bypassing existing safety guards', () => {
  for (const state of ['editPending', 'gesture', 'dirty']) {
    const { timeline, events } = fixture();
    if (state === 'dirty') timeline.canEdit = () => false;
    else timeline[state] = state === 'gesture' ? { kind: 'move' } : true;
    assert.equal(timeline.seekNavigation(2), false, state);
    assert.equal(timeline.navigateEdit(1), false, state);
    assert.equal(timeline.selectIndexEntry('source:A:a1'), false, state);
    assert.deepEqual(events, []);
  }
});
test('navigation refreshes on project updates and stays absent from source-review timelines', () => {
  const { timeline } = fixture();
  assert.equal(timeline.navigation, null, 'non-DOM test host is supported');
  let refreshes = 0; timeline.navigation = { refresh() { refreshes++; } }; timeline.loadImages = () => {};
  timeline.setProject(timeline.project); assert.equal(refreshes, 1);
  assert.match(source, /if \(timeline\.sourceReview \|\| timeline\.canvas\.id !== "timelineCanvas"/);
});

test('the index uses the existing opaque theme surface and labels frame controls for assistive technology', () => {
  const css = fs.readFileSync(path.join(__dirname, '../web/studio-workbench.css'), 'utf8');
  assert.match(css, /\.timeline-index-dialog\s*\{[^}]*background:var\(--surface-panel\)/);
  assert.match(source, /item\.setAttribute\("aria-label",/);
  assert.match(source, /field\.setAttribute\("aria-description", rate\.title\)/);
  assert.match(source, /status\.setAttribute\("aria-live", "polite"\)/);
});
