const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../web/ui-shell.js"), "utf8");

function harness({ stored = null, systemDark = false, storageBlocked = false, observer = true, matchMedia = true } = {}) {
  const events = {}, windowEvents = {}, nodes = new Map(), writes = [], mediaCalls = [];
  const store = new Map([["cutroom-theme", stored]]);
  const node = (id) => ({ id, attrs: {}, textContent: "", events: {},
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(type, callback) { this.events[type] = callback; },
  });
  const root = { dataset: {}, style: { setProperty: (key, value) => writes.push([key, value]) } };
  const meta = node("theme-color");
  const chrome = node("appChrome");
  chrome.height = 64;
  chrome.getBoundingClientRect = () => ({ height: chrome.height });
  const media = ["previewA", "previewB"].map((id) => ({ id, src: `${id}.mp4`, currentTime: 17,
    play() { mediaCalls.push([id, "play"]); },
    pause() { mediaCalls.push([id, "pause"]); },
    load() { mediaCalls.push([id, "load"]); },
  }));
  let fontReady, resized, mutated, observed, mutationTarget;
  class ResizeObserver {
    constructor(callback) { resized = callback; }
    observe(target) { observed = target; }
  }
  class MutationObserver {
    constructor(callback) { mutated = callback; }
    observe(target) { mutationTarget = target; }
  }
  const document = {
    documentElement: root,
    getElementById: (id) => nodes.get(id) || media.find((item) => item.id === id) || null,
    querySelector: (selector) => selector === 'meta[name="theme-color"]' ? meta : media[0],
    querySelectorAll: () => media,
    addEventListener: (type, callback) => { events[type] = callback; },
    fonts: { ready: { then(callback) { fontReady = callback; } } },
  };
  const window = {
    addEventListener: (type, callback) => { windowEvents[type] = callback; },
    ...(observer ? { ResizeObserver } : {}),
    ...(matchMedia ? { matchMedia: (query) => {
      assert.equal(query, "(prefers-color-scheme: dark)");
      return { matches: systemDark };
    } } : {}),
  };
  const localStorage = {
    getItem(key) { if (storageBlocked) throw Error("Storage denied"); return store.get(key) ?? null; },
    setItem(key, value) { if (storageBlocked) throw Error("Storage denied"); store.set(key, value); },
  };
  vm.runInNewContext(source, { document, window, localStorage, ResizeObserver, MutationObserver,
    pauseAllMedia: () => mediaCalls.push(["all", "pause"]),
    fetch: () => assert.fail("Appearance changes must not request network resources"),
  });
  return { root, meta, store, writes, chrome, media, mediaCalls, nodes,
    ready() {
      ["themeToggle", "themeIcon", "themeLabel"].forEach((id) => nodes.set(id, node(id)));
      nodes.set("appChrome", chrome);
      events.DOMContentLoaded();
    },
    toggle() { nodes.get("themeToggle").events.click(); },
    resize(height) { chrome.height = height; (resized || windowEvents.resize)(); },
    fontsReady() { fontReady(); },
    mutate(height) { chrome.height = height; mutated(); },
    observed: () => observed,
    mutationTarget: () => mutationTarget,
  };
}

for (const theme of ["light", "dark"]) {
  test(`stored ${theme} appearance overrides the system before the page is ready`, () => {
    const h = harness({ stored: theme, systemDark: theme !== "dark" });
    assert.equal(h.root.dataset.theme, theme);
    assert.equal(h.root.style.colorScheme, theme);
    assert.equal(h.meta.attrs.content, theme === "dark" ? "#101516" : "#f6f5f1");
    h.ready();
    assert.equal(h.nodes.get("themeToggle").attrs["aria-pressed"], String(theme === "dark"));
    assert.equal(h.nodes.get("themeLabel").textContent, theme === "dark" ? "Night" : "Day");
  });
}

test("missing and invalid preferences follow the system, with light fallback when unavailable", () => {
  for (const stored of [null, "sepia", "", "system"]) {
    for (const systemDark of [false, true]) {
      assert.equal(harness({ stored, systemDark }).root.dataset.theme, systemDark ? "dark" : "light");
    }
  }
  assert.equal(harness({ matchMedia: false }).root.dataset.theme, "light");
});

test("toggling synchronizes theme, accessible state, label, icon, meta color and storage", () => {
  const h = harness({ stored: "light" });
  h.ready();
  for (const dark of [true, false]) {
    h.toggle();
    const theme = dark ? "dark" : "light";
    assert.equal(h.root.dataset.theme, theme);
    assert.equal(h.root.style.colorScheme, theme);
    assert.equal(h.store.get("cutroom-theme"), theme);
    assert.equal(h.nodes.get("themeToggle").attrs["aria-pressed"], String(dark));
    assert.equal(h.nodes.get("themeToggle").title, dark ? "Switch to day mode" : "Switch to night mode");
    assert.equal(h.nodes.get("themeLabel").textContent, dark ? "Night" : "Day");
    assert.equal(h.nodes.get("themeIcon").textContent, dark ? "☾" : "☀");
    assert.equal(h.meta.attrs.content, dark ? "#101516" : "#f6f5f1");
  }
});

test("blocked storage still permits repeated appearance changes", () => {
  const h = harness({ storageBlocked: true, systemDark: true });
  h.ready();
  assert.equal(h.root.dataset.theme, "dark");
  h.toggle();
  assert.equal(h.root.dataset.theme, "light");
  h.toggle();
  assert.equal(h.root.dataset.theme, "dark");
  assert.equal(h.nodes.get("themeToggle").attrs["aria-pressed"], "true");
});

test("chrome observations round up changed heights and avoid duplicate or zero-height writes", () => {
  const h = harness();
  h.ready();
  assert.equal(h.observed(), h.chrome);
  assert.deepEqual(h.writes, [["--app-chrome-height", "64px"]]);
  h.resize(119.2);
  h.resize(119.9);
  h.fontsReady();
  h.resize(0);
  h.resize(120);
  h.resize(64);
  assert.deepEqual(h.writes, [64, 120, 64].map((height) => ["--app-chrome-height", `${height}px`]));
});

test("resize and DOM mutation fallback also measures wrapped controls and status changes", () => {
  const h = harness({ observer: false });
  h.ready();
  assert.equal(h.mutationTarget(), h.chrome);
  h.resize(98.4);
  h.mutate(154.4);
  h.fontsReady();
  assert.deepEqual(h.writes, [64, 99, 155].map((height) => ["--app-chrome-height", `${height}px`]));
});

test("theme changes and chrome measurements leave media playback, sources and positions untouched", () => {
  const h = harness();
  const snapshot = h.media.map(({ src, currentTime }) => ({ src, currentTime }));
  h.ready();
  h.toggle();
  h.resize(120);
  h.toggle();
  h.resize(64);
  h.fontsReady();
  assert.deepEqual(h.mediaCalls, []);
  assert.deepEqual(h.media.map(({ src, currentTime }) => ({ src, currentTime })), snapshot);
});
