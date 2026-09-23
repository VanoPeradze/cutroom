const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../web/timeline.js"), "utf8").replace(/^export /gm, "");
const plain = (value) => JSON.parse(JSON.stringify(value));

function fixture({ compact = true, width = 600, duration = 12, tracks = false } = {}) {
  const listeners = {}, draws = [], notifications = [], seeks = [], edits = [], layouts = [], captures = new Set();
  const context = new Proxy({
    fillText(text, x, y) { draws.push({ text, x, y }); },
    fillRect(x, y, width, height) { draws.push({ fill: this.fillStyle, x, y, width, height }); },
    strokeRect(x, y, width, height) { draws.push({ outline: true, x, y, width, height }); },
    measureText(text) { return { width: text.length * 6 }; },
    createLinearGradient() { return { addColorStop() {} }; },
  }, { get(target, key) { return key in target ? target[key] : () => {}; } });
  const canvas = {
    style: {}, attrs: {}, getContext: () => context,
    setAttribute(name, value) { this.attrs[name] = value; },
    getBoundingClientRect: () => ({ left: 10, top: 20, width }),
    addEventListener(name, callback) { listeners[name] = callback; },
    setPointerCapture(id) { captures.add(id); },
    hasPointerCapture(id) { return captures.has(id); },
    releasePointerCapture(id) { captures.delete(id); },
    focus() {},
  };
  const scroll = {
    clientWidth: width, scrollLeft: 0, closest: () => compact ? {} : null,
    addEventListener() {}, getBoundingClientRect: () => ({ left: 10, top: 20, width }),
  };
  const scope = vm.createContext({
    window: { devicePixelRatio: 1 },
    ResizeObserver: class { observe() {} },
    requestAnimationFrame: () => 1, cancelAnimationFrame() {},
  });
  vm.runInContext(source + "\nglobalThis.TimelineView = TimelineView; globalThis.editableClips = editableClips;", scope);
  const timeline = new scope.TimelineView(canvas, scroll,
    (time) => seeks.push(time), (selection) => notifications.push(plain(selection)), (edit) => edits.push(plain(edit)),
    { onLayoutSelect: (scene) => layouts.push(plain(scene)),
      ...(tracks ? { getTrackClips: (project, slot) => project.manual?.source_tracks?.[slot] || [] } : {}) });
  const project = {
    id: "fixture", sources: { A: { duration } },
    draft: { keep_ranges: [{ start: 0, end: 5 }, { start: 7, end: duration }], edit_points: [2], cuts: [{ start: 5, end: 7 }] },
  };
  if (tracks) {
    project.sources.B = { duration };
    project.manual = { source_tracks: {
      A: [{ id: "a", start: 0, end: duration, source_start: 0 }],
      B: [{ id: "b1", start: 0, end: 3, source_start: 4 }, { id: "b2", start: 8, end: 12, source_start: 0 }],
    } };
  }
  timeline.setProject(project);
  const event = (time, extra = {}) => ({
    button: 0, pointerId: 1, clientX: 10 + time / duration * width,
    clientY: 20 + (compact ? 85 : 140),
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.propagationStopped = true; },
    ...extra,
  });
  return { timeline, project, canvas, scroll, listeners, scope, notifications, seeks, edits, layouts, draws, captures, event };
}

function sequenceFixture({ twoSources = true, compact = true, fps = 60 } = {}) {
  const h = fixture({ tracks: true, duration: 30, compact });
  h.project.settings = { fps };
  h.project.manual.sequence = { version: 1, duration: 12 };
  h.project.manual.source_tracks = {
    A: [{ id: "a1", start: 0, end: 3, source_start: 10 }, { id: "a2", start: 3, end: 6, source_start: 15 }, { id: "a3", start: 8, end: 12, source_start: 0 }],
    B: [{ id: "b1", start: 0, end: 4, source_start: 5 }, { id: "b2", start: 5, end: 12, source_start: 15 }],
  };
  if (!twoSources) delete h.project.sources.B;
  h.project.draft = { keep_ranges: [{ start: 0, end: 12 }], cuts: [], camera_plan: [{ start: 0, end: 12, camera: twoSources ? "stacked" : "A" }] };
  h.timeline.setProject(h.project);
  h.point = (time, y = 80, extra = {}) => h.event(time, { clientX: 10 + time * h.timeline.geometry().px, clientY: 20 + y, ...extra });
  return h;
}

function mediaFixture(options = {}) {
  const h = sequenceFixture(options);
  h.project.assets = {
    video: { kind: 'video', name: 'B-roll', duration: 20 },
    image: { kind: 'image', name: 'Diagram', duration: 0 },
    sound: { kind: 'audio', name: 'Sound', duration: 20, waveform: [.1, .5, 1] },
  };
  h.project.manual.media_clips = [{ id: 'visual', asset_id: 'video', start: 2, end: 6, source_start: 3, video_source_start: 5, speed: 2, role: 'effects' }];
  h.mediaEdits = []; h.mediaPreviews = []; h.mediaSelections = []; h.mediaActions = [];
  h.timeline.onMediaEdit = (id, patch) => h.mediaEdits.push({ id, patch: plain(patch) });
  h.timeline.onMediaPreview = (id, patch) => h.mediaPreviews.push({ id, patch: plain(patch) });
  h.timeline.onMediaSelect = id => h.mediaSelections.push(id);
  h.timeline.onMediaAction = (action, payload) => h.mediaActions.push({ action, ...plain(payload) });
  h.mediaPoint = (time, row = 0, extra = {}) => h.point(time, h.timeline.baseHeight() + row * 46 + 20, extra);
  return h;
}

test('media rows pack nonoverlapping visuals and keep overlapping clips and audio groups distinct', () => {
  const h = mediaFixture();
  h.project.manual.media_clips = [
    { id: 'v1', asset_id: 'video', start: 1, end: 4, speed: 1 },
    { id: 'image', asset_id: 'image', start: 4, end: 6, speed: 1 },
    { id: 'v2', asset_id: 'video', start: 3, end: 5, speed: 1 },
    { id: 'music', asset_id: 'sound', start: 0, end: 6, role: 'music', speed: 1 },
    { id: 'voice', asset_id: 'sound', start: 2, end: 3, role: 'voice', speed: 1 },
    { id: 'missing', asset_id: 'unknown', start: 0, end: 12 },
  ];
  const before = JSON.stringify(h.project), rows = plain(h.timeline.mediaRows());
  assert.deepEqual(rows.map(row => [row.group, row.clips.map(clip => clip.id)]), [
    ['visual', ['v1', 'image']], ['visual', ['v2']], ['music', ['music']], ['voice', ['voice']],
  ]);
  assert.deepEqual(rows.map(row => [row.top, row.bottom]), [[230,276],[276,322],[322,368],[368,414]]);
  assert.equal(h.timeline.mediaAtEvent(h.mediaPoint(4, 0)).clip.id, 'image', 'shared endpoint belongs to following clip');
  assert.equal(h.timeline.mediaAtEvent(h.mediaPoint(3.5, 1)).clip.id, 'v2');
  assert.equal(h.timeline.mediaAtEvent(h.mediaPoint(6, 0)), null);
  assert.equal(h.timeline.mediaAtEvent(h.point(3, 229)), null, 'base track never hits added media');
  assert.equal(JSON.stringify(h.project), before);
  h.timeline.sourceReview = true;
  assert.deepEqual(plain(h.timeline.mediaRows()), []);
});

for (const twoSources of [false, true]) {
  test(`media rows and captions expand the canvas below ${twoSources ? 'both sources' : 'source A'}`, () => {
    const h = mediaFixture({ twoSources });
    h.project.settings.captions = true;
    h.project.analysis = { audio_source: 'A', transcript: { segments: [{ start: 10.5, end: 11, text: 'Speech' }] } };
    h.timeline.draw();
    const base = twoSources ? 230 : 174;
    assert.equal(h.canvas.style.height, `${base + 46 + 30}px`);
    assert.equal(h.canvas.height, base + 46 + 30);
    const caption = h.draws.find(draw => draw.text === 'Cc Speech');
    assert.ok(caption);
    assert.equal(caption.y, base + 46 + 17);
    assert.ok(Math.abs(caption.x - (.5 * h.timeline.geometry().px + 4)) < 1e-8, 'captions follow original speech mapping');
    assert.equal(h.timeline.mediaAtEvent(h.point(.75, base + 46 + 12)), null, 'caption lane is not a media clip');
    h.project.settings.captions = false;
    h.timeline.draw();
    assert.equal(h.canvas.height, base + 46 + 30, 'burned captions remain visible without SRT export');
    h.project.settings.burn_captions = false;
    h.timeline.draw();
    assert.equal(h.canvas.height, base + 46);
  });
}

test('media drag previews and commits only the added clip while preserving source lanes', () => {
  const h = mediaFixture(), before = JSON.stringify(h.project);
  h.timeline.pointerDown(h.mediaPoint(4));
  assert.deepEqual(h.mediaSelections, ['visual']);
  assert.equal(h.timeline.gesture.kind, 'media');
  h.timeline.pointerMove(h.mediaPoint(7));
  assert.equal(h.mediaPreviews.at(-1).id, 'visual');
  assert.ok(Math.abs(h.mediaPreviews.at(-1).patch.start - 5) < 1e-8);
  assert.equal(h.mediaPreviews.at(-1).patch.end, 9);
  h.timeline.pointerUp(h.mediaPoint(7));
  assert.equal(h.mediaEdits.length, 1);
  assert.equal(h.mediaEdits[0].id, 'visual');
  assert.ok(Math.abs(h.mediaEdits[0].patch.start - 5) < 1e-8);
  assert.equal(h.mediaEdits[0].patch.end, 9);
  assert.deepEqual(h.mediaPreviews.at(-1), { id: 'visual', patch: null });
  assert.deepEqual(h.edits, []);
  assert.equal(h.captures.size, 0);
  assert.equal(JSON.stringify(h.project), before);
});

