const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function harness({connection, api: respond, busy = () => false} = {}) {
  const nodes = new Map(), calls = [], radios = [];
  for (const value of ["local", "free", "own"]) {
    let checked = value === "local";
    radios.push({value, name: "connectionMode", get checked() { return checked; },
      set checked(next) { if (next) radios.filter(radio => radio.value !== value).forEach(radio => { radio.checked = false; }); checked = next; }});
  }
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
      id, value: "", textContent: "", dataset: {}, hidden: false, disabled: false, events: {}, checked: false,
      addEventListener(type, handler) { this.events[type] = handler; },
      fire(type, target = this) { return this.events[type]?.({target, preventDefault() {}}); },
      showModal() { this.open = true; }, close() { this.open = false; this.fire("close"); },
      focus() {}, scrollIntoView() {},
      querySelector(selector) {
        if (selector.includes(":checked")) return radios.find(radio => radio.checked);
        const value = selector.match(/input\[value="([^"]+)"\]/)?.[1];
        return value ? radios.find(radio => radio.value === value) : node(selector);
      },
    });
    return nodes.get(id);
  }
  const document = {getElementById: node, querySelectorAll: () => []};
  const scope = vm.createContext({document, URL});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../web/welcome.js"), "utf8").replace(/^export /gm, ""), scope);
  const welcome = scope.initWelcome({document, busy, pause() {}, changed: async () => {},
    createProject: async () => {}, goHome: async () => {},
    api: async (url, options) => {
      const body = JSON.parse(options.body); calls.push({url, body});
      if (respond) return respond(body);
      return {connection: {...body, api_key: undefined, has_key: body.mode !== "local", configured: true}};
    },
  });
  if (connection) welcome.setConnection(connection);
  welcome.openConnection();
  const chooseMode = async value => {
    const radio = radios.find(item => item.value === value); radio.checked = true;
    await node("aiConnectionForm").fire("change", radio);
  };
  const chooseProvider = async value => {
    node("cloudProvider").value = value;
    await node("aiConnectionForm").fire("change", node("cloudProvider"));
  };
  return {node, calls, welcome, scope, chooseMode, chooseProvider,
    submit: () => node("aiConnectionForm").fire("submit"),
    async endpoint(value) { node("cloudBaseURL").value = value; await node("cloudBaseURL").fire("input"); },
    consent(key = "synthetic-api-key") { node("cloudAPIKey").value = key; node("cloudConsent").checked = true; },
    async custom() {
      await chooseMode("own"); await chooseProvider("openai-compatible");
      node("cloudBaseURL").value = "https://api.example.com/v1"; await node("cloudBaseURL").fire("input");
      node("cloudStoryModel").value = "story-model"; node("cloudTranscriptModel").value = "speech-model";
    },
  };
}

const savedCustom = {mode: "own", provider: "openai-compatible", base_url: "https://api.example.com/v1",
  model: "story-model", transcript_model: "speech-model", has_key: true, configured: true};

test("compatible controls are available only for own-provider mode and make no network requests", async () => {
  const h = harness();
  await h.custom();
  assert.equal(h.node("cloudProviderField").hidden, false);
  assert.equal(h.node("compatibleConnectionFields").hidden, false);
  assert.equal(h.node("cloudBaseURL").required, true);
  assert.equal(h.node("cloudTranscriptModel").required, true);
  assert.equal(h.node("cloudModelSettings").open, true);
  assert.equal(h.node("groqKeyLink").hidden, true);
  assert.match(h.node("cloudProviderHelp").textContent, /chat\/completions.*JSON object.*audio\/transcriptions.*verbose_json.*word timestamps/);
  await h.chooseMode("free");
  assert.equal(h.node("cloudProvider").value, "groq");
  assert.equal(h.node("compatibleConnectionFields").hidden, true);
  assert.equal(h.node("cloudBaseURL").disabled, true);
  assert.equal(h.node("cloudTranscriptModel").required, false);
  assert.match(h.node("cloudProviderHelp").textContent, /quotas.*paid account.*no shared API key or credit/);
  assert.equal(h.calls.length, 0);
});

test("compatible save submits explicit endpoint consent and both model IDs only to the local API", async () => {
  const h = harness(); await h.custom();
  await h.endpoint("https://api.example.com/v1/"); h.consent();
  await h.submit();
  assert.deepEqual(h.calls, [{url: "/api/ai/connection", body: {
    mode: "own", provider: "openai-compatible", model: "story-model", consent: true,
    api_key: "synthetic-api-key", base_url: "https://api.example.com/v1", transcript_model: "speech-model",
    endpoint_consent: "https://api.example.com/v1",
  }}]);
  assert.equal(h.node("cloudAPIKey").value, "");
  assert.equal(h.node("cloudConsent").checked, false);
  assert.equal(h.node("aiConnectionDialog").open, false);
});

