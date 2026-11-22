const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function harness(overrides = {}) {
  const nodes = new Map();
  const modes = ["local", "free", "own"].map(value => ({value, checked: value === "local"}));
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
      id, dataset: {}, value: "", textContent: "", hidden: false, disabled: false, events: {},
      addEventListener(type, handler) { this.events[type] = handler; },
      async fire(type, target = this) { return this.events[type]?.({target, preventDefault() {}}); },
      showModal() { this.open = true; }, close() { this.open = false; this.events.close?.(); },
      focus() { this.focused = true; }, scrollIntoView() { this.scrolled = true; },
      querySelector(selector) {
        if (selector.includes(":checked")) return modes.find(item => item.checked);
        const value = selector.match(/input\[value="([^"]+)"\]/)?.[1];
        if (value) return modes.find(item => item.value === value);
        return node(selector);
      },
    });
    return nodes.get(id);
  }
  const cards = ["short", "youtube", "manual"].map(kind => {
    const card = node(kind); card.dataset.startWorkflow = kind; return card;
  });
  const calls = [];
  const document = {getElementById: node, querySelectorAll: () => cards};
  const scope = vm.createContext({document});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../web/welcome.js"), "utf8").replace(/^export /gm, ""), scope);
  const welcome = scope.initWelcome({document,
    api: async (url, options) => {
      const body = JSON.parse(options.body); calls.push({url, body});
      return {connection: {mode: body.mode, model: "openai/gpt-oss-120b", configured: true, has_key: body.mode !== "local"}};
    },
    createProject: async options => calls.push(options), goHome: async () => {},
    pause: () => {}, changed: async () => {}, busy: () => false, ...overrides});
  return {node, cards, calls, welcome, settings: scope.workflowSettings,
    chooseMode: async value => {
      modes.forEach(item => {item.checked = item.value === value;});
      await node("aiConnectionForm").fire("change", {name: "connectionMode"});
    }};
}

test("starting points preserve YouTube aspect and manual no-AI intent", () => {
  const {settings} = harness();
  assert.equal(settings("short").aspect, "9:16");
  assert.equal(settings("youtube").aspect, "16:9");
  assert.equal(settings("youtube").goal, "youtube");
  assert.equal(settings("manual").workflow, "manual");
  assert.equal(settings("manual").editorial_effects, false);
  assert.throws(() => settings("unknown"));
});

test("service selection dispatches the selected workflow", async () => {
  const h = harness();
  for (const kind of ["short", "youtube", "manual"]) await h.node(kind).fire("click");
  assert.deepEqual(h.calls.map(call => call.workflow), ["short", "youtube", "manual"]);
  assert.equal(h.node("sourceSlotA").focused, true);
});

test("double-click does not create duplicate projects and failed creation unlocks cards", async () => {
  let release, count = 0;
  const h = harness({createProject: async () => {count++; await new Promise(resolve => {release = resolve;}); throw Error("Offline");}});
  const first = h.node("youtube").fire("click");
  await h.node("youtube").fire("click");
  assert.equal(count, 1);
  assert.ok(h.cards.every(card => card.disabled));
  release();
  await assert.rejects(first, /Offline/);
  assert.ok(h.cards.every(card => !card.disabled));
});

test("choosing a cloud radio is not consent or a network request", async () => {
  const h = harness();
  h.welcome.openConnection();
  await h.chooseMode("free");
  assert.equal(h.node("cloudConnectionFields").hidden, false);
  assert.equal(h.node("cloudConsent").required, true);
  assert.equal(h.node("cloudAPIKey").required, true);
  assert.equal(h.calls.length, 0);
  assert.equal(h.node("cloudConsent").checked, false);
});

