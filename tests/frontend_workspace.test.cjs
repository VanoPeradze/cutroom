const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../web/workspace.js"), "utf8").replace(/^export /gm, "");
const context = vm.createContext({});
vm.runInContext(source + "\nglobalThis.initWorkspace = initWorkspace;", context);

class Target {
  constructor() { this.events = new Map(); }
  addEventListener(type, fn) { this.events.set(type, [...(this.events.get(type) || []), fn]); }
  removeEventListener(type, fn) { this.events.set(type, (this.events.get(type) || []).filter((value) => value !== fn)); }
  emit(type, event = {}) { for (const fn of [...(this.events.get(type) || [])]) fn(event); }
}
class Element extends Target {
  constructor(tag, doc) {
    super(); this.tagName = tag; this.doc = doc; this.children = []; this.attrs = new Map(); this.dataset = {};
    this.classes = new Set(); this.hidden = false; this.open = false; this.rect = { height: 800 }; this.capture = null;
    this.classList = { add: (v) => this.classes.add(v), remove: (v) => this.classes.delete(v), contains: (v) => this.classes.has(v),
      toggle: (v, on) => on ? this.classes.add(v) : this.classes.delete(v) };
    this.properties = new Map(); this.style = { setProperty: (k, v) => this.properties.set(k, v), removeProperty: (k) => this.properties.delete(k) };
  }
  set id(value) { this._id = value; this.doc.ids.set(value, this); }
  get id() { return this._id || ""; }
  set className(value) { this.classes = new Set(value.split(" ")); }
  set textContent(value) { this.text = value; }
  get textContent() { return [this.text || "", ...this.children.map((el) => el.textContent)].join(""); }
  get firstChild() { return this.children[0] || null; }
  get nextSibling() { return this.parentElement?.children[this.parentElement.children.indexOf(this) + 1] || null; }
  appendChild(el) { el.remove(); this.children.push(el); el.parentElement = this; return el; }
  append(...children) { children.forEach((el) => this.appendChild(el)); }
  insertBefore(el, next) { el.remove(); const i = this.children.indexOf(next); if (i < 0) this.appendChild(el); else { this.children.splice(i, 0, el); el.parentElement = this; } }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter((v) => v !== this); this.parentElement = null; }
  setAttribute(k, v) { this.attrs.set(k, v); }
  getAttribute(k) { return this.attrs.get(k); }
  removeAttribute(k) { this.attrs.delete(k); }
  contains(el) { return this === el || this.descendants().includes(el); }
  descendants() { return this.children.flatMap((el) => [el, ...el.descendants()]); }
  querySelector(selector) { return this.descendants().find((el) => selector.startsWith(".") ? el.classList.contains(selector.slice(1)) : selector === "dialog[open]" && el.tagName === "dialog" && el.open) || null; }
  getBoundingClientRect() { return this.rect; }
  focus() { this.doc.activeElement = this; }
  click() { this.emit("click"); }
  showModal() { this.open = true; }
  close() { this.open = false; this.emit("close"); }
  setPointerCapture(id) { this.capture = id; }
  hasPointerCapture(id) { return this.capture === id; }
  releasePointerCapture(id) { this.capture = null; this.emit("lostpointercapture", { pointerId: id }); }
}
const event = (extra = {}) => ({ preventDefault() {}, stopPropagation() {}, stopImmediatePropagation() {}, ...extra });

