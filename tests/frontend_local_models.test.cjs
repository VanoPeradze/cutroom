const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const clone = value => JSON.parse(JSON.stringify(value));
const fixture = () => ({
  runtime: {installed: true, available: false, state: "idle", message: "Local AI has not been checked yet."},
  transcription_engine_installed: true,
  models: [
    {kind: "transcription", model: "base", label: "Whisper Base", profiles: ["lite"], estimated_download_gb: 0.15, installed: false, status: "not_installed", can_download: true},
    {kind: "transcription", model: "small", label: "Whisper Small", profiles: ["balanced"], estimated_download_gb: 0.49, installed: false, status: "not_installed", can_download: true},
    {kind: "editor", model: "qwen3.5:4b", label: "Story · Balanced", profiles: ["balanced"], estimated_download_gb: 3.4, installed: false, status: "not_installed", can_download: true},
  ], jobs: [], notes: [],
});
const job = (status = "running", extra = {}) => ({id: "model-job", kind: "model_install", project_id: null, status,
  progress: 0.25, message: "Downloading model files", cancel_requested: false, ...extra});
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => {resolve = a; reject = b;}); return {promise, resolve, reject}; };
const tick = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

function harness(options = {}) {
  const nodes = new Map(), calls = [], timers = new Map();
  let timerId = 0, changed = 0, busy = false;
  function element(tag = "div", id = "") {
    return {id, tagName: tag.toUpperCase(), children: [], textContent: "", className: "", value: "", hidden: false, disabled: false, attributes: {}, events: {},
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      setAttribute(key, value) { this.attributes[key] = value; },
      addEventListener(type, handler) { this.events[type] = handler; },
      fire(type) { return this.events[type]?.({target: this, preventDefault() {}}); },
      focus() { this.focused = true; },
    };
  }
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, element("div", id));
    return nodes.get(id);
  }
  const document = {getElementById: node, createElement: element};
  let catalog = fixture(), currentJob = job();
  const context = vm.createContext({document});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../web/local-models.js"), "utf8").replace(/^export /gm, ""), context);
  const api = async (url, request = {}) => {
    const call = {url, method: request.method || "GET", body: request.body ? JSON.parse(request.body) : undefined};
    calls.push(call);
    if (options.api) return options.api(call);
    if (url === "/api/models/local") return clone(catalog);
    if (url === "/api/models/install") return {job: clone(currentJob)};
    if (url.endsWith("/cancel")) return {accepted: true, job: {...currentJob, cancel_requested: true, message: "Cancelling"}};
    if (url.startsWith("/api/jobs/")) return {job: clone(currentJob)};
    if (url === "/api/runtime/prepare") return {runtime: {available: true}};
    throw Error(`Unexpected endpoint ${url}`);
  };
  const models = context.initLocalModels({document, api, busy: () => busy,
    changed: async () => { changed++; },
    schedule: (fn, delay) => { const id = ++timerId; timers.set(id, {fn, delay}); return id; },
    unschedule: id => timers.delete(id),
  });
  function descendants(root) { return [root, ...root.children.flatMap(descendants)]; }
  function card(kind) { return node("localModelCards").children[kind === "transcription" ? 0 : 1]; }
  function part(kind, tag) { return descendants(card(kind)).find(item => item.tagName === tag.toUpperCase()); }
  return {node, models, calls, timers, size: context.modelSize, select: kind => part(kind, "select"), download: kind => part(kind, "button"),
    setCatalog(value) {catalog = value;}, setJob(value) {currentJob = value;}, setBusy(value) {busy = value;},
    get changed() {return changed;},
    async nextTimer() {const entry = timers.entries().next().value; assert.ok(entry, "Expected a scheduled progress check"); timers.delete(entry[0]); await entry[1].fn();},
    async request(kind = "transcription") {await part(kind, "button").fire("click");},
    async confirm() {await node("confirmModelDownload").fire("click");},
  };
}

test("model sizes are estimates and invalid sizes do not become fake zero downloads", () => {
  const h = harness();
  assert.equal(h.size(0.49), "About 0.49 GB");
  assert.equal(h.size(3.4), "About 3.4 GB");
  for (const value of [null, undefined, NaN, -3, 0]) assert.equal(h.size(value), "Size varies");
});

test("opening and refreshing local setup performs only inventory reads", async () => {
  const h = harness();
  assert.equal(h.calls.length, 0);
  await h.models.refresh();
  await h.models.refresh();
  assert.deepEqual(h.calls.map(call => [call.method, call.url]), [["GET", "/api/models/local"], ["GET", "/api/models/local"]]);
  assert.equal(h.models.active, null);
  assert.equal(h.timers.size, 0);
});

