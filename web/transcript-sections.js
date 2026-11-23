// Read-only saved transcript sections and synchronous navigation ownership.
const record = value => value !== null && typeof value === "object" && !Array.isArray(value);
const number = value => typeof value === "number" && Number.isFinite(value);
const own = (value, key) => Object.hasOwn(value, key);
const unicode = value => typeof value === "string" && !Array.from(value).some(char => char.length === 1 && /[\uD800-\uDFFF]/u.test(char));
const id = value => (unicode(value) && value.trim() && Array.from(value).length <= 128)
  || (typeof value === "number" && Number.isSafeInteger(value));
const freeze = value => {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.values(value).forEach(freeze); Object.freeze(value);
  }
  return value;
};
const fail = (code, issue) => freeze({ ok: false, code, issue, sections: [] });
const invalid = () => { throw new Error("Invalid saved section model"); };
const EPSILON = 1e-9;

function routing(project) {
  const raw = project.manual?.source_mixer;
  if (raw !== undefined && !record(raw)) invalid();
  if (raw && own(raw, "audio_slot") && !["A", "B"].includes(raw.audio_slot)) invalid();
  let slot = raw?.audio_slot || "A";
  if (project.sources?.[slot]?.has_audio !== true)
    slot = project.sources?.A?.has_audio === true ? "A" : project.sources?.B?.has_audio === true ? "B" : null;
  return slot;
}

function identityFor(project, segment, sourceSlot, offset, rows) {
  const metadata = { ...project.analysis.transcript };
  delete metadata.text; delete metadata.segments;
  // Pin media and analysis metadata literally. No content/file-proof claim.
  return JSON.stringify({ projectId: project.id, revision: project.revision,
    segment, metadata, sources: project.sources, sourceSlot, offset,
    mixer: project.manual?.source_mixer ?? null,
    sequence: project.editor_sequence, rows });
}

export function planTranscriptSections(project, segmentId) {
  try {
    if (!record(project) || typeof project.id !== "string" || !/^project_[0-9a-f]{12}$/.test(project.id)
      || !Number.isSafeInteger(project.revision) || project.revision < 1 || !id(segmentId))
      return fail("identity", "Reopen a saved project and choose one uniquely identified transcript line.");
    if (!record(project.analysis) || !record(project.sources) || (own(project, "manual") && !record(project.manual))) invalid();
    const transcript = project.analysis?.transcript;
    if (!record(transcript) || !Array.isArray(transcript.segments))
      return fail("transcript", "The saved transcript is unavailable.");
    const matches = transcript.segments.filter(row => record(row) && own(row, "id") && id(row.id)
      && String(row.id) === String(segmentId));
    if (matches.length !== 1) return fail("segment_identity", "This saved transcript line is missing or ambiguous.");
    const segment = matches[0];
    if (!unicode(segment.text) || !number(segment.start) || !number(segment.end) || segment.end <= segment.start
      || Math.abs(segment.start) > 604800 || Math.abs(segment.end) > 604800) invalid();
    const sequence = project.editor_sequence;
    if (!record(sequence) || own(sequence, "error") || typeof sequence.active !== "boolean"
      || !record(sequence.sequence) || sequence.sequence.version !== 1
      || !number(sequence.duration) || sequence.duration <= 0 || sequence.duration > 86400
      || sequence.sequence.duration !== sequence.duration || !record(sequence.source_tracks)
      || (own(project.manual || {}, "sequence") && (!record(project.manual.sequence) || project.manual.sequence.version !== 1)))
      return fail("projection", "The saved edited timeline cannot be addressed safely.");
    const sourceSlot = project.analysis.audio_source;
    if (!["A", "B"].includes(sourceSlot)) return fail("source_clock", "The analyzed source-audio clock is unavailable.");
    const offset = sourceSlot === "B" ? project.analysis.audio_timeline_offset : 0;
    if (!number(offset) || Math.abs(offset) > 604800) return fail("source_clock", "The analyzed source-audio offset is unavailable.");
    const source = project.sources?.[sourceSlot];
    if (!record(source) || source.has_audio !== true || !number(source.duration) || source.duration <= 0)
      return fail("source", "The analyzed audio source is unavailable.");
    // The existing Program seek requires A, even for an edited B-audio section.
    if (!record(project.sources?.A) || !number(project.sources.A.duration) || project.sources.A.duration <= 0)
      return fail("program", "Open a valid edited Program preview before going to a section.");
    if (source.generation !== undefined && source.generation !== "" &&
      (typeof source.generation !== "string" || source.generation === "unversioned" || !/^[A-Za-z0-9_-]{1,128}$/.test(source.generation))) invalid();
    if (routing(project) !== sourceSlot)
      return fail("audio_changed", "This transcript belongs to a different selected audio source.");
    const rows = sequence.source_tracks[sourceSlot];
    if (!Array.isArray(rows) || rows.length > 500) invalid();
    const seen = new Set(); let previousEnd = 0;
    for (const row of rows) {
      if (!record(row) || !unicode(row.id) || !row.id.trim() || Array.from(row.id).length > 128 || seen.has(row.id)
        || ![row.start, row.end, row.source_start].every(number) || row.start < 0 || row.end > sequence.duration + EPSILON
        || row.end - row.start < 1 / 60 - EPSILON || row.source_start < 0
        || row.source_start + row.end - row.start > source.duration + EPSILON
        || row.start < previousEnd) invalid();
      // An overlap, even within a legacy tolerance, is not one exact seek owner.
      if (own(row, "video_speed") && (!number(row.video_speed) || row.video_speed < .25 || row.video_speed > 4)) invalid();
      if (own(row, "video_source_start") && (!number(row.video_source_start) || row.video_source_start < 0)) invalid();
      seen.add(row.id); previousEnd = row.end;
    }
    const sections = [];
    for (const row of rows) {
      const transcriptStart = row.source_start + offset;
      const transcriptEnd = transcriptStart + row.end - row.start;
      const left = Math.max(segment.start, transcriptStart), right = Math.min(segment.end, transcriptEnd);
      if (!(right > left)) continue;
      const start = row.start + left - transcriptStart, end = row.start + right - transcriptStart;
      const sourceStart = left - offset, sourceEnd = right - offset;
      if (![start, end, sourceStart, sourceEnd].every(number) || start < 0 || start >= sequence.duration
        || !(end > start) || sourceStart < 0 || sourceStart >= source.duration) invalid();
      const key = JSON.stringify([sourceSlot, row.id, String(segment.id), start, end, sourceStart, sourceEnd]);
      sections.push({ key, ordinal: sections.length + 1, clipId: row.id, start, end,
        sourceStart, sourceEnd, partial: left !== segment.start || right !== segment.end });
    }
    return freeze({ ok: true, code: sections.length ? "ready" : "no_sections",
      issue: sections.length ? "" : "This source passage has no saved section on the current audio track.",
      projectId: project.id, revision: project.revision, segmentId: String(segment.id), sourceSlot, offset,
      sourceStart: segment.start - offset, sourceEnd: segment.end - offset,
      identity: identityFor(project, segment, sourceSlot, offset, rows), sections });
  } catch {
    return fail("invalid", "The saved transcript or source timeline is invalid; no section was guessed.");
  }
}