function harness({ fullscreen = "supported", savedHeight = null, storageDenied = false, inspector = false, savedWidth = null, savedCollapsed = null, width = 1280, translate } = {}) {
  const doc = new Target(); doc.ids = new Map(); doc.getElementById = (id) => doc.ids.get(id) || null;
  doc.createElement = (tag) => new Element(tag, doc); doc.documentElement = doc.createElement("html"); doc.body = doc.createElement("body"); doc.documentElement.appendChild(doc.body);
  const add = (parent, tag, id, className = "") => { const el = doc.createElement(tag); if (id) el.id = id; el.className = className; parent.appendChild(el); return el; };
  const panel = add(doc.body, "section", "advancedPanel");
  panel.rect.width = width;
  if (inspector) add(panel, "div", "studioInspector", "advanced-content");
  const header = add(panel, "header", "", "studio-header"); header.rect = { height: 44 };
  const actions = add(header, "div", "", "studio-header-actions");
  const dock = add(panel, "div", "studioPreviewDock");
  const preview = add(dock, "div", "previewColumn", "preview-column");
  const stage = add(preview, "div", "previewStage", "preview-stage");
  const a = add(stage, "video", "previewA"), b = add(stage, "video", "previewB"), caption = add(stage, "div", "previewCaption");
  a.play = b.play = () => assert.fail("Display controls must not start playback");
  a.pause = b.pause = () => assert.fail("Display controls must not pause playback");
  const controls = add(preview, "div", "", "preview-controls"); add(controls, "button", "playButton");
  const win = new Target(); win.innerHeight = 720; win.innerWidth = width;
  let redraws = 0, shortcuts = 0, requests = 0, exits = 0; const frames = new Map(); let id = 0;
  win.requestAnimationFrame = (fn) => { frames.set(++id, fn); return id; }; win.cancelAnimationFrame = (id) => frames.delete(id);
  const store = new Map([["cutroom-timeline-height-v3", savedHeight],["cutroom-inspector-width-v1",savedWidth],["cutroom-inspector-collapsed-v1",savedCollapsed]]);
  win.localStorage = { getItem: (k) => { if (storageDenied) throw Error("Denied"); return store.get(k) ?? null; },
    setItem: (k, v) => { if (storageDenied) throw Error("Denied"); store.set(k, v); }, removeItem: (k) => store.delete(k) };
  let observerCallback; win.MutationObserver = class { constructor(fn) { observerCallback = fn; } observe() {} disconnect() { observerCallback = null; } };
  let finishRequest;
  doc.documentElement.requestFullscreen = () => assert.fail("Never expand the editor document");
  if (fullscreen !== "unsupported") preview.requestFullscreen = async () => {
    requests++;
    if (fullscreen === "rejected") throw Error("Denied");
    if (fullscreen === "pending") await new Promise((resolve) => { finishRequest = resolve; });
    doc.fullscreenElement = preview; doc.emit("fullscreenchange");
  };
  doc.exitFullscreen = async () => { exits++; doc.fullscreenElement = null; doc.emit("fullscreenchange"); };
  const controller = context.initWorkspace({ document: doc, window: win, translate, onResize: () => redraws++, openShortcuts: () => shortcuts++ });
  return { doc, win, panel, actions, dock, preview, stage, a, b, caption, controls, controller, store, el: (id) => doc.getElementById(id),
    observe: () => observerCallback?.(), finishRequest: () => finishRequest?.(),
    flush: () => { for (const [id, fn] of frames) { frames.delete(id); fn(); } }, counts: () => ({ redraws, shortcuts, requests, exits }) };
}

test("only Help is added to the editor header; video fullscreen is attached to the preview", () => {
  const h = harness(); assert.equal(h.actions.children.length, 1); assert.equal(h.actions.children[0].id, "workspaceGuide");
  assert.equal(h.el("previewFullscreen").parentElement, h.preview);
  for (const id of ["workspaceInspector", "workspaceProportions", "workspaceFullscreen"]) assert.equal(h.el(id), null);
  assert.equal(context.initWorkspace({ document: h.doc, window: h.win }), h.controller);
  assert.equal(h.actions.children.length, 1);
  assert.equal(h.controller.setView, undefined);
  h.flush(); assert.equal(h.counts().redraws, 1);
});

