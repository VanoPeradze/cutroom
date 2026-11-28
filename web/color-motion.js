// Color & motion: a whole-edit grade (look, sliders, .cube LUT) and zoom
// keyframes. The export compiles the same saved values with FFmpeg
// (cutroom/grading.py); the preview here is a close CSS approximation.

export const LOOKS = [
  ["none", "ללא", "None"], ["warm", "חם", "Warm"], ["cool", "קר", "Cool"],
  ["teal_orange", "טיל וכתום", "Teal & orange"], ["vintage", "וינטג׳", "Vintage"],
  ["punchy", "חי ועשיר", "Punchy"], ["matte", "מט", "Matte"], ["mono", "שחור־לבן", "Black & white"],
];
const LOOK_CSS = {
  warm: "sepia(.18) saturate(1.08)", cool: "hue-rotate(-8deg) saturate(.96)",
  teal_orange: "contrast(1.06) saturate(1.15) hue-rotate(-4deg)", vintage: "sepia(.32) contrast(.92) brightness(1.03)",
  punchy: "contrast(1.15) saturate(1.3)", matte: "contrast(.86) brightness(1.04)", mono: "grayscale(1)",
};
const SLIDERS = [
  ["exposure", "חשיפה", "Exposure"], ["contrast", "ניגודיות", "Contrast"],
  ["saturation", "רוויה", "Saturation"], ["temperature", "חום צבע", "Warmth"],
];
export const MAX_KEYFRAMES = 32;
const clamp = (value, low, high) => Math.min(high, Math.max(low, Number.isFinite(Number(value)) ? Number(value) : low));

export function normalizeColor(raw) {
  const value = raw && typeof raw === "object" ? raw : {};
  const look = LOOKS.some(([id]) => id === value.look) ? value.look : "none";
  const color = { look };
  for (const [key] of SLIDERS) color[key] = Math.round(clamp(value[key] ?? 0, -1, 1) * 10000) / 10000;
  color.lut_id = typeof value.lut_id === "string" && /^[0-9a-f]{16}$/.test(value.lut_id) ? value.lut_id : null;
  color.lut_name = color.lut_id && typeof value.lut_name === "string" ? value.lut_name.slice(0, 120) : null;
  return color;
}

export function colorIsNeutral(color) {
  const clean = normalizeColor(color);
  return clean.look === "none" && !clean.lut_id && SLIDERS.every(([key]) => Math.abs(clean[key]) < 1e-4);
}

/** CSS approximation of the FFmpeg grade (lut3d cannot be previewed). */
export function colorCssFilter(raw) {
  const color = normalizeColor(raw);
  const parts = [];
  if (color.look !== "none") parts.push(LOOK_CSS[color.look]);
  if (color.exposure) parts.push(`brightness(${(1 + 0.3 * color.exposure).toFixed(3)})`);
  if (color.contrast) parts.push(`contrast(${(1 + 0.5 * color.contrast).toFixed(3)})`);
  if (color.saturation) parts.push(`saturate(${(1 + color.saturation).toFixed(3)})`);
  if (color.temperature > 0) parts.push(`sepia(${(0.3 * color.temperature).toFixed(3)})`);
  if (color.temperature < 0) parts.push(`hue-rotate(${(12 * color.temperature).toFixed(1)}deg) saturate(${(1 + 0.1 * color.temperature).toFixed(3)})`);
  return parts.join(" ") || "none";
}

const EMPHASIS_STOP = new Set("about after again against because before being between could doesn't during everything nothing really should something through without would actually basically literally probably".split(" "));

/** A word worth a punch-in: a number, a long content word, or an exclamation. */
export function isEmphasisWord(word) {
  const raw = String(word || "").trim(), core = raw.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
  if (!core) return false;
  return /\p{N}/u.test(core) || raw.endsWith("!") || (core.length >= 7 && /^\p{L}+$/u.test(core) && !EMPHASIS_STOP.has(core.toLowerCase()));
}

/** Punch-in keyframes on key words of the edit's captions (edit/output time).
    Each punch eases in over 0.25 s, holds, and eases out; punches stay at least
    `gap` seconds apart and never overlap existing keyframes. */
export function autoZoomKeyframes(captions, existing = [], { zoom = 1.15, hold = 1.0, gap = 4, x = 0.5, y = 0.42 } = {}) {
  const words = (captions || []).filter((c) => !c.hidden && !c.estimated_words && Array.isArray(c.words))
    .flatMap((c) => c.words.map(([start, , word]) => ({ start: Number(start), word })))
    .filter((w) => Number.isFinite(w.start) && w.start >= 0.3 && isEmphasisWord(w.word)).sort((a, b) => a.start - b.start);
  const rows = normalizeKeyframes(existing);
  const busy = rows.map((r) => r.time);
  const out = [...rows];
  let last = -Infinity;
  for (const w of words) {
    if (out.length + 4 > MAX_KEYFRAMES) break;
    const t = w.start, span = [t - 0.25, t + hold + 0.35];
    if (t - last < gap || busy.some((time) => time >= span[0] - 0.5 && time <= span[1] + 0.5)) continue;
    out.push({ time: t - 0.25, zoom: 1, x, y }, { time: t, zoom, x, y }, { time: t + hold, zoom, x, y }, { time: t + hold + 0.35, zoom: 1, x, y });
    last = t;
  }
  return normalizeKeyframes(out);
}

