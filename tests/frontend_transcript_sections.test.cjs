"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
let planTranscriptSections, captureSectionIntent, navigateSection;
test.before(async () => {
  const text = fs.readFileSync(path.join(__dirname, "../web/transcript-sections.js"), "utf8");
  ({ planTranscriptSections, captureSectionIntent, navigateSection } = await import("data:text/javascript;base64," + Buffer.from(text).toString("base64")));
});

const clone = value => structuredClone(value);
function fixture() {
  return { id: "project_0123456789ab", revision: 7,
    sources: { A: { duration: 8, has_audio: true, generation: "sourceA", path: "syntheticA.mp4" },
      B: { duration: 8, has_audio: true, generation: "sourceB", path: "syntheticB.mp4" } },
    analysis: { audio_source: "A", audio_timeline_offset: 0,
      transcript: { model: "synthetic", language: "mixed", segments: [{ id: "s1", start: .1, end: .34, text: "Speech שלום" }] } },
    manual: { source_mixer: { audio_slot: "A" } },
    editor_sequence: { active: false, duration: 24, sequence: { version: 1, duration: 24, camera_plan: [] },
      source_tracks: { A: [0, 8, 16].map((start, i) => ({ id: `A:context:${i}`, start, end: start + 8, source_start: 0 })), B: [] } } };
}
const rows = p => p.editor_sequence.source_tracks[p.analysis.audio_source];
const segment = p => p.analysis.transcript.segments[0];
const plan = p => planTranscriptSections(p, segment(p).id);
const clocks = p => plan(p).sections.map(s => [s.clipId, s.start, s.end, s.sourceStart, s.sourceEnd, s.partial]);

test("three exact saved sections, immutable plan and unchanged input", () => {
  const p = fixture(), before = JSON.stringify(p), result = plan(p);
  assert.equal(result.ok, true); assert.equal(result.sections.length, 3);
  assert.deepEqual(clocks(p), [0, 8, 16].map((t, i) => [`A:context:${i}`, t + .1, t + .34, .1, .34, false]));
  assert.equal(new Set(result.sections.map(s => s.key)).size, 3);
  assert.equal(Object.isFrozen(result.sections[0]), true);
  assert.throws(() => { result.sections[0].start = 0; });
  assert.equal(JSON.stringify(p), before); assert.equal(Object.isFrozen(p), false);
});

test("adjacent repeated speech is two sections, never a union", () => {
  const p = fixture(); Object.assign(segment(p), { start: 1, end: 2 });
  p.editor_sequence.source_tracks.A = [{ id: "one", start: 0, end: 1, source_start: 1 }, { id: "repeat", start: 1, end: 2, source_start: 1 }];
  assert.deepEqual(clocks(p), [["one", 0, 1, 1, 2, false], ["repeat", 1, 2, 1, 2, false]]);
});

test("adjacent split source pieces stay separate and partial", () => {
  const p = fixture(); Object.assign(segment(p), { start: 1, end: 2 });
  p.editor_sequence.source_tracks.A = [{ id: "one", start: 0, end: .5, source_start: 1 }, { id: "split", start: .5, end: 1, source_start: 1.5 }];
  assert.deepEqual(clocks(p), [["one", 0, .5, 1, 1.5, true], ["split", .5, 1, 1.5, 2, true]]);
});

test("disjoint fragments retain exact source spans without selecting the gap", () => {
  const p = fixture(); Object.assign(segment(p), { start: 1, end: 4 });
  p.editor_sequence.source_tracks.A = [{ id: "left", start: 0, end: .5, source_start: 1 }, { id: "right", start: 10, end: 10.5, source_start: 3.5 }];
  assert.deepEqual(clocks(p), [["left", 0, .5, 1, 1.5, true], ["right", 10, 10.5, 3.5, 4, true]]);
});

test("B uses analyzed offset, not the current sync offset", () => {
  const p = fixture(); p.analysis.audio_source = "B"; p.analysis.audio_timeline_offset = 5;
  p.manual.source_mixer = { audio_slot: "B", sync_offset: -17 };
  Object.assign(segment(p), { start: 10, end: 13 });
  p.editor_sequence.source_tracks.B = [{ id: "B:actual", start: 12, end: 13, source_start: 6 }];
  assert.deepEqual(clocks(p), [["B:actual", 12, 13, 6, 7, true]]);
});

