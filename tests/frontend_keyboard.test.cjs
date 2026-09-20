const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const context = vm.createContext({});
const source = fs.readFileSync(path.join(__dirname, "../web/keyboard.js"), "utf8").replace(/^export /gm, "");
vm.runInContext(source + "\nglobalThis.api = { KEYBOARD_PROFILES, resolveEditorShortcut, shortcutRows };", context);
const { KEYBOARD_PROFILES, resolveEditorShortcut: resolve, shortcutRows } = context.api;
const event = (key, options = {}) => ({ key, code: "", shiftKey: false, altKey: false, ctrlKey: false, metaKey: false, repeat: false, ...options });

test("every profile exposes every supported action with readable nonempty help", () => {
  assert.deepEqual(Array.from(KEYBOARD_PROFILES, (profile) => profile.id), ["cutroom", "resolve", "premiere", "protools", "finalcut"]);
  for (const { id } of KEYBOARD_PROFILES) {
    const rows = shortcutRows(id);
    assert.equal(rows.length, 28);
    assert.equal(new Set(rows.map((row) => row.action)).size, 28);
    assert.ok(rows.every((row) => row.keys && row.label && typeof row.custom === "boolean" && typeof row.bound === "boolean"));
    assert.ok(rows.every((row) => Array.isArray(row.bindings) && row.bindings.every((binding) => typeof binding.keys === "string" && typeof binding.custom === "boolean" && typeof binding.note === "string")));
    assert.ok(rows.filter((row) => !row.bound).every((row) => row.keys === "Not assigned" && !row.custom && row.bindings.length === 0));
  }
});

test("each profile routes split to its actual CUTROOM action, without leaking other keymaps", () => {
  assert.equal(resolve(event("s")), "split");
  assert.equal(resolve(event("b", { ctrlKey: true }), "resolve"), "split");
  assert.equal(resolve(event("k", { ctrlKey: true }), "premiere"), "split");
  assert.equal(resolve(event("b", { ctrlKey: true }), "premiere"), null);
  assert.equal(resolve(event("s"), "premiere"), "toggle_snapping");
  assert.equal(resolve(event("k", { ctrlKey: true }), "resolve"), null);
  assert.equal(resolve(event("b"), "protools"), "split");
  assert.equal(resolve(event("b", { metaKey: true }), "finalcut"), "split");
  assert.equal(resolve(event("b", { ctrlKey: true }), "protools"), null);
});

test("NLE navigation stays familiar without inventing reverse or accelerated shuttle", () => {
  const common = { " ": "toggle_play", k: "stop", i: "mark_in", o: "mark_out", x: "select_clip",
    Escape: "clear_selection", ArrowLeft: "frame_back", ArrowRight: "frame_forward",
    ArrowUp: "previous_edit", ArrowDown: "next_edit", "=": "zoom_in", "-": "zoom_out" };
  for (const id of ["cutroom", "resolve", "premiere", "finalcut"]) {
    for (const [key, action] of Object.entries(common)) {
      if (id === "finalcut" && ["=", "-"].includes(key)) continue;
      assert.equal(resolve(event(key), id), action);
    }
    assert.equal(resolve(event("l"), id), "play_forward");
    assert.equal(resolve(event("j"), id), null);
    assert.equal(resolve(event("L", { shiftKey: true }), id), null);
    assert.equal(resolve(event("Home"), id), "jump_start");
    assert.equal(resolve(event("End"), id), "jump_end");
  }
  assert.equal(resolve(event("R", { shiftKey: true })), "restore_selection");
  for (const id of ["resolve", "premiere", "protools", "finalcut"])
    assert.equal(resolve(event("R", { shiftKey: true }), id), null, "Do not replace native reverse-match-frame etc.");
  assert.equal(resolve(event("="), "finalcut"), null, "Final Cut's timecode entry is not zoom");
  assert.equal(resolve(event("-"), "finalcut"), null);
});