export function normalizeKeyframes(raw) {
  const rows = new Map();
  for (const item of Array.isArray(raw) ? raw : []) {
    if (!item || typeof item !== "object" || !Number.isFinite(Number(item.time))) continue;
    const time = Math.round(clamp(item.time, 0, 604800) * 1000) / 1000;
    rows.set(time, {
      time, zoom: Math.round(clamp(item.zoom ?? 1, 1, 3) * 10000) / 10000,
      x: Math.round(clamp(item.x ?? 0.5, 0, 1) * 10000) / 10000, y: Math.round(clamp(item.y ?? 0.5, 0, 1) * 10000) / 10000,
    });
  }
  return [...rows.values()].sort((a, b) => a.time - b.time).slice(0, MAX_KEYFRAMES);
}

/** Linear between keyframes, holding the first/last value, like the export. */
export function keyframeAt(raw, time) {
  const rows = normalizeKeyframes(raw);
  if (!rows.length) return null;
  const t = Number(time) || 0;
  if (t <= rows[0].time) return { ...rows[0], time: t };
  for (let index = 1; index < rows.length; index += 1) {
    const before = rows[index - 1], after = rows[index];
    if (t < after.time) {
      const k = (t - before.time) / Math.max(after.time - before.time, 1e-3);
      return { time: t, zoom: before.zoom + (after.zoom - before.zoom) * k, x: before.x + (after.x - before.x) * k, y: before.y + (after.y - before.y) * k };
    }
  }
  return { ...rows.at(-1), time: t };
}

/** Insert or replace the keyframe at ``time`` (within one frame at 30 FPS). */
export function setKeyframe(raw, frame) {
  const rows = normalizeKeyframes(raw).filter(row => Math.abs(row.time - frame.time) >= 1 / 30);
  if (rows.length >= MAX_KEYFRAMES) return null;
  return normalizeKeyframes([...rows, frame]);
}

function formatClock(seconds) {
  const total = Math.max(0, Number(seconds) || 0), minutes = Math.floor(total / 60);
  return `${String(minutes).padStart(2, "0")}:${(total - minutes * 60).toFixed(1).padStart(4, "0")}`;
}