test("negative B analyzed offset is inverted exactly", () => {
  const p = fixture(); p.analysis.audio_source = "B"; p.analysis.audio_timeline_offset = -2;
  p.manual.source_mixer.audio_slot = "B"; Object.assign(segment(p), { start: -1, end: 0 });
  p.editor_sequence.source_tracks.B = [{ id: "B:actual", start: 12, end: 13, source_start: 1 }];
  assert.deepEqual(clocks(p), [["B:actual", 12, 13, 1, 2, false]]);
});

test("picture speed/hold does not retime spoken source clock", () => {
  const p = fixture(), expected = clocks(p);
  rows(p).forEach(r => Object.assign(r, { video_speed: 4, video_source_start: 500 }));
  assert.deepEqual(clocks(p), expected);
});

test("caption text/timing/hidden/alternative and track mute/lock are not authority", () => {
  const p = fixture(), expected = clocks(p);
  p.editor_captions = [{ id: "alien", start: 23, end: 24, text: "Not source speech" }];
  p.manual.caption_overrides = { alien: { hidden: true, start_delta: 2, text: "Local" } };
  p.manual.caption_alternative = "different"; p.manual.track_protection = { A: true };
  p.manual.audio_mix = { original: { muted: true, gain_db: -60 } };
  assert.deepEqual(clocks(p), expected);
});

test("tiny positive source intersection is navigable without a Range minimum", () => {
  const p = fixture(); Object.assign(segment(p), { start: .1, end: .100001 });
  assert.equal(plan(p).sections.length, 3);
  assert.ok(plan(p).sections.every(s => s.end > s.start && s.end - s.start < 1 / 60));
});

test("half-open clip boundaries create no zero-length appearance", () => {
  const p = fixture(); Object.assign(segment(p), { start: 8, end: 8.5 });
  assert.equal(plan(p).code, "no_sections"); assert.deepEqual(plan(p).sections, []);
});

test("explicit empty canonical lane remains empty, no implicit fallback", () => {
  const p = fixture(); p.editor_sequence.source_tracks.A = [];
  assert.equal(plan(p).code, "no_sections"); assert.equal(plan(p).ok, true);
});

for (const version of [undefined, 1, 2, 3]) test(`canonical projection preserves raw track representation ${version}`, () => {
  const p = fixture(); if (version) p.manual.layer_tracks = { version, arbitrary: "Untouched, validated by host readiness" };
  const before = JSON.stringify(p); assert.equal(plan(p).sections.length, 3); assert.equal(JSON.stringify(p), before);
});

test("unversioned legacy source is pinned literally, not certified as file content", () => {
  const p = fixture(); delete p.sources.A.generation;
  assert.equal(plan(p).ok, true); assert.equal(JSON.stringify(p).includes('"generation":"sourceA"'), false);
});

