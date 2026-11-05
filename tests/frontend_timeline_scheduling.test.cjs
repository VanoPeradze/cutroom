const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const sourcePath = process.env.CUTROOM_TIMELINE_SOURCE
  || path.join(__dirname, '../web/timeline.js');
const source = fs.readFileSync(sourcePath, 'utf8').replace(/^export /gm, '');

function fixture({firstFrameId = 1} = {}) {
  let nextFrame = firstFrameId;
  let requested = 0;
  let cancelled = 0;
  const frames = new Map();
  const ctx = new Proxy({}, { get: () => () => {} });
  const canvas = {
    style: {}, getContext: () => ctx, setAttribute() {}, addEventListener() {},
  };
  const scroll = {
    clientWidth: 600, scrollLeft: 0, closest: () => null, addEventListener() {},
  };
  const scope = vm.createContext({
    window: {devicePixelRatio: 1},
    ResizeObserver: class { observe() {} },
    requestAnimationFrame(callback) {
      const id = nextFrame++;
      requested++;
      frames.set(id, callback);
      return id;
    },
    cancelAnimationFrame(id) { cancelled++; frames.delete(id); },
  });
  vm.runInContext(source + '\nglobalThis.TimelineView = TimelineView;', scope);
  const timeline = new scope.TimelineView(canvas, scroll, () => {});
  timeline.project = { id: 'synthetic', sources: {A: {duration: 120}}, manual: {sequence: {duration: 120}} };
  timeline.mediaLayout = () => ({height: 120, rows: [], caption: null});
  timeline.syncTrackHeaders = () => false;
  timeline.hasTrackLanes = () => false;
  for (const name of ['drawRuler','drawFilmstrip','drawLaneBackgrounds','drawRanges',
    'drawTracks','drawGaps','drawAudioEvidence','drawLayouts','drawWaveform',
    'drawMedia','drawSelection','drawPendingCut','drawLabels','drawHover',
    'drawPlayhead','drawSnapGuide']) timeline[name] = () => {};
  const flush = () => {
    const scheduled = [...frames.entries()];
    frames.clear();
    scheduled.forEach(([, callback]) => callback(0));
  };
  return {timeline, scroll, flush, frames, counts: () => ({requested, cancelled})};
}

test('zoom to selection remains centered if playback requests another draw first', () => {
  const {timeline, scroll, flush} = fixture();
  timeline.selection = {start: 50, end: 60};
  assert.equal(timeline.zoomToSelection(), true);
  timeline.setPlayhead(0); // A playback update can arrive before the next frame.
  flush();
  const geometry = timeline.geometry();
  assert.equal(scroll.scrollLeft, 55 * geometry.px - geometry.viewport / 2);
});

test('multiple updates in the same frame share one pending draw', () => {
  const {timeline, frames, counts, flush} = fixture();
  for (let i = 0; i < 100; i++) timeline.scheduleDraw();
  assert.equal(frames.size, 1);
  assert.deepEqual(counts(), {requested: 1, cancelled: 0});
  flush();
  timeline.scheduleDraw();
  assert.equal(counts().requested, 2, 'the next frame remains schedulable');
});

test('a valid animation frame ID of zero is coalesced too', () => {
  const {timeline, frames, counts} = fixture({firstFrameId: 0});
  timeline.scheduleDraw();
  timeline.scheduleDraw();
  assert.equal(frames.size, 1);
  assert.deepEqual(counts(), {requested: 1, cancelled: 0});
});

test('fit overrides a pending selection zoom', () => {
  const {timeline, scroll, flush} = fixture();
  timeline.selection = {start: 50, end: 60};
  timeline.zoomToSelection();
  timeline.fit();
  flush();
  assert.equal(timeline.zoom, 1);
  assert.equal(scroll.scrollLeft, 0);
});

test('a newer zoom request follows the latest playhead instead of an older selection', () => {
  const {timeline, scroll, flush} = fixture();
  timeline.selection = {start: 50, end: 60};
  timeline.zoomToSelection();
  timeline.setZoom(4);
  timeline.setPlayhead(20);
  flush();
  const geometry = timeline.geometry();
  assert.equal(scroll.scrollLeft, Math.max(0, 20 * geometry.px - geometry.viewport / 2));
});

test('switching projects clears pending selection focus', () => {
  const {timeline, scroll, flush} = fixture();
  timeline.selection = {start: 50, end: 60};
  timeline.zoomToSelection();
  scroll.scrollLeft = 123;
  timeline.loadImages = () => {};
  timeline.setProject({id:'other', sources:{A:{duration:60}}, manual:{sequence:{duration:60}}});
  flush();
  assert.equal(scroll.scrollLeft, 123);
});