test('media edge trim keeps independent picture and audio in-points', () => {
  const h = mediaFixture(), before = JSON.stringify(h.project);
  h.timeline.pointerDown(h.mediaPoint(2.01));
  assert.equal(h.timeline.gesture.edge, 'start');
  h.timeline.pointerMove(h.mediaPoint(3.01));
  assert.ok(Math.abs(h.mediaPreviews.at(-1).patch.video_source_start - 7) < 1e-8);
  h.timeline.pointerUp(h.mediaPoint(3.01));
  const patch = h.mediaEdits[0].patch;
  assert.ok(Math.abs(patch.start - 3) < 1e-8);
  assert.ok(Math.abs(patch.source_start - 4) < 1e-8);
  assert.equal('video_source_start' in patch, false, 'the server derives picture time; public update must not send the private field');
  assert.equal(JSON.stringify(h.project), before);
  const tail = mediaFixture();
  tail.timeline.pointerDown(tail.mediaPoint(5.99));
  assert.equal(tail.timeline.gesture.edge, 'end');
  tail.timeline.pointerMove(tail.mediaPoint(7.99));
  tail.timeline.pointerUp(tail.mediaPoint(7.99));
  assert.ok(Math.abs(tail.mediaEdits[0].patch.end - 8) < 1e-8);
});

test('media release uses its final position even when the browser coalesces pointer moves', () => {
  const h = mediaFixture();
  h.timeline.pointerDown(h.mediaPoint(4));
  h.timeline.pointerUp(h.mediaPoint(7));
  assert.equal(h.mediaEdits.length, 1);
  assert.equal(h.mediaEdits[0].id, 'visual');
  assert.ok(Math.abs(h.mediaEdits[0].patch.start - 5) < 1e-8);
  assert.equal(h.mediaEdits[0].patch.end, 9);
});

test('foreign pointers cannot preview or commit a media gesture', () => {
  const h = mediaFixture();
  h.timeline.pointerDown(h.mediaPoint(4));
  h.timeline.pointerMove(h.mediaPoint(7, 0, { pointerId: 2 }));
  h.timeline.pointerUp(h.mediaPoint(7, 0, { pointerId: 2 }));
  assert.ok(h.timeline.gesture);
  assert.deepEqual(h.mediaPreviews, []);
  assert.deepEqual(h.mediaEdits, []);
  h.timeline.pointerCancel(h.mediaPoint(4));
  assert.equal(h.captures.size, 0);
});

test('cancelled media drag clears the preview and preserves the existing edit selection', () => {
  const h = mediaFixture();
  h.timeline.setSelection({ start: 1, end: 2 }, false, true);
  h.timeline.pointerDown(h.mediaPoint(4));
  h.timeline.pointerMove(h.mediaPoint(7));
  h.timeline.pointerCancel(h.mediaPoint(7));
  assert.deepEqual(plain(h.timeline.selection), { start: 1, end: 2 });
  assert.equal(h.timeline.selectionIsRange, true);
  assert.deepEqual(h.mediaPreviews.at(-1), { id: 'visual', patch: null });
  assert.deepEqual(h.mediaEdits, []);
  assert.equal(h.timeline.gesture, null);
});

test('media split and delete target only the selected added clip and honor the busy guard', () => {
  const h = mediaFixture();
  h.timeline.setTool('blade');
  h.timeline.pointerDown(h.mediaPoint(4));
  h.timeline.pointerUp(h.mediaPoint(4));
  assert.deepEqual(h.mediaActions, [{ action: 'media_split', clip_id: 'visual', time: 4 }]);
  h.timeline.keyDown(h.event(0, { key: 'Delete' }));
  assert.deepEqual(h.mediaActions.at(-1), { action: 'media_remove', clip_id: 'visual' });
  h.timeline.canEdit = () => false;
  h.timeline.pointerDown(h.mediaPoint(4));
  h.timeline.keyDown(h.event(0, { key: 'Delete' }));
  assert.equal(h.mediaActions.length, 2);
  assert.deepEqual(h.edits, []);
});

test('media trims obey the backend minimum and cannot extend beyond original sound samples', () => {
  const tail = mediaFixture();
  tail.project.assets.video.duration = 7; // Source in 3 + existing span 4 already reaches EOF.
  tail.timeline.pointerDown(tail.mediaPoint(5.99));
  tail.timeline.pointerUp(tail.mediaPoint(10));
  assert.deepEqual(tail.mediaEdits, [], 'a clamped unchanged edge needs no save');
  const shortest = mediaFixture();
  shortest.timeline.pointerDown(shortest.mediaPoint(5.99));
  shortest.timeline.pointerUp(shortest.mediaPoint(0));
  assert.ok(Math.abs(shortest.mediaEdits[0].patch.end - 2.08) < 1e-8);
  const head = mediaFixture();
  head.timeline.pointerDown(head.mediaPoint(2.01));
  head.timeline.pointerUp(head.mediaPoint(10));
  assert.ok(Math.abs(head.mediaEdits[0].patch.start - 5.92) < 1e-8);
  assert.ok(Math.abs(head.mediaEdits[0].patch.source_start - 6.92) < 1e-8);
});

test('image trims can reveal earlier timeline time and shortening clips keeps fades inside the span', () => {
  const image = mediaFixture();
  image.project.manual.media_clips[0] = { id: 'visual', asset_id: 'image', start: 2, end: 6, source_start: 0, speed: 1 };
  image.timeline.pointerDown(image.mediaPoint(2.01));
  image.timeline.pointerUp(image.mediaPoint(0));
  assert.deepEqual(image.mediaEdits, [{ id: 'visual', patch: { start: 0 } }]);
  const sound = mediaFixture();
  Object.assign(sound.project.manual.media_clips[0], { fade_in: 1, fade_out: 1 });
  sound.timeline.pointerDown(sound.mediaPoint(5.99));
  sound.timeline.pointerUp(sound.mediaPoint(2.99));
  const patch = sound.mediaEdits[0].patch;
  assert.ok(Math.abs(patch.end - 3) < 1e-8);
  assert.ok(Math.abs(patch.fade_in - .5) < 1e-8);
  assert.ok(Math.abs(patch.fade_out - .5) < 1e-8);
});

test('a plain media click does not save and protected keyboard events cannot remove the clip', () => {
  const h = mediaFixture();
  h.timeline.pointerDown(h.mediaPoint(4));
  h.timeline.pointerUp(h.mediaPoint(4));
  assert.deepEqual(h.mediaEdits, []);
  for (const extra of [{ defaultPrevented: true }, { isComposing: true }, { repeat: true }, { ctrlKey: true }, { metaKey: true }, { altKey: true }]) {
    h.timeline.keyDown(h.event(0, { key: 'Delete', ...extra }));
  }
  h.timeline.editPending = true;
  h.timeline.keyDown(h.event(0, { key: 'Delete' }));
  assert.deepEqual(h.mediaActions, []);
});

test('media blade rejects fragments shorter than .08 seconds and releases pointer capture', () => {
  const h = mediaFixture();
  h.timeline.setTool('blade');
  for (const time of [2.02, 5.98]) {
    h.timeline.pointerDown(h.mediaPoint(time));
    h.timeline.pointerUp(h.mediaPoint(time));
  }
  assert.deepEqual(h.mediaActions, []);
  assert.equal(h.captures.size, 0);
});

test('zoom in and out center the yellow playhead, including when it was scrolled offscreen',()=>{
  const h=sequenceFixture();h.timeline.setPlayhead(7);h.timeline.selectRange(1,2);
  const original=JSON.stringify(h.project);
  for (const zoom of [4,8,2,16,3]) {
    h.scroll.scrollLeft=0;h.timeline.setZoom(zoom);h.timeline.draw();
    const g=h.timeline.geometry();
    assert.ok(Math.abs(7*g.px-h.scroll.scrollLeft-g.viewport/2)<1e-6);
    assert.equal(h.timeline.playhead,7);assert.deepEqual(plain(h.timeline.selection),{start:1,end:2});
  }
  assert.equal(JSON.stringify(h.project),original);assert.deepEqual(h.edits,[]);assert.deepEqual(h.seeks,[]);
});

test('wheel zoom follows the playhead regardless of mouse position',()=>{
  for (const x of [10,200,610]) {
    const h=fixture();h.timeline.setPlayhead(8);h.timeline.setZoom(4);h.timeline.draw();
    for (const delta of [-10,10]) {
      h.timeline.handleWheel({ctrlKey:true,deltaY:delta,clientX:x,preventDefault(){}});h.timeline.draw();
      const g=h.timeline.geometry();assert.ok(Math.abs(8*g.px-h.scroll.scrollLeft-300)<1e-6);
    }
  }
});

test('rapid zoom and playback redraws cannot cancel playhead focus',()=>{
  const h=sequenceFixture();h.timeline.setPlayhead(5);
  h.timeline.setZoom(2);h.timeline.setZoom(4);h.timeline.setZoom(8);
  h.timeline.setPlayhead(7);h.timeline.scheduleDraw();h.timeline.draw();
  assert.ok(Math.abs(7*h.timeline.geometry().px-h.scroll.scrollLeft-300)<1e-6);
  assert.equal(h.timeline.zoomFocusPending,false);
  h.scroll.scrollLeft=0;h.timeline.draw();assert.equal(h.scroll.scrollLeft,0,'ordinary redraws must still allow manual scrolling');
});

