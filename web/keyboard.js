// Small, explicit editing keymaps, not a full emulation of another NLE.
// The caller owns workspace/busy-state checks and calls preventDefault only
// after it accepts an action. Nothing here changes media or document state.
export const KEYBOARD_PROFILES = Object.freeze([
  Object.freeze({ id: "cutroom", label: "CUTROOM", description: "Fast editing keys. D selects Cut out; click twice to remove the section." }),
  Object.freeze({ id: "resolve", label: "DaVinci Resolve", description: "Core Edit-page keys: A selects, B blades, Ctrl/Cmd+B splits. Not a full Resolve emulation." }),
  Object.freeze({ id: "premiere", label: "Adobe Premiere Pro", description: "Core editing keys: V selects, C razors, Q/W ripple-trim. Not a full Premiere emulation." }),
  Object.freeze({ id: "protools", label: "Pro Tools", description: "Commands Keyboard Focus: B separates, A/S trim, R/T zoom, L / ' navigate edits. Trims close gaps in CUTROOM." }),
  Object.freeze({ id: "finalcut", label: "Final Cut Pro", description: "Core timeline keys: A selects, B blades, R selects a range. Command shortcuts also accept Ctrl on Windows." }),
]);

const ACTION_LABELS = {
  toggle_play: "Play / pause", stop: "Stop playback", mark_in: "Mark selection in",
  mark_out: "Mark selection out", select_clip: "Mark clip at playhead",
  clear_selection: "Clear selection", split: "Split at playhead",
  delete_selection: "Remove selection from edit", restore_selection: "Restore selection to edit",
  undo: "Undo edit", redo: "Redo edit", frame_back: "Previous frame",
  frame_forward: "Next frame", previous_edit: "Previous edit point",
  next_edit: "Next edit point", zoom_in: "Zoom timeline in",
  zoom_out: "Zoom timeline out", fit: "Fit timeline",
  tool_select: "Select tool", tool_range: "Range tool", tool_blade: "Blade tool",
  tool_remove_between: "Cut out tool (two clicks)", play_forward: "Play forward at 1×",
  trim_start: "Remove clip start up to playhead", trim_end: "Remove playhead to clip end",
  jump_start: "Go to timeline start", jump_end: "Go to timeline end",
};