test("explicit connection save sends only to local API and clears the key field", async () => {
  const h = harness();
  h.welcome.openConnection();
  await h.chooseMode("own");
  h.node("cloudAPIKey").value = "not-a-real-key";
  h.node("cloudConsent").checked = true;
  await h.node("aiConnectionForm").fire("submit");
  assert.equal(h.calls[0].url, "/api/ai/connection");
  assert.equal(h.calls[0].body.consent, true);
  assert.equal(h.node("cloudAPIKey").value, "");
  assert.equal(h.node("aiConnectionDialog").open, false);
  assert.equal(h.node("processingBadge").textContent, "Cloud AI");
});

test("closing without saving clears secrets and never changes the selected connection", async () => {
  const h = harness();
  h.welcome.openConnection();
  await h.chooseMode("free");
  h.node("cloudAPIKey").value = "discard-me";
  h.node("aiConnectionDialog").close();
  assert.equal(h.node("cloudAPIKey").value, "");
  assert.equal(h.calls.length, 0);
});

test("active processing blocks connection changes", async () => {
  const h = harness({busy: () => true});
  h.welcome.openConnection();
  await h.chooseMode("own");
  await h.node("aiConnectionForm").fire("submit");
  assert.equal(h.calls.length, 0);
  assert.equal(h.node("connectionStatus").dataset.error, "true");
});

test("manual setup explains no-AI editing and hides runtime preparation", () => {
  const h = harness();
  h.welcome.updateProject({settings: {workflow: "manual", goal: "youtube"}});
  assert.equal(h.node('[data-i18n="makeEdit"]').textContent, "Open manual editor");
  assert.equal(h.node("setupRuntimeDock").hidden, true);
  h.welcome.updateProject({settings: {workflow: "ai", goal: "youtube"}});
  assert.match(h.node("setupIntentCopy").textContent, /16:9/);
  assert.equal(h.node("setupRuntimeDock").hidden, false);
});


test("manual start focuses the visible empty-editor import control, not hidden setup", async () => {
  const h=harness();
  await h.node("manual").fire("click");
  assert.equal(h.node("[data-first-choose]").focused,true);
  assert.equal(h.node("sourceSlotA").focused,undefined);
  h.welcome.updateProject({settings:{workflow:"manual"}});
  assert.match(h.node("setupIntentCopy").textContent,/opens immediately/);
});


test("blocked Home never focuses workflow choices behind the retained editor", async () => {
  const h=harness({goHome:async()=>false});await h.node("changeWorkflowButton").fire("click");
  assert.notEqual(h.node("welcomeServices").focused,true);
});

test("a refused project create never focuses an importer in the current project",async()=>{
  const h=harness({createProject:async()=>false});await h.node("manual").fire("click");
  assert.notEqual(h.node("[data-first-choose]").focused,true);assert.notEqual(h.node("sourceSlotA").focused,true);
  assert.equal(h.node("manual").disabled,false);
});


test("primary manual entry shares the recipe creation lock, and preserves disabled controls", async () => {
  let finish, count=0;
  const h=harness({createProject:async options=>{count++;assert.equal(options.workflow,'manual');return await new Promise(r=>{finish=r})}});
  h.node('youtube').disabled=true;
  const first=h.welcome.startWorkflow('manual');
  assert.equal(h.node('newProjectButton').disabled,true);
  await h.welcome.startWorkflow('manual');await h.node('short').fire('click');assert.equal(count,1);
  finish({id:'p'});await first;
  assert.equal(h.node('[data-first-choose]').focused,true);
  assert.equal(h.node('youtube').disabled,true);assert.equal(h.node('newProjectButton').disabled,false);
});
test("busy or refused primary entry makes no new project and never focuses a hidden importer",async()=>{
  const busy=harness({busy:()=>true});await busy.welcome.startWorkflow();assert.equal(busy.calls.length,0);
  const h=harness({createProject:async()=>false});await h.welcome.startWorkflow();assert.notEqual(h.node('[data-first-choose]').focused,true);
  const hidden=harness();hidden.node('[data-first-choose]').closest=()=>({hidden:true});await hidden.welcome.startWorkflow();assert.notEqual(hidden.node('[data-first-choose]').focused,true);
});