const corruptions = {
  "wrong project ID": p => { p.id = "other"; },
  "revision string": p => { p.revision = "7"; },
  "revision zero": p => { p.revision = 0; },
  "revision unsafe": p => { p.revision = Number.MAX_SAFE_INTEGER + 1; },
  "manual malformed": p => { p.manual = "invalid"; },
  "sources array": p => { p.sources = []; },
  "missing transcript": p => { delete p.analysis.transcript; },
  "nonarray transcript": p => { p.analysis.transcript.segments = {}; },
  "missing selected ID": p => { delete segment(p).id; },
  "duplicate selected ID": p => { p.analysis.transcript.segments.push(clone(segment(p))); },
  "numeric/text ID collision": p => { segment(p).id = 1; p.analysis.transcript.segments.push({ ...segment(p), id: "1" }); },
  "empty text object": p => { segment(p).text = {}; },
  "surrogate text": p => { segment(p).text = "\uD800"; },
  "nonfinite segment": p => { segment(p).start = NaN; },
  "string segment clock": p => { segment(p).end = "0.34"; },
  "reversed segment": p => { segment(p).end = 0; },
  "missing projection": p => { delete p.editor_sequence; },
  "projection error": p => { p.editor_sequence.error = "future"; },
  "projection active malformed": p => { p.editor_sequence.active = "false"; },
  "future projection": p => { p.editor_sequence.sequence.version = 2; },
  "future raw sequence": p => { p.manual.sequence = { version: 2 }; },
  "projection duration mismatch": p => { p.editor_sequence.sequence.duration = 12; },
  "zero edit": p => { p.editor_sequence.duration = p.editor_sequence.sequence.duration = 0; },
  "edit beyond maximum": p => { p.editor_sequence.duration = p.editor_sequence.sequence.duration = 86401; },
  "missing analyzed slot": p => { delete p.analysis.audio_source; },
  "unknown analyzed slot": p => { p.analysis.audio_source = "C"; },
  "B absent not A fallback": p => { p.analysis.audio_source = "B"; delete p.sources.B; },
  "B offset absent": p => { p.analysis.audio_source = "B"; delete p.analysis.audio_timeline_offset; },
  "B offset boolean": p => { p.analysis.audio_source = "B"; p.analysis.audio_timeline_offset = true; },
  "source duration string": p => { p.sources.A.duration = "8"; },
  "source without sound": p => { p.sources.A.has_audio = false; },
  "source generation malformed": p => { p.sources.A.generation = {}; },
  "reserved generation": p => { p.sources.A.generation = "unversioned"; },
  "routing changed": p => { p.manual.source_mixer.audio_slot = "B"; },
  "routing invalid": p => { p.manual.source_mixer.audio_slot = "C"; },
  "routing array": p => { p.manual.source_mixer = []; },
  "missing canonical lane": p => { delete p.editor_sequence.source_tracks.A; },
  "lane array invalid": p => { p.editor_sequence.source_tracks.A = {}; },
  "clip duplicate ID": p => { rows(p)[1].id = rows(p)[0].id; },
  "clip empty ID": p => { rows(p)[0].id = " "; },
  "clip ID number": p => { rows(p)[0].id = 4; },
  "clip start string": p => { rows(p)[0].start = "0"; },
  "clip clock infinite": p => { rows(p)[0].end = Infinity; },
  "clip negative": p => { rows(p)[0].start = -1; },
  "clip reversed": p => { rows(p)[0].end = 0; },
  "source start negative": p => { rows(p)[0].source_start = -1; },
  "clip source overflow": p => { rows(p)[0].source_start = 1; },
  "unordered lane": p => { rows(p).reverse(); },
  "tiny ambiguous overlap": p => { rows(p)[1].start -= 1e-10; rows(p)[1].end -= 1e-10; },
  "picture speed invalid": p => { rows(p)[0].video_speed = 100; },
  "picture source invalid": p => { rows(p)[0].video_source_start = NaN; },
  "cyclic metadata": p => { p.sources.A.cycle = p; },
};
for (const [name, mutate] of Object.entries(corruptions)) test(`fail closed: ${name}`, () => {
  const p = fixture(); mutate(p);
  const result = planTranscriptSections(p, ownSegmentId(p));
  assert.equal(result.ok, false, JSON.stringify(result)); assert.deepEqual(result.sections, []);
});
function ownSegmentId(p) { return p.analysis?.transcript?.segments?.[0]?.id ?? "s1"; }

function navigation() {
  const p = fixture(), original = JSON.stringify(p), view = {};
  const state = { project: p, viewToken: view, segmentId: "s1", mode: "edit", range: { start: 3, end: 4 }, cursor: 0,
    buffers: new Map([["s1", { text: "Uncommitted corrected text", base: segment(p).text }]]), selection: "unchanged" };
  const sectionPlan = plan(p); const intent = captureSectionIntent(state, sectionPlan, sectionPlan.sections[1].key);
  const calls = [];
  const api = { snapshot: () => state, issue: () => "", current: () => true,
    cancelCut: () => calls.push("cancelCut"), pause: () => calls.push("pause"),
    seek: time => { calls.push(["seek", time]); state.cursor = time; } };
  return { p, state, original, intent, calls, api };
}

test("explicit Go only cancels anchor, pauses and seeks once; project/buffer/range exact", () => {
  const h = navigation(), buffer = h.state.buffers.get("s1"), range = h.state.range;
  assert.equal(navigateSection(h.intent, h.api), true);
  assert.deepEqual(h.calls, ["cancelCut", "pause", ["seek", 8.1]]);
  assert.equal(JSON.stringify(h.p), h.original); assert.equal(h.state.buffers.get("s1"), buffer);
  assert.equal(h.state.range, range); assert.equal(h.state.selection, "unchanged"); assert.equal(h.state.mode, "edit");
});

test("capture/render/choice alone do not pause, seek, freeze source or write", () => {
  const h = navigation(); assert.ok(h.intent); assert.deepEqual(h.calls, []);
  assert.equal(Object.isFrozen(h.p), false); assert.equal(JSON.stringify(h.p), h.original);
});