// The live host must provide real readiness/current-DOM checks. These callbacks
// are intentionally synchronous: no flush, promise, API request or replay.
export function captureSectionIntent(snapshot, plan, key) {
  try {
    if (!record(snapshot) || !plan?.ok || !Array.isArray(plan.sections) || snapshot.project?.id !== plan.projectId
      || snapshot.project?.revision !== plan.revision || String(snapshot.segmentId) !== plan.segmentId
      || snapshot.viewToken == null || !plan.sections.some(section => section?.key === key)) return null;
    const fresh = planTranscriptSections(snapshot.project, snapshot.segmentId);
    if (!fresh.ok || fresh.identity !== plan.identity) return null;
    return Object.freeze({ project: snapshot.project, viewToken: snapshot.viewToken,
      segmentId: plan.segmentId, identity: plan.identity, key });
  } catch { return null; }
}

export function navigateSection(intent, { snapshot, issue, current, cancelCut, pause, seek } = {}) {
  if (!intent || ![snapshot, issue, current, cancelCut, pause, seek].every(value => typeof value === "function")) return false;
  const verify = () => {
    try {
      const bound = now => record(now) && now.project === intent.project && now.viewToken === intent.viewToken
        && String(now.segmentId) === intent.segmentId && now.mode === "edit";
      const now = snapshot();
      if (!bound(now) || current(intent) !== true || issue(now) !== "") return null;
      // A readiness or DOM callback may synchronously trigger a newer view.
      if (current(intent) !== true) return null;
      const after = snapshot(); if (!bound(after)) return null;
      const plan = planTranscriptSections(after.project, after.segmentId);
      if (!plan.ok || plan.identity !== intent.identity) return null;
      return plan.sections.find(section => section.key === intent.key) || null;
    } catch { return null; }
  };
  if (!verify()) return false;
  try { cancelCut(); } catch { return false; }
  if (!verify()) return false;
  try { pause(); } catch { return false; }
  const section = verify(); if (!section) return false;
  try { seek(section.start); } catch { return false; }
  // No focus, selection or status callback follows if newer ownership won.
  return Boolean(verify());
}