test("tool shortcuts remain profile-specific and CUTROOM's two-click cut is never substituted for a native tool", () => {
  for (const [id, select, blade] of [["cutroom", "v", "b"], ["resolve", "a", "b"], ["premiere", "v", "c"], ["finalcut", "a", "b"]]) {
    assert.equal(resolve(event(select), id), "tool_select");
    assert.equal(resolve(event(blade), id), "tool_blade");
  }
  assert.equal(resolve(event("r")), "tool_range");
  assert.equal(resolve(event("r"), "finalcut"), "tool_range");
  assert.equal(resolve(event("r"), "premiere"), null);
  assert.equal(resolve(event("d")), "tool_remove_between");
  for (const id of ["resolve", "premiere", "protools", "finalcut"]) {
    assert.equal(resolve(event("d"), id), null);
    assert.equal(resolve(event("B", { shiftKey: true }), id), null);
    assert.equal(shortcutRows(id).find((row) => row.action === "tool_remove_between").keys, "Not assigned");
  }
});

test("Pro Tools Commands Focus uses separate meanings instead of leaking NLE I O K X and arrows", () => {
  const native = { b: "split", a: "trim_start", s: "trim_end", r: "zoom_out", t: "zoom_in", l: "previous_edit", "'": "next_edit", z: "undo", Enter: "jump_start" };
  for (const [key, action] of Object.entries(native)) assert.equal(resolve(event(key), "protools"), action);
  assert.equal(resolve(event("Z", { shiftKey: true }), "protools"), "redo");
  assert.equal(resolve(event("Enter", { ctrlKey: true }), "protools"), "jump_end");
  assert.equal(resolve(event("Enter", { metaKey: true }), "protools"), null);
  for (const key of ["i", "o", "j", "k", "x", "v", "f", "q", "w", "n", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "=", "-", "Home", "End"])
    assert.equal(resolve(event(key), "protools"), null, key);
  assert.equal(resolve(event(","), "protools"), "frame_back");
  assert.equal(resolve(event("."), "protools"), "frame_forward");
  for (const action of ["trim_start", "trim_end", "frame_back", "frame_forward", "delete_selection"])
    assert.equal(shortcutRows("protools").find((row) => row.action === action).custom, true, action);
});

test("Premiere ripple trims do not leak onto other applications' unrelated native tools", () => {
  for (const id of ["cutroom", "premiere"]) {
    assert.equal(resolve(event("q"), id), "trim_start");
    assert.equal(resolve(event("w"), id), "trim_end");
  }
  for (const id of ["resolve", "finalcut"])
    for (const key of ["q", "w"]) assert.equal(resolve(event(key), id), null);
});

test("snapping follows the selected profile without borrowing Pro Tools N", () => {
  for (const [profile, key] of [["cutroom", "n"], ["resolve", "n"], ["premiere", "s"], ["finalcut", "n"]]) {
    assert.equal(resolve(event(key), profile), "toggle_snapping");
    assert.equal(resolve(event(key, {repeat: true}), profile), null);
    for (const modifier of ["ctrlKey", "metaKey", "altKey", "shiftKey"])
      assert.equal(resolve(event(key, {[modifier]: true}), profile), null);
  }
  assert.equal(resolve(event("n"), "protools"), null);
  assert.equal(resolve(event("n"), "premiere"), null);
  assert.equal(resolve(event("ד", {code: "KeyS"}), "premiere"), "toggle_snapping");
});

test("Premiere Extract removes a marked range and does not replace another profile's navigation", () => {
  assert.equal(resolve(event("'"), "premiere"), "delete_selection");
  assert.equal(resolve(event("'", {repeat: true}), "premiere"), null);
  for (const modifier of ["ctrlKey", "metaKey", "altKey", "shiftKey"])
    assert.equal(resolve(event("'", {[modifier]: true}), "premiere"), null);
  assert.equal(resolve(event("'"), "protools"), "next_edit");
  assert.equal(resolve(event("'"), "finalcut"), "next_edit");
  assert.equal(resolve(event("'"), "resolve"), null);
  const extract = shortcutRows("premiere").find(row => row.action === "delete_selection").bindings.find(binding => binding.keys === "'");
  assert.equal(extract.custom, false);
  assert.match(extract.note, /Together.*source-only.*gap/);
});