test("changing provider mode or endpoint clears pending credentials and consent", async () => {
  for (const change of [h => h.chooseMode("free"), h => h.chooseProvider("groq"), h => h.endpoint("https://other.example.com/v1")]) {
    const h = harness({connection: savedCustom}); h.consent();
    await change(h);
    assert.equal(h.node("cloudAPIKey").value, "");
    assert.equal(h.node("cloudConsent").checked, false);
    assert.equal(h.node("cloudAPIKey").required, true);
    assert.equal(h.calls.length, 0);
  }
});

test("returning to the saved endpoint after an edit still requires a fresh key", async () => {
  const h = harness({connection: savedCustom});
  await h.endpoint("https://other.example.com/v1"); await h.endpoint(savedCustom.base_url);
  h.node("cloudConsent").checked = true;
  await h.submit();
  assert.equal(h.calls.length, 0);
  assert.match(h.node("connectionStatus").textContent, /fresh API key/);
});

test("an unchanged saved custom connection can retain its scoped session key with fresh consent", async () => {
  const h = harness({connection: savedCustom});
  assert.equal(h.node("cloudModelSettings").open, true);
  assert.equal(h.node("cloudAPIKey").required, false);
  assert.equal(h.node("cloudConsent").checked, false);
  await h.submit(); assert.equal(h.calls.length, 0);
  h.node("cloudConsent").checked = true;
  await h.submit();
  assert.equal(h.calls[0].body.api_key, "");
  assert.equal(h.calls[0].body.endpoint_consent, savedCustom.base_url);
});

test("a destination change without an input event cannot carry a pending key into submission", async () => {
  const h = harness(); await h.custom(); h.consent();
  h.node("cloudBaseURL").value = "https://other.example.com/v1";
  await h.submit();
  assert.equal(h.calls.length, 0);
  assert.equal(h.node("cloudAPIKey").value, "");
  assert.equal(h.node("cloudConsent").checked, false);
  assert.match(h.node("connectionStatus").textContent, /destination changed/);
});

test("invalid HTTPS destinations and missing transcription models fail before any request", async () => {
  for (const url of ["http://api.example.com/v1", "https://key@api.example.com/v1", "https://api.example.com/v1?key=secret", "https://api.example.com/v1#fragment", "not a URL"]) {
    const h = harness(); await h.custom(); await h.endpoint(url); h.consent();
    await h.submit();
    assert.equal(h.calls.length, 0, url);
    assert.match(h.node("connectionStatus").textContent, /HTTPS/);
  }
  const h = harness(); await h.custom(); h.node("cloudTranscriptModel").value = ""; h.consent();
  await h.submit();
  assert.equal(h.calls.length, 0);
  assert.match(h.node("connectionStatus").textContent, /word timestamps/);
});

test("Groq saves do not include custom endpoint fields and local saves do not include credentials", async () => {
  const h = harness(); await h.chooseMode("free"); h.consent(); await h.submit();
  assert.equal(h.calls[0].body.provider, "groq");
  for (const field of ["base_url", "endpoint_consent", "transcript_model"]) assert.equal(field in h.calls[0].body, false);
  h.welcome.openConnection(); await h.chooseMode("local"); h.node("cloudAPIKey").value = "discard-me";
  await h.submit();
  assert.deepEqual(h.calls[1].body, {mode: "local"});
});

test("custom connection status names the selected provider without Groq branding", () => {
  const h = harness({connection: savedCustom});
  assert.match(h.node("homeConnectionDetail").textContent, /Your API provider/);
  assert.doesNotMatch(h.node("homePrivacyNote").textContent, /Groq/);
  assert.match(h.node("cloudConsentCopy").textContent, /https:\/\/api\.example\.com\/v1/);
});

test("the editor's cloud status uses the provider selected by the connection", () => {
  const h = harness({connection: savedCustom});
  const source = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
  const render = source.slice(source.indexOf("function renderModelStatus()"), source.indexOf("function prepareLocalAI()"));
  h.scope.state = {system: {ai_connection: savedCustom}};
  h.scope.elements = {modelStatus: h.node("modelStatus"), modelButton: h.node("modelButton"), retryAIButton: h.node("retryAIButton")};
  h.scope.$ = selector => h.node(selector);
  vm.runInContext(render + "\nrenderModelStatus();", h.scope);
  assert.match(h.node("b").textContent, /Your API provider/);
  assert.doesNotMatch(h.node("small").textContent, /Groq/);
  h.scope.state.system.ai_connection = {...savedCustom, provider: "groq"};
  vm.runInContext("renderModelStatus();", h.scope);
  assert.match(h.node("b").textContent, /Groq/);
});

test("closing and busy state cannot leak or submit pending custom credentials", async () => {
  const h = harness({busy: () => true}); await h.custom(); h.consent();
  await h.submit(); assert.equal(h.calls.length, 0);
  h.node("aiConnectionDialog").close();
  assert.equal(h.node("cloudAPIKey").value, "");
  assert.equal(h.node("cloudConsent").checked, false);
});