test('zoom near either end clamps safely and Fit still shows the whole recording',()=>{
  const h=fixture();
  for (const time of [0,12]) {
    h.timeline.setPlayhead(time);h.timeline.setZoom(4);h.timeline.draw();
    const g=h.timeline.geometry();assert.equal(h.scroll.scrollLeft,time===0 ? 0 : g.width-g.viewport);
    h.timeline.fit();h.timeline.draw();assert.equal(h.scroll.scrollLeft,0);
  }
  h.timeline.setZoom(8);h.timeline.fit();h.timeline.draw();
  assert.equal(h.timeline.zoomFocusPending,false);assert.equal(h.timeline.zoom,1);
});

test('explicit zoom-to-selection overrides pending playhead focus',()=>{
  const h=sequenceFixture();h.timeline.setPlayhead(9);h.timeline.setZoom(8);h.timeline.selectRange(1,2);
  assert.equal(h.timeline.zoomToSelection(),true);assert.equal(h.timeline.zoomFocusPending,false);
});

test('original review keeps full duration, selects removed footage and quantizes custom ranges',()=>{
  const h=fixture({compact:false});
  h.timeline.sourceReview=true;h.project.__sourceReview=true;h.project.settings={fps:60};h.timeline.draw();
  assert.equal(h.canvas.style.height,'180px');
  assert.deepEqual(plain(h.timeline.editLane()),{top:72,bottom:100});
  assert.equal(h.timeline.geometry().duration,12);
  h.timeline.pointerDown(h.event(6,{clientY:105}));h.timeline.pointerUp(h.event(6,{clientY:105}));
  assert.deepEqual(plain(h.timeline.selection),{start:5,end:7});
  assert.ok(Math.abs(h.timeline.snappedTime(1.109,{})-1.1166666666666667)<1e-9);
  assert.deepEqual(plain(h.timeline.selectRange(5,5+1/60)),{start:5,end:5+1/60});
  assert.ok(h.draws.some(d=>d.text==='REMOVED'));
});

test('original Fit filmstrip samples the end as well as the beginning of long footage',()=>{
  const h=fixture();h.timeline.sourceReview=true;
  h.timeline.images=Array.from({length:36},(_,id)=>({id,width:160,height:90}));
  const samples=[];h.timeline.context.drawImage=image=>samples.push(image.id);
  h.timeline.drawFilmstrip(h.timeline.context,600);
  assert.ok(samples.length<=7);assert.ok(samples[0]<5);assert.ok(samples.at(-1)>30);
});

test("sequence starts Together and its blocks respect both source cuts but not layout changes", () => {
  const h = sequenceFixture();
  h.project.draft.camera_plan = [{ start: 0, end: 1, camera: "A" }, { start: 1, end: 12, camera: "stacked" }];
  assert.equal(h.timeline.editTarget, "edit");
  assert.deepEqual(plain(h.timeline.targetClips()), [
    { start: 0, end: 3, index: 0 }, { start: 3, end: 4, index: 1 },
    { start: 4, end: 5, index: 2 }, { start: 5, end: 6, index: 3 },
    { start: 6, end: 8, index: 4 }, { start: 8, end: 12, index: 5 },
  ]);
  for (const y of [60, 110]) {
    h.timeline.pointerDown(h.point(3.5, y)); h.timeline.pointerUp(h.point(3.5, y));
    assert.equal(h.timeline.editTarget, "edit", "touching a track must not unlink Together");
    assert.deepEqual(plain(h.timeline.selection), { start: 3, end: 4 });
  }
  assert.deepEqual(h.edits, []);
});

test("Together drag moves one atomic time block with a linked insertion preview", () => {
  for (const y of [60, 110]) {
    const h = sequenceFixture(), original = JSON.stringify(h.project);
    h.timeline.pointerDown(h.point(3.5, y));
    assert.equal(h.timeline.gesture.kind, "move");
    h.timeline.pointerMove(h.point(6.5, y)); h.timeline.draw();
    const ghosts = h.draws.filter((draw) => draw.fill === "rgba(185,244,213,.6)");
    assert.deepEqual(ghosts.map((draw) => draw.y), [36, 92]);
    assert.ok(h.draws.some((draw) => draw.text === "Move together · 00:06.0"));
    h.timeline.pointerUp(h.point(6.5, y));
    assert.deepEqual(h.edits, [{ action: "sequence_move_range", start: 3, end: 4, to: 6 }]);
    assert.deepEqual(h.notifications, [{ start: 3, end: 4 }]);
    assert.equal(JSON.stringify(h.project), original, "the API performs the atomic synchronized reorder");
  }
});

test("Together supports backward moves and clamps end drops without mutating either source lane", () => {
  for (const [origin, release, expected] of [[9, 2, 1], [1, 14, 9]]) {
    const h = sequenceFixture();
    h.timeline.pointerDown(h.point(origin, 110)); h.timeline.pointerUp(h.point(release, 110));
    const block = origin === 9 ? { start: 8, end: 12 } : { start: 0, end: 3 };
    assert.deepEqual(h.edits, [{ action: "sequence_move_range", ...block, to: expected }]);
  }
});

test("pixel-based sequence dragging lands on output frames without sub-frame leftovers", () => {
  for (const fps of [30, 60]) {
    for (const target of ["edit", "A"]) {
      const h = sequenceFixture({ fps });
      h.timeline.setEditTarget(target);
      h.timeline.pointerDown(h.point(.5038, 60));
      h.timeline.pointerUp(h.point(6.50295, 60));
      const edit = h.edits[0];
      assert.equal(target === "edit" ? edit.to : edit.start, 6);
    }
  }
});

test("moving a cut near the end cannot create a black tail", () => {
  for (const release of [11, 12]) {
    const h = sequenceFixture();
    h.timeline.pointerDown(h.point(1, 110)); h.timeline.pointerUp(h.point(release, 110));
    assert.deepEqual(h.edits, [{ action: "sequence_move_range", start: 0, end: 3, to: 9 }]);
  }
  const h = sequenceFixture();
  h.timeline.pointerDown(h.point(1, 110)); h.timeline.pointerUp(h.point(13, 110));
  assert.deepEqual(h.edits, [{ action: "sequence_move_range", start: 0, end: 3, to: 9 }], "a normal drop appends without adding empty time");
});

test("Cut tool can drag an individual cut without silently swallowing the gesture", () => {
  for (const target of ["edit", "A", "B"]) {
    const h = sequenceFixture();
    h.timeline.setEditTarget(target); h.timeline.setTool("blade");
    h.timeline.pointerDown(h.point(1, target === "B" ? 110 : 60));
    h.timeline.pointerUp(h.point(6, target === "B" ? 110 : 60));
    assert.equal(h.edits.length, 1);
    assert.equal(h.edits[0].action, target === "edit" ? "sequence_move_range" : "track_move");
    assert.equal(target === "edit" ? h.edits[0].to : h.edits[0].start, 5);
    assert.ok(h.timeline.selection.end <= 4, "only the clicked cut, not the full recording");
  }
});

test("Together selection survives explicit scope changes and other lane clicks never switch the scope", () => {
  const h = sequenceFixture();
  h.timeline.selectRange(1, 2);
  for (const target of ["A", "B", "edit"]) {
    h.timeline.setEditTarget(target);
    assert.deepEqual(plain(h.timeline.selection), { start: 1, end: 2 });
  }
  h.timeline.setEditTarget("A");
  h.timeline.pointerDown(h.point(3.5, 110)); h.timeline.pointerUp(h.point(3.5, 110));
  assert.equal(h.timeline.editTarget, "A");
  assert.deepEqual(h.edits, []);
  h.timeline.setEditTarget("B");
  h.timeline.pointerDown(h.point(3.5, 60)); h.timeline.pointerUp(h.point(3.5, 60));
  assert.equal(h.timeline.editTarget, "B");
});

test("Together Range crosses both tracks and complete gaps, without moving source clips", () => {
  const h = sequenceFixture();
  h.project.manual.source_tracks.B = [{ id: "b", start: 0, end: 3, source_start: 0 }];
  h.timeline.setTool("range");
  h.timeline.pointerDown(h.point(5.5, 110)); h.timeline.pointerUp(h.point(8.5, 110));
  assert.ok(Math.abs(h.notifications[0].start - 5.5) < 1e-9);
  assert.ok(Math.abs(h.notifications[0].end - 8.5) < 1e-9);
  assert.equal(h.timeline.editTarget, "edit");
  h.timeline.draw();
  const tint = h.draws.find((draw) => draw.fill === "rgba(68,185,198,.14)");
  assert.ok(tint.y <= 36 && tint.y + tint.height >= 140, "range highlight spans A and B");
  assert.deepEqual(h.edits, []);
  h.timeline.setSelection(null, false); h.timeline.setTool("select");
  h.timeline.pointerDown(h.point(7, 60)); h.timeline.pointerUp(h.point(7, 60));
  assert.deepEqual(plain(h.timeline.selection), { start: 6, end: 8 }, "an empty gap can be removed with the same range tools");
  assert.deepEqual(h.edits, [], "gaps are not phantom draggable footage");
});

test("Together Cut out can close a fully empty gap while independent Cut out cannot remove missing media", () => {
  const h = sequenceFixture();
  h.project.manual.source_tracks.B = [];
  h.timeline.setTool("remove_between"); h.timeline.cutOutAt(6); h.timeline.cutOutAt(8);
  assert.deepEqual(h.edits, [{ action: "delete_range", start: 6, end: 8 }]);
  h.timeline.setEditTarget("A"); h.timeline.cutOutAt(6);
  assert.equal(h.timeline.cutOutAt(8), false);
  assert.equal(h.edits.length, 1);
});

