const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const app = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../web/index.html"), "utf8");
const start = app.indexOf("function manualTranscriptionView(");
const end = app.indexOf("\nfunction renderTranscript()", start);
const implementation = app.slice(start, end);

function setup() {
  const nodes = new Map();
  const make = (name, extra = {}) => {
    const node = { id: name, hidden: true, disabled: false, textContent: "", dataset: {}, ...extra };
    nodes.set(name, node);
    return node;
  };
  const events = [];
  const button = make("manualTranscriptionStart");
  const panel = make("manualTranscription", { contains: node => node === button });
  const language = make("manualTranscriptionLanguage", { options: ["auto", "he", "en"].map(value => ({ value })) });
  const status = make("manualTranscriptionStatus");
  make("manualTranscriptionTitle");
  make("manualTranscriptionHelp");
  make("manualTranscriptionLanguageLabel");
  const section = make("transcriptSection", { querySelector: () => ({ focus: () => events.push("focus-transcript") }) });
  const state = {
    project: { id: "p", revision: 7, analysis: { engine: "manual", transcript: { segments: [], words: [], text: "" } },
               draft: { engine: "manual" }, settings: { spoken_language: "auto" }, sources: { A: { has_audio: true } } },
    projectViewToken: 10, captionDirty: false, transcriptBuffers: new Map(),
    manualSelection: { start: 2, end: 3 }, timeline: { scheduleDraw: () => events.push("draw") },
  };
  const document = { getElementById: id => nodes.get(id), activeElement: button };
  const calls = [];
  const h = { state, document, panel, language, button, status, section, calls, events,
              cancelled: false, busy: false, flush: async () => true,
              complete: async () => ({ result: { saved: true, revision: 8, segment_count: 1 } }) };
  const context = vm.createContext({
    state, document, Number, JSON, encodeURIComponent,
    uiCopy: (_he, en) => en,
    foregroundBusy: () => h.busy,
    assertJobStartNotCancelled: () => { if (h.cancelled) throw Error("Cancelled"); },
    flushCurrentProjectSaves: () => h.flush(),
    acquireJobStartLock: (kind, id) => { if (h.busy) return null; h.busy = true; events.push([kind, id]); return "lock"; },
    releaseJobStartLock: () => { h.busy = false; events.push("released"); },
    api: async (url, options) => {
      calls.push([url, options?.body ? JSON.parse(options.body) : null]);
      if (url.endsWith("/manual-transcript")) return { job: { id: "j", kind: "manual_transcript" } };
      return { project: { ...state.project, revision: 8,
                         analysis: { engine: "manual", transcript: { segments: [{ id: "s1", text: "test" }] } } } };
    },
    pollJob: (id, options) => { calls.push([id, { ...options }]); return h.complete(); },
    reconcileProjectSnapshot: project => project,
    rememberProjectRevision: project => events.push(["revision", project.revision]),
    editorProject: () => state.project,
    renderTranscript: () => { events.push("transcript"); vm.runInContext("renderManualTranscription()", context); },
    renderCaptionControls: () => events.push("caption-controls"),
    renderCaptionInspector: () => events.push("caption-inspector"),
    previewPlaybackTime: () => 2.4,
    updatePreviewCaption: time => events.push(["preview", time]),
    toast: (message, level) => events.push([message, level]),
  });
  vm.runInContext(implementation, context);
  h.render = () => vm.runInContext("renderManualTranscription()", context);
  h.start = language => { context.language = language; return vm.runInContext("startManualTranscription(language)", context); };
  return h;
}

test("discoverable native button appears in Captions without starting inference on render", () => {
  const h = setup();
  h.render();
  assert.equal(h.panel.hidden, false);
  assert.equal(h.button.disabled, false);
  assert.equal(h.button.textContent, "Transcribe locally");
  assert.equal(h.language.value, "auto");
  assert.equal(h.calls.length, 0);
  const transcriptPanel = html.indexOf('id="studioPanelTranscript"');
  const control = html.indexOf('id="manualTranscription"');
  const alternative = html.indexOf('id="captionAlternatives"');
  assert.ok(transcriptPanel > 0 && transcriptPanel < control && control < alternative);
  assert.match(html, /<button type="button" id="manualTranscriptionStart"/);
  assert.match(html, /for="manualTranscriptionLanguage"/);
});

test("explicit language makes one local-only job and paints the existing view in place", async () => {
  const h = setup();
  h.render();
  h.language.value = "he";
  await h.button.onclick();
  assert.equal(h.calls[0][0], "/api/projects/p/manual-transcript");
  assert.deepEqual(h.calls[0][1], { language: "he", expected_revision: 7 });
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls[1])), ["j", { projectId: "p", kind: "manual_transcript", silent: true }]);
  assert.deepEqual(h.calls[2], ["/api/projects/p", null]);
  assert.equal(h.state.project.revision, 8);
  assert.equal(h.panel.hidden, true);
  assert.deepEqual(h.state.manualSelection, { start: 2, end: 3 });
  assert.ok(h.events.includes("draw") && h.events.includes("focus-transcript") && h.events.includes("released"));
  assert.deepEqual(h.events.find(event => event[0] === "preview"), ["preview", 2.4]);
  assert.equal(h.section.open, true);
});

test("cannot use remote result after switching to a different view of the same project", async () => {
  const h = setup();
  h.complete = async () => { h.state.projectViewToken++; return { result: { saved: true, revision: 8 } }; };
  await h.start("en");
  assert.equal(h.state.project.revision, 7);
  assert.equal(h.calls.length, 2);
  assert.ok(!h.events.includes("draw"));
});

test("finished no-speech, cancelled or failed jobs never replace the displayed project", async () => {
  for (const [expected, complete] of [
    ["No speech", async () => ({ result: { saved: false, reason: "no_speech" } })],
    ["cancelled", async () => { throw Error("Cancelled"); }],
    ["Check Local models", async () => { throw Error("Check Local models"); }],
  ]) {
    const h = setup();
    h.complete = complete;
    const shown = h.state.project;
    await h.start("en");
    assert.equal(h.state.project, shown);
    assert.ok(h.status.textContent.includes(expected));
    assert.equal(h.calls.length, 2);
  }
});

test("pending text, flush failure, existing versions, and silent or unsupported source block action", async () => {
  for (const condition of ["captionDirty", "flush", "silent", "B", "versions"]) {
    const h = setup();
    if (condition === "captionDirty") h.state.captionDirty = true;
    if (condition === "flush") h.flush = async () => false;
    if (condition === "silent") h.state.project.sources.A.has_audio = false;
    if (condition === "B") {
      h.state.project.manual = { source_mixer: { audio_slot: "B" } };
      h.state.project.sources.B = { has_audio: true };
    }
    if (condition === "versions") h.state.project.caption_alternatives = [{ id: "old" }];
    h.render();
    if (["silent", "B", "versions"].includes(condition)) assert.equal(h.button.disabled, true);
    await h.start("en");
    assert.equal(h.calls.length, 0);
  }
});

test("existing canonical transcript or non-manual draft hides the first-transcript action", () => {
  const h = setup();
  h.state.project.analysis.transcript.segments.push({ id: "old" });
  h.render();
  assert.equal(h.panel.hidden, true);
  h.state.project.analysis.transcript.segments = [];
  h.state.project.draft.engine = "audio_cleanup";
  h.render();
  assert.equal(h.panel.hidden, true);
});
