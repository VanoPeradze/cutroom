const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const appSource = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8")
  .replace(/^import .*;\r?\n/gm, "")
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, "");
const plain = (value) => JSON.parse(JSON.stringify(value));

function app() {
  const nodes = new Map();
  const node = (id = "") => ({
    id, value: "", dataset: {}, attrs: {}, listeners: {}, controls: [], style: { setProperty() {} },
    classList: { add() {}, remove() {}, toggle() {} },
    setAttribute(key, value) { this.attrs[key] = value; },
    removeAttribute(key) { delete this.attrs[key]; },
    addEventListener(key, callback) { this.listeners[key] = callback; },
    querySelectorAll() { return this.controls; }, querySelector() { return node(); },
    focus() { this.focused = true; }, scrollIntoView() { this.scrolled = true; },
  });
  const document = {
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, node(id)); return nodes.get(id); },
    querySelectorAll() { return []; }, querySelector() { return null; }, addEventListener() {},
  };
  const context = vm.createContext({ document, console, dictionaries: { en: {} }, setTimeout, clearTimeout,
    window: { addEventListener() {} }, requestAnimationFrame: (callback) => callback() });
  const run = (code) => vm.runInContext(code, context);
  run(fs.readFileSync(path.join(__dirname, "../web/source-tracks.js"), "utf8").replace(/^export /gm, ""));
  run(fs.readFileSync(path.join(__dirname, "../web/timeline.js"), "utf8").replace(/^export /gm, ""));
  run(appSource);
  run(`cacheElements();
    globalThis.pauses = 0; globalThis.seeks = []; globalThis.edits = []; globalThis.messages = [];
    state.project = { id: "p", sources: { A: { duration: 100, fps: 29.97, has_audio: true }, B: { duration: 80 } },
      settings: {}, manual: { source_mixer: { sync_offset: 0 } },
      draft: { keep_ranges: [{ start: 0, end: 20 }, { start: 30, end: 100 }], camera_plan: [{ start: 0, end: 100, camera: "stacked" }] } };
    state.studio.open = true;
    state.timeline = {
      selectRange(start, end) { setManualSelection({start,end}); },
      clearSelection() { setManualSelection(null); },
    };
    pauseAllMedia = () => { pauses++; state.preview.playing = false; };
    seekPreview = (time) => seeks.push({ time, mode: state.preview.mode });
    renderManualControls = renderRangeEditors;
    renderSourceMixer = highlightTranscriptSelection = syncSecondaryPreview = () => {};
    setAdvanced = (open) => { state.studio.open = open; };
    selectAdvancedTab = (tab) => { globalThis.selectedTab = tab; };
    toast = (text) => messages.push(text);
    applyManualEdit = async (action, payload) => { edits.push({action, ...payload}); return state.project; };
  `);
  for (const prefix of ["layout", "timeline"]) {
    nodes.get(`${prefix}RangeForm`).controls = [nodes.get(`${prefix}RangeStart`), nodes.get(`${prefix}RangeEnd`), node("submit")];
  }
  return { run, nodes };
}

test("manual actions dispatch to selected source; transcript and layout actions retain entire-edit scope", async () => {
  const { run } = app();
  run('setEditTarget("B"); setManualSelection({start:1,end:3});');
  await run('runManualRangeEdit("delete_range")');
  await run('handleTimelineEdit({action:"split",time:4})');
  await run('runManualRangeEdit("delete_range","edit")');
  assert.deepEqual(plain(run('edits')), [
    {action:'track_remove_range',slot:'B',start:1,end:3},
    {action:'track_split',slot:'B',time:4},
    {action:'delete_range',start:1,end:3},
  ]);
  run('openTimelineLayout({start:3,end:5})');
  assert.equal(run('activeEditTarget()'), 'edit');
});