test("Together Blade splits all sources even at a boundary that only A already has", () => {
  const h = sequenceFixture(); h.timeline.setTool("blade");
  h.timeline.pointerDown(h.point(3, 60)); h.timeline.pointerUp(h.point(3, 60));
  assert.deepEqual(h.edits, [{ action: "split", time: 3, target: "edit" }]);
  h.timeline.pointerDown(h.point(1, 110)); h.timeline.pointerUp(h.point(1, 110));
  assert.deepEqual(h.edits.at(-1), { action: "split", time: 1, target: "edit" });
  h.timeline.pointerDown(h.point(0, 110)); h.timeline.pointerUp(h.point(0, 110));
  assert.equal(h.edits.length, 2, "edges cannot create empty clips");
});

test("Together Blade refuses a valid A split when it would create a sub-frame fragment on B", () => {
  for (const partial of [{ start: 0, end: 2.001 }, { start: 1.999, end: 4 }]) {
    const h = sequenceFixture();
    h.project.manual.source_tracks.B = [{ id: "b", ...partial, source_start: 0 }];
    h.timeline.setTool("blade");
    assert.equal(h.timeline.canSplitAt(2), false);
    h.timeline.pointerMove(h.point(2, 60));
    assert.equal(h.canvas.style.cursor, "not-allowed");
    h.timeline.pointerDown(h.point(2, 60)); h.timeline.pointerUp(h.point(2, 60));
    assert.deepEqual(h.edits, [], "no partial linked split is submitted");
    h.timeline.setEditTarget("A");
    assert.equal(h.timeline.canSplitAt(2), true, "independent A editing is unaffected");
    h.timeline.pointerDown(h.point(2, 60)); h.timeline.pointerUp(h.point(2, 60));
    assert.deepEqual(h.edits, [{ action: "split", time: 2, target: "A" }]);
  }
});

test("Together Blade permits other-track gaps and exact cuts but does not repeat an aligned cut", () => {
  const h = sequenceFixture();
  h.project.manual.source_tracks.B = [{ id: "b", start: 2, end: 4, source_start: 0 }];
  assert.equal(h.timeline.canSplitAt(1), true, "B gap requires no split");
  assert.equal(h.timeline.canSplitAt(2), true, "B starts exactly here and A can split");
  h.project.manual.source_tracks.A = [{ id: "a1", start: 0, end: 2, source_start: 0 }, { id: "a2", start: 2, end: 3, source_start: 5 }];
  assert.equal(h.timeline.canSplitAt(2), false, "both tracks already have this boundary");
});

test("cancelling a Together reorder restores the prior range and does not submit any edit", () => {
  const h = sequenceFixture(); h.timeline.selectRange(4, 5); h.notifications.length = 0;
  h.timeline.pointerDown(h.point(1, 110)); h.timeline.pointerMove(h.point(6, 110));
  h.timeline.pointerCancel(h.point(6, 110));
  assert.deepEqual(plain(h.timeline.selection), { start: 4, end: 5 });
  assert.deepEqual(h.notifications, [{ start: 4, end: 5 }]);
  assert.deepEqual(h.edits, []);
});

test("an empty sequence stays finite and editable after removing all footage", () => {
  const h = sequenceFixture();
  h.project.manual.sequence.duration = 0;
  h.project.manual.source_tracks = { A: [], B: [] }; h.project.draft.keep_ranges = [];
  h.timeline.setProject(h.project); h.timeline.draw();
  assert.deepEqual(plain(h.timeline.targetClips()), []);
  assert.equal(h.canvas.attrs["aria-valuemax"], "0");
  assert.ok(Number.isFinite(h.timeline.geometry().px) && h.timeline.geometry().px > 0);
  h.timeline.pointerDown(h.point(1)); h.timeline.pointerUp(h.point(1));
  assert.equal(h.timeline.selection, null);
  assert.deepEqual(h.edits, []);
  assert.equal(h.timeline.editTarget, "edit");
});

test("sequence Select grabs and moves a clip into occupied time using insert semantics", () => {
  const h = sequenceFixture();
  h.timeline.setEditTarget("A");
  h.timeline.pointerMove(h.point(1));
  assert.equal(h.canvas.style.cursor, "grab");
  const original = JSON.stringify(h.project);
  h.timeline.pointerDown(h.point(1));
  assert.equal(h.canvas.style.cursor, "grabbing");
  assert.deepEqual(h.notifications, []);
  h.timeline.pointerMove(h.point(5));
  assert.equal(h.timeline.gesture.collision, false, "occupied sequence time must not be rejected as overlap");
  h.timeline.pointerUp(h.point(5));
  assert.deepEqual(h.edits, [{ action: "track_move", slot: "A", clip_id: "a1", start: 4 }]);
  assert.deepEqual(h.notifications, [{ start: 0, end: 3 }]);
  assert.equal(JSON.stringify(h.project), original, "backend owns atomic insertion and shifting");
});

test("sequence exposes a trim tail but normal moves append without empty time", () => {
  const h = sequenceFixture();
  h.timeline.setEditTarget("A");
  assert.equal(h.scope.timelineDuration(h.project), 12, "source A is30s but sequence is12s");
  assert.equal(h.canvas.attrs["aria-valuemax"], "12");
  assert.equal(h.timeline.geometry().duration, 13);
  assert.equal(h.timeline.timeFromEvent(h.point(12.8)), 12.8);
  h.timeline.pointerDown(h.point(1)); h.timeline.pointerUp(h.point(12.8));
  assert.deepEqual(h.edits, [{ action: "track_move", slot: "A", clip_id: "a1", start: 9 }]);
  assert.equal(h.timeline.selectableRangeAt(12.8), null, "blank tail must not become phantom source footage");
  h.timeline.selectRange(10, 12.8);
  assert.deepEqual(plain(h.timeline.selection), { start: 10, end: 12 });
});

test('white edge drag extends source A into a gap without moving the whole cut',()=>{
  const h=sequenceFixture();h.timeline.setEditTarget('A');h.timeline.selectRange(3,6);
  const before=JSON.stringify(h.project);
  h.timeline.pointerDown(h.point(6,60));assert.equal(h.timeline.gesture.kind,'trim');
  h.timeline.pointerMove(h.point(9,60));assert.equal(h.canvas.style.cursor,'ew-resize');
  assert.deepEqual(plain(h.timeline.selection),{start:3,end:8},'next clip stops the extension');
  h.timeline.pointerUp(h.point(9,60));
  assert.deepEqual(h.edits,[{action:'sequence_trim_edge',start:3,end:6,edge:'end',time:8,slot:'A'}]);
  assert.equal(JSON.stringify(h.project),before,'API owns source changes');
});

test('left edge reveals earlier source frames and stops at the previous clip',()=>{
  const h=sequenceFixture();h.project.manual.source_tracks.A[2].source_start=20;
  h.timeline.setEditTarget('A');h.timeline.selectRange(8,12);
  h.timeline.pointerDown(h.point(8,60));h.timeline.pointerUp(h.point(5,60));
  assert.deepEqual(h.edits,[{action:'sequence_trim_edge',start:8,end:12,edge:'start',time:6,slot:'A'}]);
});

test('edge at source-media limit never invents frames; range tool stays selection-only',()=>{
  const h=sequenceFixture();h.timeline.setEditTarget('A');h.timeline.selectRange(8,12);
  h.timeline.pointerDown(h.point(8,60));h.timeline.pointerUp(h.point(6,60));
  assert.deepEqual(h.edits,[],'source starts at zero so no left extension exists');
  h.timeline.setTool('range');h.timeline.selectRange(3,6);
  h.timeline.pointerDown(h.point(6,60));h.timeline.pointerUp(h.point(7,60));
  assert.deepEqual(h.edits,[],'Range edges do not trim media');
});

test('Together edges carry scope and Escape cancels a trim without saving',()=>{
  const h=sequenceFixture();h.timeline.selectRange(0,3);
  h.timeline.pointerDown(h.point(3,60));h.timeline.pointerUp(h.point(2,60));
  assert.deepEqual(h.edits,[{action:'sequence_trim_edge',start:0,end:3,edge:'end',time:2}]);
  h.edits.length=0;h.timeline.selectRange(0,3);
  h.timeline.pointerDown(h.point(3,60));h.timeline.pointerMove(h.point(2,60));
  h.timeline.keyDown({key:'Escape',preventDefault(){},stopPropagation(){}});
  assert.deepEqual(plain(h.timeline.selection),{start:0,end:3});assert.equal(h.timeline.gesture,null);assert.deepEqual(h.edits,[]);
});

test('gap detection retains intervals covered by either source',()=>{
  const h=sequenceFixture();
  assert.deepEqual(plain(h.scope.sequenceGaps(h.project,h.timeline.getTrackClips)),[]);
  assert.deepEqual(plain(h.scope.sequenceGaps(h.project,h.timeline.getTrackClips,'A')),[{start:6,end:8}]);
  h.project.manual.source_tracks.B[1].start=9;
  assert.deepEqual(plain(h.scope.sequenceGaps(h.project,h.timeline.getTrackClips)),[{start:6,end:8}]);
});

test('a one-frame 60 FPS cut cannot be pushed into its neighbor after switching to 30 FPS',()=>{
  const h=sequenceFixture({fps:30});h.timeline.setEditTarget('A');
  h.project.manual.source_tracks.A=[{id:'one',start:0,end:1/60,source_start:0},{id:'next',start:1/60,end:6,source_start:5}];
  assert.equal(h.timeline.trimEdgeTime(h.project.manual.source_tracks.A[0],'end',0),1/60);
});