function editorCanvas(ancestor = null) {
  return {tagName: "CANVAS", dataset: {editorShortcuts: "on"},
    closest: selector => ancestor && selector.split(",").includes(ancestor) ? {} : null};
}

test("Pro Tools F7 and F8 select adapted tools only on the opted-in timeline canvas", () => {
  const target = editorCanvas();
  for (const [key, action] of [["F7", "tool_range"], ["F8", "tool_select"]]) {
    assert.equal(resolve(event(key, {target}), "protools"), action, "event.key works without event.code");
    assert.equal(resolve(event("", {code: key, target}), "protools"), action);
    assert.equal(resolve(event(key), "protools"), null);
    for (const otherTarget of [chromeButton(), {tagName: "DIV", dataset: {editorShortcuts: "on"}}, {tagName: "CANVAS", dataset: {editorShortcuts: "off"}}])
      assert.equal(resolve(event(key, {target: otherTarget}), "protools"), null);
    for (const profile of ["cutroom", "resolve", "premiere", "finalcut"])
      assert.equal(resolve(event(key, {target}), profile), null);
    for (const field of ["ctrlKey", "metaKey", "altKey", "shiftKey", "repeat", "isComposing", "defaultPrevented"])
      assert.equal(resolve(event(key, {target, [field]: true}), "protools"), null);
    assert.equal(resolve(event(key, {target, getModifierState: name => name === "AltGraph"}), "protools"), null);
    assert.equal(resolve(event(key, {target, keyCode: 229}), "protools"), null);
    for (const ancestor of ["dialog", "input", "textarea", "select", "[data-editor-shortcuts='off']"])
      assert.equal(resolve(event(key, {target: editorCanvas(ancestor)}), "protools"), null);
    assert.equal(resolve(event(key, {target, composedPath: () => [{isContentEditable: true}]}), "protools"), null);
    const protectedFocus = editorCanvas(); protectedFocus.ownerDocument = {activeElement: {isContentEditable: true}};
    assert.equal(resolve(event(key, {target: protectedFocus}), "protools"), null);
  }
});

test("profile-specific remove, clear and fit keys preserve their documented scope", () => {
  assert.equal(resolve(event("Delete")), "delete_selection");
  assert.equal(resolve(event("Backspace")), "delete_selection");
  assert.equal(resolve(event("Delete"), "resolve"), "delete_selection");
  assert.equal(resolve(event("Delete"), "premiere"), null);
  assert.equal(resolve(event("Delete", { shiftKey: true }), "premiere"), "delete_selection");
  assert.equal(resolve(event("x", { ctrlKey: true, shiftKey: true }), "premiere"), "clear_selection");
  assert.equal(resolve(event("f")), "fit");
  assert.equal(resolve(event("z", { shiftKey: true }), "resolve"), "fit");
  assert.equal(resolve(event("\\"), "premiere"), "fit");
  assert.equal(resolve(event("z", { shiftKey: true }), "finalcut"), "fit");
  assert.equal(resolve(event("x", { metaKey: true, shiftKey: true }), "premiere"), null, "Mac shortcut means something else");
  assert.equal(resolve(event(";"), "finalcut"), "previous_edit");
  assert.equal(resolve(event("'"), "finalcut"), "next_edit");
});

test("command keys work on Mac as well, with exact modifiers rather than permissive matches", () => {
  for (const { id } of KEYBOARD_PROFILES) {
    for (const modifier of ["ctrlKey", "metaKey"]) {
      assert.equal(resolve(event("z", { [modifier]: true }), id), "undo");
      assert.equal(resolve(event("z", { [modifier]: true, shiftKey: true }), id), "redo");
    }
  }
  assert.equal(resolve(event("b", { metaKey: true }), "resolve"), "split");
  assert.equal(resolve(event("k", { metaKey: true }), "premiere"), "split");
  assert.equal(resolve(event("z", { metaKey: true, ctrlKey: true })), null);
  assert.equal(resolve(event("b", { ctrlKey: true, shiftKey: true }), "resolve"), null);
});

