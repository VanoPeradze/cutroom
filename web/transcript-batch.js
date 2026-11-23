const clone = value => structuredClone(value);
const freeze = value => {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
};

const strip = /^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/gu;
export const pythonStrip = text => text.replace(strip, "");
const unicode = text => typeof text === "string" && !Array.from(text).some(value => value.length === 1 && /[\uD800-\uDFFF]/u.test(value));
const itemKeys = ["base_text", "end", "segment_id", "start", "text"];

export function frozenBatchBinding(projectId, revision, items) {
  if (typeof projectId !== "string" || !projectId || !Number.isSafeInteger(revision) || revision < 1
    || !Array.isArray(items) || !items.length || items.length > 1000) throw new Error("Invalid reviewed batch binding");
  const ids = new Set();
  for (const item of items) {
    if (!item || Array.isArray(item) || typeof item !== "object" || Object.keys(item).sort().join("|") !== itemKeys.join("|")
      || !unicode(item.segment_id) || !item.segment_id || Array.from(item.segment_id).length > 128 || ids.has(item.segment_id)
      || !unicode(item.base_text) || Array.from(item.base_text).length > 20000
      || !unicode(item.text) || Array.from(item.text).length > 20000 || !pythonStrip(item.text) || Array.from(pythonStrip(item.text)).length > 4000
      || typeof item.start !== "number" || typeof item.end !== "number" || !Number.isFinite(item.start)
      || !Number.isFinite(item.end) || Math.abs(item.start) > 604800 || Math.abs(item.end) > 604800
      || item.end <= item.start) throw new Error("Invalid reviewed transcript item");
    ids.add(item.segment_id);
  }
  const captured = clone(items);
  const request = { action: "transcript_text_batch", items: captured, expected_revision: revision };
  const body = JSON.stringify(request);
  if (new TextEncoder().encode(body).length > 6 * 1024 * 1024 + 4096) throw new Error("The reviewed batch exceeds the existing request limit");
  return freeze({ projectId, revision, items: captured, body });
}