for (const compact of [true, false]) {
  test(`sequence lane hitboxes match visible tracks and never create a phantom B (${compact ? "compact" : "full"})`, () => {
    const h = sequenceFixture({ compact });
    assert.deepEqual(plain(h.timeline.trackLane("A")), { top: 36, bottom: 84 });
    assert.deepEqual(plain(h.timeline.trackLane("B")), { top: 92, bottom: 140 });
    for (const [y,target] of [[35,null],[36,"A"],[84,"A"],[85,null],[92,"B"],[140,"B"],[141,null],[152,null],[174,null],[198,null]]) {
      assert.equal(h.timeline.targetAtEvent(h.point(1,y)), target, `y=${y}`);
    }
    h.timeline.setEditTarget("B");
    h.timeline.pointerDown(h.point(1,160)); h.timeline.pointerUp(h.point(1,160));
    assert.equal(h.timeline.editTarget,"B", "layout changes keep the active source track");
    assert.deepEqual(h.layouts,[{start:0,end:12,camera:"stacked"}]);
    h.timeline.draw(); assert.equal(h.canvas.height,230);
    delete h.project.sources.B; h.timeline.setProject(h.project);
    assert.equal(h.timeline.editTarget,"edit");
    h.timeline.pointerDown(h.point(1,110)); h.timeline.pointerUp(h.point(1,110));
    assert.equal(h.timeline.editTarget,"edit");
    assert.equal(h.timeline.targetAtEvent(h.point(1,110)),null);
    assert.equal(h.timeline.inLayoutLane(h.point(1,96)),true);
    assert.equal(h.timeline.inLayoutLane(h.point(1,118)),true);
    assert.equal(h.timeline.inLayoutLane(h.point(1,119)),false);
    h.timeline.setEditTarget("B"); assert.equal(h.timeline.editTarget,"edit");
    h.timeline.draw(); assert.equal(h.canvas.height,174);
    assert.equal(h.timeline.inSelectionArea(h.point(1,175)),false);
  });
}

test("sequence Range and Shift select partial footage instead of moving clips", () => {
  for (const shiftKey of [false,true]) {
    const h=sequenceFixture();
    h.timeline.setTool(shiftKey?"select":"range");
    h.timeline.pointerDown(h.point(1,80,{shiftKey}));
    h.timeline.pointerUp(h.point(2,80,{shiftKey}));
    assert.deepEqual(h.notifications,[{start:1,end:2}]);
    assert.deepEqual(h.edits,[]);
  }
});

test("a persisted60fps frame remains selectable and zoomable after switching to30fps", () => {
  const h=sequenceFixture({twoSources:false,fps:30});
  h.project.manual.source_tracks.A=[{id:"one-frame",start:1,end:1+1/60,source_start:2}];
  h.timeline.setProject(h.project);
  h.timeline.pointerDown(h.point(1+1/120)); h.timeline.pointerUp(h.point(1+1/120));
  assert.deepEqual(h.notifications,[{start:1,end:1+1/60}]);
  assert.equal(h.timeline.zoomToSelection(),true);
  assert.deepEqual(h.edits,[]);
  h.timeline.fit();
  h.timeline.setSelection(null,false);
  h.timeline.setTool("range");
  h.timeline.pointerDown(h.point(1)); h.timeline.pointerUp(h.point(1+1/60));
  assert.ok(Math.abs(h.timeline.selection.end-h.timeline.selection.start-1/60)<1e-9);
  assert.equal(h.timeline.canSplitClip(h.project.manual.source_tracks.A[0],1+1/120),false);
});

test("sequence Blade creates individual frames at the configured output fps, never subframe pieces", () => {
  for (const fps of [24,25,30,50,60]) {
    const h=sequenceFixture({fps});
    h.timeline.setEditTarget("B");
    const frame=1/fps;
    h.project.manual.source_tracks.B=[{id:"two-frames",start:0,end:frame*2,source_start:1}];
    h.timeline.setTool("blade");
    h.timeline.pointerDown(h.point(frame,110)); h.timeline.pointerUp(h.point(frame,110));
    assert.equal(h.edits.length,1,`${fps}fps frame boundary is accepted`);
    assert.equal(h.edits[0].action,"split"); assert.equal(h.edits[0].target,"B");
    assert.ok(Math.abs(h.edits[0].time-frame)<1e-9);
    // Mimic the saved split before clicking near the same boundary again.
    h.project.manual.source_tracks.B = [
      {id:"left-frame",start:0,end:frame,source_start:1},
      {id:"right-frame",start:frame,end:frame*2,source_start:1+frame},
    ];
    h.timeline.pointerDown(h.point(frame/2,110)); h.timeline.pointerUp(h.point(frame/2,110));
    assert.equal(h.edits.length,1, "Blade cannot create a subframe clip");
  }
});

test("pixel-based Cut clicks land on complete output frames", () => {
  for (const fps of [24, 25, 30, 50, 60]) {
    const h = sequenceFixture({fps}); h.timeline.setTool("blade");
    h.timeline.pointerDown(h.point(1.004)); h.timeline.pointerUp(h.point(1.004));
    assert.equal(h.edits[0].time, 1);
  }
});

test("Range then Select moves exactly the selected part, never the enclosing recording", () => {
  for (const target of ["edit", "A", "B"]) {
    const h = sequenceFixture(); h.timeline.setEditTarget(target);
    const y = target === "B" ? 110 : 60;
    h.timeline.setTool("range");
    h.timeline.pointerDown(h.point(1, y)); h.timeline.pointerUp(h.point(2, y));
    h.timeline.setTool("select");
    h.timeline.pointerDown(h.point(1.5, y)); h.timeline.pointerUp(h.point(5.5, y));
    assert.deepEqual(h.edits, [{action:"sequence_move_range",start:1,end:2,to:5,...(target === "edit" ? {} : {slot:target})}]);
  }
});

test("sequence Cut out uses one output frame while legacy minimum stays unchanged", () => {
  for (const fps of [30,60]) {
    const h=sequenceFixture({fps});
    h.timeline.setEditTarget("A");
    h.timeline.setTool("remove_between"); h.timeline.cutOutAt(.1);
    assert.equal(h.timeline.cutOutAt(.1+1/fps/2),false);
    assert.equal(h.timeline.cutOutAt(.1+1/fps),true);
    assert.equal(h.edits.length,1); assert.equal(h.edits[0].target,"A");
    assert.ok(h.timeline.selection);
  }
  const h=fixture(); h.timeline.setTool("remove_between"); h.timeline.cutOutAt(.1);
  assert.equal(h.timeline.cutOutAt(.1+1/60),false);
});

test("separate source lanes select their own clips and preserve the global edit", () => {
  const h = fixture({ tracks: true }); const before = JSON.stringify(h.project);
  h.timeline.pointerDown(h.event(1, { clientY: 170 }));
  h.timeline.pointerUp(h.event(1, { clientY: 170 }));
  assert.equal(h.timeline.editTarget, "B");
  assert.deepEqual(h.notifications.at(-1), { start: 0, end: 3 });
  assert.equal(JSON.stringify(h.project), before);
  h.timeline.draw(); assert.equal(h.canvas.style.height, "248px");
});

test("source blade targets B, including material outside global keep ranges", () => {
  const h = fixture({ tracks: true }); h.timeline.setTool("blade");
  h.timeline.pointerDown(h.event(2, { clientY: 170 }));
  h.timeline.pointerUp(h.event(2, { clientY: 170 }));
  assert.deepEqual(h.edits, [{ action: "split", time: 2, target: "B" }]);
  h.timeline.pointerDown(h.event(6, { clientY: 135 }));
  h.timeline.pointerUp(h.event(6, { clientY: 135 }));
  assert.deepEqual(h.edits.at(-1), { action: "split", time: 6, target: "A" });
});

test("move drags B into an empty gap and rejects overlapping moves", () => {
  const h = fixture({ tracks: true }); h.timeline.setTool("move");
  h.timeline.pointerDown(h.event(1, { clientY: 170 }));
  h.timeline.pointerMove(h.event(5, { clientY: 170 }));
  h.timeline.pointerUp(h.event(5, { clientY: 170 }));
  assert.deepEqual(h.edits, [{ action: "track_move", slot: "B", clip_id: "b1", start: 4 }]);
  h.timeline.pointerDown(h.event(1, { clientY: 170 }));
  h.timeline.pointerUp(h.event(8, { clientY: 170 }));
  assert.equal(h.edits.length, 1, "overlapping target must not submit");
});

test("changing track cancels a half-finished cut and layout clicks target the entire edit", () => {
  const h = fixture({ tracks: true });
  h.timeline.setEditTarget("B"); h.timeline.setTool("remove_between"); h.timeline.cutOutAt(1);
  h.timeline.setEditTarget("A"); assert.equal(h.timeline.cutAnchor, null);
  h.timeline.cutOutAt(1); h.timeline.cutOutAt(2);
  assert.deepEqual(h.edits, [{ action: "delete_range", start: 1, end: 2, target: "A" }]);
  h.project.draft.camera_plan = [{ start: 0, end: 4, camera: "stacked" }];
  h.timeline.setTool("select");
  h.timeline.pointerDown(h.event(1, { clientY: 202 })); h.timeline.pointerUp(h.event(1, { clientY: 202 }));
  assert.equal(h.timeline.editTarget, "edit");
  assert.deepEqual(h.layouts, [{ start: 0, end: 4, camera: "stacked" }]);
});

test("A edits remain accessible after B is removed; missing B cannot be selected", () => {
  const h = fixture({ tracks: true }); h.project.sources.B = null; h.timeline.setProject(h.project);
  assert.equal(h.timeline.hasTrackLanes(), true);
  h.timeline.setEditTarget("B"); assert.equal(h.timeline.editTarget, "edit");
  h.timeline.setEditTarget("A"); assert.equal(h.timeline.editTarget, "A");
});