test("source clip inspector sends timeline and media-local trim fields independently", async () => {
  const { run, nodes } = app();
  run('setEditTarget("B"); state.trimClip={id:"B:base",projectId:"p",start:0,end:80};');
  nodes.get('clipTrimIn').value='5'; nodes.get('clipTrimOut').value='10'; nodes.get('clipSourceIn').value='30';
  await run('applySelectedClipTrim({preventDefault(){}})');
  assert.deepEqual(plain(run('edits')), [{action:'track_trim',slot:'B',clip_id:'B:base',start:5,end:10,source_start:30}]);
});

test("source time parser accepts seconds and exact conventional timecodes, not malformed or ambiguous input", () => {
  const { run } = app();
  for (const [raw, expected] of [["0",0],[" 90.125 ",90.125],["01:02.125",62.125],["1:02:03.000001",3723.000001],["100:00",6000]]) {
    assert.equal(run(`parseSourceTime(${JSON.stringify(raw)})`), expected);
  }
  for (const raw of ["", " ", "-1", "+2", "1e2", "0x10", "1,2", "1:60", "1:60:00", "1:2:60", "1:2:3:4", ":20", "1.", "1.0000001", "Infinity", "NaN"]) {
    assert.ok(Number.isNaN(run(`parseSourceTime(${JSON.stringify(raw)})`)), raw);
  }
});

test("time fields format millisecond rollover and invalid durations safely", () => {
  const { run } = app();
  for (const [raw, expected] of [["0","00:00.000"],["59.9999","01:00.000"],["3600.125","60:00.125"],["-1","00:00.000"],["NaN","00:00.000"],["Infinity","00:00.000"]]) {
    assert.equal(run(`formatSourceTime(${raw})`), expected);
  }
});

for (const prefix of ["layout", "timeline"]) {
  test(`${prefix} typed selection pauses media and seeks exact source time, including omitted footage`, () => {
    const { run, nodes } = app();
    nodes.get(`${prefix}RangeStart`).value = "00:21.125";
    nodes.get(`${prefix}RangeEnd`).value = "30.875";
    assert.equal(run(`selectTypedRange("${prefix}")`), true);
    assert.deepEqual(plain(run("state.manualSelection")), { start:21.125,end:30.875 });
    assert.deepEqual(plain(run("seeks")), [{ time:21.125,mode:"edit" }], "a range seek preserves the chosen playback mode");
    assert.equal(run("pauses"), 1);
    assert.deepEqual(plain(run("edits")), [], "selecting must never remove or apply a layout");
    assert.equal(nodes.get("layoutRangeStart").value, "00:21.125");
    assert.equal(nodes.get("timelineRangeEnd").value, "00:30.875");
    assert.equal(nodes.get("layoutScopeBadge").textContent, "Selected range");
  });
}

test("typed range rejects reversed, negative, malformed, tiny and out-of-source values without changing the edit", () => {
  for (const [start,end,invalid] of [["5","3","End"],["-1","3","Start"],["bad","3","Start"],["3","3.079","End"],["3","101","End"],["100","100","Start"]]) {
    const { run,nodes } = app();
    run("setManualSelection({start:1,end:2})");
    nodes.get("layoutRangeStart").value = start;
    nodes.get("layoutRangeEnd").value = end;
    assert.equal(run('selectTypedRange("layout")'), false, `${start}→${end}`);
    assert.deepEqual(plain(run("state.manualSelection")), {start:1,end:2});
    assert.equal(nodes.get(`layoutRange${invalid}`).attrs["aria-invalid"], "true");
    assert.equal(nodes.get(`layoutRange${invalid}`).focused, true);
    assert.equal(run("pauses"), 0);
    assert.deepEqual(plain(run("edits")), []);
  }
});