// The host retains this owner by project, not by pane or textarea lifetime.
// It supplies semantic receipt checks and controls whether results may enter
// its current view. This protocol never replaces a project or clears a buffer.
export function createBatchProtocol({ binding, post, read, verify, classify, admit, unchanged,
  accepted = () => {}, changed = () => {} }) {
  const rebuilt = frozenBatchBinding(binding?.projectId, binding?.revision, binding?.items);
  if (rebuilt.body !== binding?.body) throw new Error("The reviewed request body changed");
  binding = rebuilt;
  let state = { status: "ready", pending: false, attempts: 0, checkedBaseline: false,
    issue: null, result: null, outcome: null, reviewRevision: null };
  const notify = () => { try { changed(snapshot()); } catch {} };
  const isUnchanged = () => { try { return unchanged(binding) === true; } catch { return false; } };
  const snapshot = () => freeze({ ...state, binding, canCheck: !state.pending && ["unknown", "conflict"].includes(state.status),
    canRetry: !state.pending && state.status === "unknown" && state.checkedBaseline && isUnchanged(),
    canLoadNewer: !state.pending && state.status === "conflict" && Number.isSafeInteger(state.reviewRevision) && state.reviewRevision > binding.revision });
  const set = patch => { state = { ...state, ...patch }; notify(); };
  const deliver = (result, outcome) => {
    set({ status: outcome === "unchanged" ? "unchanged" : "saved", pending: false,
      checkedBaseline: false, reviewRevision: null, issue: null, result: clone(result), outcome });
    // Consumer failures cannot turn an authoritative saved result into a
    // retryable failure. The host may decline installation in a newer view.
    try { accepted(clone(result), outcome, binding); } catch {}
    return true;
  };
  async function send(retry) {
    const allowed = retry ? snapshot().canRetry : state.status === "ready" && !state.pending;
    if (!allowed) return false;
    set({ status: "submitting", pending: true, checkedBaseline: false, reviewRevision: null, issue: null });
    // Reserve before notification, and recheck after that potentially
    // reentrant callback. No consumer callback occurs between admit and POST.
    let permitted;
    try { permitted = (!retry || unchanged(binding) === true) && admit(binding, { retry }) === true; }
    catch { permitted = false; }
    if (!permitted) {
      set({ status: retry ? "unknown" : "refused", pending: false,
        issue: "Review the current saved project and retained text before saving." });
      return false;
    }
    let response;
    try {
      state = { ...state, attempts: state.attempts + 1 };
      const promise = post(binding.projectId, binding.body);
      response = await promise;
    } catch (error) {
      const status = Number(error?.status);
      const rejected = status >= 400 && status < 500 && status !== 408 && status !== 499;
      // A definite refusal of the retry says nothing about the still-uncertain
      // original. Keep its fence reachable until a read establishes the result.
      set({ status: status === 409 ? "conflict" : rejected && !retry ? "rejected" : "unknown", pending: false,
        issue: error?.message || "The save outcome could not be confirmed. Check saved changes; your text is retained." });
      return false;
    }
    let result;
    try { result = verify(binding, response); } catch { result = null; }
    if (!result || !["changed", "unchanged"].includes(result.outcome)) {
      set({ status: "unknown", pending: false,
        issue: "The save receipt could not be verified. Check saved changes; do not send a new batch." });
      return false;
    }
    return deliver(response, result.outcome);
  }
  async function check() {
    if (!snapshot().canCheck) return false;
    const priorStatus = state.status;
    set({ pending: true, checkedBaseline: false, reviewRevision: null, issue: null });
    let latest, assessment;
    try { latest = await read(binding.projectId); assessment = classify(binding, latest); }
    catch (error) {
      set({ status: priorStatus, pending: false,
        issue: error?.message || "Saved changes could not be checked. Your text is retained." });
      return false;
    }
    if (assessment?.outcome === "saved-now") return deliver(latest, "saved-now");
    if (assessment?.outcome === "baseline") {
      set({ status: "unknown", pending: false, checkedBaseline: true,
        issue: "The saved version is unchanged, but the first request may still arrive. You may explicitly retry only the same save." });
      return false;
    }
    set({ status: "conflict", pending: false,
      reviewRevision: assessment?.reviewable === true && Number.isSafeInteger(assessment.revision)
        && assessment.revision > binding.revision ? assessment.revision : null,
      issue: "The saved text differs from this reviewed batch. Every draft is retained; no changes were repeated." });
    return false;
  }
  function acceptNewerLoad(project) {
    // Called only after a separately explicit, host-owned read-only reload.
    // It is not a save success and cannot clear any retained buffer.
    if (!snapshot().canLoadNewer || project?.id !== binding.projectId || !Number.isSafeInteger(project.revision)
      || project.revision < state.reviewRevision) return false;
    set({ status: "review", reviewRevision: project.revision, checkedBaseline: false, pending: false,
      issue: "The newer saved version is loaded. Retained drafts are review-only until explicitly copied and discarded.", outcome: "review" });
    return true;
  }
  return Object.freeze({ snapshot, submit: () => send(false), retrySame: () => send(true), check, acceptNewerLoad });
}

export function captureTranscriptBuffers(buffers) {
  return Object.freeze(buffers.map(value => Object.freeze({ key: `${value.projectId}:${String(value.id)}`,
    identity: value, fields: freeze(clone(value)) })));
}
export function matchingCapturedBuffers(captured, current) {
  // Used only after every target has an authoritative saved result. A mixed
  // GET never reaches this helper. A newer local version is never discarded.
  return captured.filter(item => {
    const now = current.get(item.key);
    return now === item.identity && Object.keys(now).length === Object.keys(item.fields).length
      && Object.keys(item.fields).every(key => Object.is(now[key], item.fields[key]));
  }).map(item => item.key);
}

export function retainedDraftViews(buffers, project, { provenanceVerified = false } = {}) {
  const rows = Array.isArray(project?.analysis?.transcript?.segments) ? project.analysis.transcript.segments : [];
  return Object.freeze(buffers.filter(value => value.projectId === project?.id).map(value => {
    const matches = rows.filter((row, index) => row && typeof row === "object" && !Array.isArray(row)
      && String(Object.hasOwn(row, "id") ? row.id : index) === String(value.id));
    const current = provenanceVerified === true && matches.length === 1 ? matches[0] : null;
    const sameTime = current && Object.is(current.start, value.start) && Object.is(current.end, value.end);
    return Object.freeze({ key: `${value.projectId}:${String(value.id)}`, identity: value,
      kind: current && sameTime ? "stale" : "orphan", readOnly: true,
      canSeek: false, canRemove: false, canRestore: false, canSave: false, canCopy: true, canDiscard: true,
      current: current && sameTime ? current : null,
      reason: provenanceVerified !== true ? "unverified_provenance" : matches.length !== 1 ? "missing_or_ambiguous_identity"
        : !sameTime ? "changed_source_times" : "retained_review" });
  }));
}