test("waveform follows analyzed source clips and never substitutes a different source", () => {
  const h = fixture({ tracks: true });
  h.project.analysis = { audio_source: "B", audio_timeline_offset: 2 };
  h.project.manual.source_mixer = { audio_slot: "B" };
  const bins = [{ start: 6, end: 7, rms_dbfs: -20 }];
  assert.deepEqual(plain(h.timeline.audioTimelineRanges(bins)), [{ start: 0, end: 1, rms_dbfs: -20 }]);
  assert.equal(h.timeline.audioTimelineRanges(bins), h.timeline.audioTimelineRanges(bins), "repaints reuse mapped bins");
  h.project.manual.source_mixer.audio_slot = "A";
  assert.deepEqual(plain(h.timeline.audioTimelineRanges(bins)), []);
});

test("time labels truncate tenths without floating-point underflow or second overflow", () => {
  const { scope } = fixture();
  for (const [seconds, expected] of [
    [1.2, "00:01.2"], [3.5, "00:03.5"], [1.2999, "00:01.2"],
    [59.999, "00:59.9"], [59.99999999999999, "00:59.9"],
    [60, "01:00.0"], [3599.999, "59:59.9"], [3600, "01:00:00.0"],
    [3601.2, "01:00:01.2"], [3663.5, "01:01:03.5"], [43201.2, "12:00:01.2"],
  ]) {
    assert.equal(scope.formatTime(seconds, true), expected, String(seconds));
    assert.equal(scope.formatTime(seconds), expected.slice(0, -2), String(seconds));
  }
});

test("non-finite and negative time labels safely fall back to zero", () => {
  const { scope } = fixture();
  for (const seconds of [NaN, Infinity, -Infinity, -3, undefined, "invalid"]) {
    assert.equal(scope.formatTime(seconds, true), "00:00.0");
    assert.equal(scope.formatTime(seconds), "00:00");
  }
});

test("editable clips respect real keep gaps and explicit split points without mutating the draft", () => {
  const { project, scope } = fixture();
  const original = JSON.stringify(project);
  assert.deepEqual(plain(scope.editableClips(project)), [
    { start: 0, end: 2, index: 0 }, { start: 2, end: 5, index: 1 }, { start: 7, end: 12, index: 2 },
  ]);
  assert.equal(JSON.stringify(project), original);
  assert.deepEqual(plain(scope.editableClips({ sources: { A: { duration: 12 } } })), []);
});

test("invalid, out-of-source and overlapping ranges cannot produce phantom clips", () => {
  const { scope } = fixture();
  const clips = plain(scope.editableClips({ sources: { A: { duration: 12 } }, draft: {
    keep_ranges: [{ start: 2, end: 8 }, { start: -5, end: 4 }, { start: 8, end: 30 }, { start: "bad", end: 10 }],
    edit_points: [-1, 0, 2, 2, 4, 12, 50, "bad"],
  } }));
  assert.deepEqual(clips, [
    { start: 0, end: 2, index: 0 }, { start: 2, end: 4, index: 1 },
    { start: 4, end: 8, index: 2 }, { start: 8, end: 12, index: 3 },
  ]);
});

test("near-duplicate split points never create missing kept time", () => {
  const { scope, project } = fixture();
  project.draft.edit_points = [2, 2.01, 2.01, 4.99];
  assert.deepEqual(plain(scope.editableClips(project)), [
    { start: 0, end: 2, index: 0 }, { start: 2, end: 5, index: 1 }, { start: 7, end: 12, index: 2 },
  ]);
});

for (const compact of [true, false]) {
  test(`EDIT click selects one real clip and seeks without making any edit (${compact ? "compact" : "full"})`, () => {
    const { timeline, event, notifications, seeks, edits } = fixture({ compact });
    timeline.pointerDown(event(3));
    timeline.pointerUp(event(3));
    assert.deepEqual(notifications, [{ start: 2, end: 5 }]);
    assert.deepEqual(seeks, [3]);
    assert.deepEqual(edits, []);
    timeline.pointerDown(event(6));
    timeline.pointerUp(event(6));
    assert.deepEqual(notifications.at(-1), { start: 5, end: 7 });
    assert.equal(seeks.at(-1), 6);
  });
}

test("a click exactly on a split boundary chooses the following clip", () => {
  const { timeline, event, notifications } = fixture();
  timeline.pointerDown(event(2));
  timeline.pointerUp(event(2));
  assert.deepEqual(notifications, [{ start: 2, end: 5 }]);
});

for (const compact of [true, false]) {
  test(`Select dragging selects across kept and removed material without Shift (${compact ? "compact" : "full"})`, () => {
    const { timeline, event, notifications, seeks, edits } = fixture({ compact });
    timeline.pointerDown(event(3));
    timeline.pointerMove(event(6));
    timeline.pointerUp(event(9));
    assert.deepEqual(seeks, [3, 6, 9]);
    assert.deepEqual(notifications, [{ start: 3, end: 9 }]);
    assert.deepEqual(plain(timeline.selection), { start: 3, end: 9 });
    assert.deepEqual(edits, []);
    assert.equal(timeline.scrubbing, false);

    timeline.pointerDown(event(6));
    timeline.pointerUp(event(6.5));
    assert.deepEqual(seeks.slice(-2), [6, 6.5]);
    assert.deepEqual(plain(timeline.selection), { start: 6, end: 6.5 });
  });
}

for (const tool of ["select", "range", "blade", "remove_between"]) {
  test(`ruler scrubs normally with ${tool} tool and does not apply edits`, () => {
    const { timeline, event, notifications, seeks, edits } = fixture();
    timeline.setTool(tool);
    timeline.pointerDown(event(1, { clientY: 30 }));
    timeline.pointerMove(event(3, { clientY: 65 }));
    timeline.pointerUp(event(3, { clientY: 65 }));
    assert.deepEqual(seeks, [1, 3]);
    assert.deepEqual(notifications, []);
    assert.deepEqual(edits, []);
  });
}

test("range tool and Shift drag notify once on release and never mutate media", () => {
  for (const shiftKey of [false, true]) {
    const { timeline, event, notifications, seeks, edits, project } = fixture();
    const original = JSON.stringify(project);
    timeline.setTool(shiftKey ? "select" : "range");
    timeline.pointerDown(event(1, { shiftKey }));
    timeline.pointerMove(event(4, { shiftKey }));
    assert.deepEqual(plain(timeline.selection), { start: 1, end: 4 });
    assert.deepEqual(notifications, []);
    timeline.pointerUp(event(4, { shiftKey }));
    assert.deepEqual(notifications, [{ start: 1, end: 4 }]);
    assert.deepEqual(seeks, [1, 4]);
    assert.deepEqual(edits, []);
    assert.equal(JSON.stringify(project), original);
  }
});

test("range selection snaps to edit boundaries and Alt bypasses snapping", () => {
  for (const altKey of [false, true]) {
    const { timeline, event } = fixture();
    timeline.setSnapping(true);
    timeline.setTool("range");
    timeline.pointerDown(event(2.08, { altKey }));
    timeline.pointerUp(event(4.92, { altKey }));
    const expected = altKey ? { start: 2.08, end: 4.92 } : { start: 2, end: 5 };
    assert.ok(Math.abs(timeline.selection.start - expected.start) < .00001);
    assert.ok(Math.abs(timeline.selection.end - expected.end) < .00001);
  }
});

for (const y of [65, 105, 135, 175]) {
  test(`default selection drags on the filmstrip and all linked lanes, with no implicit snapping (y=${y})`, () => {
    const { timeline, event, notifications, edits } = fixture();
    timeline.pointerDown(event(1.96, {clientY:y}));
    assert.deepEqual(notifications, [], "pointerdown must not open the trim inspector and move the canvas");
    timeline.pointerMove(event(7.06, {clientY:y}));
    timeline.pointerUp(event(7.06, {clientY:y}));
    assert.ok(Math.abs(timeline.selection.start - 1.96) < .00001);
    assert.ok(Math.abs(timeline.selection.end - 7.06) < .00001);
    assert.equal(notifications.length, 1);
    assert.deepEqual(edits, []);
  });
}

test("clicking omitted source footage selects leading, internal and trailing gaps", () => {
  const { timeline, project, event } = fixture();
  project.draft.keep_ranges = [{start:2,end:5},{start:7,end:10}];
  for (const [time, expected] of [[1,{start:0,end:2}], [6,{start:5,end:7}], [11,{start:10,end:12}]]) {
    timeline.clearSelection(); timeline.pointerDown(event(time)); timeline.pointerUp(event(time));
    assert.deepEqual(plain(timeline.selection), expected);
  }
});

test("selection edges can be adjusted from the filmstrip, without forcing kept boundaries", () => {
  const { timeline, event } = fixture();
  timeline.setSelection({ start: 3, end: 6 });
  timeline.pointerDown(event(6, {clientY:65})); timeline.pointerUp(event(7.06, {clientY:65}));
  assert.ok(Math.abs(timeline.selection.end - 7.06) < .00001);
  assert.equal(timeline.selection.start, 3);
});

test("reverse Select drag crosses removed footage; ruler dragging preserves its range", () => {
  const { timeline, event, notifications, seeks } = fixture();
  timeline.pointerDown(event(9)); timeline.pointerUp(event(3));
  assert.deepEqual(plain(timeline.selection), {start:3,end:9});
  timeline.pointerDown(event(4, {clientY:30})); timeline.pointerUp(event(6, {clientY:30}));
  assert.deepEqual(plain(timeline.selection), {start:3,end:9});
  assert.deepEqual(notifications, [{start:3,end:9}]);
  assert.equal(seeks.at(-1), 6);
});