const key = (action, code, keys, options = {}) => ({ action, code, keys, mod: false, shift: false, custom: false, ...options });
// Share only semantics that really agree. In Pro Tools Commands Keyboard Focus,
// K snaps a clip, I/O manage timeline selection and X cuts to the clipboard.
// Importing an NLE's common keys there would silently perform the wrong edits.
const COMMON = [
  key("toggle_play", "Space", "Space"),
  key("clear_selection", "Escape", "Esc", { custom: true }),
  key("undo", "KeyZ", "Ctrl/Cmd+Z", { mod: true }),
  key("redo", "KeyZ", "Ctrl/Cmd+Shift+Z", { mod: true, shift: true }),
];
const NLE_NAVIGATION = [
  key("stop", "KeyK", "K"), key("play_forward", "KeyL", "L", { custom: true }),
  key("mark_in", "KeyI", "I"), key("mark_out", "KeyO", "O"),
  key("select_clip", "KeyX", "X"),
  key("frame_back", "ArrowLeft", "Left"), key("frame_forward", "ArrowRight", "Right"),
  key("previous_edit", "ArrowUp", "Up"), key("next_edit", "ArrowDown", "Down"),
  key("jump_start", "Home", "Home"), key("jump_end", "End", "End"),
];
const PLAIN_ZOOM = [
  key("zoom_in", "Equal", "= / +"), key("zoom_in", "Equal", "= / +", { shift: true }),
  key("zoom_out", "Minus", "−"),
];
const PROFILE_KEYS = {
  cutroom: [
    ...NLE_NAVIGATION, ...PLAIN_ZOOM,
    key("split", "KeyS", "S"), key("delete_selection", "Delete", "Delete / Backspace"),
    key("delete_selection", "Backspace", "Delete / Backspace"), key("fit", "KeyF", "F"),
    key("redo", "KeyY", "Ctrl/Cmd+Y", { mod: true }),
    key("restore_selection", "KeyR", "Shift+R", { shift: true }),
    key("tool_select", "KeyV", "V"), key("tool_range", "KeyR", "R"),
    key("tool_blade", "KeyB", "B"), key("tool_remove_between", "KeyD", "D"),
    key("trim_start", "KeyQ", "Q"), key("trim_end", "KeyW", "W"),
  ],
  resolve: [
    ...NLE_NAVIGATION, ...PLAIN_ZOOM.map((binding) => ({ ...binding, custom: true })),
    key("tool_select", "KeyA", "A"), key("tool_blade", "KeyB", "B"),
    key("split", "KeyB", "Ctrl/Cmd+B", { mod: true }),
    key("delete_selection", "Delete", "Delete", { custom: true }),
    key("delete_selection", "Delete", "Shift+Delete", { shift: true }),
    key("delete_selection", "Backspace", "Shift+Backspace", { shift: true }),
    key("fit", "KeyZ", "Shift+Z", { shift: true }),
  ],
  premiere: [
    ...NLE_NAVIGATION, ...PLAIN_ZOOM,
    key("tool_select", "KeyV", "V"), key("tool_blade", "KeyC", "C"),
    key("split", "KeyK", "Ctrl/Cmd+K", { mod: true }),
    key("delete_selection", "Delete", "Shift+Delete", { shift: true }),
    key("clear_selection", "KeyX", "Ctrl+Shift+X", { mod: true, modifier: "ctrl", shift: true }),
    key("fit", "Backslash", "\\"),
    key("trim_start", "KeyQ", "Q"), key("trim_end", "KeyW", "W"),
  ],
  protools: [
    key("split", "KeyB", "B"),
    key("trim_start", "KeyA", "A", { custom: true }), key("trim_end", "KeyS", "S", { custom: true }),
    key("zoom_out", "KeyR", "R"), key("zoom_in", "KeyT", "T"),
    key("previous_edit", "KeyL", "L"), key("next_edit", "Quote", "'"),
    key("undo", "KeyZ", "Z"), key("redo", "KeyZ", "Shift+Z", { shift: true }),
    key("frame_back", "Comma", ",", { custom: true }), key("frame_forward", "Period", ".", { custom: true }),
    key("jump_start", "Enter", "Enter / Return"),
    key("jump_end", "Enter", "Ctrl+Enter", { mod: true, modifier: "ctrl" }),
    key("delete_selection", "Delete", "Delete / Backspace", { custom: true }),
    key("delete_selection", "Backspace", "Delete / Backspace", { custom: true }),
  ],
  finalcut: [
    ...NLE_NAVIGATION,
    key("tool_select", "KeyA", "A"), key("tool_blade", "KeyB", "B"), key("tool_range", "KeyR", "R"),
    key("split", "KeyB", "Ctrl/Cmd+B", { mod: true }),
    key("delete_selection", "Backspace", "Delete (Mac) / Backspace"),
    key("delete_selection", "Delete", "Forward Delete", { custom: true }),
    key("previous_edit", "Semicolon", ";"), key("next_edit", "Quote", "'"),
    key("fit", "KeyZ", "Shift+Z", { shift: true }),
  ],
};
const REPEATABLE = new Set(["frame_back", "frame_forward", "previous_edit", "next_edit", "zoom_in", "zoom_out"]);
const KEY_CODES = {
  " ": "Space", Spacebar: "Space", Escape: "Escape", Esc: "Escape", Delete: "Delete", Del: "Delete",
  Backspace: "Backspace", ArrowLeft: "ArrowLeft", Left: "ArrowLeft", ArrowRight: "ArrowRight", Right: "ArrowRight",
  ArrowUp: "ArrowUp", Up: "ArrowUp", ArrowDown: "ArrowDown", Down: "ArrowDown",
  Home: "Home", End: "End", Enter: "Enter", Return: "Enter",
  "'": "Quote", "\"": "Quote", ";": "Semicolon", ":": "Semicolon", ",": "Comma", "<": "Comma", ".": "Period", ">": "Period",
  "=": "Equal", "+": "Equal", "-": "Minus", "_": "Minus", "\\": "Backslash", "|": "Backslash",
};
const PROTECTED_SELECTOR = [
  "input", "textarea", "select", "button", "a[href]", "summary", "dialog", "[role='dialog']",
  "[aria-modal='true']", "[role='textbox']", "[role='combobox']", "[role='listbox']", "[role='option']",
  "[role='slider']:not(canvas[data-editor-shortcuts='on'])", "[role='spinbutton']", "[role='button']", "[role='tab']", "[role='menuitem']",
  "[role='checkbox']", "[role='radio']", "[role='switch']", "[role='menu']", "[role='tree']", "[role='treeitem']",
  "video[controls]", "audio[controls]",
  "[contenteditable]:not([contenteditable='false'])", "[data-editor-shortcuts='off']",
].join(",");
const TRANSPORT_BUTTON_SELECTOR = "button,[role='button'],[role='tab'],[role='checkbox'],[role='radio'],[role='switch']";
const TRANSPORT_SCOPE_SELECTOR = ".studio-timeline-dock,.studio-header,.advanced-tabs,.preview-controls,.preview-stage,[data-editor-transport='on']";
const TRANSPORT_PROTECTED_SELECTOR = [
  "input", "textarea", "select", "a[href]", "summary", "dialog", "[role='dialog']", "[aria-modal='true']",
  "[role='textbox']", "[role='combobox']", "[role='listbox']", "[role='option']", "[role='menu']", "[role='menuitem']",
  "[role='slider']:not(canvas[data-editor-shortcuts='on'])", "[role='spinbutton']", "[role='tree']", "[role='treeitem']",
  "[popover]", "video[controls]", "audio[controls]", "[contenteditable]:not([contenteditable='false'])", "[data-editor-shortcuts='off']",
].join(",");