test("non-Latin hardware layout falls back to code; Latin remaps and caps lock remain usable", () => {
  assert.equal(resolve(event("ד", { code: "KeyS" })), "split");
  assert.equal(resolve(event("נ", { code: "KeyB", ctrlKey: true }), "resolve"), "split");
  assert.equal(resolve(event("ן", { code: "KeyI" })), "mark_in");
  assert.equal(resolve(event("s", { code: "KeyQ" })), "split");
  assert.equal(resolve(event("S", { code: "KeyS" })), "split");
  assert.equal(resolve(event("S", { code: "KeyS", shiftKey: true })), null);
  assert.equal(resolve(event("", { code: "ArrowRight" })), "frame_forward");
  assert.equal(resolve(event("נ", { code: "KeyB" }), "protools"), "split");
  assert.equal(resolve(event("ש", { code: "KeyA" }), "protools"), "trim_start");
  assert.equal(resolve(event("ד", { code: "KeyS" }), "protools"), "trim_end");
  assert.equal(resolve(event("ך", { code: "KeyL" }), "protools"), "previous_edit");
  assert.equal(resolve(event("ת", { code: "Comma" }), "protools"), "frame_back");
  assert.equal(resolve(event("ר", { code: "KeyR" }), "finalcut"), "tool_range");
  assert.equal(resolve(event("ג", { code: "KeyD" })), "tool_remove_between");
});

test("browser shortcuts, Alt and IME keystrokes are never intercepted", () => {
  for (const { id } of KEYBOARD_PROFILES) {
    for (const key of ["r", "R", "e", "f", "w", "t", "n", "l", "s", "c", "x", "v", "+", "=", "-", "0", "ArrowLeft"])
      assert.equal(resolve(event(key, { ctrlKey: true }), id), null, `${id}: Ctrl+${key}`);
    for (const key of ["Tab", "F1", "F5", "F6", "F7", "F8", "F11", "F12"])
      assert.equal(resolve(event(key, { code: key }), id), null);
    assert.equal(resolve(event("i", { altKey: true }), id), null);
    assert.equal(resolve(event("s", { isComposing: true }), id), null);
    assert.equal(resolve(event("s", { keyCode: 229 }), id), null);
    assert.equal(resolve(event("s", { defaultPrevented: true }), id), null);
    assert.equal(resolve(event("s", { getModifierState: (name) => name === "AltGraph" }), id), null);
    for (const key of ["Dead", "Process", "Unidentified"])
      assert.equal(resolve(event(key, { code: "KeyB" }), id), null);
  }
});

test("typing, native controls, editable ancestors and dialogs keep their own keyboard events", () => {
  for (const selector of ["input", "textarea", "select", "button", "a[href]", "summary", "dialog", "[role='dialog']", "[role='textbox']", "[role='tab']", "[role='checkbox']", "[role='radio']", "[role='switch']", "[role='treeitem']", "video[controls]", "audio[controls]", "[role='slider']:not(canvas[data-editor-shortcuts='on'])", "[contenteditable]:not([contenteditable='false'])"]) {
    const target = { closest: (actual) => actual.split(",").includes(selector) ? {} : null };
    for (const key of [" ", "i", "Delete", "ArrowLeft", "z"])
      assert.equal(resolve(event(key, { target, ctrlKey: key === "z" })), null, selector);
  }
  assert.equal(resolve(event("Delete", { target: { isContentEditable: true } })), null);
  assert.equal(resolve(event("Delete", { target: { nodeType: 3, parentElement: { isContentEditable: true } } })), null);
  assert.equal(resolve(event("Delete", { composedPath: () => [{ isContentEditable: true }] })), null);
  assert.equal(resolve(event("Delete", { target: { ownerDocument: { activeElement: { isContentEditable: true } } } })), null);
});