export function initColorMotion(root, options) {
  const { getProject, save, uploadLut, outputTime, seek, stage, copy = (_he, en) => en, toast = () => {} } = options;
  if (!root) return null;
  const el = (tag, props = {}, children = []) => {
    const node = Object.assign(document.createElement(tag), props);
    for (const child of [].concat(children)) if (child != null) node.append(child);
    return node;
  };
  let color = normalizeColor(null), keyframes = [];

  const look = el("select", { className: "color-look", ariaLabel: copy("מראה", "Look") });
  for (const [id, he, en] of LOOKS) look.append(el("option", { value: id, textContent: copy(he, en) }));
  const sliders = new Map();
  const sliderRows = SLIDERS.map(([key, he, en]) => {
    const input = el("input", { type: "range", min: "-100", max: "100", step: "1", value: "0" });
    const output = el("output", { textContent: "0" });
    input.setAttribute("aria-label", copy(he, en));
    sliders.set(key, { input, output });
    input.addEventListener("input", () => { output.textContent = input.value; color = { ...color, [key]: Number(input.value) / 100 }; preview(); });
    input.addEventListener("change", commitColor);
    input.addEventListener("dblclick", () => { input.value = "0"; output.textContent = "0"; color = { ...color, [key]: 0 }; preview(); commitColor(); });
    return el("label", { className: "color-slider" }, [el("span", { textContent: copy(he, en) }), input, output]);
  });
  const lutName = el("span", { className: "color-lut-name" });
  const lutInput = el("input", { type: "file", accept: ".cube,text/plain", hidden: true });
  const lutButton = el("button", { type: "button", className: "button ghost compact", textContent: copy("טעינת LUT…", "Load LUT…") });
  const lutRemove = el("button", { type: "button", className: "button ghost compact", textContent: copy("הסרה", "Remove") });
  const resetColor = el("button", { type: "button", className: "button ghost compact", textContent: copy("איפוס צבע", "Reset color") });
  const colorNote = el("small", { className: "color-note" });

  const zoom = el("input", { type: "range", min: "100", max: "300", step: "1", value: "100" });
  const anchorX = el("input", { type: "range", min: "0", max: "100", step: "1", value: "50" });
  const anchorY = el("input", { type: "range", min: "0", max: "100", step: "1", value: "50" });
  const motionRows = [[zoom, "זום", "Zoom", "%"], [anchorX, "מרכז אופקי", "Center X", "%"], [anchorY, "מרכז אנכי", "Center Y", "%"]].map(([input, he, en, unit]) => {
    const output = el("output", { textContent: `${input.value}${unit}` });
    input.setAttribute("aria-label", copy(he, en));
    input.addEventListener("input", () => { output.textContent = `${input.value}${unit}`; previewMotion(currentFrame()); });
    input._output = output; input._unit = unit;
    return el("label", { className: "color-slider" }, [el("span", { textContent: copy(he, en) }), input, output]);
  });
  const addKey = el("button", { type: "button", className: "button primary compact", textContent: copy("קיפריים במיקום הנוכחי", "Keyframe at playhead") });
  const clearKeys = el("button", { type: "button", className: "button ghost compact", textContent: copy("ניקוי הכול", "Clear all") });
  const autoZoom = el("button", { type: "button", className: "button ghost compact", textContent: copy("זום אוטומטי על מילות מפתח", "Auto zoom on key words") });
  autoZoom.title = copy("מוסיף פאנץ׳־אין קצר על מספרים ומילים חשובות בתמלול", "Adds a short punch-in on numbers and key words in the transcript");
  const keyList = el("ol", { className: "keyframe-list" });
  const motionNote = el("small", { className: "color-note" });

  root.replaceChildren(
    el("div", { className: "color-motion-block" }, [
      el("div", { className: "color-motion-head" }, [el("b", { textContent: copy("צבע לכל העריכה", "Color for the whole edit") }),
        el("small", { textContent: copy("חל על הייצוא לפני הכתוביות.", "Applies to the export, before captions.") })]),
      el("label", { className: "color-slider color-look-row" }, [el("span", { textContent: copy("מראה", "Look") }), look]),
      ...sliderRows,
      el("div", { className: "color-lut-row" }, [lutButton, lutRemove, resetColor, lutName, lutInput]),
      colorNote,
    ]),
    el("div", { className: "color-motion-block" }, [
      el("div", { className: "color-motion-head" }, [el("b", { textContent: copy("זום וקיפריימים", "Zoom keyframes") }),
        el("small", { textContent: copy("התמונה מתקרבת סביב נקודת המרכז, ונעה בהדרגה בין קיפריימים.", "The picture zooms around the center point and eases between keyframes.") })]),
      ...motionRows,
      el("div", { className: "color-actions" }, [addKey, autoZoom, clearKeys]),
      keyList,
      motionNote,
    ]),
  );

  function currentFrame() {
    return { time: Math.round(Math.max(0, Number(outputTime()) || 0) * 1000) / 1000, zoom: Number(zoom.value) / 100, x: Number(anchorX.value) / 100, y: Number(anchorY.value) / 100 };
  }
  function showMotionValues(frame) {
    zoom.value = String(Math.round((frame?.zoom ?? 1) * 100));
    anchorX.value = String(Math.round((frame?.x ?? 0.5) * 100));
    anchorY.value = String(Math.round((frame?.y ?? 0.5) * 100));
    for (const input of [zoom, anchorX, anchorY]) input._output.textContent = `${input.value}${input._unit}`;
  }
  function preview() {
    if (!stage) return;
    const filter = colorCssFilter(color);
    stage.style.setProperty("--grade-filter", filter);
    stage.classList.toggle("is-graded", filter !== "none");
  }
  function previewMotion(frame) {
    if (!stage) return;
    const active = frame && frame.zoom > 1.0001;
    stage.classList.toggle("has-keyframes", Boolean(active));
    stage.style.setProperty("--kf-transform", active ? `scale(${frame.zoom.toFixed(4)})` : "none");
    stage.style.setProperty("--kf-origin", frame ? `${(frame.x * 100).toFixed(2)}% ${(frame.y * 100).toFixed(2)}%` : "50% 50%");
  }
  function commitColor() {
    color = normalizeColor(color);
    // Always the full object: project patches deep-merge, so {} would not clear.
    save({ color });
    renderNotes();
  }
  function commitKeyframes(next) {
    keyframes = normalizeKeyframes(next);
    save({ keyframes });
    renderKeyframes();
    sync(outputTime());
  }
  function renderNotes() {
    lutName.textContent = color.lut_id ? `LUT: ${color.lut_name || "LUT"}` : copy("לא נבחר LUT", "No LUT selected");
    lutRemove.hidden = !color.lut_id;
    colorNote.textContent = color.lut_id
      ? copy("התצוגה המקדימה משוערת. ה־LUT מוחל במלואו בייצוא.", "The preview is approximate. The LUT is applied in full on export.")
      : copy("התצוגה המקדימה קרובה לייצוא. לחיצה כפולה על סליידר מאפסת אותו.", "The preview closely matches export. Double-click a slider to reset it.");
  }
  function renderKeyframes() {
    keyList.replaceChildren(...keyframes.map((row) => {
      const go = el("button", { type: "button", className: "keyframe-time", textContent: formatClock(row.time) });
      go.title = copy("מעבר לקיפריים", "Go to keyframe");
      go.addEventListener("click", () => seek?.(row.time));
      const remove = el("button", { type: "button", className: "keyframe-remove", textContent: "×" });
      remove.setAttribute("aria-label", copy(`מחיקת קיפריים ב־${formatClock(row.time)}`, `Delete keyframe at ${formatClock(row.time)}`));
      remove.addEventListener("click", () => commitKeyframes(keyframes.filter(item => item !== row)));
      return el("li", {}, [go, el("span", { textContent: `${Math.round(row.zoom * 100)}% · ${Math.round(row.x * 100)}/${Math.round(row.y * 100)}` }), remove]);
    }));
    clearKeys.hidden = !keyframes.length;
    motionNote.textContent = keyframes.length
      ? copy(`${keyframes.length} קיפריימים. התנועה מוצגת בתצוגה המקדימה ובייצוא.`, `${keyframes.length} keyframe${keyframes.length === 1 ? "" : "s"}. Motion shows in preview and export.`)
      : copy("עדיין אין קיפריימים. כוונו זום ומרכז, ואז הוסיפו קיפריים.", "No keyframes yet. Set zoom and center, then add a keyframe.");
  }

  look.addEventListener("change", () => { color = { ...color, look: look.value }; preview(); commitColor(); });
  resetColor.addEventListener("click", () => { color = normalizeColor(null); showColor(); preview(); commitColor(); });
  lutButton.addEventListener("click", () => lutInput.click());
  lutRemove.addEventListener("click", () => { color = { ...color, lut_id: null, lut_name: null }; commitColor(); });
  lutInput.addEventListener("change", async () => {
    const file = lutInput.files?.[0];
    lutInput.value = "";
    if (!file) return;
    if (!/\.cube$/i.test(file.name)) { toast(copy("בחרו קובץ ‎.cube", "Choose a .cube file.")); return; }
    lutButton.disabled = true;
    try {
      const lut = await uploadLut(file);
      color = { ...color, lut_id: lut.id, lut_name: lut.name };
      commitColor();
    } catch (error) {
      toast(error?.message || copy("לא ניתן לטעון את ה־LUT.", "Could not load the LUT."));
    } finally { lutButton.disabled = false; }
  });
  addKey.addEventListener("click", () => {
    const next = setKeyframe(keyframes, currentFrame());
    if (!next) { toast(copy(`אפשר עד ${MAX_KEYFRAMES} קיפריימים.`, `Use at most ${MAX_KEYFRAMES} keyframes.`)); return; }
    commitKeyframes(next);
  });
  clearKeys.addEventListener("click", () => commitKeyframes([]));
  autoZoom.addEventListener("click", () => {
    const captions = getProject()?.editor_captions || [];
    if (!captions.some((c) => !c.hidden && c.words?.length && !c.estimated_words)) { toast(copy("זום אוטומטי צריך תמלול עם תזמון מילים.", "Auto zoom needs a transcript with word timing.")); return; }
    const next = autoZoomKeyframes(captions, keyframes);
    const added = (next.length - keyframes.length) / 4;
    if (!added) { toast(copy("לא נמצאו מקומות חדשים לזום.", "No new places to zoom were found.")); return; }
    commitKeyframes(next);
    toast(copy(`נוספו ${added} זומים. אפשר למחוק כל קיפריים ברשימה.`, `Added ${added} zoom${added === 1 ? "" : "s"}. Delete any keyframe in the list.`));
  });

  function showColor() {
    look.value = color.look;
    for (const [key, { input, output }] of sliders) { input.value = String(Math.round(color[key] * 100)); output.textContent = input.value; }
    renderNotes();
  }
  function render() {
    const manual = getProject()?.manual || {};
    color = normalizeColor(manual.color);
    keyframes = normalizeKeyframes(manual.keyframes);
    showColor();
    renderKeyframes();
    preview();
    sync(outputTime());
  }
  function sync(time) {
    // While a motion slider is in use, the preview follows the slider instead.
    if (root.contains(document.activeElement) && [zoom, anchorX, anchorY].includes(document.activeElement)) return;
    const frame = keyframeAt(keyframes, time);
    previewMotion(frame);
    if (frame) showMotionValues(frame);
  }
  return { render, sync };
}