test("cancelling a default Select drag restores the previous selection without committing", () => {
  const { timeline, event, notifications, edits } = fixture();
  timeline.setSelection({start:8,end:11}, false);
  timeline.pointerDown(event(1)); timeline.pointerMove(event(4));
  assert.deepEqual(notifications, []);
  timeline.pointerCancel(event(4)); timeline.pointerUp(event(4));
  assert.deepEqual(plain(timeline.selection), {start:8,end:11});
  assert.deepEqual(notifications, [{start:8,end:11}]);
  assert.deepEqual(edits, []);
});

test("a removed passage can be selected and previewed independently of the kept clips", () => {
  const { timeline, event, notifications, seeks, edits } = fixture();
  timeline.setTool("range");
  timeline.pointerDown(event(5.5));
  timeline.pointerUp(event(6.5));
  assert.deepEqual(notifications, [{ start: 5.5, end: 6.5 }]);
  assert.deepEqual(seeks, [5.5, 6.5]);
  assert.deepEqual(edits, []);
});

test("selection snapping never changes the exact source frame requested for preview", () => {
  const { timeline, event, seeks } = fixture();
  timeline.setSnapping(true);
  timeline.setTool("range");
  timeline.pointerDown(event(5.08));
  timeline.pointerUp(event(6.92));
  assert.deepEqual(plain(timeline.selection), { start: 5, end: 7 });
  assert.ok(Math.abs(seeks[0] - 5.08) < .00001);
  assert.ok(Math.abs(seeks[1] - 6.92) < .00001);
});

test("selection edges adjust a proposed range only and snap unless Alt is pressed", () => {
  const { timeline, event, notifications, seeks, edits, project } = fixture();
  timeline.setSnapping(true);
  timeline.setSelection({ start: 1, end: 4 }, false);
  const original = JSON.stringify(project);
  timeline.pointerDown(event(4));
  timeline.pointerMove(event(4.91));
  timeline.pointerUp(event(4.91));
  assert.deepEqual(notifications, [{ start: 1, end: 5 }]);
  timeline.pointerDown(event(1));
  timeline.pointerUp(event(2.09, { altKey: true }));
  assert.ok(Math.abs(timeline.selection.start - 2.09) < .00001);
  assert.equal(timeline.selection.end, 5);
  assert.deepEqual(seeks, [4, 4.91, 1, 2.09]);
  assert.deepEqual(edits, []);
  assert.equal(JSON.stringify(project), original);
});

test("selection handles do not flip or clear when dragged past the other edge", () => {
  const { timeline, event } = fixture();
  timeline.setSelection({ start: 2, end: 5 }, false);
  timeline.pointerDown(event(2));
  timeline.pointerUp(event(7));
  assert.equal(timeline.selection.end, 5);
  assert.ok(timeline.selection.start > 4.9 && timeline.selection.start < 5);
});

test("blade requests an explicit split callback only on completed kept-clip clicks", () => {
  const { timeline, event, edits, project } = fixture();
  const original = JSON.stringify(project);
  timeline.setTool("blade");
  timeline.pointerDown(event(3));
  assert.deepEqual(edits, []);
  timeline.pointerUp(event(3));
  assert.deepEqual(edits, [{ action: "split", time: 3 }]);
  for (const time of [0, 2, 5, 6, 7, 12]) {
    timeline.pointerDown(event(time)); timeline.pointerUp(event(time));
  }
  timeline.pointerDown(event(3)); timeline.pointerUp(event(4));
  assert.equal(edits.length, 1);
  assert.equal(JSON.stringify(project), original);
});

test("Blade previews removed footage but signals that a removed clip cannot be split", () => {
  const { timeline, canvas, event, seeks, edits } = fixture();
  timeline.setTool("blade");
  timeline.pointerDown(event(6));
  assert.equal(canvas.style.cursor, "not-allowed");
  timeline.pointerUp(event(6));
  assert.deepEqual(seeks, [6]);
  assert.deepEqual(edits, []);
  timeline.pointerMove(event(3));
  assert.equal(canvas.style.cursor, "crosshair");
  timeline.pointerDown(event(3));
  assert.equal(seeks.at(-1), 3);
  assert.deepEqual(edits, []);
  timeline.pointerUp(event(3));
  assert.deepEqual(edits, [{ action: "split", time: 3 }]);
});

test("the scrubber seeks to pointerup even when the device omits its final pointermove", () => {
  const { timeline, event, seeks, edits } = fixture();
  timeline.pointerDown(event(4, { clientY: 30 }));
  timeline.pointerUp(event(6, { clientY: 30 }));
  assert.deepEqual(seeks, [4, 6]);
  assert.deepEqual(edits, []);
});

for (const cancellation of ["pointercancel", "lostpointercapture", "escape"]) {
  test(`${cancellation} restores the selection before a live gesture instead of committing it`, () => {
    const { timeline, event, listeners, notifications, captures, edits } = fixture();
    timeline.setSelection({ start: 7, end: 12 }, false);
    timeline.setTool("range");
    timeline.pointerDown(event(1));
    timeline.pointerMove(event(4));
    if (cancellation === "escape") {
      const key = event(0, { key: "Escape" });
      timeline.keyDown(key);
      assert.equal(key.defaultPrevented, true);
      assert.equal(key.propagationStopped, true);
    } else listeners[cancellation](event(4));
    assert.deepEqual(plain(timeline.selection), { start: 7, end: 12 });
    assert.deepEqual(notifications, [{ start: 7, end: 12 }]);
    assert.equal(captures.size, 0);
    assert.equal(timeline.gesture, null);
    timeline.pointerUp(event(4));
    assert.equal(notifications.length, 1);
    assert.deepEqual(edits, []);
  });
}

test("cancelled blade and foreign pointer events cannot commit a split", () => {
  const { timeline, event, edits } = fixture();
  timeline.setTool("blade");
  timeline.pointerDown(event(3));
  timeline.pointerCancel(event(3, { pointerId: 2 }));
  assert.ok(timeline.gesture);
  timeline.pointerUp(event(3, { pointerId: 2 }));
  assert.ok(timeline.gesture);
  timeline.pointerCancel(event(3));
  timeline.pointerUp(event(3));
  assert.deepEqual(edits, []);
});

test("pointer capture loss/errors are safe and changing tool cancels an unfinished range", () => {
  const { timeline, canvas, event, notifications } = fixture();
  canvas.setPointerCapture = () => { throw Error("NotFoundError"); };
  canvas.hasPointerCapture = () => true;
  canvas.releasePointerCapture = () => { throw Error("NotFoundError"); };
  timeline.setTool("range");
  timeline.pointerDown(event(1));
  timeline.pointerMove(event(4));
  assert.doesNotThrow(() => timeline.setTool("select"));
  assert.equal(timeline.selection, null);
  assert.deepEqual(notifications, [null]);
  assert.equal(timeline.setTool("not-a-tool"), false);
  assert.equal(timeline.tool, "select");
});

test("canvas keys respect already handled shortcuts and prevent duplicate bubbled actions", () => {
  const { timeline, event, seeks } = fixture();
  timeline.keyDown(event(0, { key: "ArrowRight", defaultPrevented: true }));
  assert.deepEqual(seeks, []);
  const right = event(0, { key: "ArrowRight" });
  timeline.keyDown(right);
  assert.deepEqual(seeks, [.25]);
  assert.equal(right.propagationStopped, true);
  timeline.keyDown(event(0, { key: "End" }));
  assert.equal(seeks.at(-1), 12);
});

for (const points of [[1.97, 8], [8, 1.97]]) {
  test(`Cut out uses two exact clicks in either direction (${points}) as one range edit`, () => {
    const { timeline, event, edits, project } = fixture();
    const original = JSON.stringify(project);
    timeline.setTool("remove_between");
    for (const [index, time] of points.entries()) {
      timeline.pointerDown(event(time)); timeline.pointerUp(event(time));
      assert.equal(edits.length, index);
      if (!index) assert.equal(timeline.cutAnchor, time);
    }
    assert.deepEqual(edits, [{ action: "delete_range", start: 1.97, end: 8 }]);
    assert.equal(timeline.cutAnchor, null);
    assert.equal(JSON.stringify(project), original);
    timeline.pointerUp(event(8));
    assert.equal(edits.length, 1);
  });
}

test("invalid, tiny and already removed intervals leave the first cut available", () => {
  const { timeline, edits } = fixture();
  timeline.setTool("remove_between");
  for (const time of [NaN, Infinity, -1, 13]) assert.equal(timeline.cutOutAt(time), false);
  timeline.cutOutAt(5.5);
  for (const time of [5.5, 5.51, 6, NaN]) assert.equal(timeline.cutOutAt(time), false);
  assert.equal(timeline.cutAnchor, 5.5);
  assert.equal(edits.length, 0);
  assert.equal(timeline.cutOutAt(8), true);
  assert.deepEqual(edits, [{ action: "delete_range", start: 5.5, end: 8 }]);
});

test("a dragged, right-clicked or cancelled cut never removes footage even if released back at its origin", () => {
  const { timeline, event, edits } = fixture();
  timeline.setTool("remove_between");
  timeline.cutOutAt(1);
  timeline.pointerDown(event(3)); timeline.pointerMove(event(8)); timeline.pointerUp(event(3));
  timeline.pointerDown(event(3, { button: 2 })); timeline.pointerUp(event(3));
  timeline.pointerDown(event(3)); timeline.pointerCancel(event(3)); timeline.pointerUp(event(3));
  assert.equal(timeline.cutAnchor, 1);
  assert.deepEqual(edits, []);
});