test("only an explicitly opted-in canvas slider accepts editor keys; ancestors still protect it", () => {
  function slider(tagName, enabled, parent = null) {
    const node = { tagName, parentElement: parent };
    node.closest = (selector) => {
      const clauses = selector.split(",");
      const isExcluded = clauses.includes("[role='slider']:not(canvas[data-editor-shortcuts='on'])")
        && !(tagName === "CANVAS" && enabled);
      return isExcluded ? node : parent?.closest?.(selector) || null;
    };
    return node;
  }
  const canvas = slider("CANVAS", true);
  for (const [key, action] of [["i", "mark_in"], ["s", "split"], ["ArrowLeft", "frame_back"], ["Delete", "delete_selection"]]) {
    assert.equal(resolve(event(key, { target: canvas, composedPath: () => [canvas] })), action);
    for (const target of [slider("DIV", true), slider("DIV", false), slider("CANVAS", false)])
      assert.equal(resolve(event(key, { target })), null);
  }
  const ancestorSlider = slider("DIV", false);
  const nestedCanvas = slider("CANVAS", true, ancestorSlider);
  assert.equal(resolve(event("s", { target: nestedCanvas, composedPath: () => [nestedCanvas, ancestorSlider] })), null);
  const dialog = { closest: (selector) => selector.split(",").includes("dialog") ? dialog : null };
  assert.equal(resolve(event("s", { target: slider("CANVAS", true, dialog) })), null);
});

test("holding a destructive or playback key never repeats edits or toggles", () => {
  for (const { id } of KEYBOARD_PROFILES) {
    for (const key of [" ", "k", "i", "o", "x", "Escape", "Delete"])
      assert.equal(resolve(event(key, { repeat: true }), id), null);
    assert.equal(resolve(event("z", { ctrlKey: true, repeat: true }), id), null);
    assert.equal(resolve(event("r", { shiftKey: true, repeat: true }), id), null);
    if (id !== "protools") assert.equal(resolve(event("ArrowRight", { repeat: true }), id), "frame_forward");
    if (!["protools", "finalcut"].includes(id)) assert.equal(resolve(event("=", { repeat: true }), id), "zoom_in");
    for (const key of ["a", "b", "s", "q", "w", "d", "Enter", "Home", "End"])
      assert.equal(resolve(event(key, { repeat: true }), id), null);
  }
  assert.equal(resolve(event("t", { repeat: true }), "protools"), "zoom_in");
  assert.equal(resolve(event("r", { repeat: true }), "protools"), "zoom_out");
  assert.equal(resolve(event(",", { repeat: true }), "protools"), "frame_back");
  assert.equal(resolve(event("b", { ctrlKey: true, repeat: true }), "resolve"), null);
  assert.equal(resolve(event("k", { ctrlKey: true, repeat: true }), "premiere"), null);
});

function chromeButton(scope = '.studio-timeline-dock', ancestor = null, role = null) {
  const button = { tagName: 'BUTTON' };
  button.closest = selector => {
    const clauses = selector.split(',');
    if (ancestor && clauses.includes(ancestor)) return {};
    if (clauses.includes('button') || (role && clauses.includes(`[role='${role}']`))) return button;
    if (scope && clauses.includes(scope)) return {};
    return null;
  };
  return button;
}

test('Space is transport on editor toolbar buttons and custom toggles, not a native click', () => {
  for (const scope of ['.studio-timeline-dock','.studio-header','.advanced-tabs','.preview-controls','.preview-stage']) {
    for (const {id} of KEYBOARD_PROFILES) {
      const target = chromeButton(scope);
      assert.equal(resolve(event(' ', {target}),id), 'toggle_play');
      assert.equal(resolve(event(' ', {target,repeat:true}),id), null);
      assert.equal(resolve(event('s', {target}),id), null, 'editing bindings do not leak into controls');
      assert.equal(resolve(event('Enter', {target}),id), null, 'Enter still activates the focused button');
    }
  }
  for (const role of ['checkbox','radio','switch','tab']) {
    const target = chromeButton('.studio-timeline-dock',null,role);
    assert.equal(resolve(event(' ', {target})), 'toggle_play');
  }
  assert.equal(resolve(event(' ', {target:chromeButton(null)})), null, 'buttons elsewhere retain native Space');
});

