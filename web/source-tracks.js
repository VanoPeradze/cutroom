// Non-destructive source clips live on the existing project timeline. The
// source clock is local to each clip; neither video element owns the playhead.
export function hasSourceTracks(project) {
  const tracks = project?.manual?.source_tracks;
  return Boolean(tracks && ["A", "B"].some(slot => Object.hasOwn(tracks, slot)));
}

export function trackClips(project, slot, syncOffset) {
  const source = project?.sources?.[slot];
  if (!source || !["A", "B"].includes(slot)) return [];
  const duration = Number(project?.sources?.A?.duration) || 0;
  const tracks = project?.manual?.source_tracks;
  if (tracks && Object.hasOwn(tracks, slot)) return Array.isArray(tracks[slot]) ? tracks[slot] : [];
  const rawOffset = project?.manual?.source_mixer?.sync_offset;
  const offset = slot === "A" ? 0 : Number(syncOffset ?? rawOffset ?? project?.analysis?.sync?.offset) || 0;
  const sourceDuration = Number(source.duration) || 0;
  const start = Math.max(0, offset), end = Math.min(duration, offset + sourceDuration);
  return end > start ? [{ id: `${slot}:base`, start, end, source_start: start - offset }] : [];
}

export function trackAt(project, slot, timelineTime, syncOffset) {
  const time = Number(timelineTime);
  if (!Number.isFinite(time)) return null;
  const clip = trackClips(project, slot, syncOffset).find(item => time >= Number(item.start) && time < Number(item.end));
  if (!clip) return null;
  const sourceTime = Number(clip.source_start) + time - Number(clip.start);
  const source = project.sources[slot];
  const limit = Number(source.duration) || 0;
  return sourceTime >= 0 && sourceTime < limit ? { clip, sourceTime } : null;
}

export class SourceTimelineClock {
  constructor(now = () => performance.now()) {
    this.now = now;
    this.position = 0;
    this.startedAt = 0;
    this.playing = false;
  }
  time() { return this.position + (this.playing ? Math.max(0, this.now() - this.startedAt) / 1000 : 0); }
  seek(time) {
    this.position = Math.max(0, Number(time) || 0);
    this.startedAt = this.now();
    return this.position;
  }
  play() { if (!this.playing) { this.startedAt = this.now(); this.playing = true; } }
  pause() { this.position = this.time(); this.playing = false; return this.position; }
}
