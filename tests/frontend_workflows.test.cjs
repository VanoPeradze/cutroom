const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

test("compact persistent timeline keeps all lanes visible and preserves seek coordinates", () => {
  const timelineSource = fs.readFileSync(path.join(__dirname, "../web/timeline.js"), "utf8").replace(/^export /gm, "");
  const scope = vm.createContext({ window: { devicePixelRatio: 1 } });
  vm.runInContext(timelineSource + "\nglobalThis.TimelineView = TimelineView;", scope);
  const labels = [];
  const context = new Proxy({
    fillText(text, x, y) { labels.push({ text, y }); },
    measureText(text) { return { width: text.length * 6 }; },
    createLinearGradient() { return { addColorStop() {} }; },
  }, { get(target, key) { return key in target ? target[key] : () => {}; } });
  const timeline = Object.create(scope.TimelineView.prototype);
  Object.assign(timeline, {
    context, zoom: 1, images: [], playhead: 0, selection: null, hoverTime: null,
    canvas: { style: {}, getBoundingClientRect: () => ({ left: 0, width: 600 }) },
    scroll: { clientWidth: 600, closest: () => ({}) },
    project: { sources: { A: { duration: 12 } }, draft: { keep_ranges: [{ start: 0, end: 12 }], camera_plan: [{ start: 0, end: 12, camera: "A" }] } },
  });
  timeline.draw();
  assert.equal(timeline.canvas.height, 180);
  for (const label of ["EDIT", "LAYOUT", "AUDIO"]) assert.ok(labels.some(row => row.text === label && row.y < 180));
  assert.equal(timeline.timeFromEvent({ clientX: 300 }), 6);
  // Fit must fit the visible phone viewport, not force a hidden 520px timeline.
  timeline.scroll.clientWidth = 290;
  timeline.canvas.getBoundingClientRect = () => ({ left: 0, width: 290 });
  timeline.draw();
  assert.equal(timeline.canvas.style.width, "290px");
  assert.equal(timeline.timeFromEvent({ clientX: 145 }), 6);
  timeline.scroll.clientWidth = 600;
  timeline.canvas.getBoundingClientRect = () => ({ left: 0, width: 600 });
  timeline.scroll.closest = () => null;
  timeline.draw();
  assert.equal(timeline.canvas.height, 310);
  assert.equal(timeline.timeFromEvent({ clientX: 300 }), 6);
});

test("creator frame applies the camera role on top without changing YouTube output", async () => {
  const { run } = app();
  run(`
    state.project.sources.B = { duration: 20, has_audio: true };
    state.project.manual = { source_mixer: { screen_slot: "B", camera_slot: "A" } };
    state.project.draft = { keep_ranges: [{ start: 0, end: 20 }] };
    state.project.settings = { goal: "youtube", aspect: "16:9", target_duration: 120 };
    elements.aspectSelect.value = "16:9";
    sourceMixerControlBusy = () => false;
    pauseAllMedia = () => {};
    saveSourceMixer = async (payload) => { globalThis.savedFrame = payload; return state.project; };
    applyFramingPreview = () => { globalThis.frameUpdated = true; };
    scheduleSettingsPatch = () => {};
    applySourceLayout = async (scope) => { globalThis.frameScope = scope; };
  `);
  await run("applyCreatorFrame()");
  assert.equal(run("savedFrame.first_slot"), "A");
  assert.equal(run("savedFrame.stack_fit"), "cover");
  assert.equal(run("savedFrame.primary_role"), "screen");
  assert.equal(run("elements.aspectSelect.value"), "16:9");
  assert.equal(run("state.project.settings.goal"), "youtube");
  assert.equal(run("state.project.settings.target_duration"), 120);
  assert.equal(run("frameUpdated"), true);
  assert.equal(run("frameScope"), "all");
  assert.equal(run("state.sourceMixerLayout"), "stacked");
});

test("embedded crop preview covers only the chosen rectangle at every player size", () => {
  const { run } = app();
  for (const sourceRatio of [16 / 9, 4 / 3]) {
    const geometry = run(`embeddedFacePreviewGeometry({x:.7,y:.05,w:.25,h:.3}, ${sourceRatio}, ${(9 / 16) / .34})`);
    const cropLeft = geometry.left + geometry.width * .7;
    const cropRight = cropLeft + geometry.width * .25;
    const cropTop = geometry.top + geometry.height * .05;
    const cropBottom = cropTop + geometry.height * .3;
    assert.ok(cropLeft <= .001 && cropRight >= 99.999);
    assert.ok(cropTop <= .001 && cropBottom >= 99.999);
    assert.ok(Math.abs(cropLeft + cropRight - 100) < .001);
    assert.ok(Math.abs(cropTop + cropBottom - 100) < .001);
  }
});

// Execute the shipped UI functions without starting a server or importing media.
// DOM/media doubles expose lifecycle races deterministically; backend calls remain mocked.
const source = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8")
  .replace(/^import .*;\r?\n/gm, "")
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, "");

function node(id = "") {
  const children = new Map();
  return {
    id, dataset: {}, style: { setProperty() {} }, listeners: {}, hidden: false,
    children: [], parentElement: null,
    classList: { add() {}, remove() {}, toggle() {} },
    querySelector(key) { if (!children.has(key)) children.set(key, node(key)); return children.get(key); },
    querySelectorAll() { return []; },
    addEventListener(type, callback) { this.listeners[type] = callback; },
    setAttribute() {}, removeAttribute() {}, append() {}, replaceChildren() {},
    appendChild(child) { return this.insertBefore(child, null); },
    insertBefore(child, before) {
      if (before && before.parentElement !== this) throw new Error("NotFoundError: reference node is in another dock");
      if (child.parentElement) child.parentElement.children = child.parentElement.children.filter((item) => item !== child);
      const index = before ? this.children.indexOf(before) : this.children.length;
      this.children.splice(index, 0, child);
      child.parentElement = this;
      return child;
    },
  };
}

function app() {
  const nodes = new Map();
  const selectors = new Map();
  const document = {
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, node(id)); return nodes.get(id); },
    querySelectorAll(selector) { return selectors.get(selector) || []; },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    createElement: node, addEventListener() {},
  };
  const context = vm.createContext({ document, console, dictionaries: { en: {} }, setTimeout, clearTimeout, window: {addEventListener() {}}, requestAnimationFrame: (callback) => callback() });
  const run = (code) => vm.runInContext(code, context);
  run(fs.readFileSync(path.join(__dirname, "../web/keyboard.js"), "utf8").replace(/^export /gm, ""));
  run(fs.readFileSync(path.join(__dirname, "../web/source-tracks.js"), "utf8").replace(/^export /gm, ""));
  run(fs.readFileSync(path.join(__dirname, "../web/timeline.js"), "utf8").replace(/^export /gm, ""));
  run(source);
  run(`cacheElements();
    state.project = { id: "p", sources: { A: { duration: 100 } }, settings: { goal: "short" }, draft: { goal: "short", keep_ranges: [{ start: 0, end: 10 }] } };
    globalThis.messages = [];
    toast = (message, type) => messages.push({ message, type });
  `);
  return { context, run, nodes, selectors };
}

function settingsApp() {
  const fixture = app();
  const { run, nodes } = fixture;
  for (const [id, values] of Object.entries({
    goalChoices: ["short", "youtube", "podcast", "clean"],
    paceChoices: ["balanced", "gentle", "dynamic"],
    audioPresetChoices: ["clean", "natural", "tight"],
  })) {
    const buttons = values.map((value) => {
      const button = node();
      button.dataset.value = value;
      button.classList.toggle = (_class, active) => { button.active = active; };
      return button;
    });
    nodes.get(id).querySelectorAll = () => buttons;
    nodes.get(id).querySelector = () => buttons.find((button) => button.active) || null;
  }
  for (const [id, values] of Object.entries({
    layoutSelect: ["auto", "A", "embedded_stack"], aspectSelect: ["source", "16:9", "9:16", "1:1", "4:5"],
    resolutionSelect: ["720", "1080", "2160"], qualitySelect: ["balanced", "high"],
    captionStyleSelect: ["clean"], captionPositionSelect: ["bottom"],
    spokenLanguageSelect: ["auto", "en"], performanceModeSelect: ["auto", "lite", "quality"],
  })) nodes.get(id).options = values.map((value) => ({ value }));
  nodes.get("layoutSelect").closest = () => null;
  run(`
    renderEditStyleChoices = renderCaptionControls = renderLanguageDetectionStatus = loadCropControls = () => {};
    state.project.sources.A.duration = 500;
    state.project.settings = { goal: "short", aspect: "9:16", target_duration: 75, edit_style: "smart", pace: "gentle" };
    state.system = { edit_styles: [
      { id: "smart", defaults: { goal: "short", aspect: "9:16", target_duration: 60, pace: "balanced" } },
      { id: "reaction_burst", defaults: { goal: "short", aspect: "9:16", target_duration: 45, pace: "dynamic", layout: "A", resolution: "1080", quality: "balanced", editorial_effects: true, audio_cleanup: { preset: "tight" } } },
      { id: "clean_vod", defaults: { goal: "youtube", aspect: "16:9", target_duration: 180, pace: "gentle", layout: "A", editorial_effects: false, audio_cleanup: { preset: "natural" } } },
    ] };
    hydrateSettings();
  `);
  return fixture;
}

test("live media and mixer autosaves do not pause, seek or reload the preview", async () => {
  for (const action of ['media_update','set_audio_mixer']) {
    const {run}=app();
    run(`
      state.project={id:'mix',revision:1,draft:{keep_ranges:[{start:0,end:10}]},sources:{A:{duration:10}},manual:{}};
      state.preview.playing=true;
      previewTimelineTime=()=>3; foregroundBusy=()=>false;
      renderReadiness=renderManualControls=renderSourceMixer=()=>{};
      flushProjectSaves=async()=>{}; updateMediaPreview=()=>{};
      pausePreview=renderDraft=seekSourcePreview=()=>{throw new Error('must keep playback continuous');};
      state.timeline={cancelPendingCut(){},scheduleDraw(){}};
      api=async()=>({project:{...state.project,revision:2,manual:{audio_mixer:{music_db:-6}}}});
    `);
    const result=await run(`applyManualEdit('${action}',{music_db:-6})`);
    assert.equal(result?.revision,2);
    assert.equal(run('state.preview.playing'),true);
    assert.equal(run('state.manualEditBusy'),false);
  }
});

test("late startup checks do not override a project opened from the welcome screen", async () => {
  const {run} = app();
  run(`
    state.project = null;
    state.projectViewToken = 0;
    bindEvents = () => {};
    applyTranslations = () => ({});
    initWelcome = () => ({});
    initLocalModels = () => null;
    initWorkspace = () => {};
    initializeKeyboardProfile = () => {};
    TimelineView = class {};
    AudioThresholdView = class {};
    loadProjects = async () => {};
    loadSystem = () => new Promise(resolve => { globalThis.releaseStartup = resolve; });
    globalThis.welcomed = false;
    showWelcome = () => { welcomed = true; };
  `);
  const starting = run("boot()");
  run(`state.project = {id: "chosen-project"}; state.projectViewToken += 1; releaseStartup();`);
  await starting;
  assert.equal(run("welcomed"), false);
  assert.equal(run("state.project.id"), "chosen-project");
});

