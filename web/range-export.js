// Work in output frames, not media time. An intentional choice pins the exact
// visible marks and saved project revision across asynchronous settings/track saves.
const rates = new Set([24, 25, 30, 50, 60]);
export function makeExportRangePlan(s, fps) {
  if (!s?.editor || !s.editMode || s.occurrence || s.dirtyRange || !s.id || !Number.isInteger(s.revision)
      || !rates.has(fps) || !Number.isFinite(s.duration) || !(s.duration > 0)
      || !Number.isFinite(s.start) || !Number.isFinite(s.end)
      || s.start < 0 || s.end <= s.start || s.end > s.duration) return null;
  const frame = t => Math.floor(t * fps + .5);
  const start = frame(s.start), end = frame(s.end);
  if (start >= end || end > frame(s.duration)) return null;
  return {id:s.id, view:s.view, duration:s.duration, inTime:s.start, outTime:s.end,
    range:{start_frame:start, end_frame:end, fps, expected_revision:s.revision}};
}
export function sameExportRangePlan(a, b) {
  if (!a || !b) return false;
  return ['id','view','duration','inTime','outTime'].every(k => a[k] === b[k])
    && ['start_frame','end_frame','fps','expected_revision'].every(k => a.range[k] === b.range[k]);
}
export function exportFrameTime(frame, fps) {
  const sec = Math.floor(frame / fps);
  return [Math.floor(sec/3600), Math.floor(sec/60)%60, sec%60, frame%fps].map(n => String(n).padStart(2,'0')).join(':');
}
export function exportRangeLabel(range) {
  return `${exportFrameTime(range.start_frame,range.fps)} → ${exportFrameTime(range.end_frame,range.fps)} · ${range.end_frame-range.start_frame} frames`;
}