test("native fullscreen targets the composite wrapper, preserving both sources, captions and controls", async () => {
  const h = harness(); await h.controller.toggleFullscreen();
  assert.equal(h.doc.fullscreenElement, h.preview);
  assert.equal(h.a.parentElement, h.stage); assert.equal(h.b.parentElement, h.stage); assert.equal(h.caption.parentElement, h.stage);
  assert.equal(h.controls.parentElement, h.preview); assert.equal(h.preview.parentElement, h.dock);
  assert.equal(h.el("previewFullscreen").getAttribute("aria-label"), "Exit video full screen");
  assert.equal(h.doc.activeElement.id, "playButton", "Space should control playback, not immediately exit fullscreen");
  await h.controller.toggleFullscreen(); assert.equal(h.doc.fullscreenElement, null);
  assert.equal(h.counts().exits, 1); assert.equal(h.preview.classList.contains("video-expanded"), false);
});

for (const fullscreen of ["unsupported", "rejected"]) test(`${fullscreen} fullscreen uses a video-only modal and restores the original DOM order`, async () => {
  const h = harness({ fullscreen }); const sibling = h.doc.createElement("span"); h.dock.appendChild(sibling);
  await h.controller.toggleFullscreen();
  assert.equal(h.preview.parentElement, h.el("videoFullscreenDialog"));
  assert.ok(h.el("videoFullscreenDialog").open); assert.ok(h.preview.classList.contains("video-expanded"));
  assert.equal(h.panel.parentElement, h.doc.body); assert.equal(h.counts().exits, 0);
  h.win.emit("keydown", event({ key: "Escape" })); await Promise.resolve();
  assert.equal(h.preview.parentElement, h.dock); assert.equal(h.preview.nextSibling, sibling);
  assert.equal(h.el("videoFullscreenDialog").open, false);
  assert.equal(h.preview.classList.contains("video-expanded"), false);
});

test("fallback close does not undo a concurrent application move back to the overview", async () => {
  const h = harness({ fullscreen: "rejected" }); await h.controller.toggleFullscreen();
  const overview = h.doc.createElement("div"); h.doc.body.appendChild(overview); overview.appendChild(h.preview);
  h.panel.hidden = true; h.observe(); await Promise.resolve();
  assert.equal(h.preview.parentElement, overview); assert.equal(h.el("videoFullscreenDialog").open, false);
});

test("Escape belongs to fullscreen only and regular editing keys are not intercepted", async () => {
  const h = harness();
  h.win.emit("keydown", event({ key: "Escape", preventDefault: () => assert.fail("ordinary editing owns Escape") }));
  await h.controller.toggleFullscreen();
  h.win.emit("keydown", event({ key: "s", preventDefault: () => assert.fail("not a display key") }));
  let stopped = false;
  h.win.emit("keydown", event({ key: "Escape", stopImmediatePropagation: () => { stopped = true; } }));
  assert.ok(stopped); assert.equal(h.counts().exits, 1);
});

test("native browser Escape updates the button and leaves the editor document unchanged", async () => {
  const h = harness(); await h.controller.toggleFullscreen();
  h.doc.fullscreenElement = null; h.doc.emit("fullscreenchange");
  assert.equal(h.preview.classList.contains("video-expanded"), false);
  assert.equal(h.el("previewFullscreen").getAttribute("aria-pressed"), "false");
  assert.equal(h.doc.body.classList.contains("workspace-expanded"), false);
});

test("late fullscreen permission cannot strand a closed editor", async () => {
  const h = harness({ fullscreen: "pending" }); const pending = h.controller.toggleFullscreen();
  h.panel.hidden = true; h.observe(); h.finishRequest(); await pending;
  assert.equal(h.doc.fullscreenElement, null); assert.equal(h.el("previewFullscreen").disabled, false);
  assert.equal(h.el("videoFullscreenDialog").open, false);
});

test("another element's fullscreen session is not taken over or exited", async () => {
  const h = harness(); const other = h.doc.createElement("div"); h.doc.fullscreenElement = other;
  await h.controller.toggleFullscreen(); assert.equal(h.doc.fullscreenElement, other);
  assert.equal(h.counts().requests, 0); assert.equal(h.counts().exits, 0);
});