test("generation hint follows the goal and remains correct after a style change", () => {
  const { run } = settingsApp();
  run(`
    state.dictionary = { oneDraft: "One main edit plus ranked Reel options" };
    setChoiceValue(elements.goalChoices, "youtube");
    applyGoalMode("youtube", true);
    applyEditStyle("reaction_burst");
  `);
  const hint = () => run(`elements.generateButton.querySelector('[data-i18n="oneDraft"]').textContent`);
  assert.equal(hint(), "A full-length YouTube cleanup — not a Reel");
  run('applyGoalMode("clean")');
  assert.match(hint(), /preserving its structure/);
  run('applyGoalMode("short")');
  assert.match(hint(), /ranked Reel options/);
});

test("frame rate is numeric, legacy-safe and synchronized in both export controls", () => {
  const { run } = settingsApp();
  assert.equal(run("currentSettings().fps"), 30);
  for (const fps of [24, 25, 30, 50, 60]) {
    run(`updateFrameRateControls(${fps}); applyEditStyle("reaction_burst");`);
    assert.equal(run("currentSettings().fps"), fps);
    assert.equal(run("elements.exportFpsSelect.value"), String(fps));
  }
  assert.match(run("elements.fpsHelp.textContent"), /repeat frames; no motion interpolation/);
  run('state.project.settings.fps = 60; hydrateSettings();');
  assert.equal(run("elements.fpsSelect.value"), "60");
  assert.equal(run("selectedFrameRate('999')"), 30);
});

function aspectApp() {
  const fixture = settingsApp();
  fixture.run(`
    globalThis.aspectButtons = ['16:9', '9:16'].map(aspect => ({dataset: {outputAspect: aspect},
      setAttribute(key, value) { this[key] = value; }}));
    elements.quickAspectChoices.querySelectorAll = () => aspectButtons;
    state.project.manual = { crops: [{start: 1, end: 4, x: .3}] };
    state.project.editor_sequence = { tracks: {A: [{id:'clip-1', start: 1, end: 4}]} };
    state.framingDraft = { crop: {x:.3}, scope: {start:1,end:4} };
    globalThis.beforeAspectEdit = JSON.stringify([state.project.manual, state.project.editor_sequence, state.framingDraft]);
    foregroundBusy = () => false;
    editorProject = () => state.project;
    previewPlaybackTime = () => 3;
    applyPreviewPipGeometry = () => {};
    syncSecondaryPreview = time => { globalThis.aspectPreviewTime = time; };
    renderSourceCompositionPreview = mixer => { if (!mixer) throw new Error('Missing source mixer'); };
    applyFramingPreview = () => { throw new Error('Aspect must not stage a crop or seek'); };
    globalThis.aspectRequests = [];
    api = async (url, options) => {
      const patch = JSON.parse(options.body);
      aspectRequests.push(patch);
      return {project: {...state.project, settings: {...state.project.settings, ...patch.settings}, revision: 1}};
    };
  `);
  return fixture;
}

test("manual aspect buttons update immediately and save only output format, without AI or clip changes", async () => {
  const {run} = aspectApp();
  for (const aspect of ['16:9', '9:16']) {
    run(`setOutputAspect('${aspect}')`);
    assert.equal(run('elements.previewStage.dataset.aspect'), aspect);
    assert.equal(run('aspectPreviewTime'), 3);
    assert.equal(run(`aspectButtons.find(button => button.dataset.outputAspect === '${aspect}')['aria-pressed']`), 'true');
    assert.equal(run('JSON.stringify([state.project.manual, state.project.editor_sequence, state.framingDraft])'), run('beforeAspectEdit'));
    assert.equal(run('state.draftDirtyReasons.size'), 0);
    assert.match(run('elements.studioDraftStatus.textContent'), new RegExp(aspect));
    await run("flushProjectSaves('p')");
    assert.equal(run('state.project.settings.aspect'), aspect);
    assert.equal(run('JSON.stringify(aspectRequests.at(-1).settings)'), JSON.stringify({aspect}));
    run('hydrateSettings()');
    assert.equal(run('elements.aspectSelect.value'), aspect);
  }
});

test("aspect dropdown uses the same no-rebuild output path", async () => {
  const {run} = aspectApp();
  run("bindEvents(); elements.aspectSelect.value = '1:1'; elements.aspectSelect.listeners.change();");
  assert.equal(run('elements.previewStage.dataset.aspect'), '1:1');
  assert.equal(run("aspectButtons.every(button => button['aria-pressed'] === 'false')"), true);
  await run("flushProjectSaves('p')");
  assert.equal(run('state.project.settings.aspect'), '1:1');
});

test("quick aspect changes reject invalid formats and cannot mutate a busy edit", () => {
  const {run} = aspectApp();
  run("setOutputAspect('invalid'); foregroundBusy = () => true; setOutputAspect('16:9');");
  assert.equal(run('elements.aspectSelect.value'), '9:16');
  assert.equal(run('state.saveQueues.size'), 0);
});

test("busy aspect dropdown restores the accepted pending format instead of leaking a rejected choice", async () => {
  const {run} = aspectApp();
  run("bindEvents(); setOutputAspect('16:9'); state.manualEditBusy = true; elements.aspectSelect.value = '9:16'; elements.aspectSelect.listeners.change();");
  assert.equal(run('elements.aspectSelect.value'), '16:9');
  assert.equal(run('elements.previewStage.dataset.aspect'), '16:9');
  await run("flushProjectSaves('p')");
  assert.equal(run('state.project.settings.aspect'), '16:9');
});

test("changing FPS in the export dialog persists without an AI rebuild", () => {
  const { run } = settingsApp();
  run(`bindEvents();
    scheduleSettingsPatch = (options) => { globalThis.fpsPatch = options; };
    elements.exportFpsSelect.value = "60";
    elements.exportFpsSelect.listeners.change();
  `);
  assert.equal(run("currentSettings().fps"), 60);
  assert.equal(run("fpsPatch.requiresRebuild"), false);
});

test("export submits the selected frame rate after saving", async () => {
  const { run } = settingsApp();
  run(`
    pauseAllMedia = () => {};
    flushProjectSaves = async () => { updateFrameRateControls(60); };
    api = async (url, options) => { globalThis.renderBody = JSON.parse(options.body); return { job: {id: "r"} }; };
    setActiveJob = () => {};
    pollExportJob = async () => ({});
    completeExportJob = async () => {};
  `);
  await run('startExport()');
  assert.equal(run("renderBody.fps"), 60);
});

test("style radios support arrow and boundary keys without consuming modified shortcuts", () => {
  const { run, nodes } = app();
  const radios = ["smart", "reaction_burst", "clean_vod"].map(value => {
    const button = node(value); button.dataset.value = value; button.closest = () => button; return button;
  });
  nodes.get("editStyleChoices").querySelectorAll = () => radios;
  run('chooseEditStyle = (id) => { globalThis.chosenStyle = id; state.selectedEditStyle = id; };');
  run('globalThis.keyTest = (event) => handleEditStyleKeydown(event);');
  let prevented = false;
  const send = (key, index, extra = {}) => {
    nodes.get("editStyleChoices").testEvent = { key, target: radios[index], preventDefault() { prevented = true; }, ...extra };
    run('keyTest(elements.editStyleChoices.testEvent)');
  };
  send("ArrowLeft", 0);
  assert.equal(run("chosenStyle"), "clean_vod");
  assert.equal(prevented, true);
  send("Home", 2);
  assert.equal(run("chosenStyle"), "smart");
  send("End", 0, { ctrlKey: true });
  assert.equal(run("chosenStyle"), "smart");
});

test("switching styles preserves the explicit goal, format and duration in either direction", () => {
  const { run } = settingsApp();
  for (const [goal, aspect, style, pace] of [
    ["youtube", "16:9", "reaction_burst", "dynamic"],
    ["clean", "source", "reaction_burst", "dynamic"],
    ["podcast", "1:1", "clean_vod", "gentle"],
    ["short", "4:5", "clean_vod", "gentle"],
  ]) {
    run(`
      setChoiceValue(elements.goalChoices, "${goal}"); applyGoalMode("${goal}", true);
      elements.aspectSelect.value = "${aspect}"; updateDurationControl(165);
      elements.resolutionSelect.value = "2160"; elements.qualitySelect.value = "high";
      applyEditStyle("${style}");
    `);
    assert.equal(run("currentSettings().goal"), goal);
    assert.equal(run("currentSettings().aspect"), aspect);
    assert.equal(run("currentSettings().target_duration"), 165);
    assert.equal(run("currentSettings().resolution"), "2160");
    assert.equal(run("currentSettings().quality"), "high");
    assert.equal(run("currentSettings().edit_style"), style);
    assert.equal(run("currentSettings().pace"), pace);
    if (["youtube", "clean"].includes(goal)) assert.equal(run("currentSettings().editorial_effects"), false);
  }
});

test("hydration restores the saved brief without applying the selected style defaults", () => {
  const { run } = settingsApp();
  run(`
    state.project.settings = { goal: "youtube", aspect: "16:9", target_duration: 155, edit_style: "reaction_burst", pace: "gentle", resolution: "2160", quality: "high" };
    hydrateSettings();
  `);
  assert.equal(run("currentSettings().goal"), "youtube");
  assert.equal(run("currentSettings().aspect"), "16:9");
  assert.equal(run("currentSettings().target_duration"), 155);
  assert.equal(run("currentSettings().edit_style"), "reaction_burst");
  assert.equal(run("currentSettings().pace"), "gentle");
  assert.equal(run("elements.durationGroup.hidden"), true);
});

for (const saving of [false, true])
  test(`upload refresh preserves settings while their save is ${saving ? "in flight" : "queued"}`, async () => {
    const { context, run } = settingsApp();
    run(`
      state.project.revision = 1; state.project.draft = null;
      renderSources = renderReadiness = renderSourceMixer = clearDraftRebuild = () => {};
      loadProjects = loadSystem = async () => {};
      validateUploadFile = () => "";
      globalThis.uploadStarted = new Promise((resolve) => { globalThis.markUploadStarted = resolve; });
      uploadWithProgress = () => new Promise((resolve) => { globalThis.finishUpload = resolve; markUploadStarted(); });
      globalThis.uploadSnapshot = { ...state.project, revision: 2, sources: { A: { duration: 500, generation: "new-media" } } };
      globalThis.patchBodies = [];
      api = (url, options = {}) => {
        if (options.method === "PATCH") {
          const body = JSON.parse(options.body); patchBodies.push(body);
          return new Promise((resolve) => { globalThis.finishPatch = () => resolve({project: {...uploadSnapshot, revision: 3, settings: body.settings}}); });
        }
        return Promise.resolve({project: uploadSnapshot});
      };
      globalThis.uploadOperation = uploadSource("A", { name: "test.mp4", size: 1 });
    `);
    await context.uploadStarted;
    run(`
      setChoiceValue(elements.goalChoices, "youtube"); applyGoalMode("youtube", true);
      updateDurationControl(165); elements.directorInstruction.value = "Keep my ending";
      applyEditStyle("reaction_burst");
      schedulePatch({settings: currentSettings()}, {delay: 60000});
      state.saveQueues.get("p").timer.unref();
      ${saving ? 'globalThis.saveOperation = flushProjectSaves("p");' : ""}
      finishUpload({project: uploadSnapshot});
    `);
    await context.uploadOperation;
    assert.equal(run("currentSettings().goal"), "youtube");
    assert.equal(run("currentSettings().aspect"), "16:9");
    assert.equal(run("currentSettings().target_duration"), 165);
    assert.equal(run("currentSettings().edit_style"), "reaction_burst");
    assert.equal(run("currentSettings().instruction"), "Keep my ending");
    assert.equal(run("state.project.sources.A.generation"), "new-media");
    if (!saving) run('globalThis.saveOperation = flushProjectSaves("p");');
    run("finishPatch();");
    await context.saveOperation;
    assert.equal(run("patchBodies[0].settings.goal"), "youtube");
    assert.equal(run("state.saveQueues.get('p').inFlightPatch"), null);
  });