function profileId(profile) {
  return KEYBOARD_PROFILES.some((item) => item.id === profile) ? profile : "cutroom";
}

function bindings(profile) {
  const id = profileId(profile);
  return [...COMMON, ...PROFILE_KEYS[id]];
}

function protectsKeyboard(node) {
  const element = node?.nodeType === 3 ? node.parentElement : node;
  return !!(element?.isContentEditable || element?.closest?.(PROTECTED_SELECTOR));
}

function eventCode(event) {
  const value = event.key || "";
  // Honor a user's Latin layout (e.g. AZERTY); use the physical key when the
  // active layout emits Hebrew/other non-Latin text. IME events are excluded.
  if (/^[a-z]$/i.test(value)) return `Key${value.toUpperCase()}`;
  if (Object.hasOwn(KEY_CODES, value)) return KEY_CODES[value];
  return event.code || "";
}

/** Space is transport in editor chrome, not a second click on its last button.
 * Other keys retain native button behavior; text controls and popups opt out.
 * The caller handles hold/release so repeated Space never activates a button.
 */
export function isEditorTransportSpace(event, { keyup = false } = {}) {
  if (!event || eventCode(event) !== "Space" || event.isComposing || event.keyCode === 229) return false;
  if (!keyup && (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || event.getModifierState?.("AltGraph"))) return false;
  const path = typeof event.composedPath === "function" ? event.composedPath() : [];
  for (const raw of [event.target, event.target?.ownerDocument?.activeElement, ...path]) {
    const node = raw?.nodeType === 3 ? raw.parentElement : raw;
    if (node?.isContentEditable || node?.closest?.(TRANSPORT_PROTECTED_SELECTOR)) return false;
    if (protectsKeyboard(node)) {
      const button = node?.closest?.(TRANSPORT_BUTTON_SELECTOR);
      if (!button?.closest?.(TRANSPORT_SCOPE_SELECTOR)) return false;
    }
  }
  return true;
}

/** Resolve a keydown without intercepting form controls, dialogs or browser keys. */
export function resolveEditorShortcut(event, profile = "cutroom") {
  if (!event || event.defaultPrevented || event.isComposing || event.keyCode === 229 || event.altKey) return null;
  if (["Dead", "Process", "Unidentified"].includes(event.key)) return null;
  if (event.ctrlKey && event.metaKey) return null;
  if (event.getModifierState?.("AltGraph")) return null;
  if (isEditorTransportSpace(event)) return event.repeat ? null : "toggle_play";
  const path = typeof event.composedPath === "function" ? event.composedPath() : [];
  if ([event.target, event.target?.ownerDocument?.activeElement, ...path].some(protectsKeyboard)) return null;
  const code = eventCode(event);
  const mod = !!(event.ctrlKey || event.metaKey);
  const shift = !!event.shiftKey;
  const binding = bindings(profile).find((item) => item.code === code && item.mod === mod && item.shift === shift
    && (!item.modifier || (item.modifier === "ctrl" ? !!event.ctrlKey : !!event.metaKey)));
  if (!binding || (event.repeat && !REPEATABLE.has(binding.action))) return null;
  return binding.action;
}

/** Readable rows; custom=true denotes a CUTROOM adaptation in an imported set. */
export function shortcutRows(profile = "cutroom") {
  const id = profileId(profile);
  return Object.keys(ACTION_LABELS).map((action) => {
    const matches = bindings(id).filter((item) => item.action === action);
    const custom = id !== "cutroom" && matches.some((item) => item.custom);
    return { action, label: ACTION_LABELS[action], keys: [...new Set(matches.map((item) => item.keys))].join(" or ") || "Toolbar", custom,
      bound: matches.length > 0 };
  });
}