test("divider resizing is bounded, keyboard accessible, persistent and resettable", () => {
  const h = harness(); const divider = h.el("workspaceDivider");
  assert.equal(divider.getAttribute("role"), "separator"); assert.equal(divider.getAttribute("aria-orientation"), "horizontal");
  assert.equal(divider.getAttribute("data-editor-shortcuts"), "off", "resize arrows must not seek the editing timeline");
  const initial = Number(divider.getAttribute("aria-valuenow"));
  divider.emit("keydown", event({ key: "ArrowUp" })); assert.equal(Number(divider.getAttribute("aria-valuenow")), initial + 24);
  divider.emit("keydown", event({ key: "End" })); assert.equal(Number(divider.getAttribute("aria-valuenow")), 348);
  assert.equal(h.controller.setTimelineHeight(9999), 348); assert.equal(h.controller.setTimelineHeight(-10), 184);
  divider.emit("dblclick"); assert.equal(Number(divider.getAttribute("aria-valuenow")), initial);
  assert.equal(h.store.has("cutroom-timeline-height-v4"), false);
});

test("divider drag updates live and cancellation restores previous preference", () => {
  const h = harness(); const d = h.el("workspaceDivider"); const initial = Number(d.getAttribute("aria-valuenow"));
  d.emit("pointerdown", event({ button: 0, pointerId: 4, clientY: 300 }));
  d.emit("pointermove", event({ pointerId: 4, clientY: 250 })); assert.equal(Number(d.getAttribute("aria-valuenow")), initial + 50);
  d.emit("pointercancel", event({ pointerId: 4 })); assert.equal(Number(d.getAttribute("aria-valuenow")), initial);
  d.emit("pointerdown", event({ button: 0, pointerId: 5, clientY: 300 }));
  d.emit("pointermove", event({ pointerId: 5, clientY: 270 })); d.emit("pointerup", event({ pointerId: 5 }));
  assert.equal(h.store.get("cutroom-timeline-height-v4"), String(initial + 30));
  assert.equal(h.panel.classList.contains("workspace-resizing"), false);
});

test("invalid display preferences or blocked storage do not break the editor", () => {
  const invalid = harness({ savedHeight: "NaN" }); assert.equal(invalid.el("workspaceDivider").getAttribute("aria-valuenow"), "256");
  const h = harness({ storageDenied: true }); assert.doesNotThrow(() => h.controller.setTimelineHeight(320));
  assert.equal(h.el("workspaceDivider").getAttribute("aria-valuenow"), "320");
});

test("guide explains clip tools and opens existing shortcut help", () => {
  const h = harness(); h.controller.openGuide(); const guide = h.el("workspaceGuideDialog");
  for (const text of ["Snap", "cyan guide", "Alt", "hours:minutes:seconds:frames"]) assert.ok(guide.textContent.includes(text), text);
  for (const text of ["Select", "Range", "Together", "Cut", "Layout", "divider", "both tracks", "Escape", "Original footage", "Restore to edit", "A only", "B only", "60 FPS", "Save", "Undo", "white edges", "Close gaps", "without overwriting"]) assert.ok(guide.textContent.includes(text), text);
  for (const obsolete of ["Hide inspector", "Preview focus", "Larger timeline", "whole editor", "Editing stays within A's original duration"]) assert.equal(guide.textContent.includes(obsolete), false);
  h.el("workspaceGuideShortcuts").click(); assert.equal(guide.open, false); assert.equal(h.counts().shortcuts, 1);
});

test("destroy exits our video, restores fallback media and removes all display controls", async () => {
  const h = harness({ fullscreen: "rejected" }); await h.controller.toggleFullscreen(); h.controller.destroy(); await Promise.resolve(); h.flush();
  assert.equal(h.preview.parentElement, h.dock); assert.equal(h.preview.classList.contains("video-expanded"), false);
  assert.equal(h.actions.children.length, 0); assert.equal(h.panel.workspaceController, undefined); assert.equal(h.counts().redraws, 0);
});