const lifetime = {
  "project replacement": h => { h.state.project = clone(h.p); },
  "copied branch same clip IDs": h => { h.state.project = { ...clone(h.p), id: "project_abcdef012345" }; },
  "view replacement": h => { h.state.viewToken = {}; },
  "selected line change": h => { h.state.segmentId = "another"; },
  "Full source": h => { h.state.mode = "source"; },
  "saved revision": h => { h.p.revision++; },
  "source generation": h => { h.p.sources.A.generation = "new"; },
  "original path": h => { h.p.sources.A.path = "replacement.mp4"; },
  "transcript metadata": h => { h.p.analysis.transcript.model = "new-analysis"; },
  "segment timing": h => { segment(h.p).start += .01; },
  "segment text": h => { segment(h.p).text = "new-saved-text"; },
  "clip reassignment": h => { rows(h.p)[1].source_start = .01; rows(h.p)[1].end -= .01; },
  "local selection token": h => { h.api.current = () => false; },
  "current promise": h => { h.api.current = () => Promise.resolve(true); },
  "readiness draft": h => { h.api.issue = () => "Finish the other draft"; },
  "unknown batch": h => { h.api.issue = () => "Check saved changes"; },
  "readiness promise": h => { h.api.issue = () => Promise.resolve(""); },
};
for (const [name, mutate] of Object.entries(lifetime)) test(`refusal has no side effect: ${name}`, () => {
  const h = navigation(); mutate(h); assert.equal(navigateSection(h.intent, h.api), false); assert.deepEqual(h.calls, []);
});

for (const stage of ["cancelCut", "pause"]) for (const change of ["view", "segment", "mode", "source"]) test(`new ${change} after ${stage} cannot seek`, () => {
  const h = navigation(); const old = h.api[stage];
  h.api[stage] = () => { old();
    if (change === "view") h.state.viewToken = {};
    if (change === "segment") h.state.segmentId = "new-line";
    if (change === "mode") h.state.mode = "source";
    if (change === "source") h.p.sources.A.generation = "new";
  };
  assert.equal(navigateSection(h.intent, h.api), false);
  assert.equal(h.calls.some(c => Array.isArray(c)), false);
});

for (const callback of ["current", "issue"]) test(`ownership rechecked after reentrant ${callback}`, () => {
  const h = navigation(); h.api[callback] = () => { h.state.project = clone(h.p); return callback === "current" ? true : ""; };
  assert.equal(navigateSection(h.intent, h.api), false); assert.deepEqual(h.calls, []);
});

for (const afterPause of [false, true]) for (const replacement of ["option", "DOM"]) test(`readiness replaces ${replacement} ${afterPause ? "after pause" : "before admission"}: no stale seek`, () => {
  const h = navigation(), originalNode = {}, originalChoice = h.intent.key;
  let node = originalNode, choice = originalChoice, calls = 0;
  h.api.current = () => node === originalNode && choice === originalChoice;
  h.api.issue = () => {
    calls++;
    if (calls === (afterPause ? 3 : 1)) {
      if (replacement === "option") choice = "newer choice";
      else node = {};
    }
    return "";
  };
  assert.equal(navigateSection(h.intent, h.api), false);
  assert.equal(h.calls.some(c => Array.isArray(c)), false);
  if (!afterPause) assert.deepEqual(h.calls, []);
});

for (const callback of ["snapshot", "issue", "current", "cancelCut", "pause", "seek"]) test(`throw in ${callback} stops further work`, () => {
  const h = navigation(); h.api[callback] = () => { throw new Error("controlled"); };
  assert.equal(navigateSection(h.intent, h.api), false);
});

test("new ownership during seek never gets a success/focus continuation", () => {
  const h = navigation(); h.api.seek = time => { h.calls.push(["seek", time]); h.state.viewToken = {}; };
  assert.equal(navigateSection(h.intent, h.api), false); assert.deepEqual(h.calls, ["cancelCut", "pause", ["seek", 8.1]]);
});

test("capture refuses invalid key, stale plan and another view's segment", () => {
  const h = navigation(), p = plan(h.p);
  assert.equal(captureSectionIntent(h.state, p, "missing"), null);
  h.p.revision++; assert.equal(captureSectionIntent(h.state, p, p.sections[0].key), null);
  assert.equal(navigateSection(null), false); assert.equal(navigateSection(h.intent), false);
  assert.equal(captureSectionIntent(h.state, { ...p, sections: null }, "key"), null);
  assert.equal(captureSectionIntent(null, p, "key"), null);
});