test('transport exceptions never override native fields, dialog/menu content, opt-out or modifiers', () => {
  for (const ancestor of ['input','textarea','select','dialog',"[role='dialog']","[aria-modal='true']","[popover]","[role='menu']","[role='listbox']","[data-editor-shortcuts='off']","[contenteditable]:not([contenteditable='false'])"]) {
    assert.equal(resolve(event(' ', {target:chromeButton('.studio-timeline-dock',ancestor)})), null, ancestor);
  }
  const target = chromeButton();
  for (const field of ['ctrlKey','metaKey','altKey','shiftKey','isComposing']) assert.equal(resolve(event(' ', {target,[field]:true})), null);
  const field = {isContentEditable:true};
  assert.equal(resolve(event(' ', {target,composedPath:()=>[target,field]})), null);
  target.ownerDocument = {activeElement:field};
  assert.equal(resolve(event(' ', {target})), null);
});

test("invalid stored profiles safely fall back and UI cannot mutate future shortcut rows", () => {
  for (const id of ["missing", "__proto__", "constructor", null, undefined]) {
    assert.equal(resolve(event("s"), id), "split");
    assert.equal(shortcutRows(id).find((row) => row.action === "split").keys, "S");
  }
  const rows = shortcutRows("premiere");
  rows[0].keys = "changed";
  rows[0].bindings[0].keys = "changed";
  assert.equal(shortcutRows("premiere")[0].keys, "Space");
  assert.equal(shortcutRows("premiere")[0].bindings[0].keys, "Space");
  assert.equal(shortcutRows("resolve").find((row) => row.action === "zoom_in").custom, true);
  assert.equal(shortcutRows("premiere").find((row) => row.action === "restore_selection").bound, false);
  assert.ok(shortcutRows("cutroom").every((row) => !row.custom));
});

test("help distinguishes individual adaptations and deduplicates displayed aliases", () => {
  const removal = shortcutRows("resolve").find(row => row.action === "delete_selection");
  assert.equal(removal.custom, true, "The compatibility flag still summarizes the row");
  assert.equal(removal.bindings.find(binding => binding.keys === "Delete").custom, true);
  assert.equal(removal.bindings.find(binding => binding.keys === "Shift+Delete").custom, false);
  assert.equal(removal.bindings.find(binding => binding.keys === "Shift+Backspace").custom, false);
  assert.equal(shortcutRows("resolve").find(row => row.action === "zoom_in").bindings.length, 1);
  assert.equal(shortcutRows("protools").find(row => row.action === "delete_selection").bindings.length, 1);
  for (const action of ["trim_start", "trim_end", "frame_back", "frame_forward", "tool_select", "tool_range"]) {
    const binding = shortcutRows("protools").find(row => row.action === action).bindings[0];
    assert.equal(binding.custom, true);
    assert.ok(binding.note.length > 0);
  }
  assert.equal(shortcutRows("finalcut").find(row => row.action === "delete_selection").bindings.find(binding => binding.keys === "Forward Delete").custom, true);
  assert.equal(shortcutRows().find(row => row.action === "restore_selection").label, "Review / restore original footage");
  for (const profile of KEYBOARD_PROFILES.filter(profile => profile.id !== "cutroom")) assert.ok(profile.limitations);
  assert.match(KEYBOARD_PROFILES.find(profile => profile.id === "protools").limitations, /F7\/F8.*timeline.*Tab/);
});

test("every advertised bound action is reachable in its supported focus scope", () => {
  const possible = [..."abcdefghijklmnopqrstuvwxyz", " ", "Escape", "Delete", "Backspace", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "Enter", "F7", "F8", "=", "+", "-", "\\", "'", ";", ",", "."];
  for (const { id } of KEYBOARD_PROFILES) {
    const observed = new Set();
    for (const key of possible) for (const shiftKey of [false, true]) for (const mod of [null, "ctrlKey", "metaKey"]) {
      const action = resolve(event(key, { target: editorCanvas(), shiftKey, ...(mod ? { [mod]: true } : {}) }), id);
      if (action) observed.add(action);
    }
    const advertised = shortcutRows(id).filter((row) => row.bound).map((row) => row.action);
    assert.deepEqual([...observed].sort(), Array.from(advertised).sort(), id);
  }
});