test("one accessible tool toggle and separator control the original inspector without restarting media", () => {
  const h = harness({inspector:true}), divider = h.el("workspaceInspectorDivider");
  assert.equal(h.actions.children.length, 2);
  assert.equal(divider.getAttribute("role"), "separator");
  assert.equal(divider.getAttribute("aria-orientation"), "vertical");
  assert.equal(divider.getAttribute("aria-controls"), "studioInspector studioPreviewDock");
  assert.equal(divider.getAttribute("data-editor-shortcuts"), "off");
  assert.equal(h.el("workspaceToolsToggle").getAttribute("aria-expanded"), "true");
  assert.equal(context.initWorkspace({document:h.doc,window:h.win}),h.controller);
  assert.equal(h.actions.children.length,2);
  assert.equal(h.a.parentElement,h.stage); assert.equal(h.preview.parentElement,h.dock);
});

test("inspector keyboard bounds preserve room for preview and restore a wider saved preference after resize", () => {
  const h = harness({inspector:true}), divider = h.el("workspaceInspectorDivider");
  assert.equal(h.controller.setInspectorWidth(9999),420);
  assert.equal(h.store.get("cutroom-inspector-width-v2"),"420");
  h.panel.rect.width=961; h.win.emit("resize"); h.flush();
  assert.equal(divider.getAttribute("aria-valuenow"),"326");
  assert.equal(h.store.get("cutroom-inspector-width-v2"),"420");
  h.panel.rect.width=1280; h.win.emit("resize"); h.flush();
  assert.equal(divider.getAttribute("aria-valuenow"),"420");
  divider.emit("keydown",event({key:"Home"})); assert.equal(divider.getAttribute("aria-valuenow"),"280");
  divider.emit("keydown",event({key:"ArrowLeft"})); assert.equal(divider.getAttribute("aria-valuenow"),"296");
  divider.emit("keydown",event({key:"End"})); assert.equal(divider.getAttribute("aria-valuenow"),"420");
});

test("inspector drag, RTL arrows, cancellation and double-click use display preferences only", () => {
  const h = harness({inspector:true}), d=h.el("workspaceInspectorDivider");
  d.emit("pointerdown",event({button:0,pointerId:4,clientX:400}));
  d.emit("pointermove",event({pointerId:5,clientX:470})); assert.equal(d.getAttribute("aria-valuenow"),"344");
  d.emit("pointermove",event({pointerId:4,clientX:352})); assert.equal(d.getAttribute("aria-valuenow"),"392");
  d.emit("pointerup",event({pointerId:4})); assert.equal(h.store.get("cutroom-inspector-width-v2"),"392");
  h.doc.documentElement.dir="rtl";
  d.emit("keydown",event({key:"ArrowLeft"})); assert.equal(d.getAttribute("aria-valuenow"),"376");
  d.emit("pointerdown",event({button:0,pointerId:6,clientX:400}));
  d.emit("pointermove",event({pointerId:6,clientX:430})); assert.equal(d.getAttribute("aria-valuenow"),"406");
  d.emit("keydown",event({key:"Escape"})); assert.equal(d.getAttribute("aria-valuenow"),"376");
  assert.equal(h.store.get("cutroom-inspector-width-v2"),"376");
  assert.equal(h.panel.classList.contains("inspector-resizing"),false);
  d.emit("dblclick"); assert.equal(d.getAttribute("aria-valuenow"),"344");
  assert.equal(h.store.has("cutroom-inspector-width-v2"),false);
  assert.equal(h.a.parentElement,h.stage); assert.equal(h.b.parentElement,h.stage);
});

test("collapsed inspector is inaccessible, focus stays reachable and selecting tools restores it", () => {
  const h=harness({inspector:true,savedWidth:"400",savedCollapsed:"true"}), inspector=h.el("studioInspector"),toggle=h.el("workspaceToolsToggle");
  assert.equal(h.panel.classList.contains("inspector-collapsed"),true);
  assert.equal(inspector.inert,true); assert.equal(toggle.textContent,"Show tools");
  h.controller.showInspector(); assert.equal(inspector.inert,false); assert.equal(inspector.getAttribute("aria-hidden"),"false");
  const control=h.doc.createElement("input"); inspector.append(control); control.focus();
  h.controller.setInspectorCollapsed(true);
  assert.equal(h.doc.activeElement,toggle); assert.equal(toggle.getAttribute("aria-expanded"),"false");
  assert.equal(h.store.get("cutroom-inspector-collapsed-v1"),"true");
  toggle.click(); assert.equal(inspector.inert,false); assert.equal(h.store.get("cutroom-inspector-collapsed-v1"),"false");
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"400");
});