test("an older source snapshot cannot undo a completed settings save or newer media", () => {
  const { run } = settingsApp();
  run(`
    const older = { ...state.project, revision: 2 };
    state.project = { ...state.project, revision: 3, settings: { goal: "youtube", aspect: "16:9", target_duration: 150 }, sources: { A: {duration: 500, generation: "newest"} } };
    state.project = reconcileProjectSnapshot(older); hydrateSettings();
  `);
  assert.equal(run("currentSettings().goal"), "youtube");
  assert.equal(run("currentSettings().aspect"), "16:9");
  assert.equal(run("state.project.sources.A.generation"), "newest");
  assert.equal(run("state.project.revision"), 3);
});

test("generation reads the current brief after saving and preflights that same goal", async () => {
  const { context, run } = settingsApp();
  run(`
    renderReadiness = renderReelCandidates = pauseAllMedia = showAnalysis = () => {};
    flushProjectSaves = () => new Promise((resolve) => { globalThis.finishSave = resolve; });
    ensureStoryAIReady = async (goal) => { globalThis.preparedGoal = goal; };
    api = async (_url, options) => { globalThis.submittedBrief = JSON.parse(options.body); return {job:{id:"new"}}; };
    pollJob = async () => {};
    globalThis.operation = generateDraft();
    setChoiceValue(elements.goalChoices, "youtube"); applyGoalMode("youtube", true);
    elements.directorInstruction.value = "The latest brief"; updateDurationControl(135);
    finishSave();
  `);
  await context.operation;
  assert.equal(run("submittedBrief.goal"), "youtube");
  assert.equal(run("submittedBrief.aspect"), "16:9");
  assert.equal(run("submittedBrief.target_duration"), 135);
  assert.equal(run("submittedBrief.instruction"), "The latest brief");
  assert.equal(run("preparedGoal"), "youtube");
});

test("navigation during the save flush cannot submit another project's controls", async () => {
  const { context, run } = settingsApp();
  run(`
    renderReadiness = renderReelCandidates = pauseAllMedia = showAnalysis = () => {};
    flushProjectSaves = () => new Promise((resolve) => { globalThis.finishSave = resolve; });
    globalThis.requests = [];
    ensureStoryAIReady = async () => requests.push("AI");
    api = async (url) => requests.push(url);
    globalThis.operation = generateDraft();
    state.project = {...state.project, id: "different-project"}; state.projectViewToken += 1;
    finishSave();
  `);
  await context.operation;
  assert.deepEqual(Array.from(context.requests), []);
  assert.equal(run("state.jobStartLocks.size"), 0);
});

function transcriptApp() {
  const fixture = app();
  fixture.run(`
    state.project.analysis = {transcript:{segments:[
      {id:'s1',start:0,end:2,text:'Original first line'},
      {id:'s2',start:2,end:4,text:'Original second line'}
    ]}};
    state.timeline = {selectRange: (start,end) => {state.manualSelection={start,end};}};
    pauseAllMedia = () => { globalThis.pausedMedia = true; };
    seekPreview = time => {globalThis.soughtTime=time;};
    elements.transcriptSearch.value = '';
    renderLanguageDetectionStatus = () => {};
  `);
  return fixture;
}

function independentTranscriptApp() {
  const fixture = transcriptApp();
  fixture.run(`
    state.project.sources.A.has_audio=true;
    state.project.sources.B={duration:100,has_audio:true};
    state.project.manual={source_mixer:{audio_slot:'A'},source_tracks:{A:[{id:'a',start:20,end:24,source_start:0}]}};
    state.project.draft.keep_ranges=[{start:0,end:100}]; state.project.draft.cuts=[];
    state.project.analysis.audio_source='A';
    state.timeline.clearSelection=()=>{state.manualSelection=null;};
    renderSourceMixer=hydrateSourceMixerLayout=()=>{};
    globalThis.submitted=[];
    applyManualEdit=async(action,payload)=>{submitted.push({action,...payload});return state.project;};
  `);
  return fixture;
}

test('moved audio transcript selects and removes mapped timeline time, not original source time', async () => {
  const {run} = independentTranscriptApp();
  run("state.editTarget='B'; selectTranscriptLine(state.project.analysis.transcript.segments[0]);");
  assert.equal(run('state.editTarget'), 'edit');
  assert.deepEqual(JSON.parse(JSON.stringify(run('state.manualSelection'))), {start:20,end:22});
  assert.equal(run('soughtTime'), 20);
  assert.match(run('elements.transcriptEditTime.textContent'), /Timeline 00:20.0 – 00:22.0 · Source A 00:00.0 – 00:02.0/);
  await run('runManualRangeEdit("delete_range","edit")');
  assert.deepEqual(JSON.parse(JSON.stringify(run('submitted'))), [{action:'delete_range',start:20,end:22}]);
});

test('transcript Shift selection maps a contiguous moved passage through adjacent split clips', () => {
  const {run} = independentTranscriptApp();
  run(`state.project.manual.source_tracks.A=[{id:'a1',start:20,end:22,source_start:0},{id:'a2',start:22,end:24,source_start:2}];
    selectTranscriptLine(state.project.analysis.transcript.segments[0]);
    selectTranscriptLine(state.project.analysis.transcript.segments[1],true);`);
  assert.deepEqual(JSON.parse(JSON.stringify(run('state.manualSelection'))), {start:20,end:24});
  assert.equal(run('soughtTime'), 22);
});

test('disjoint or repeated transcript mappings clear stale selection without removing unrelated time', async () => {
  for (const clips of [
    [{id:'a1',start:20,end:21,source_start:0},{id:'a2',start:30,end:31,source_start:1}],
    [{id:'a1',start:20,end:22,source_start:0},{id:'a2',start:30,end:32,source_start:0}],
  ]) {
    const {run} = independentTranscriptApp();
    run(`state.project.manual.source_tracks.A=${JSON.stringify(clips)}; state.manualSelection={start:20,end:32};
      selectTranscriptLine(state.project.analysis.transcript.segments[0]);`);
    assert.equal(run('state.manualSelection'), null);
    assert.match(run('messages.at(-1).message'), /separate timeline sections/);
    assert.equal(run('elements.transcriptEditText.value'), 'Original first line');
    await run('runManualRangeEdit("delete_range","edit")');
    assert.equal(run('submitted.length'), 0);
    run("elements.transcriptEditText.value='Text still editable'; bufferTranscriptText();");
    assert.equal(run('pendingTranscriptBuffers().length'), 1);
  }
});

test('missing audio passages and changed audio sources cannot reuse an earlier selection', () => {
  for (const change of ['state.project.manual.source_tracks.A=[];', "state.project.manual.source_mixer.audio_slot='B';"]) {
    const {run} = independentTranscriptApp();
    run(`state.manualSelection={start:1,end:2}; ${change} selectTranscriptLine(state.project.analysis.transcript.segments[0]);`);
    assert.equal(run('state.manualSelection'), null);
    assert.equal(run('elements.transcriptRemove.disabled'), true);
    assert.equal(run('elements.transcriptEditText.disabled'), false);
    assert.match(run('messages.at(-1).message'), /still edit/);
  }
});

test('B transcript mapping undoes the analyzed offset and handles trimmed source fragments', () => {
  const {run} = independentTranscriptApp();
  run(`state.project.analysis.audio_source='B'; state.project.analysis.audio_timeline_offset=5;
    state.project.manual.source_mixer.audio_slot='B';
    state.project.manual.source_tracks.B=[{id:'b',start:30,end:31,source_start:6}];
    state.project.analysis.transcript.segments=[{id:'b1',start:10,end:13,text:'B speech'}];
    selectTranscriptLine(state.project.analysis.transcript.segments[0]);`);
  assert.deepEqual(JSON.parse(JSON.stringify(run('state.manualSelection'))), {start:30,end:31});
  assert.match(run('elements.transcriptEditTime.textContent'), /Source B 00:05.0 – 00:08.0/);
  assert.equal(run('soughtTime'), 30);
});

test('transcript removal filtering and highlights follow mapped ranges without highlighting gaps', () => {
  const fixture = independentTranscriptApp();
  const {run,nodes} = fixture;
  const list = nodes.get('transcriptList');
  list.append = row => list.children.push(row);
  list.querySelectorAll = () => list.children;
  run('state.project.draft.cuts=[{start:20,end:22}]; elements.transcriptFilter.value="removed"; renderTranscript();');
  assert.equal(list.children.length, 1);
  const row = list.children[0];
  const seek = row.querySelector('.transcript-seek');
  assert.equal(seek.querySelector('time').textContent, 'T 00:20.0');
  assert.equal(seek.querySelector('b').textContent, 'Removed');
  const selections = [];
  row.classList.toggle = (name,on) => { if (name === 'selected') selections.push(on); };
  run('state.manualSelection={start:0,end:2}; highlightTranscriptSelection();');
  assert.equal(selections.at(-1), false);
  run('state.manualSelection={start:20,end:21}; highlightTranscriptSelection();');
  assert.equal(selections.at(-1), true);
  row.dataset.timelineRanges=JSON.stringify([{start:20,end:21},{start:30,end:31}]);
  run('state.manualSelection={start:24,end:26}; highlightTranscriptSelection();');
  assert.equal(selections.at(-1), false);
});

function sourceNavigationApp() {
  const fixture = app();
  fixture.run(`
    state.studio.open = true; state.preview.mode = 'source';
    state.project.sources.A.duration = 12;
    state.project.draft = {output_duration:8, keep_ranges:[{start:0,end:4},{start:6,end:10}], cuts:[{start:4,end:6},{start:10,end:12}]};
    Object.assign(elements.previewA, {currentTime:0, paused:true,
      play() { this.paused=false; return Promise.resolve(); }});
    globalThis.secondaryTimes=[];
    syncSecondaryPreview = time => secondaryTimes.push(time);
    updatePreviewCaption = () => {};
    pauseAllMedia = () => { state.preview.playRequest++; elements.previewA.paused=true; elements.previewB.paused=true; };
    state.timeline = {setPlayhead: time => {globalThis.playhead=time;}};
  `);
  return fixture;
}

test('paused seeking never jumps out of excluded footage, in either preview mode', () => {
  const {run} = sourceNavigationApp();
  for (const mode of ['source','edit']) {
    run(`state.preview.mode='${mode}'; seekPreview(5.25); onPreviewTimeUpdate(); onPreviewTimeUpdate();`);
    assert.equal(run('elements.previewA.currentTime'), 5.25);
    assert.equal(run('playhead'), 5.25);
  }
});