test("download requires separate explicit confirmation and explains size privacy and profile", async () => {
  const h = harness(); await h.models.refresh();
  await h.confirm();
  await h.request();
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
  assert.equal(h.node("modelDownloadConfirm").hidden, false);
  assert.match(h.node("modelDownloadSummary").textContent, /Whisper Small/);
  assert.match(h.node("modelDownloadSummary").textContent, /0.49 GB/);
  assert.match(h.node("modelDownloadSummary").textContent, /No footage is uploaded/);
  assert.match(h.node("modelDownloadSummary").textContent, /does not change.*quality profile/);
  await h.confirm();
  assert.deepEqual(h.calls.filter(call => call.method === "POST"), [{url: "/api/models/install", method: "POST", body: {kind: "transcription", model: "small"}}]);
});

test("dismissing or changing the selected model clears pending consent", async () => {
  const h = harness(); await h.models.refresh();
  await h.request(); await h.node("dismissModelDownload").fire("click"); await h.confirm();
  assert.equal(h.node("modelDownloadConfirm").hidden, true);
  await h.request();
  h.select("transcription").value = "base"; await h.select("transcription").fire("change");
  await h.confirm();
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
  await h.request(); await h.confirm();
  assert.equal(h.calls.at(-1).body.model, "base");
});

test("double-click confirmation cannot queue duplicate downloads", async () => {
  const waiting = deferred(); let posts = 0;
  const h = harness({api: call => call.method === "GET" ? fixture() : (posts++, waiting.promise)});
  await h.models.refresh(); await h.request();
  const first = h.confirm(); await tick();
  await h.confirm(); await h.request("editor");
  assert.equal(posts, 1);
  assert.equal(h.node("confirmModelDownload").disabled, true);
  waiting.resolve({job: job()}); await first;
  assert.equal(h.node("confirmModelDownload").disabled, false);
  assert.equal(h.download("transcription").disabled, true);
});

test("failed submission shows the error and allows an explicit retry", async () => {
  let fail = true;
  const h = harness({api: call => {
    if (call.method === "GET") return fixture();
    if (fail) throw Error("Not enough disk space");
    return {job: job()};
  }});
  await h.models.refresh(); await h.request(); await h.confirm();
  assert.match(h.node("localModelsStatus").textContent, /disk space/);
  assert.equal(h.models.active, null);
  assert.equal(h.node("confirmModelDownload").disabled, false);
  assert.equal(h.download("transcription").disabled, false);
  fail = false; await h.confirm();
  assert.equal(h.models.active.id, "model-job");
});

test("active processing prevents new downloads, including a race after opening consent", async () => {
  const h = harness(); await h.models.refresh();
  h.setBusy(true); await h.request();
  assert.equal(h.node("modelDownloadSummary").textContent, "");
  h.setBusy(false); await h.request(); h.setBusy(true); await h.confirm();
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
});

test("installed and unavailable models cannot be downloaded", async () => {
  const h = harness(), catalog = fixture();
  catalog.models.forEach(model => {model.installed = true; model.can_download = false;});
  h.setCatalog(catalog); await h.models.refresh();
  assert.equal(h.download("transcription").disabled, true);
  assert.equal(h.download("editor").disabled, true);
  await h.request(); await h.confirm();
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
  assert.equal(h.node("homeLocalStatus").textContent, "Local models found");
});

test("a refresh invalidates stale consent for a model that became downloaded", async () => {
  const h = harness(); await h.models.refresh(); await h.request();
  const catalog = fixture(); catalog.models.find(model => model.model === "small").installed = true;
  h.setCatalog(catalog); await h.models.refresh(); await h.confirm();
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
});

test("missing Story prerequisite never prevents a separate speech-model download", async () => {
  const h = harness(), catalog = fixture(); catalog.runtime.installed = false;
  catalog.models.find(model => model.kind === "editor").can_download = false;
  h.setCatalog(catalog); await h.models.refresh();
  assert.equal(h.download("editor").disabled, true);
  assert.equal(h.download("transcription").disabled, false);
  await h.request("editor"); await h.confirm();
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
  await h.request("transcription"); await h.confirm();
  assert.equal(h.calls.at(-1).body.kind, "transcription");
});

test("choosing a model only changes download selection, never project settings or API connection", async () => {
  const h = harness(); await h.models.refresh();
  h.select("transcription").value = "base"; await h.select("transcription").fire("change");
  await h.models.refresh();
  assert.equal(h.select("transcription").value, "base");
  assert.ok(h.calls.every(call => call.method === "GET"));
});