test("tool labels and separator announcements refresh through the injected live dictionary", () => {
  let dictionary={inspectorHide:"Hide tools",inspectorShow:"Show tools"};
  const h=harness({inspector:true,translate:(key,fallback)=>dictionary[key]??fallback});
  dictionary={inspectorHide:"הסתרת כלים",inspectorShow:"הצגת כלים",inspectorResize:"שינוי רוחב חלונית הכלים",inspectorWidth:"רוחב: {width} פיקסלים"};
  h.doc.documentElement.lang="he";h.doc.documentElement.dir="rtl";h.observe();h.flush();
  assert.equal(h.el("workspaceToolsToggle").textContent,dictionary.inspectorHide);
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-label"),dictionary.inspectorResize);
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuetext"),"רוחב: 344 פיקסלים");
  h.controller.setInspectorCollapsed(true);assert.equal(h.el("workspaceToolsToggle").textContent,dictionary.inspectorShow);
});

test("tool display preferences tolerate invalid storage and cleanup restores accessibility", () => {
  const h=harness({inspector:true,savedWidth:"NaN",storageDenied:true});
  assert.doesNotThrow(()=>h.controller.setInspectorWidth(-10));
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"280");
  h.controller.setInspectorCollapsed(true); h.controller.destroy(); h.flush();
  assert.equal(h.el("studioInspector").inert,false);
  assert.equal(h.el("studioInspector").getAttribute("aria-hidden"),undefined);
  assert.equal(h.el("workspaceToolsToggle").parentElement,null);
  assert.equal(h.panel.classList.contains("inspector-collapsed"),false);
  assert.equal(h.panel.properties.has("--workspace-inspector-width"),false);
});

test("focused workspaces keep independent widths, retain edit preference and never move media", () => {
  const h = harness({inspector:true, savedWidth:"400"});
  h.controller.setWorkspace("audio");
  assert.equal(h.panel.dataset.workspace,"audio");
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"400");
  h.controller.setInspectorWidth(720);
  h.controller.setWorkspace("framing");
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"344");
  h.controller.setWorkspace("timeline");
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"400");
  h.controller.setWorkspace("audio");
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"420");
  h.panel.rect.width = 961; h.win.emit("resize"); h.flush();
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"326");
  h.panel.rect.width = 1280; h.win.emit("resize"); h.flush();
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"420");
  assert.equal(h.a.parentElement,h.stage); assert.equal(h.preview.parentElement,h.dock);
  h.controller.setWorkspace("invalid"); assert.equal(h.panel.dataset.workspace,"audio");
});

test("Edit effects preserves separate widths across tabs without moving or restarting video", () => {
  const h = harness({inspector:true,savedWidth:"400"});
  h.controller.setEditEffects(true);
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"344");
  h.controller.setInspectorWidth(510);
  h.controller.setWorkspace("framing");
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"344");
  h.controller.setWorkspace("timeline");
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"420");
  h.controller.setEditEffects(false);
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"400");
  assert.equal(h.a.parentElement,h.stage);
  assert.equal(h.preview.parentElement,h.dock);
});

test("oversized legacy display settings fall back without deleting old keys or changing media", () => {
  const h=harness({inspector:true,savedWidth:"860",savedHeight:"800"});
  assert.equal(h.el("workspaceInspectorDivider").getAttribute("aria-valuenow"),"344");
  assert.equal(h.el("workspaceDivider").getAttribute("aria-valuenow"),"256");
  assert.equal(h.store.get("cutroom-inspector-width-v1"),"860");
  assert.equal(h.store.get("cutroom-timeline-height-v3"),"800");
  assert.equal(h.a.parentElement,h.stage); assert.equal(h.b.parentElement,h.stage);
});
