// Ranges the user marked by hand on the edited timeline and saved in Clips.
// Times are output frames of the edit, never recording time. The server owns
// the "changed" check; this module only reads, labels and previews the list.

const ID = /^mclip_[a-f0-9]{12}$/;
const RATES = new Set([24, 25, 30, 50, 60]);
const STATUSES = new Set(["ready", "changed", "outside"]);

// A valid saved list, sorted by time; null when the list is unknown or malformed.
export function manualClipRows(registry) {
  if (registry == null) return [];
  if (typeof registry !== "object" || registry.version !== 1 || !Array.isArray(registry.items) || registry.unavailable) return null;
  const seen = new Set(), rows = [];
  for (const row of registry.items) {
    if (!row || typeof row !== "object" || typeof row.id !== "string" || !ID.test(row.id) || seen.has(row.id)
        || typeof row.name !== "string" || !row.name || !RATES.has(row.fps)
        || !Number.isInteger(row.start_frame) || !Number.isInteger(row.end_frame)
        || row.start_frame < 0 || row.end_frame <= row.start_frame || !STATUSES.has(row.status)) return null;
    seen.add(row.id);
    rows.push(row);
  }
  return rows.sort((a, b) => a.start_frame / a.fps - b.start_frame / b.fps || a.end_frame / a.fps - b.end_frame / b.fps);
}

export function manualClipTimes(row) {
  const start = row.start_frame / row.fps, end = row.end_frame / row.fps;
  return { start, end, duration: end - start };
}

// 1:02:03 for long recordings, 2:03 otherwise; frames are dropped for display.
export function editClock(seconds) {
  const whole = Math.max(0, Math.floor(Number(seconds) + 1e-6));
  const h = Math.floor(whole / 3600), m = Math.floor(whole / 60) % 60, s = whole % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

export function manualClipLength(row) {
  const frames = row.end_frame - row.start_frame, seconds = frames / row.fps;
  return seconds < 10 ? `${seconds.toFixed(1)}s` : editClock(seconds);
}

export function manualStatusText(status) {
  if (status === "changed") return "Needs review: the edit changed inside this range.";
  if (status === "outside") return "This range now ends after the edit. Mark it again on the timeline.";
  return "";
}

// The pieces of recording A that play inside an edit window, in play order.
// Used for a quick in-card preview without moving the editor playhead.
export function sourcePieces(clips, start, end) {
  const pieces = [];
  for (const item of Array.isArray(clips) ? clips : []) {
    const a = Number(item?.start), b = Number(item?.end), source = Number(item?.source_start);
    if (![a, b, source].every(Number.isFinite) || b <= a) continue;
    const speed = Number(item.video_speed) > 0 ? Number(item.video_speed) : 1;
    const left = Math.max(start, a), right = Math.min(end, b);
    if (right - left <= 1e-6) continue;
    const from = source + (left - a) * speed;
    pieces.push({ start: left, end: right, from, to: from + (right - left) * speed });
  }
  return pieces.sort((x, y) => x.start - y.start);
}

// The batch queue item for a saved range: its exact frames and its id, so the
// server can refuse it if the edit changed inside it.
export function manualExportItem(row) {
  return { manual: true, id: row.id, name: row.name, start_frame: row.start_frame, end_frame: row.end_frame, fps: row.fps,
    ...manualClipTimes(row) };
}

export function batchItemLabel(item) {
  return item?.manual ? item.name : `Clip ${item?.rank ?? ""}`.trim();
}