test('full-source playback crosses AI cuts and trailing removed footage without rewinding', async () => {
  const {run} = sourceNavigationApp();
  run('seekPreview(5.25);');
  await run('playPreview()');
  assert.equal(run('elements.previewA.currentTime'), 5.25);
  run('elements.previewA.currentTime=5.9; onPreviewTimeUpdate();');
  assert.equal(run('elements.previewA.currentTime'), 5.9);
  run('elements.previewA.currentTime=11; onPreviewTimeUpdate();');
  assert.equal(run('elements.previewA.currentTime'), 11);
  assert.equal(run('elements.previewA.paused'), false);
  assert.equal(run('elements.previewTime.textContent'), '00:11 / 00:12');
});

test('edited playback advances to the next kept clip and stops at the last kept boundary', async () => {
  const {run} = sourceNavigationApp();
  run("state.preview.mode='edit'; seekPreview(5.25);");
  await run('playPreview()');
  assert.equal(run('elements.previewA.currentTime'), 6);
  run('elements.previewA.currentTime=4.1; onPreviewTimeUpdate();');
  assert.equal(run('elements.previewA.currentTime'), 6);
  run('elements.previewA.currentTime=10.05; onPreviewTimeUpdate(); onPreviewTimeUpdate();');
  assert.equal(run('elements.previewA.currentTime'), 10);
  assert.equal(run('elements.previewA.paused'), true);
  assert.equal(run('elements.previewTime.textContent'), '00:08 / 00:08');
});

test('manual source seeking preserves Edited cut while inspecting an excluded source frame', () => {
  const {run} = sourceNavigationApp();
  run("state.preview.mode='edit'; seekSourcePreview(5.25); onPreviewTimeUpdate();");
  assert.equal(run('state.preview.mode'), 'edit');
  assert.equal(run('elements.previewMode.value'), 'edit');
  assert.equal(run('elements.previewA.currentTime'), 5.25);
  assert.match(run('elements.previewModeHint.textContent'), /inspecting excluded footage; Play skips/);
  assert.equal(run('elements.previewTime.textContent'), '00:04 / 00:08');
});

test('playback mode switching pauses both sources without changing footage or playhead', () => {
  const {run} = sourceNavigationApp();
  run("seekPreview(5); elements.previewA.paused=false; elements.previewB.paused=false; setPreviewMode('edit');");
  assert.equal(run('elements.previewA.currentTime'), 5);
  assert.equal(run('elements.previewA.paused && elements.previewB.paused'), true);
  assert.equal(run('elements.previewTime.textContent'), '00:04 / 00:08');
  run("setPreviewMode('source');");
  assert.equal(run('elements.previewTime.textContent'), '00:05 / 00:12');
  assert.equal(run('state.project.draft.cuts.length'), 2);
});

test('seeking and frame navigation never change either explicitly selected playback mode', () => {
  const {run} = sourceNavigationApp();
  for (const mode of ['edit','source']) {
    run(`setPreviewMode('${mode}'); seekSourcePreview(5);
      state.keyboardProfile='cutroom';
      handleEditorShortcut({key:'ArrowRight',preventDefault(){}}); onPreviewTimeUpdate();`);
    assert.equal(run('state.preview.mode'), mode);
    assert.equal(run('elements.previewMode.value'), mode);
    assert.ok(Math.abs(run('elements.previewA.currentTime') - (5 + 1 / 30)) < 1e-9);
    assert.equal(run('elements.previewA.paused'), true);
  }
});

test('seek slider maps the full source or edited cut according to its explicit mode', () => {
  const {run} = sourceNavigationApp();
  run('bindEvents(); elements.previewSeek.value="400"; elements.previewSeek.listeners.input(); onPreviewTimeUpdate();');
  assert.ok(Math.abs(run('elements.previewA.currentTime') - 4.8) < 1e-9);
  run("setPreviewMode('edit'); elements.previewSeek.value='500'; elements.previewSeek.listeners.input();");
  // The boundary between clips belongs to the next kept frame, not the cut.
  assert.equal(run('elements.previewA.currentTime'), 6);
  run("elements.previewSeek.value='1000'; elements.previewSeek.listeners.input();");
  assert.equal(run('elements.previewA.currentTime'), 10);
});

test('transcript selection pauses media and Shift selection keeps the whole passage', () => {
  const {run} = transcriptApp();
  run("selectTranscriptLine(state.project.analysis.transcript.segments[0]); selectTranscriptLine(state.project.analysis.transcript.segments[1], true);");
  assert.equal(run('pausedMedia'), true);
  assert.equal(run('soughtTime'), 2);
  assert.equal(run('state.manualSelection.start'), 0);
  assert.equal(run('state.manualSelection.end'), 4);
  assert.equal(run('elements.transcriptEditText.value'), 'Original second line');
});

test('multiline transcript drafts survive switching lines and filters until explicitly saved', () => {
  const {run} = transcriptApp();
  run(`selectTranscriptLine(state.project.analysis.transcript.segments[0]);
    elements.transcriptEditText.value = 'Edited first line\\nA second paragraph'; bufferTranscriptText();
    selectTranscriptLine(state.project.analysis.transcript.segments[1]);
    elements.transcriptEditText.value = 'Edited second line'; bufferTranscriptText();
    elements.transcriptFilter.value = 'removed'; renderTranscript();
    selectTranscriptLine(state.project.analysis.transcript.segments[0]);`);
  assert.equal(run('elements.transcriptEditText.value'), 'Edited first line\nA second paragraph');
  assert.equal(run('pendingTranscriptBuffers().length'), 2);
  assert.equal(run('state.project.analysis.transcript.segments[0].text'), 'Original first line');
});

test('manual edit busy transitions re-enable transcript controls without replacing live typed text', () => {
  const {run} = transcriptApp();
  run(`selectTranscriptLine(state.project.analysis.transcript.segments[0]);
    elements.transcriptEditText.value = 'Unsaved correction\\nSecond paragraph'; bufferTranscriptText();
    elements.transcriptEditText.value += ' still typing';
    state.manualEditBusy = true; renderManualControls();`);
  assert.equal(run('elements.transcriptEditText.disabled'), true);
  assert.equal(run('elements.transcriptNext.disabled'), true);
  assert.equal(run('elements.transcriptSave.disabled'), true);
  assert.equal(run('elements.transcriptEditText.value'), 'Unsaved correction\nSecond paragraph still typing');

  // applyManualEdit renders the draft while busy, then refreshes these controls
  // in finally. That last refresh must unlock the selected line, not refill it.
  run('state.manualEditBusy = false; renderManualControls();');
  assert.equal(run('elements.transcriptEditText.disabled'), false);
  assert.equal(run('elements.transcriptNext.disabled'), false);
  assert.equal(run('elements.transcriptSave.disabled'), false);
  assert.equal(run('elements.transcriptSaveAll.disabled'), false);
  assert.equal(run('elements.transcriptPrevious.disabled'), true);
  assert.equal(run('elements.transcriptEditText.value'), 'Unsaved correction\nSecond paragraph still typing');
  assert.equal(run('pendingTranscriptBuffers()[0].text'), 'Unsaved correction\nSecond paragraph');
  assert.equal(run('state.project.analysis.transcript.segments[0].text'), 'Original first line');
});

test('failed transcript saves preserve typed text and permit retry', async () => {
  const {run} = transcriptApp();
  run(`selectTranscriptLine(state.project.analysis.transcript.segments[0]);
    elements.transcriptEditText.value = 'Keep this correction'; bufferTranscriptText();
    applyManualEdit = async () => null;`);
  assert.equal(await run('saveTranscriptBuffers()'), false);
  assert.equal(run('elements.transcriptEditText.value'), 'Keep this correction');
  assert.equal(run('state.transcriptSaving'), false);
  assert.equal(run('pendingTranscriptBuffers().length'), 1);
  run(`applyManualEdit = async (_action, payload) => {state.project.analysis.transcript.segments[0].text=payload.text;return state.project;};`);
  assert.equal(await run('saveTranscriptBuffers()'), true);
  assert.equal(run('pendingTranscriptBuffers().length'), 0);
});

test('transcript save cannot overwrite a changed underlying line or accept empty text', async () => {
  const {run} = transcriptApp();
  run(`selectTranscriptLine(state.project.analysis.transcript.segments[0]);
    elements.transcriptEditText.value = 'My correction'; bufferTranscriptText();
    state.project.analysis.transcript.segments[0].text='Newer server correction';
    applyManualEdit=async()=>{throw new Error('must not submit');};`);
  assert.equal(await run('saveTranscriptBuffers()'), false);
  assert.equal(run('elements.transcriptEditText.value'), 'My correction');
  run("discardTranscriptBuffer(); elements.transcriptEditText.value = ' '; bufferTranscriptText();");
  assert.equal(await run('saveTranscriptBuffers()'), false);
  assert.equal(run('pendingTranscriptBuffers().length'), 1);
});

test('pending transcript changes block export and are isolated to their project', () => {
  const {run} = transcriptApp();
  run(`selectTranscriptLine(state.project.analysis.transcript.segments[0]);
    elements.transcriptEditText.value='Unsaved correction'; bufferTranscriptText();
    openStudioTab = tab => {globalThis.opened=tab;};`);
  assert.equal(run('requireSavedTranscript()'), false);
  assert.equal(run('opened'), 'transcript');
  run("state.project.id='another-project';");
  assert.equal(run('requireSavedTranscript()'), true);
  assert.equal(run('selectedTranscriptSegment()'), null);
});

test('trim inspector submits one atomic edit with original and new clip boundaries', async () => {
  const {run} = app();
  run(`state.project.draft.keep_ranges=[{start:0,end:10}]; state.manualSelection={start:0,end:10};
    renderClipTrim(); elements.clipTrimIn.value='1.200'; elements.clipTrimOut.value='8.500';
    applyManualEdit=async(action,payload)=>{globalThis.trimSubmission={action,...payload};return state.project;};
    state.timeline={selectRange:(start,end)=>{globalThis.trimSelection={start,end};}};
    seekPreview=()=>{};`);
  await run('applySelectedClipTrim({preventDefault(){}})');
  assert.equal(run('trimSubmission.action'), 'trim_clip');
  assert.equal(run('trimSubmission.start'), 0);
  assert.equal(run('trimSubmission.end'), 10);
  assert.equal(run('trimSubmission.new_start'), 1.2);
  assert.equal(run('trimSelection.end'), 8.5);
});

test('keyboard routing accepts only the chosen split binding and does not close Studio on Escape', () => {
  const {run} = app();
  run(`state.studio.open=true;state.keyboardProfile='premiere'; elements.previewA.currentTime=3;
    applyManualEdit=(action,payload)=>{globalThis.keyEdit={action,...payload};};
    state.timeline={cancelGesture:()=>false,clearSelection:()=>{globalThis.cleared=true;}};
    globalThis.keyEvent=(code,ctrl=false)=>({code,key:code,ctrlKey:ctrl,preventDefault(){this.defaultPrevented=true;}});
    handleEditorShortcut(keyEvent('KeyK',true));`);
  assert.equal(run('keyEdit.action'), 'split');
  assert.equal(run('keyEdit.time'), 3);
  run("keyEdit=null; handleEditorShortcut(keyEvent('KeyB',true));");
  assert.equal(run('keyEdit'), null);
  run("handleEditorShortcut(keyEvent('Escape'));");
  assert.equal(run('cleared'), true);
  assert.equal(run('state.studio.open'), true);
});