test("an exact80ms range and the rounded displayed source endpoint remain selectable", () => {
  const {run,nodes} = app();
  nodes.get("layoutRangeStart").value = "0.10"; nodes.get("layoutRangeEnd").value = "0.18";
  assert.equal(run('selectTypedRange("layout")'), true);
  run("state.project.sources.A.duration = 12.1236; state.timeline.clearSelection(); renderRangeEditors();");
  assert.equal(nodes.get("layoutRangeEnd").value, "00:12.124");
  assert.equal(run('selectTypedRange("layout")'), true);
  assert.equal(run("state.manualSelection.end"), 12.1236, "clamp quantized source endpoint, never select beyond media");
});

test("external selections sync both forms; unrelated renders preserve unsubmitted typed input", () => {
  const {run,nodes} = app();
  run("renderRangeEditors()");
  nodes.get("layoutRangeStart").value = "12.8";
  nodes.get("layoutRangeForm").dataset.dirty = "true";
  run("renderRangeEditors()");
  assert.equal(nodes.get("layoutRangeStart").value, "12.8");
  run("setManualSelection({start:31.125,end:35.5})");
  assert.equal(nodes.get("layoutRangeStart").value, "00:31.125");
  assert.equal(nodes.get("timelineRangeEnd").value, "00:35.500");
  assert.equal(nodes.get("layoutRangeForm").dataset.dirty, "false");
  run("state.timeline.clearSelection()");
  assert.equal(nodes.get("layoutScopeBadge").textContent, "Entire edit");
  assert.equal(nodes.get("timelineRangeStart").value, "00:00.000");
  assert.equal(nodes.get("timelineRangeEnd").value, "01:40.000");
});

test("busy and draftless projects disable inputs and block typed selection", () => {
  for (const setup of ["state.transcriptSaving=true", "state.manualEditBusy=true", "state.project.draft=null"]) {
    const {run,nodes} = app();
    run(`${setup}; renderRangeEditors();`);
    assert.ok(nodes.get("layoutRangeForm").controls.every((control) => control.disabled));
    assert.equal(run('selectTypedRange("layout")'), false);
    assert.equal(run("pauses"), 0);
  }
});

test("opening a timeline layout pauses, opens framing and seeks source rather than edited output time", () => {
  const {run,nodes} = app();
  assert.equal(run('openTimelineLayout({start:40,end:48,camera:"pip"})'), true);
  assert.equal(run("selectedTab"), "framing");
  assert.deepEqual(plain(run("state.manualSelection")), {start:40,end:48});
  assert.deepEqual(plain(run("seeks")), [{time:40,mode:"edit"}]);
  assert.equal(run("pauses"), 1);
  assert.equal(nodes.get("layoutRangeForm").scrolled, true);
  run("delete state.project.sources.B");
  assert.equal(run("openTimelineLayout(null)"), true);
  assert.equal(nodes.get("embeddedCameraEditor").scrolled, true);
  run("state.manualEditBusy=true");
  assert.equal(run("openTimelineLayout(null)"), false);
});

test("layout choice uses the selected source range and explicit entire-edit scope never leaks selection", async () => {
  const {run} = app();
  run("bindEvents(); setManualSelection({start:40,end:48})");
  await run('elements.sourceLayoutChoices.listeners.click({target:{closest:()=>({dataset:{layout:"pip"}})}})');
  assert.deepEqual(plain(run("edits")), [{action:"set_camera_layout",layout:"pip",start:40,end:48}]);
  await run('elements.applyLayoutAll.listeners.click()');
  assert.deepEqual(plain(run("edits.at(-1)")), {action:"set_camera_layout",layout:"pip",start:0,end:100});
  run("setManualSelection({start:22,end:24})");
  await run('applySourceLayout("selection")');
  assert.equal(run("edits.length"), 2, "entirely removed footage cannot receive a live layout");
  run("elements.layoutWholeEdit.listeners.click()");
  assert.equal(run("state.manualSelection"), null);
  assert.equal(run("elements.layoutScopeBadge.textContent"), "Entire edit");
});