test("refresh recovers global queued or running jobs and resumes progress polling", async () => {
  const h = harness(), catalog = fixture(); catalog.jobs = [job("queued")];
  h.setCatalog(catalog); await h.models.refresh();
  assert.equal(h.models.active.id, "model-job");
  assert.equal(h.node("localDownloadJob").hidden, false);
  assert.equal(h.download("editor").disabled, true);
  assert.equal(h.timers.size, 1);
  h.setJob(job("running", {progress: 0.65, message: "Downloading 650 / 1000 bytes"}));
  await h.nextTimer();
  assert.equal(h.node("localDownloadProgress").value, 0.65);
  assert.match(h.node("localDownloadLabel").textContent, /650/);
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
});

test("accepted cancellation uses backend cancel_requested even while status remains running", async () => {
  const h = harness(); await h.models.refresh(); await h.request(); await h.confirm();
  await h.node("cancelLocalDownload").fire("click");
  assert.equal(h.node("cancelLocalDownload").disabled, true);
  assert.equal(h.node("cancelLocalDownload").textContent, "Cancelling…");
  h.setJob(job("cancelled", {cancel_requested: true})); await h.nextTimer();
  assert.equal(h.models.active, null);
  assert.match(h.node("localModelsStatus").textContent, /cancelled.*cached files/);
  assert.equal(h.node("localDownloadJob").hidden, true);
});

test("double-click cancellation creates at most one in-flight cancel request", async () => {
  const waiting = deferred(); let cancels = 0;
  const h = harness({api: call => {
    if (call.url === "/api/models/local") return fixture();
    if (call.url.endsWith("/cancel")) {cancels++; return waiting.promise;}
    return {job: job()};
  }});
  await h.models.refresh(); await h.request(); await h.confirm();
  const first = h.node("cancelLocalDownload").fire("click"); await tick();
  const second = h.node("cancelLocalDownload").fire("click");
  assert.equal(cancels, 1);
  waiting.resolve({job: job("running", {cancel_requested: true})}); await first; await second;
});

test("failed cancellation restores controls and never pretends the download stopped", async () => {
  const h = harness({api: call => {
    if (call.url === "/api/models/local") return fixture();
    if (call.url.endsWith("/cancel")) throw Error("Could not reach server");
    return {job: job()};
  }});
  await h.models.refresh(); await h.request(); await h.confirm();
  await h.node("cancelLocalDownload").fire("click");
  assert.equal(h.models.active.status, "running");
  assert.equal(h.node("cancelLocalDownload").disabled, false);
  assert.match(h.node("localModelsStatus").textContent, /Could not reach server/);
});

test("late cancellation response cannot resurrect a finished job or replace a newer download", async () => {
  const waiting = deferred(); let catalog = fixture();
  const h = harness({api: call => {
    if (call.url === "/api/models/local") return clone(catalog);
    if (call.url.endsWith("/cancel")) return waiting.promise;
    return {job: job()};
  }});
  await h.models.refresh(); await h.request(); await h.confirm();
  const cancel = h.node("cancelLocalDownload").fire("click");
  catalog.jobs = [job("running", {id: "another-download"})]; await h.models.refresh();
  waiting.resolve({job: job("cancelled", {cancel_requested: true})}); await cancel;
  assert.equal(h.models.active.id, "another-download");
  assert.equal(h.node("cancelLocalDownload").disabled, false);
});

test("terminal completion refreshes inventory and restores download controls", async () => {
  const h = harness(); await h.models.refresh(); await h.request(); await h.confirm();
  const catalog = fixture(); catalog.models.find(model => model.model === "small").installed = true;
  h.setCatalog(catalog); h.setJob(job("completed", {progress: 1})); await h.nextTimer();
  assert.equal(h.models.active, null);
  assert.equal(h.download("transcription").textContent, "Downloaded");
  assert.equal(h.download("editor").disabled, false);
  assert.match(h.node("localModelsStatus").textContent, /Download complete/);
  assert.equal(h.changed, 1);
});

test("terminal jobs release controls even if the follow-up inventory refresh fails", async () => {
  let finished = false;
  const h = harness({api: call => {
    if (call.url === "/api/models/local") {
      if (finished) throw Error("Inventory unavailable");
      return fixture();
    }
    if (call.url === "/api/models/install") return {job: job()};
    finished = true;
    return {job: job("completed", {progress: 1})};
  }});
  await h.models.refresh(); await h.request(); await h.confirm(); await h.nextTimer();
  assert.equal(h.models.active, null);
  assert.equal(h.node("localDownloadJob").hidden, true);
  assert.equal(h.download("editor").disabled, false);
  assert.match(h.node("localModelsStatus").textContent, /refresh|check.*status/i);
  assert.equal(h.timers.size, 0);
});