function mediaShortcutFixture() {
  const h = app();
  h.run(`state.studio.open=true;state.keyboardProfile='cutroom';elements.previewA.currentTime=3;
    state.project.manual={media_clips:[{id:'layer',start:2,end:6}]};
    state.manualSelection={start:0,end:5};
    globalThis.mediaCommands=[];globalThis.baseCommands=[];globalThis.mediaDeselected=false;
    applyManualEdit=(...args)=>baseCommands.push(args);runManualRangeEdit=(...args)=>baseCommands.push(args);
    state.timeline={mediaSelection:'layer',onMediaAction:(action,payload)=>mediaCommands.push({action,...payload}),
      cancelGesture:()=>false,scheduleDraw(){},clearSelection:()=>baseCommands.push('clear')};
    state.mediaStudio={select:id=>{mediaDeselected=id===null;}};
    globalThis.mediaKey=(key,extra={})=>({key,target:elements.timelineCanvas,
      preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;},...extra});`);
  return h;
}

test('captured Delete targets focused added media without touching the stale base selection', () => {
  const { run } = mediaShortcutFixture();
  run(`globalThis.mediaDelete=mediaKey('Delete');handleEditorShortcut(mediaDelete);`);
  assert.equal(run('JSON.stringify(mediaCommands)'), JSON.stringify([{ action:'media_remove', clip_id:'layer' }]));
  assert.equal(run('JSON.stringify(baseCommands)'), '[]');
  assert.equal(run('mediaDelete.defaultPrevented && mediaDelete.stopped'), true);
  assert.equal(run('JSON.stringify(state.manualSelection)'), JSON.stringify({start:0,end:5}));
});

test('focused media split follows the selected keyboard profile and rejects out-of-clip playheads', () => {
  const { run } = mediaShortcutFixture();
  run(`state.keyboardProfile='premiere';handleEditorShortcut(mediaKey('k',{ctrlKey:true}));
    handleEditorShortcut(mediaKey('b',{ctrlKey:true}));
    elements.previewA.currentTime=2.01;handleEditorShortcut(mediaKey('k',{ctrlKey:true}));
    elements.previewA.currentTime=8;handleEditorShortcut(mediaKey('k',{ctrlKey:true}));`);
  assert.equal(run('JSON.stringify(mediaCommands)'), JSON.stringify([{action:'media_split',clip_id:'layer',time:3}]));
  assert.equal(run('JSON.stringify(baseCommands)'), '[]');
});

test('media shortcuts respect busy, repeat and profile guards before canvas fallback', () => {
  const { run } = mediaShortcutFixture();
  run(`handleEditorShortcut(mediaKey('Delete',{repeat:true}));
    state.manualEditBusy=true;handleEditorShortcut(mediaKey('Delete'));handleEditorShortcut(mediaKey('s'));
    state.manualEditBusy=false;state.keyboardProfile='premiere';
    globalThis.unboundMediaDelete=mediaKey('Delete');handleEditorShortcut(unboundMediaDelete);`);
  assert.equal(run('JSON.stringify(mediaCommands)'), '[]');
  assert.equal(run('JSON.stringify(baseCommands)'), '[]');
  assert.equal(run('unboundMediaDelete.defaultPrevented && unboundMediaDelete.stopped'), true);
});

test('Escape clears focused media selection while protected inspector fields retain their keyboard input', () => {
  const { run } = mediaShortcutFixture();
  run(`const field={closest:()=>({})};handleEditorShortcut(mediaKey('Delete',{target:field}));
    handleEditorShortcut(mediaKey('s',{target:field}));
    globalThis.mediaEscape=mediaKey('Escape');handleEditorShortcut(mediaEscape);`);
  assert.equal(run('state.timeline.mediaSelection'), null);
  assert.equal(run('mediaDeselected'), true);
  assert.equal(run('mediaEscape.stopped'), true);
  assert.equal(run('JSON.stringify(mediaCommands)'), '[]');
  assert.equal(run('JSON.stringify(baseCommands)'), '[]');
  assert.equal(run('JSON.stringify(state.manualSelection)'), JSON.stringify({start:0,end:5}));
});

test('keyboard profile controls stay in sync and return focus to the timeline without escaping a dialog', () => {
  const {run, selectors} = app();
  run(`globalThis.savedKeys={};globalThis.focusCount=0;
    globalThis.localStorage={getItem:()=> 'premiere',setItem:(key,value)=>savedKeys[key]=value};
    state.studio.open=true;
    elements.timelineCanvas.focus=()=>focusCount++;
    initializeKeyboardProfile();bindKeyboardControls();`);
  assert.equal(run('elements.keyboardProfile.value'), 'premiere');
  assert.equal(run('elements.keyboardHelpProfile.value'), 'premiere');
  run(`elements.keyboardProfile.value='resolve';elements.keyboardProfile.listeners.change();`);
  assert.equal(run('focusCount'), 1);
  assert.equal(run('elements.keyboardHelpProfile.value'), 'resolve');
  assert.equal(run('savedKeys["cutroom-keyboard-profile"]'), 'resolve');
  selectors.set('dialog[open]', [{}]);
  run(`elements.keyboardHelpProfile.value='protools';elements.keyboardHelpProfile.listeners.change();`);
  assert.equal(run('focusCount'), 1, 'changing the dialog select must keep keyboard access inside the dialog');
  assert.equal(run('elements.keyboardProfile.value'), 'protools');
  run('elements.keyboardDialog.listeners.close();');
  assert.equal(run('focusCount'), 1, 'another dialog may still be open');
  selectors.delete('dialog[open]');
  run('elements.keyboardDialog.listeners.close();');
  assert.equal(run('focusCount'), 2);
  run('state.studio.open=false;elements.keyboardDialog.listeners.close();');
  assert.equal(run('focusCount'), 2);
});

test('help lists each working action once and distinguishes individual adaptations from unassigned actions', () => {
  const {run} = app();
  for (const id of ['cutroom', 'resolve', 'premiere', 'protools', 'finalcut']) {
    run(`selectKeyboardProfile('${id}');`);
    assert.equal(run('(elements.keyboardShortcutList.innerHTML.match(/class="shortcut-row"/g)||[]).length'),
      run(`shortcutRows('${id}').filter(row=>row.bound).length`));
    assert.doesNotMatch(run('elements.keyboardShortcutList.innerHTML'), /<kbd>Toolbar<\/kbd>|<kbd>Not assigned<\/kbd>/);
  }
  run(`selectKeyboardProfile('resolve');`);
  const help = run('elements.keyboardShortcutList.innerHTML');
  assert.match(help, /<kbd>Delete<\/kbd><small class="shortcut-adaptation">/);
  assert.doesNotMatch(help, /<kbd>Shift\+Delete<\/kbd><small class="shortcut-adaptation">/);
  assert.match(help, /Not assigned in this profile/);
  assert.match(run('elements.keyboardLimitations.textContent'), /./);
  run(`selectKeyboardProfile('unknown');`);
  assert.equal(run('state.keyboardProfile'), 'cutroom');
});

test('native snapping keys reach the timeline once, and busy editing prevents changes', () => {
  const {run} = app();
  run(`state.studio.open=true;globalThis.snapChanges=[];
    state.timeline={snapping:false,setSnapping(value){this.snapping=value;snapChanges.push(value);}};
    globalThis.snapKey=key=>({key,preventDefault(){this.defaultPrevented=true;}});`);
  for (const [profile, key] of [['cutroom','n'], ['resolve','n'], ['premiere','s'], ['finalcut','n']]) {
    run(`state.keyboardProfile='${profile}';handleEditorShortcut(snapKey('${key}'));`);
  }
  assert.equal(run('JSON.stringify(snapChanges)'), '[true,false,true,false]');
  run(`state.keyboardProfile='protools';handleEditorShortcut(snapKey('n'));
    state.keyboardProfile='premiere';handleEditorShortcut({...snapKey('s'),repeat:true});
    state.manualEditBusy=true;handleEditorShortcut(snapKey('s'));`);
  assert.equal(run('snapChanges.length'), 4);
});

test('Premiere Extract uses the active edit scope and never removes footage without a range', () => {
  const {run} = app();
  run(`state.studio.open=true;state.keyboardProfile='premiere';
    state.project.editor_sequence={version:1,tracks:{A:[{id:'a',start:0,end:10,source_start:0}]}};
    globalThis.extractEdits=[];
    targetEditableClips=()=>[{start:0,end:10}];editorDuration=()=>10;previewTimelineTime=()=>3;
    applyManualEdit=(action,detail)=>extractEdits.push({action,...detail});
    globalThis.extract=()=>handleEditorShortcut({key:"'",preventDefault(){}});
    activeEditTarget=()=> 'edit';state.manualSelection=null;extract();
    state.manualSelection={start:2,end:4};extract();
    activeEditTarget=()=> 'A';extract();`);
  assert.equal(run('JSON.stringify(extractEdits)'), JSON.stringify([
    {action:'sequence_ripple_delete',start:2,end:4},
    {action:'track_remove_range',start:2,end:4,slot:'A'},
  ]));
});

test('Shift+R opens original footage without requiring an unrelated edited-timeline selection', () => {
  const {run} = app();
  run(`state.studio.open=true;state.keyboardProfile='cutroom';state.manualSelection=null;
    state.project.editor_sequence={version:1};globalThis.reviewCount=0;
    previewTimelineTime=()=>3;targetEditableClips=()=>[];
    openSourceReview=()=>reviewCount++;
    handleEditorShortcut({key:'R',shiftKey:true,preventDefault(){}});`);
  assert.equal(run('reviewCount'), 1);
  run(`state.manualEditBusy=true;handleEditorShortcut({key:'R',shiftKey:true,preventDefault(){}});`);
  assert.equal(run('reviewCount'), 1);
});

function transportFixture() {
  const fixture = app();
  fixture.run(`state.studio.open=true; state.preview.mode='edit';
    state.manualSelection={start:1,end:3}; globalThis.transports=0;
    togglePreview=()=>transports++;`);
  const target = {closest(selector) {
    const clauses=selector.split(',');
    if (clauses.includes('button')) return this;
    if (clauses.includes('.studio-timeline-dock')) return {};
    return null;
  }};
  const fire = (type, other = {}) => {
    const event = {key:' ',code:'Space',target,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;},...other};
    fixture.context.transportEvent=event;
    fixture.run(`${type === 'keyup' ? 'handleEditorShortcutKeyUp' : 'handleEditorShortcut'}(transportEvent);`);
    return event;
  };
  return {...fixture,target,fire};
}

test('Space press/hold/release on a focused tool button toggles only playback once', () => {
  const {run,fire} = transportFixture();
  const down = fire('keydown');
  assert.equal(down.defaultPrevented, true);
  assert.equal(down.stopped, true);
  assert.equal(run('transports'), 1);
  assert.equal(fire('keydown',{repeat:true}).defaultPrevented, true);
  assert.equal(fire('keydown',{repeat:true}).defaultPrevented, true);
  assert.equal(run('transports'), 1);
  const up = fire('keyup');
  assert.equal(up.defaultPrevented, true, 'native keyup must not click a tool, clear a range or toggle Snap');
  assert.equal(up.stopped, true);
  assert.equal(run('state.preview.spaceHeld'), false);
  assert.equal(run('state.preview.mode'), 'edit');
  assert.equal(run('JSON.stringify(state.manualSelection)'), '{"start":1,"end":3}');
  fire('keydown'); fire('keyup');
  assert.equal(run('transports'), 2);
});