test("B coverage uses signed source-time offsets and actual video duration, including no-overlap cases", () => {
  const {run} = app();
  for (const [offset,duration,expected] of [[10,80,{start:10,end:90,full:false}],[-10,120,{start:0,end:100,full:true}],[-90,80,{start:0,end:0,full:false}],[110,80,{start:100,end:100,full:false}],[0,100,{start:0,end:100,full:true}]]) {
    assert.deepEqual(plain(run(`sourceBCoverage({A:{duration:100},B:{duration:${duration}}},${offset})`)),expected);
  }
  assert.deepEqual(plain(run("sourceBCoverage({A:{duration:100},B:{duration:120,video_duration:80}},0)")), {start:0,end:80,full:false});
});

test("semantic source roles survive mixer saves and do not turn into AI choice", () => {
  const {run} = app();
  for (const value of ['screen', 'camera', 'stacked', 'pip']) assert.equal(run(`sourceMixerLayoutFromSetting('${value}')`), value);
  run("state.project.manual.source_mixer.screen_slot='B';state.project.manual.source_mixer.camera_slot='A'");
  assert.equal(run("sourceMixerLayoutFromSetting('A')"), 'camera');
  assert.equal(run("sourceMixerLayoutFromSetting('B')"), 'screen');
});

test("source mixer refresh replaces the timeline snapshot without resetting its selection or zoom", () => {
  const {run} = app();
  run(`state.timeline.project={id:state.project.id};state.timeline.zoom=3;
    state.timeline.selection={start:40,end:48};state.timeline.scheduleDraw=()=>{globalThis.redrawn=true};
    refreshSourceMixerTimeline();`);
  assert.equal(run('state.timeline.project === state.project'),true);
  assert.equal(run('state.timeline.zoom'),3);
  assert.deepEqual(plain(run('state.timeline.selection')),{start:40,end:48});
  assert.equal(run('redrawn'),true);
});

test("unsubmitted layout times cannot apply a composition to the old range", async () => {
  const {run} = app();
  run(`setManualSelection({start:40,end:48});
    elements.layoutRangeForm.hidden=false; elements.layoutRangeForm.dataset.dirty='true';`);
  await run('applySourceLayout("selection")');
  await run('applySourceLayout("all")');
  assert.equal(run('edits.length'), 0);
});

test("B sync nudges persist precise source frames without accumulating display rounding", async () => {
  const {run} = app();
  run(`globalThis.offsets=[];
    saveSourceMixer = async ({sync_offset}) => {
      offsets.push(sync_offset); state.project.manual.source_mixer.sync_offset=sync_offset; return state.project;
    };`);
  for (let index=0; index<10; index++) {
    run("nudgeSourceSync(1)");
    await new Promise(setImmediate);
  }
  assert.ok(Math.abs(run("offsets.at(-1)") - 10/29.97) < 1e-12);
  run("state.project.sources.A.fps = 59.94; nudgeSourceSync(-1)");
  await new Promise(setImmediate);
  assert.ok(Math.abs(run("offsets.at(-1)") - (10/29.97-1/59.94)) < 1e-12);
  run("state.project.sources.A.fps = 0; state.project.manual.source_mixer.sync_offset = 0; nudgeSourceSync(1)");
  await new Promise(setImmediate);
  assert.equal(run("offsets.at(-1)"),1/30);
  run("state.project.manual.source_mixer.sync_offset=600; nudgeSourceSync(1)");
  await new Promise(setImmediate);
  assert.equal(run("offsets.at(-1)"),600);
  run("state.project.manual.source_mixer.sync_offset=-600; nudgeSourceSync(-1)");
  await new Promise(setImmediate);
  assert.equal(run("offsets.at(-1)"),-600);
  const saved = run("offsets.length");
  run("state.manualEditBusy=true; nudgeSourceSync(1); state.manualEditBusy=false; delete state.project.sources.B; nudgeSourceSync(1)");
  await new Promise(setImmediate);
  assert.equal(run("offsets.length"),saved);
});