test("Escape, switching tools, and replacing projects cancel a pending first cut", () => {
  const { timeline, event, project, edits } = fixture();
  for (const cancel of [() => timeline.keyDown(event(0, { key: "Escape" })), () => timeline.setTool("select"), () => timeline.setProject({ ...project, id: "next" })]) {
    timeline.setTool("remove_between"); timeline.cutOutAt(1);
    cancel();
    assert.equal(timeline.cutAnchor, null);
  }
  assert.deepEqual(edits, []);
});

test("an asynchronous removal blocks duplicate requests and unlocks after errors", async () => {
  const { timeline, event, edits } = fixture();
  let rejectEdit;
  timeline.onEdit = (edit) => { edits.push(plain(edit)); return new Promise((_resolve, reject) => { rejectEdit = reject; }); };
  timeline.setTool("remove_between"); timeline.cutOutAt(1); timeline.cutOutAt(3);
  assert.equal(timeline.editPending, true);
  assert.equal(timeline.cutOutAt(4), false);
  timeline.pointerDown(event(4)); timeline.pointerUp(event(4));
  assert.equal(edits.length, 1);
  rejectEdit(new Error("save failed"));
  await new Promise(setImmediate); // Allow the VM's cross-realm promise assimilation to settle.
  assert.equal(timeline.editPending, false);
  assert.deepEqual(plain(timeline.selection), { start: 1, end: 3 });
  assert.equal(timeline.cutOutAt(4), true);
});

test("busy host state blocks pointer and keyboard edits; Enter is local, composition-safe and non-repeating", () => {
  const { timeline, canvas, event, edits, seeks } = fixture();
  canvas.dataset = { editorShortcuts: "on" };
  timeline.setTool("remove_between");
  timeline.playhead = 1;
  timeline.canEdit = () => false;
  timeline.keyDown(event(0, { key: "Enter" })); timeline.pointerDown(event(3)); timeline.pointerUp(event(3));
  assert.equal(timeline.cutAnchor, null);
  timeline.canEdit = () => true;
  for (const extra of [{ isComposing: true }, { repeat: true }, { ctrlKey: true }, { shiftKey: true }]) timeline.keyDown(event(0, { key: "Enter", ...extra }));
  assert.equal(timeline.cutAnchor, null);
  timeline.keyDown(event(0, { key: "Enter" }));
  timeline.playhead = 3;
  timeline.keyDown(event(0, { key: "Enter" }));
  assert.deepEqual(edits, [{ action: "delete_range", start: 1, end: 3 }]);
  timeline.keyDown(event(0, { key: "ArrowRight" }));
  timeline.keyDown(event(0, { key: "Home" }));
  assert.deepEqual(seeks, [], "unbound profile navigation must not fall back to generic NLE keys");
});

test("repeated Shift arrows extend the active endpoint, reverse across the anchor, and follow source time", () => {
  const { timeline, event, seeks } = fixture();
  timeline.setPlayhead(3);
  const step = (key) => timeline.keyDown(event(0, { key, shiftKey: true }));
  step("ArrowRight"); step("ArrowRight");
  assert.deepEqual(plain(timeline.selection), {start:3,end:3.5});
  step("ArrowLeft"); step("ArrowLeft"); step("ArrowLeft");
  assert.deepEqual(plain(timeline.selection), {start:2.75,end:3});
  assert.deepEqual(seeks, [3.25,3.5,3.25,3,2.75]);
  timeline.setPlayhead(8); timeline.clearSelection(); step("ArrowLeft");
  assert.deepEqual(plain(timeline.selection), {start:7.75,end:8});
});

test("clip boundaries and labels fit both existing timeline heights without changing time coordinates", () => {
  for (const compact of [true, false]) {
    const { timeline, canvas, draws, event } = fixture({ compact });
    timeline.setSelection({ start: 2, end: 5 }, false);
    timeline.draw();
    assert.equal(canvas.height, compact ? 180 : 310);
    assert.equal(timeline.timeFromEvent(event(6)), 6);
    const outlines = draws.filter((draw) => draw.outline);
    assert.equal(outlines.length, 3);
    for (const label of ["EDIT", "LAYOUT", "AUDIO"]) assert.ok(draws.some((draw) => draw.text === label && draw.y < canvas.height));
    assert.ok(draws.some((draw) => String(draw.text).startsWith("Clip 2")));
  }
});

for (const compact of [true, false]) {
  test(`Layout lane selects exact scene and opens inspector only on release (${compact ? "compact" : "full"})`, () => {
    const { timeline, project, event, notifications, layouts, seeks, edits } = fixture({ compact });
    project.draft.camera_plan = [{ start: 0, end: 4, camera: "stacked" }, { start: 4, end: 12, camera: "pip" }];
    const point = (time) => event(time, { clientY: 20 + (compact ? 118 : 198) });
    timeline.pointerDown(point(3));
    assert.deepEqual(notifications, []);
    assert.deepEqual(layouts, []);
    timeline.pointerUp(point(3));
    assert.deepEqual(notifications, [{ start: 0, end: 4 }]);
    assert.deepEqual(layouts, [{ start: 0, end: 4, camera: "stacked" }]);
    assert.deepEqual(seeks, [3]);
    assert.deepEqual(edits, []);

    timeline.clearSelection(false);
    timeline.pointerDown(point(4)); timeline.pointerUp(point(4));
    assert.deepEqual(layouts.at(-1), { start: 4, end: 12, camera: "pip" });
    assert.deepEqual(notifications.at(-1), { start: 4, end: 12 });
  });

  test(`Layout drag remains arbitrary range selection across excluded footage (${compact ? "compact" : "full"})`, () => {
    const { timeline, project, event, notifications, layouts } = fixture({ compact });
    project.draft.camera_plan = [{ start: 0, end: 12, camera: "stacked" }];
    const point = (time) => event(time, { clientY: 20 + (compact ? 118 : 198) });
    timeline.pointerDown(point(3)); timeline.pointerMove(point(8)); timeline.pointerUp(point(9));
    assert.deepEqual(notifications, [{ start: 3, end: 9 }]);
    assert.deepEqual(layouts, []);
    timeline.clearSelection(false);
    timeline.pointerDown(point(9)); timeline.pointerUp(point(3));
    assert.deepEqual(notifications.at(-1), { start: 3, end: 9 });
    assert.deepEqual(layouts, []);
  });
}

test("layout rendering omits excluded footage, merges edit splits and bounds invalid scenes", () => {
  const { timeline, project, draws, canvas } = fixture();
  const plan = [null, { start: "bad", end: 4 }, { start: 4, end: 4 },
    { start: -5, end: 4, camera: "stacked" }, { start: 4, end: 30, camera: "pip" }];
  project.draft.camera_plan = plan;
  const original = JSON.stringify(project);
  assert.deepEqual(plain(timeline.layoutSegments()), [
    { start: 0, end: 4, camera: "stacked" }, { start: 4, end: 5, camera: "pip" }, { start: 7, end: 12, camera: "pip" },
  ]);
  assert.equal(timeline.layoutAt(6), null, "excluded time has no active scene");
  assert.deepEqual(plain(timeline.layoutAt(12)), { start: 4, end: 12, camera: "pip" });
  assert.equal(JSON.stringify(project), original);
  timeline.draw();
  assert.equal(canvas.height, 180);
  assert.ok(draws.some((draw) => draw.text === "Stacked"));
  assert.ok(draws.some((draw) => draw.text === "PiP"));
  project.draft.camera_plan = {};
  assert.deepEqual(plain(timeline.layoutScenes()), []);
});

test("removed Layout gaps are restorable selections and cancelled clicks never open inspector", () => {
  const { timeline, project, event, notifications, layouts } = fixture();
  project.draft.camera_plan = [{ start: 0, end: 12, camera: "A" }];
  const point = (time) => event(time, { clientY: 138 });
  timeline.pointerDown(point(6)); timeline.pointerUp(point(6));
  assert.deepEqual(notifications, [{ start: 5, end: 7 }]);
  assert.deepEqual(layouts, []);
  timeline.pointerDown(point(3)); timeline.pointerCancel(point(3)); timeline.pointerUp(point(3));
  assert.deepEqual(plain(timeline.selection), { start: 5, end: 7 });
  assert.deepEqual(layouts, []);
});

test("range, blade, cut-out and Shift interactions do not open Layout inspector", () => {
  for (const tool of ["range", "blade", "remove_between", "select"]) {
    const { timeline, project, event, layouts, edits } = fixture();
    project.draft.camera_plan = [{ start: 0, end: 12, camera: "A" }];
    timeline.setTool(tool);
    const point = event(3, { clientY: 138, shiftKey: tool === "select" });
    timeline.pointerDown(point); timeline.pointerUp(point);
    assert.deepEqual(layouts, []);
    assert.deepEqual(edits, []);
  }
});

test("Zoom selection centers a bounded source-time range without changing selection or draft", () => {
  const { timeline, project, scroll } = fixture();
  timeline.scheduleDraw = (after) => after?.();
  assert.equal(timeline.zoomToSelection(), false);
  timeline.setSelection({ start: 7, end: 9 }, false);
  const original = JSON.stringify(project);
  assert.equal(timeline.zoomToSelection(), true);
  assert.equal(timeline.zoom, 5);
  assert.equal(scroll.scrollLeft, 1700);
  assert.deepEqual(plain(timeline.selection), { start: 7, end: 9 });
  assert.equal(JSON.stringify(project), original);
  timeline.setSelection({ start: 0, end: .04 }, false); timeline.zoomToSelection();
  assert.equal(timeline.zoom, 16);
  assert.equal(scroll.scrollLeft, 0);
  timeline.setSelection({ start: 0, end: 12 }, false); timeline.zoomToSelection();
  assert.equal(timeline.zoom, 1);
  assert.equal(scroll.scrollLeft, 0);
});