test('busy editor Space is consumed without activating a toolbar button or starting playback', () => {
  const {run,fire} = transportFixture();
  run('state.manualEditBusy=true;');
  assert.equal(fire('keydown').defaultPrevented, true);
  assert.equal(fire('keyup').defaultPrevented, true);
  assert.equal(run('transports'), 0);
});

test('Space keyup protection is scoped to its accepted press and never traps input or dialog Space', () => {
  const {run,fire,selectors} = transportFixture();
  const field = {closest:selector=>selector.split(',').includes('input') ? {} : null};
  assert.equal(fire('keyup').defaultPrevented, undefined, 'a keyup without an accepted press is native');
  assert.equal(fire('keydown',{target:field}).defaultPrevented, undefined);
  assert.equal(fire('keyup',{target:field}).defaultPrevented, undefined);
  fire('keydown');
  assert.equal(fire('keyup',{target:field}).defaultPrevented, undefined, 'focus moved to a field');
  assert.equal(run('state.preview.spaceHeld'), false);
  fire('keydown'); run('resetEditorTransportKey();');
  assert.equal(fire('keyup').defaultPrevented, undefined, 'blur released the editor key');
  selectors.set('dialog[open]',[{}]);
  assert.equal(fire('keydown').defaultPrevented, undefined);
  assert.equal(fire('keyup').defaultPrevented, undefined);
});

test('two-click timeline callback preserves both boundaries for one backend operation', () => {
  const {run} = app();
  run(`globalThis.edits=[]; applyManualEdit=(action,detail)=>edits.push({action,...detail});
    handleTimelineEdit({action:'delete_range',start:1.97,end:8});
    handleTimelineEdit({action:'split',time:3});
    handleTimelineEdit({action:'unknown',start:0,end:100});`);
  assert.equal(run('JSON.stringify(edits)'), JSON.stringify([{action:'delete_range',start:1.97,end:8},{action:'split',time:3}]));
});

test('range actions distinguish kept, omitted and mixed footage and skip no-op saves', () => {
  const {run} = app();
  run(`state.project.sources.A.duration=12;state.project.draft.keep_ranges=[{start:0,end:4},{start:6,end:12}];
    globalThis.edits=[];applyManualEdit=(action,detail)=>edits.push({action,...detail});`);
  for (const [range, canRemove, canRestore] of [
    [{start:1,end:3},true,false], [{start:4,end:6},false,true], [{start:3,end:7},true,true], [{start:1,end:1.03},false,false],
  ]) {
    run(`state.manualSelection=${JSON.stringify(range)};renderManualControls();`);
    assert.equal(run('elements.manualDelete.disabled'), !canRemove);
    assert.equal(run('elements.manualRestore.disabled'), !canRestore);
    run("edits=[];runManualRangeEdit('delete_range');runManualRangeEdit('restore_range');");
    assert.equal(run('edits.length'), Number(canRemove)+Number(canRestore));
  }
  assert.equal(run('elements.manualRestore.textContent'), 'Add to edit');
});

test('imported trim, tool and navigation bindings reach their real handlers without NLE leakage', () => {
  const {run} = app();
  run(`state.studio.open=true;state.keyboardProfile='protools';elements.previewA.currentTime=3;
    globalThis.edits=[]; globalThis.seeks=[];
    applyManualEdit=(action,detail)=>edits.push({action,...detail});
    pauseAllMedia=()=>{};seekSourcePreview=(time)=>seeks.push(time);
    globalThis.keyEvent=(key)=>({key,preventDefault(){this.defaultPrevented=true;}});
    handleEditorShortcut(keyEvent('a'));handleEditorShortcut(keyEvent('s'));
    handleEditorShortcut(keyEvent('l'));handleEditorShortcut(keyEvent('Enter'));
    for(const key of ['i','o','j','k','x','ArrowRight']) handleEditorShortcut(keyEvent(key));`);
  assert.equal(run('JSON.stringify(edits)'), JSON.stringify([
    {action:'trim_clip',start:0,end:10,new_start:3,new_end:10},
    {action:'trim_clip',start:0,end:10,new_start:0,new_end:3},
  ]));
  assert.equal(run('JSON.stringify(seeks)'), '[0,0]');
  run(`setTimelineTool=(tool)=>{globalThis.selectedTool=tool;};
    state.keyboardProfile='resolve';handleEditorShortcut(keyEvent('b'));`);
  assert.equal(run('selectedTool'), 'blade');
  run(`state.keyboardProfile='premiere';handleEditorShortcut(keyEvent('v'));`);
  assert.equal(run('selectedTool'), 'select');
});

test('Cut out Enter overrides Pro Tools only in the focused tool canvas; Escape cancels its marker', () => {
  const {run} = app();
  run(`state.studio.open=true;state.keyboardProfile='protools';elements.previewA.currentTime=3;
    globalThis.localMarks=0;globalThis.seeks=[];
    pauseAllMedia=()=>{};seekSourcePreview=(time)=>seeks.push(time);
    state.timeline={tool:'remove_between',keyDown:()=>localMarks++,cancelGesture:()=>false,cancelPendingCut:()=>{globalThis.cutCancelled=true;return true;},clearSelection:()=>{throw Error('selection should be preserved');}};
    globalThis.enter=(target)=>({key:'Enter',target,preventDefault(){}});
    handleEditorShortcut(enter(elements.timelineCanvas));
    handleEditorShortcut(enter(null));
    handleEditorShortcut({key:'Escape',preventDefault(){}});`);
  assert.equal(run('localMarks'), 1);
  assert.equal(run('JSON.stringify(seeks)'), '[0]');
  assert.equal(run('cutCancelled'), true);
  run(`state.manualEditBusy=true;handleEditorShortcut(enter(elements.timelineCanvas));`);
  assert.equal(run('localMarks'), 1);
});

test('disabled AI does not suggest downloading even when a shared Ollama is available', () => {
  const {run} = app();
  run(`state.system={runtime:{state:'disabled',available:false,can_retry:false,message:'AI is disabled in settings.'},models:{ollama:{available:true},story_ai_ready:false}};renderModelStatus();`);
  assert.equal(run('elements.modelButton.hidden'), true);
  assert.equal(run("$('small',elements.modelStatus).textContent"), 'AI is disabled in settings.');
});

for (const action of ["generateDraft()", 'refineDraft("new_variation")', "startExport()"])
  test(`cancel during pending saves does not start ${action}`, async () => {
    const { context, run } = app();
    run(`
      renderReadiness = renderReelCandidates = pauseAllMedia = showAnalysis = showResult = () => {};
      currentSettings = () => ({});
      reconcileDirectorOutcome = async () => {};
      globalThis.calls = [];
      api = async (url) => { calls.push(url); return { job: { id: "new" } }; };
      ensureStoryAIReady = async () => calls.push("prepare AI");
      flushProjectSaves = () => new Promise((resolve) => { globalThis.finishSave = resolve; });
      globalThis.operation = ${action};
      state.cancelBeforeStart = true;
      finishSave();
    `);
    await context.operation;
    assert.deepEqual(Array.from(context.calls), []);
    assert.equal(run("state.jobStartLocks.size"), 0);
    assert.equal(run("state.cancelBeforeStart"), false);
  });

test("cancellation during AI readiness prevents a Director request", async () => {
  const { context, run } = app();
  run(`
    renderReadiness = renderReelCandidates = pauseAllMedia = showAnalysis = () => {};
    currentSettings = () => ({});
    reconcileDirectorOutcome = async () => {};
    flushProjectSaves = async () => {};
    globalThis.calls = [];
    api = async (url) => calls.push(url);
    ensureStoryAIReady = async () => { state.cancelBeforeStart = true; };
    globalThis.operation = generateDraft();
  `);
  await context.operation;
  assert.deepEqual(Array.from(context.calls), []);
});

test("a duplicate start cannot clear a pending cancellation", async () => {
  const { run } = app();
  run('state.jobStartLocks.add("director:p"); state.cancelBeforeStart = true;');
  await run("generateDraft()");
  await run('refineDraft("shorter")');
  run("pauseAllMedia = () => {};");
  await run("startExport()");
  assert.equal(run("state.cancelBeforeStart"), true);
});

test("model download cannot start after Stop while local AI is preparing", async () => {
  const { run } = app();
  run(`
    api = async (url) => {
      if (url !== "/api/runtime/prepare") throw new Error("model install must not start");
      state.cancelBeforeStart = true;
      return { runtime: {state: "ready", available: true}, story_ai: {ready: false, recommended_model: "test-model"} };
    };
  `);
  await assert.rejects(run('ensureStoryAIReady("short")'), /Cancelled/);
});

test("Director readiness starts the local engine and reuses the installed fallback", async () => {
  const { run } = app();
  run(`
    elements.performanceModeSelect.value = "quality";
    globalThis.calls = [];
    api = async (url, options) => {
      calls.push({url, body: JSON.parse(options.body)});
      return { runtime: {state: "ready", available: true}, story_ai: {ready: true, ollama_available: true, selected_model: "installed-fallback", recommended_model: "larger-model", installed_models: ["installed-fallback"]} };
    };
  `);
  assert.equal(await run('ensureStoryAIReady("short")'), true);
  assert.equal(run("calls.length"), 1);
  assert.equal(run("calls[0].url"), "/api/runtime/prepare");
  assert.equal(run("calls[0].body.performance_mode"), "quality");
  assert.equal(run("elements.jobMessage.textContent"), "Preparing local AI…");
  assert.equal(run("elements.modelStatus.dataset.state"), "ready");
  assert.match(run('$("small", elements.modelStatus).textContent'), /installed-fallback/);
});

test("unavailable engine surfaces actionable recovery without attempting model download", async () => {
  const { run } = app();
  run(`
    globalThis.calls = [];
    api = async (url) => {
      calls.push(url);
      return {runtime: {state: "error", available: false, message: "Install the local AI engine using CUTROOM setup, then use Retry AI."}, story_ai: {ready: false}};
    };
  `);
  await assert.rejects(run('ensureStoryAIReady("podcast")'), /CUTROOM setup/);
  assert.equal(run("calls.length"), 1);
  assert.equal(run("elements.modelStatus.dataset.state"), "missing-engine");
  assert.equal(run("elements.retryAIButton.hidden"), false);
  assert.equal(run("elements.modelButton.hidden"), true);
});

test("Retry AI shares preparation and never blindly downloads a missing model", async () => {
  const { context, run } = app();
  run(`
    globalThis.calls = [];
    api = (url) => { calls.push(url); return new Promise((resolve) => { globalThis.finishPrepare = resolve; }); };
    globalThis.first = retryLocalAI();
    globalThis.second = retryLocalAI();
  `);
  await Promise.resolve();
  assert.equal(run("elements.retryAIButton.disabled"), true);
  assert.equal(run("elements.modelStatus.dataset.state"), "starting");
  run('finishPrepare({runtime: {state:"ready",available:true}, story_ai:{ready:false,recommended_model:"story-local"}});');
  await Promise.all([context.first, context.second]);
  assert.deepEqual(Array.from(run("calls")), ["/api/runtime/prepare"]);
  assert.equal(run("elements.modelStatus.dataset.state"), "missing-model");
  assert.equal(run("elements.modelButton.hidden"), false);
});