test("refresh during an in-flight progress request leaves only one polling timer", async () => {
  const waiting = deferred(), catalog = fixture(); catalog.jobs = [job()];
  const h = harness({api: call => call.url === "/api/models/local" ? clone(catalog) : waiting.promise});
  await h.models.refresh();
  const polling = h.nextTimer(); await tick();
  await h.models.refresh();
  assert.equal(h.timers.size, 1);
  waiting.resolve({job: job("running", {progress: 0.6})}); await polling;
  assert.equal(h.timers.size, 1);
  assert.equal(h.node("localDownloadProgress").value, 0.6);
});

test("failed and interrupted downloads remain visible after refresh without automatic retry", async () => {
  for (const status of ["failed", "interrupted"]) {
    const h = harness(), catalog = fixture(); catalog.jobs = [job(status, {error: "The application restarted before completion."})];
    h.setCatalog(catalog); await h.models.refresh();
    assert.match(h.node("localModelsStatus").textContent, /restarted|interrupted|did not finish/i);
    assert.equal(h.models.active, null);
    assert.equal(h.timers.size, 0);
    assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
  }
});

test("three failed progress checks stop looping, and Refresh reconnects without another install", async () => {
  let failing = true;
  const catalog = fixture(); catalog.jobs = [job()];
  const h = harness({api: call => {
    if (call.url === "/api/models/local") return clone(catalog);
    if (failing) throw Error("Network interrupted");
    return {job: job("running", {progress: 0.8})};
  }});
  await h.models.refresh(); await h.nextTimer(); await h.nextTimer(); await h.nextTimer();
  assert.equal(h.timers.size, 0);
  assert.match(h.node("localModelsStatus").textContent, /Refresh/);
  failing = false; await h.node("refreshLocalModels").fire("click"); await tick(); await h.nextTimer();
  assert.equal(h.node("localDownloadProgress").value, 0.8);
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
});

test("installed engine in idle state is distinct from running or missing", async () => {
  const h = harness(); await h.models.refresh();
  assert.equal(h.node("localRuntimeTitle").textContent, "Story engine is installed");
  assert.equal(h.node("localRuntimeInstall").hidden, true);
  assert.equal(h.node("startLocalEngine").hidden, false);
  const catalog = fixture(); catalog.runtime.installed = false; h.setCatalog(catalog); await h.models.refresh();
  assert.equal(h.node("localRuntimeInstall").hidden, false);
  assert.equal(h.node("startLocalEngine").hidden, true);
  catalog.runtime.installed = true; catalog.runtime.available = true; h.setCatalog(catalog); await h.models.refresh();
  assert.equal(h.node("localRuntimeTitle").textContent, "Story engine available at last check");
  assert.equal(h.node("startLocalEngine").hidden, false);
  assert.equal(h.node("startLocalEngine").textContent, "Check local engine");
});

test("starting local engine requires local connection and does not download weights", async () => {
  const h = harness(); await h.models.refresh();
  h.models.setConnection({mode: "free"}); await h.node("startLocalEngine").fire("click");
  assert.equal(h.calls.filter(call => call.method === "POST").length, 0);
  h.models.setConnection({mode: "local"}); await h.node("startLocalEngine").fire("click");
  assert.deepEqual(h.calls.filter(call => call.method === "POST").map(call => call.url), ["/api/runtime/prepare"]);
  assert.equal(h.changed, 1);
});

test("a stale successful refresh cannot overwrite a newer inventory", async () => {
  const earlier = deferred(); let calls = 0;
  const latest = fixture(); latest.runtime.available = true;
  const h = harness({api: () => ++calls === 1 ? earlier.promise : latest});
  const first = h.models.refresh(); await tick(); await h.models.refresh();
  earlier.resolve(fixture()); await first;
  assert.equal(h.node("localRuntimeTitle").textContent, "Story engine available at last check");
});

test("a stale failed refresh cannot overwrite a newer successful status", async () => {
  const earlier = deferred(); let calls = 0;
  const h = harness({api: () => ++calls === 1 ? earlier.promise : fixture()});
  const first = h.models.refresh(); await tick(); await h.models.refresh();
  earlier.reject(Error("Old request failed")); await first;
  assert.doesNotMatch(h.node("localModelsStatus").textContent, /Old request failed/);
  assert.equal(h.node("refreshLocalModels").disabled, false);
});