test("a stale ready runtime never hides that the engine stopped responding", () => {
  const { run } = app();
  run('state.system = {runtime:{state:"ready",available:true,message:"Ready"},models:{ollama:{available:false},story_ai_ready:false}}; renderModelStatus();');
  assert.equal(run("elements.modelStatus.dataset.state"), "missing-engine");
  assert.equal(run("elements.retryAIButton.hidden"), false);
  assert.equal(run("elements.modelButton.hidden"), true);
  assert.match(run('$("small", elements.modelStatus).textContent'), /no longer responding/);
});

test("disabled AI explains configuration recovery without an ineffective Retry button", () => {
  const { run } = app();
  run('state.system = {runtime:{state:"disabled",available:false,can_retry:false,message:"Enable local AI in config.json and restart CUTROOM."},models:{ollama:{available:false}}}; renderModelStatus();');
  assert.equal(run('$("b", elements.modelStatus).textContent'), "Local AI is disabled");
  assert.match(run('$("small", elements.modelStatus).textContent'), /config.json/);
  assert.equal(run("elements.retryAIButton.hidden"), true);
  assert.equal(run("elements.modelButton.hidden"), true);
});

test("missing model download requires a named one-time size disclosure and explicit confirmation", async () => {
  const { run } = app();
  run(`
    globalThis.calls = []; globalThis.downloaded = false;
    globalThis.window = {confirm: (message) => { globalThis.confirmation = message; return true; }};
    api = async (url, options) => {
      calls.push({url, body: JSON.parse(options.body)});
      if (url === "/api/models/install") { downloaded = true; return {job:{id:"model-job"}}; }
      return {runtime: {state:"ready",available:true}, story_ai:{ready:downloaded,ollama_available:true,recommended_model:"story-local",selected_model:downloaded ? "story-local" : null}};
    };
    pollJob = async (id, options) => { globalThis.polled = {id, options}; return {status:"completed"}; };
  `);
  await run('ensureStoryAIReady("short")');
  assert.match(run("confirmation"), /story-local/);
  assert.match(run("confirmation"), /one-time.*several GB/);
  assert.equal(run("calls[1].body.model"), "story-local");
  assert.equal(run("polled.options.modelInstall"), true);
  assert.equal(run("calls.length"), 3);
  assert.equal(run("state.modelInstallJob"), null);
});

test("duplicate install clicks cannot create a second download or confirmation", async () => {
  const { context, run } = app();
  run(`
    globalThis.installs = 0; globalThis.confirmations = 0;
    globalThis.window = {confirm: () => { confirmations++; return true; }};
    api = async (url) => {
      if (url === "/api/models/install") { installs++; return {job:{id:"model-job"}}; }
      return {runtime:{state:"ready",available:true},story_ai:{ready:false,recommended_model:"story-local"}};
    };
    renderReadiness = renderReelCandidates = () => {};
    pollJob = () => new Promise((resolve) => { globalThis.finishDownload = resolve; });
    globalThis.first = installModel();
    globalThis.second = installModel();
  `);
  for (let index = 0; index < 8; index++) await Promise.resolve();
  assert.equal(run("installs"), 1);
  assert.equal(run("confirmations"), 1);
  await run("installModel()");
  assert.equal(run("installs"), 1);
  run('state.cancelBeforeStart = true; finishDownload({status:"cancelled"});');
  await Promise.all([context.first, context.second]);
  assert.equal(run("state.jobStartLocks.size"), 0);
  assert.equal(run("messages.length"), 0);
});

test("Stop racing with model completion still cancels the pending edit", async () => {
  const { run } = app();
  run(`
    setActiveJob = (id) => { state.activeJob = id; state.cancelRequestedJobs.add(id); };
    renderReadiness = () => {};
    api = async () => ({job:{id:"model-job",status:"completed",kind:"model_install"}});
  `);
  await assert.rejects(run('pollJob("model-job", {modelInstall:true, silent:true})'), /Cancelled/);
  assert.equal(run("state.activeJob"), null);
});

test("a slow system snapshot cannot overwrite a completed AI preparation", async () => {
  const { context, run } = app();
  run(`
    renderUploadLimits = renderEditStyleChoices = () => {};
    api = async (url) => {
      if (url === "/api/system") return new Promise((resolve) => { globalThis.finishSnapshot = resolve; });
      return {runtime:{state:"ready",available:true},story_ai:{ready:true,ollama_available:true,selected_model:"already-installed"}};
    };
    globalThis.loading = loadSystem();
    globalThis.preparing = prepareLocalAI();
  `);
  await context.preparing;
  run('finishSnapshot({instance_id:"local-id",runtime:{state:"starting",available:false},models:{ollama:{available:false},story_ai_ready:false}});');
  await context.loading;
  assert.equal(run("state.system.runtime.state"), "ready");
  assert.equal(run("state.system.models.selected_story_model"), "already-installed");
  assert.equal(run("state.system.instance_id"), "local-id");
  assert.equal(run("state.runtimeRefreshTimer"), null);
});

test("declining a model download cancels preparation without a failure or a download", async () => {
  const { run } = app();
  run(`
    globalThis.calls = [];
    globalThis.window = {confirm: () => false};
    api = async (url) => { calls.push(url); return {runtime:{state:"ready",available:true},story_ai:{ready:false,recommended_model:"story-local"}}; };
  `);
  await assert.rejects(run('ensureStoryAIReady("short")'), /^Error: Cancelled$/);
  assert.deepEqual(Array.from(run("calls")), ["/api/runtime/prepare"]);
  assert.equal(run("messages.length"), 0);
  assert.equal(run("state.modelInstallPending"), false);
});

test("navigation during preparation cancels the original edit before any download", async () => {
  const { run } = app();
  run(`
    api = async () => {
      state.projectViewToken += 1;
      return {runtime:{state:"ready",available:true},story_ai:{ready:false,recommended_model:"story-local"}};
    };
    globalThis.window = {confirm: () => { throw new Error("confirmation belongs to an old project"); }};
  `);
  await assert.rejects(run('ensureStoryAIReady("short")'), /Cancelled/);
});

test("starting status refresh is bounded and never downloads", async () => {
  const { run } = app();
  run(`
    globalThis.scheduled = [];
    setTimeout = (callback) => { scheduled.push(callback); return scheduled.length; };
    clearTimeout = () => {};
    globalThis.checks = 0;
    state.system = {runtime:{state:"starting",available:false}};
    loadSystem = async () => { checks++; scheduleRuntimeRefresh(); };
    scheduleRuntimeRefresh();
  `);
  for (let index = 0; index < 20; index++) await run(`scheduled[${index}]()`);
  assert.equal(run("checks"), 20);
  assert.equal(run("scheduled.length"), 20);
  assert.equal(run("state.runtimeRefreshTimer"), null);
  run("renderModelStatus();");
  assert.equal(run("elements.retryAIButton.disabled"), false);
  assert.match(run('$("small", elements.modelStatus).textContent'), /taking longer/);
});

test("the same AI status card docks in setup and the editor without duplicated controls", () => {
  const { run } = app();
  run("dockRuntimeStatus();");
  assert.equal(run("elements.modelStatus.parentElement.id"), "setupRuntimeDock");
  run("state.studio.open = true; dockRuntimeStatus();");
  assert.equal(run("elements.modelStatus.parentElement.id"), "studioRuntimeDock");
  assert.equal(run("elements.setupRuntimeDock.children.length"), 0);
  run("state.studio.open = false; dockRuntimeStatus();");
  assert.equal(run("elements.modelStatus.parentElement.id"), "setupRuntimeDock");
  assert.equal(run("elements.studioRuntimeDock.children.length"), 0);
});

test("dirty settings disable candidate/variation controls and reject direct actions", async () => {
  const { run, selectors } = app();
  const variation = node(); variation.dataset.command = "new_variation";
  const candidate = node(); candidate.dataset.candidateId = "alternate";
  selectors.set(".refine-grid button", [variation]);
  run("elements.reelCandidateList.querySelectorAll = () => globalThis.candidates;");
  run("globalThis.candidates = [];");
  // The actual event and programmatic paths share the same dirty-state guard.
  const contextCandidates = run("candidates"); contextCandidates.push(candidate);
  run('state.draftDirtyReasons.add("language"); renderDraftActions();');
  assert.equal(variation.disabled, true);
  assert.equal(candidate.disabled, true);
  run('api = async () => { throw new Error("must not submit a stale edit"); };');
  await run('refineDraft("new_variation")');
  assert.equal(await run('applyManualEdit("apply_reel_candidate", { candidate_id: "alternate" })'), null);
  await run("startExport()");
  assert.equal(run("state.jobStartLocks.size"), 0);
  run("state.draftDirtyReasons.clear(); renderDraftActions();");
  assert.equal(variation.disabled, false);
  assert.equal(candidate.disabled, false);
});

test("variation is unavailable for a non-short draft or a changed target", async () => {
  const { run, selectors } = app();
  const button = node(); button.dataset.command = "new_variation";
  selectors.set(".refine-grid button", [button]);
  for (const [draftGoal, settingGoal] of [["youtube", "youtube"], ["short", "clean"]]) {
    run(`state.project.draft.goal = "${draftGoal}"; state.project.settings.goal = "${settingGoal}"; renderDraftActions();`);
    assert.equal(button.hidden, true);
    await run('refineDraft("new_variation")');
    assert.equal(run("state.jobStartLocks.size"), 0);
  }
});

test("reselecting an active edit style preserves tuned settings", () => {
  const { run } = app();
  run(`
    bindEvents();
    state.selectedEditStyle = "gaming";
    globalThis.applied = 0; globalThis.saved = 0;
    applyEditStyle = () => { applied += 1; };
    scheduleSettingsPatch = () => { saved += 1; };
    elements.editStyleChoices.listeners.click({ target: { closest: () => ({ dataset: { value: "gaming" } }) } });
  `);
  assert.equal(run("applied"), 0);
  assert.equal(run("saved"), 0);
  run('elements.editStyleChoices.listeners.click({ target: { closest: () => ({ dataset: { value: "podcast" } }) } });');
  assert.equal(run("applied"), 1);
  assert.equal(run("saved"), 1);
});

for (const changed of [false, true])
  test(`variation completion reports actual changed=${changed}`, async () => {
    const { context, run } = app();
    run(`
      renderReadiness = renderReelCandidates = pauseAllMedia = showAnalysis = showResult = () => {};
      flushProjectSaves = async () => {};
      ensureStoryAIReady = async () => true;
      api = async () => ({ job: { id: "job" } });
      pollJob = async (_id, options) => {
        if (options.announceReady !== false) throw new Error("A variation must not announce success before checking whether its cut changed");
        ${changed ? 'state.project.draft.keep_ranges = [{ start: 20, end: 30 }];' : ""}
        return { result: { variation_changed: ${changed} } };
      };
      globalThis.operation = refineDraft("new_variation");
    `);
    await context.operation;
    assert.equal(context.messages.at(-1).message, changed ? "anotherCutReady" : "anotherCutUnchanged");
    assert.equal(context.messages.at(-1).type, changed ? "success" : "info");
  });

test("hidden or busy previews cannot restart with Space", async () => {
  const { run } = app();
  run('elements.previewA.play = () => { throw new Error("hidden playback started"); }; elements.resultPanel.hidden = true;');
  await run("playPreview()");
  run('elements.resultPanel.hidden = false; state.jobStartLocks.add("director:p"); togglePreview();');
  await run("playPreview()");
});

test("Pause during asynchronous A.play never starts source B", async () => {
  const { context, run } = app();
  run(`
    globalThis.syncCalls = 0;
    elements.previewA.currentTime = 5;
    elements.previewA.play = () => new Promise((resolve) => { globalThis.finishPlay = resolve; });
    elements.previewB.pause = () => {};
    inCut = () => false; setPreviewPlaying = () => {};
    syncSecondaryPreview = () => { syncCalls += 1; };
    globalThis.operation = playPreview();
    stopPreviewPlayback(); finishPlay();
  `);
  await context.operation;
  assert.equal(context.syncCalls, 0);
});

test("source B playback follows visibility, offset and primary pause state", () => {
  const { run } = app();
  run(`
    state.project.sources.B = { duration: 20, has_audio: true };
    globalThis.starts = 0; globalThis.pauses = 0;
    elements.previewA.paused = false;
    Object.assign(elements.previewB, { src: "b.mp4", currentTime: 0, paused: true,
      play() { starts++; this.paused = false; return Promise.resolve(); }, pause() { pauses++; this.paused = true; } });
    state.preview.playing = true;
    cameraAt = () => "stacked";
    sourceMixerSettings = () => ({ syncOffset: 10, screenSlot: "A", cameraSlot: "B", primaryRole: "screen", firstSlot: "A", audioSlot: "A" });
    syncSecondaryPreview(5);
  `);
  assert.equal(run("starts"), 0);
  assert.equal(run("elements.previewB.hidden"), true);
  assert.equal(run("elements.previewA.hidden"), false);
  run("syncSecondaryPreview(15);");
  assert.equal(run("starts"), 1);
  assert.equal(run("elements.previewB.hidden"), false);
  assert.equal(run("elements.previewB.currentTime"), 5);
  run("elements.previewA.paused = true; syncSecondaryPreview(16);");
  assert.equal(run("elements.previewB.paused"), true);
  run('elements.previewA.paused = false; cameraAt = () => "A"; syncSecondaryPreview(17);');
  assert.equal(run("starts"), 1);
  run('cameraAt = () => "B"; syncSecondaryPreview(30);');
  assert.equal(run("elements.previewB.hidden"), true);
  assert.equal(run("elements.previewA.hidden"), false);
  // A source can have a longer audio stream than video. Stop displaying B at
  // the actual video end instead of leaving a frozen last frame on screen.
  run('state.project.sources.B.video_duration = 5; syncSecondaryPreview(14);');
  assert.equal(run("elements.previewB.hidden"), false);
  assert.equal(run("elements.previewB.paused"), false);
  run("syncSecondaryPreview(15);");
  assert.equal(run("elements.previewB.hidden"), true);
  assert.equal(run("elements.previewB.paused"), true);
  assert.equal(run("elements.previewA.hidden"), false);
  run('state.project.sources.B.video_duration = 0; syncSecondaryPreview(15);');
  assert.equal(run("elements.previewB.hidden"), false);
});

test("progress explains the actual stage and cancellation takes precedence", () => {
  const { run } = app();
  run('renderActiveJobBar = () => {}; updateJobUI({ progress: .68, message: "Summarizing chapter 4 of 12" });');
  assert.equal(run("elements.jobMessage.textContent"), "Summarizing chapter 4 of 12");
  run('state.cancelBeforeStart = true; updateJobUI({ progress: .68, message: "Summarizing chapter 4 of 12" });');
  assert.equal(run("elements.jobMessage.textContent"), "cancelling");
});

test("audio-only and short-evidence drafts disclose their limitations", () => {
  const { run } = app();
  run('state.project.draft.engine = "audio_visual_highlights"; state.project.analysis = { warnings: [{ type: "limited_highlight_evidence" }] }; renderDraftWarning();');
  assert.equal(run("elements.draftWarning.hidden"), false);
  assert.equal(run("elements.draftWarningText.textContent"), "audioHighlightWarning limitedHighlightWarning");
  run('state.project.draft.engine = "ollama_hierarchical_story"; state.project.analysis.warnings = []; renderDraftWarning();');
  assert.equal(run("elements.draftWarning.hidden"), true);
});

test("rejected speech shows the original language estimate, not its empty placeholder", () => {
  const { run } = app();
  run(`
    elements.spokenLanguageSelect.value = "auto";
    state.project.analysis = { transcript: {
      language: "en", language_probability: 0, detected_language: "en", detected_language_probability: .5811,
      language_detection: { ambiguous: true, source: "whisper" },
      discarded_quality: { language: "en", language_probability: .5811 }
    } };
    renderLanguageDetectionStatus();
  `);
  assert.match(run("elements.captionLanguageStatus.textContent"), /Speech could not be transcribed reliably/);
  assert.match(run("elements.captionLanguageStatus.textContent"), /English · 58%/);
});

test("missing language probability is not reported as a measured zero", () => {
  const { run } = app();
  run(`
    elements.spokenLanguageSelect.value = "auto";
    state.project.analysis = { transcript: { language: "en", language_probability: null } };
    renderLanguageDetectionStatus();
  `);
  assert.equal(run("elements.captionLanguageStatus.textContent"), "Detected: English");
});

test("Draft quick-edit buttons pause playback and open the requested Studio tab", () => {
  const { run, selectors } = app();
  const buttons = ["timeline", "framing", "transcript", "settings"].map((tab) => {
    const button = node(); button.dataset.openStudioTab = tab;
    return button;
  });
  selectors.set("[data-open-studio-tab]", buttons);
  run(`
    globalThis.navigation = [];
    pauseAllMedia = () => navigation.push("pause");
    setAdvanced = (open) => navigation.push(open ? "open" : "close");
    selectAdvancedTab = (tab) => navigation.push(tab);
    bindEvents();
  `);
  for (const button of buttons) {
    run("navigation.length = 0;");
    button.listeners.click();
    assert.deepEqual(Array.from(run("navigation")), ["pause", "open", button.dataset.openStudioTab]);
  }
});

test("quick-edit navigation stays available for dirty drafts but blocks running work", () => {
  const { run, selectors } = app();
  const button = node(); button.dataset.openStudioTab = "framing";
  selectors.set("[data-open-studio-tab]", [button]);
  run('state.draftDirtyReasons.add("pace"); renderDraftActions();');
  assert.equal(button.disabled, false);
  run('state.activeJob = "job"; renderDraftActions(); pauseAllMedia = () => { throw new Error("busy navigation must not run"); };');
  assert.equal(button.disabled, true);
  assert.equal(run('openStudioTab("framing")'), false);
  run('state.activeJob = null; state.project.draft = null;');
  assert.equal(run('openStudioTab("timeline")'), false);
  assert.equal(run('openStudioTab("unknown")'), false);
});

test("a ready draft opens Studio by default and closing restores both overview docks", () => {
  const { context, run } = app();
  run(`
    document.body = { classList: { add() {}, remove() {} } };
    globalThis.scrolls = [];
    globalThis.window = { scrollY: 42, scrollTo: (position) => scrolls.push(position) };
    globalThis.requestAnimationFrame = (callback) => callback();
    globalThis.events = [];
    pauseAllMedia = () => events.push("pause");
    setStep = () => {};
    renderDraft = () => events.push("render");
    applyFramingPreview = updateStudioStatus = syncSecondaryPreview = () => {};
    state.timeline = { setProject() {}, draw() {} };
    elements.resultGrid.appendChild(elements.previewColumn);
    elements.resultGrid.appendChild(elements.verdictColumn);
    showResult();
  `);
  assert.equal(run("state.studio.open"), true);
  assert.equal(run("elements.previewColumn.parentElement === elements.studioPreviewDock"), true);
  assert.equal(run("state.preview.mode"), 'edit', 'opening Studio must not rewrite the playback choice');
  assert.equal(run("elements.verdictColumn.parentElement === elements.studioDirectorDock"), true);
  assert.equal(run("elements.resultPanel.inert"), true);
  assert.equal(context.scrolls.length, 0);
  assert.ok(context.events.indexOf("render") < context.events.lastIndexOf("pause"));

  run("setAdvanced(false);");
  assert.equal(run("state.studio.open"), false);
  assert.equal(run("elements.resultPanel.inert"), false);
  assert.deepEqual(Array.from(run("elements.resultGrid.children.map((child) => child.id)")), ["previewColumn", "verdictColumn"]);
  assert.equal(context.scrolls.at(-1).top, 42);
  run("renderDraft();");
  assert.equal(run("state.studio.open"), false);
  run("showResult();");
  assert.equal(run("state.studio.open"), true);
  run("setPreviewMode('source'); setAdvanced(false); setAdvanced(true);");
  assert.equal(run('state.preview.mode'), 'source', 'reopening Studio also preserves Full source');
});

test("vertical tool-rail navigation leaves the persistent timeline and selection intact", () => {
  const { run, selectors } = app();
  const tabs = ["timeline", "framing", "transcript", "settings"].map((tab) => {
    const button = node(); button.dataset.tab = tab; button.focus = () => {};
    return button;
  });
  const panels = tabs.map((tab) => {
    const panel = node(); panel.dataset.panel = tab.dataset.tab; return panel;
  });
  selectors.set(".advanced-tabs [role='tab']", tabs);
  selectors.set(".advanced-tabs button", tabs);
  selectors.set(".tab-panel", panels);
  run(`
    document.documentElement = { dir: "ltr" };
    globalThis.window = { setTimeout: (callback) => callback() };
    globalThis.resetCount = 0;
    state.timeline = { selection: { start: 12, end: 18 }, draw() {}, setProject() { resetCount++; } };
    document.getElementById("studioTimelineDock").hidden = false;
    globalThis.keyEvent = { key: "ArrowDown", currentTarget: document.querySelectorAll(".advanced-tabs button")[0], preventDefault() {} };
    handleStudioTabKeydown(keyEvent);
  `);
  assert.equal(panels[0].hidden, true);
  assert.equal(panels[1].hidden, false);
  assert.equal(run('document.getElementById("studioTimelineDock").hidden'), false);
  assert.equal(run("state.timeline.selection.start"), 12);
  assert.equal(run("resetCount"), 0);
  run('keyEvent.key = "ArrowUp"; keyEvent.currentTarget = document.querySelectorAll(".advanced-tabs button")[1]; handleStudioTabKeydown(keyEvent);');
  assert.equal(panels[0].hidden, false);
  assert.equal(run("resetCount"), 0);
  panels[1].parentElement = { scrollTop: 240 };
  panels[1].scrollIntoView = (options) => { panels[1].scrollOptions = options; };
  run('window.matchMedia = () => ({ matches: true }); selectAdvancedTab("framing");');
  assert.equal(panels[1].scrollOptions.block, "start");
  assert.equal(panels[1].parentElement.scrollTop, 240);
  run('window.matchMedia = () => ({ matches: false }); selectAdvancedTab("framing");');
  assert.equal(panels[1].parentElement.scrollTop, 0);
  assert.equal(run("state.timeline.selection.start"), 12);
  const timelineDock = run('document.getElementById("studioTimelineDock")');
  timelineDock.scrollIntoView = (options) => { timelineDock.scrollOptions = options; };
  run('window.matchMedia = () => ({ matches: true }); selectAdvancedTab("timeline");');
  assert.equal(timelineDock.scrollOptions.block, 'start');
  assert.equal(run("state.timeline.selection.start"), 12);
});
