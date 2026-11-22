const STORAGE_KEY = 'cutroom-preview-repair-operations-v1';
const PROJECT = /^project_[0-9a-f]{12}$/;
const ASSET = /^asset_[0-9a-f]{32}$/;
const TOKEN = /^[0-9a-f]{32}$/;
const JOB = /^job_[0-9a-f]{12}$/;
const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'rejected']);
const SERVER = new Set(['queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted']);
const ERROR_CODES = new Set(['original_missing', 'original_changed', 'original_unverifiable',
  'original_proof_invalid', 'original_unsafe', 'repair_stale', 'preview_repair_failed']);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const revision = value => Number.isSafeInteger(value) && value > 0;
const text = value => value === null || typeof value === 'string';
const matches = (pattern, value) => typeof value === 'string' && pattern.test(value);
const binding = value => ({project_id:value.project_id, asset_id:value.asset_id,
  expected_revision:value.expected_revision, operation_token:value.operation_token});
const sameBinding = (a, b) => ['project_id', 'asset_id', 'expected_revision', 'operation_token'].every(key => a[key] === b[key]);
function validBinding(value) {
  return object(value) && matches(PROJECT, value.project_id) && matches(ASSET, value.asset_id)
    && revision(value.expected_revision) && matches(TOKEN, value.operation_token);
}
function safeText(value, fallback = '') {
  if (typeof value !== 'string' || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]|[A-Za-z]:[\\/]|file:\/\/|\\\\/.test(value)) return fallback;
  return value.slice(0, 1000);
}
function errorCode(value, explicit) {
  const code = typeof explicit === 'string' ? explicit : typeof value === 'string' ? value.split(':', 1)[0] : '';
  return /^[a-z][a-z0-9_]{0,79}$/.test(code) ? code : null;
}
function parsedJob(job) {
  if (!object(job) || !matches(JOB, job.id) || job.kind !== 'prepare_asset' || !matches(PROJECT, job.project_id)
      || typeof job.dedupe_key !== 'string' || !SERVER.has(job.status) || typeof job.cancel_requested !== 'boolean'
      || typeof job.progress !== 'number' || !Number.isFinite(job.progress) || job.progress < 0 || job.progress > 1
      || !text(job.message) || !text(job.error) || job.status === 'completed' && job.progress !== 1) return null;
  const parts = /^repair:(asset_[0-9a-f]{32}):([1-9][0-9]*):([0-9a-f]{32})$/.exec(job.dedupe_key);
  if (!parts || !revision(Number(parts[2]))) return null;
  const op = {project_id:job.project_id, asset_id:parts[1], expected_revision:Number(parts[2]),
    operation_token:parts[3], job_id:job.id, status:job.status, progress:job.progress,
    message:safeText(job.message), error:job.error === null ? null : safeText(job.error, 'Preview verification failed.'),
    error_code:errorCode(job.error), cancel_requested:job.cancel_requested, result:null};
  if (job.result !== undefined && job.result !== null) {
    const result = job.result;
    if (!object(result) || result.project_id !== op.project_id || result.asset_id !== op.asset_id) return null;
    const clean = {project_id:result.project_id, asset_id:result.asset_id};
    if (Object.hasOwn(result, 'preparation_reused')) {
      if (typeof result.preparation_reused !== 'boolean') return null;
      clean.preparation_reused = result.preparation_reused;
    }
    for (const field of ['before_preview_version', 'after_preview_version']) {
      if (!Object.hasOwn(result, field)) continue;
      if (!matches(/^[0-9a-f]{24}$/, result[field])) return null;
      clean[field] = result[field];
    }
    op.result = Object.freeze(clean);
  }
  return op;
}

// Transport and recovery only. The host owns saved projects, players, and view identity.
// An uncertain POST is reconciled with GET; this controller never replays it.
export function initPreviewRepairController({api, prepare, admit, changed, settled,
  storage = localStorage, token = () => crypto.randomUUID().replaceAll('-', ''),
  schedule = setTimeout, clearSchedule = clearTimeout}) {
  const entries = new Map();
  let destroyed = false, storageIssue = '', readIssue = '';
  const activeEntry = e => !e.superseded && !TERMINAL.has(e.op.status);
  function forEntry(projectId, assetId) {
    const found = [...entries.values()].filter(e => e.op.project_id === projectId && e.op.asset_id === assetId && !e.superseded);
    const newest = found.at(-1);
    if (newest?.settling) return newest;
    // A late receipt for a superseded request may fence the project again, but
    // must not replace the newer explicit operation in this asset's UI.
    return found.filter(activeEntry).at(-1) || newest;
  }
  function snapshot(e) {
    if (!e) return null;
    return Object.freeze({...e.op, known:e.known, pending:e.pending, earlier_request:e.earlier,
      canCancel:!destroyed && activeEntry(e) && !e.pending && !e.op.cancel_requested
        && (!e.submitted && e.op.status === 'preparing' || e.known && !!e.op.job_id),
      canCheck:!destroyed && activeEntry(e) && e.submitted && !e.pending,
      canRestart:!destroyed && activeEntry(e) && e.op.status === 'unknown' && e.restartable && !e.pending && !storageIssue});
  }
  function notify(callback, ...args) {
    if (destroyed || typeof callback !== 'function') return;
    try { const result = callback(...args); if (result?.then) return Promise.resolve(result).catch(() => {}); return result; }
    catch { /* Consumer errors must not replay work. */ }
  }
  const emit = e => notify(changed, snapshot(e));
  function stop(e) { if (e.timer !== null) { clearSchedule(e.timer); e.timer = null; } }
  function poll(e) {
    stop(e);
    if (destroyed || !activeEntry(e) || !e.submitted || e.pending) return;
    e.timer = schedule(() => { e.timer = null; if (!destroyed) void checkEntry(e); }, e.op.status === 'unknown' ? 2500 : 1000);
  }
  function newEntry(op, submitted = false) {
    return {op:{...op}, submitted, known:false, pending:false, restartable:false, superseded:false,
      context:undefined, timer:null, flight:null, settled:false, settling:false, earlier:false, serverPhase:null};
  }
  function local(b, status, message = '') {
    return {...b, job_id:null, status, progress:0, message, error:null, error_code:null, cancel_requested:false, result:null};
  }
  function readStored() {
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (raw === null) { readIssue = ''; return; }
      const saved = JSON.parse(raw);
      if (!object(saved) || saved.version !== 1 || !Array.isArray(saved.operations) || saved.operations.length > 1000) throw Error();
      const seen = new Set();
      // Validate the entire record before merging any of it.
      for (const b of saved.operations) {
        if (!validBinding(b) || !(b.job_id === null || matches(JOB, b.job_id)) || seen.has(b.operation_token)) throw Error();
        seen.add(b.operation_token);
        const old = entries.get(b.operation_token);
        if (old && (!old.submitted || !sameBinding(old.op, b) || old.op.job_id && b.job_id && old.op.job_id !== b.job_id)) throw Error();
      }
      for (const b of saved.operations) {
        const old = entries.get(b.operation_token);
        if (old) { if (!old.op.job_id && b.job_id && activeEntry(old)) old.op.job_id = b.job_id; continue; }
        entries.set(b.operation_token, newEntry({...local(binding(b), 'unknown', 'The previous verification outcome is unconfirmed. Check status.'), job_id:b.job_id}, true));
      }
      readIssue = '';
    } catch {
      readIssue = storageIssue = 'Preview recovery information is unavailable or invalid. Restore browser storage before verifying another preview.';
    }
  }
  function persist() {
    readStored();
    if (readIssue) throw Error(readIssue);
    const operations = [...entries.values()].filter(e => e.submitted && activeEntry(e))
      .map(e => ({...binding(e.op), job_id:e.op.job_id}));
    try { storage.setItem(STORAGE_KEY, JSON.stringify({version:1, operations})); storageIssue = ''; }
    catch { storageIssue = 'Preview recovery could not be saved in this browser. Free browser storage before verifying another preview.'; throw Error(storageIssue); }
  }
  function finish(e) {
    stop(e);
    const first = !e.settled;
    if (first) { e.settled = true; e.settling = true; }
    try { persist(); } catch { /* A confirmed receipt remains authoritative. New submissions remain fenced. */ }
    emit(e);
    if (first) {
      const result = notify(settled, snapshot(e), e.context);
      const release = () => { e.settling = false; emit(e); };
      if (result?.then) Promise.resolve(result).then(release, release);
      else release();
    }
  }
  function reject(e, error, code = 'repair_preflight_failed') {
    if (destroyed || TERMINAL.has(e.op.status)) return;
    e.pending = false;
    e.op = {...e.op, status:'rejected', error:safeText(error?.message, 'Preview verification could not be started.'),
      error_code:errorCode(null, error?.code) || code, message:'Preview verification was not started.'};
    finish(e);
  }
  function unknown(e, message) {
    if (destroyed || TERMINAL.has(e.op.status)) return;
    e.restartable = false;
    e.op = {...e.op, status:'unknown', message, error:message, error_code:null};
    emit(e);
  }
  function adopt(op, expected) {
    if (destroyed || !op) return null;
    let e = entries.get(op.operation_token);
    if (expected && (e !== expected || !sameBinding(expected.op, op))) return null;
    if (e && (!sameBinding(e.op, op) || e.op.job_id && e.op.job_id !== op.job_id)) return null;
    if (e && TERMINAL.has(e.op.status)) return snapshot(e);
    if (e?.known && e.serverPhase === 'running' && op.status === 'queued') return snapshot(e);
    if (!e) { e = newEntry(op, true); entries.set(op.operation_token, e); }
    if (!TERMINAL.has(op.status)) e.superseded = false;
    const cancelRequested = e.op.cancel_requested || op.cancel_requested;
    e.op = {...op, cancel_requested:cancelRequested};
    if (e.earlier && !TERMINAL.has(op.status)) e.op.message = `An earlier verification request is still active. ${op.message}`;
    e.known = true; e.submitted = true; e.serverPhase = op.status; e.restartable = false;
    if (TERMINAL.has(op.status)) { e.pending = false; finish(e); }
    else { try { persist(); } catch { } emit(e); poll(e); }
    return snapshot(e);
  }
  const receipt = (e, job) => adopt(parsedJob(job), e);
  async function listFor(e, allowRestart) {
    try {
      const payload = await api(`/api/jobs?project_id=${encodeURIComponent(e.op.project_id)}`);
      if (destroyed || TERMINAL.has(e.op.status)) return;
      if (!Array.isArray(payload?.jobs)) throw Error();
      const repairs = [];
      for (const job of payload.jobs) {
        if (!object(job) || job.project_id !== e.op.project_id) throw Error();
        if (typeof job.dedupe_key !== 'string' || !job.dedupe_key.startsWith('repair:')) continue;
        const op = parsedJob(job); if (!op) throw Error(); repairs.push(op);
      }
      const matching = repairs.filter(op => sameBinding(e.op, op));
      if (matching.length > 1 || matching.length === 1 && !receipt(e, payload.jobs.find(job => job.id === matching[0].job_id))) throw Error();
      for (const op of repairs) if (!sameBinding(e.op, op) && !TERMINAL.has(op.status)) adopt(op);
      if (matching.length) return;
      unknown(e, 'The previous verification outcome is unconfirmed. No matching retained job was found.');
      e.restartable = !!allowRestart && !repairs.some(op => !TERMINAL.has(op.status));
      emit(e);
    } catch {
      if (!destroyed) unknown(e, 'Preview verification status could not be confirmed. Check status again.');
    }
  }
  async function lookup(e) {
    if (!e.op.job_id) { await listFor(e, true); return; }
    try {
      const payload = await api(`/api/jobs/${encodeURIComponent(e.op.job_id)}`);
      if (!destroyed && !receipt(e, payload?.job)) unknown(e, 'Preview verification returned an invalid or mismatched job receipt. Check status again.');
    } catch (error) {
      if (destroyed || TERMINAL.has(e.op.status)) return;
      unknown(e, 'Preview verification status could not be confirmed. Check status again.');
      if (Number(error?.status) === 404) await listFor(e, true);
    }
  }
  function checkEntry(e) {
    if (!e || destroyed || !activeEntry(e) || !e.submitted) return Promise.resolve(snapshot(e));
    if (e.flight) return e.flight;
    if (e.pending) return Promise.resolve(snapshot(e));
    stop(e); e.pending = true; e.restartable = false; emit(e);
    const work = lookup(e).finally(() => {
      if (e.flight === work) { e.flight = null; e.pending = false; emit(e); poll(e); }
    }).then(() => snapshot(e));
    e.flight = work;
    return work;
  }
  async function runStart(e) {
    try {
      const prepared = await prepare(e.op.project_id, e.op.asset_id, e.op.operation_token);
      if (destroyed || TERMINAL.has(e.op.status)) return snapshot(e);
      if (!validBinding(prepared) || prepared.project_id !== e.op.project_id || prepared.asset_id !== e.op.asset_id
          || prepared.operation_token !== e.op.operation_token) throw Error('The saved asset revision could not be confirmed.');
      e.context = prepared.context; e.op.expected_revision = prepared.expected_revision;
      readStored(); if (readIssue) throw Error(readIssue);
      if ([...entries.values()].some(other => other !== e && other.op.project_id === e.op.project_id && activeEntry(other))) throw Error('Resolve the active preview verification for this project first.');
      e.submitted = true;
      try { persist(); } catch (error) { e.submitted = false; throw error; }
      e.pending = true; e.op.message = 'Submitting preview verification...'; emit(e);
      // No asynchronous boundary is allowed between admission and the one POST.
      // Notify first: a host callback may synchronously change the current view.
      const permitted = admit(Object.freeze(binding(e.op)), e.context);
      if (permitted !== true) { if (permitted?.then) Promise.resolve(permitted).catch(() => {}); throw Error('The project or asset changed before preview verification. Review it and try again.'); }
      if (destroyed || TERMINAL.has(e.op.status)) return snapshot(e);
      try {
        const request = api(`/api/projects/${encodeURIComponent(e.op.project_id)}/assets/${encodeURIComponent(e.op.asset_id)}/repair-preview`,
          {method:'POST', body:JSON.stringify({expected_revision:e.op.expected_revision, operation_token:e.op.operation_token})});
        // Preparing is exempt from the host's save guard so its own flush can
        // finish. Once POST is dispatched, fence editing until admission is known.
        e.op = {...e.op, status:'unknown', message:'The preview verification request is awaiting confirmation.'};
        emit(e);
        const payload = await request;
        if (!destroyed && !receipt(e, payload?.job)) {
          unknown(e, 'The verification response could not be confirmed. Checking retained jobs.');
          await listFor(e, true);
        }
      } catch (error) {
        if (!destroyed && !TERMINAL.has(e.op.status)) {
          const status = Number(error?.status);
          if (status >= 400 && status < 500 && !e.known) reject(e, error, ERROR_CODES.has(errorCode(error?.message)) ? errorCode(error.message) : 'repair_rejected');
          else { unknown(e, 'The verification outcome is unconfirmed. Checking retained jobs.'); await listFor(e, true); }
        }
      }
    } catch (error) { reject(e, error); }
    finally { e.pending = false; emit(e); poll(e); }
    return snapshot(e);
  }
  async function start(projectId, assetId) {
    if (destroyed) throw Error('Preview repair controller is closed.');
    if (!matches(PROJECT, projectId) || !matches(ASSET, assetId)) throw Error('Choose a valid imported asset.');
    readStored(); if (readIssue) throw Error(readIssue);
    const current = forEntry(projectId, assetId);
    if (current?.settling) return snapshot(current);
    const restart = current && activeEntry(current) && snapshot(current).canRestart;
    if (current && activeEntry(current) && !restart) return snapshot(current);
    if ([...entries.values()].some(e => e !== current && e.op.project_id === projectId && activeEntry(e))) throw Error('Resolve the active preview verification for this project first.');
    const operationToken = token();
    if (!matches(TOKEN, operationToken) || entries.has(operationToken)) throw Error('A unique valid verification token is required.');
    if (storageIssue) persist();
    if (restart) { current.superseded = true; current.earlier = true; current.context = undefined; stop(current); }
    const e = newEntry(local({project_id:projectId, asset_id:assetId, expected_revision:null, operation_token:operationToken}, 'preparing', 'Saving before preview verification...'));
    entries.set(operationToken, e); emit(e);
    const work = runStart(e); e.flight = work;
    try { return await work; } finally { if (e.flight === work) e.flight = null; poll(e); }
  }
  function cancel(projectId, assetId) {
    const e = forEntry(projectId, assetId);
    if (!e || destroyed) return Promise.resolve(snapshot(e));
    if (e.op.status === 'preparing' && !e.submitted) {
      e.op = {...e.op, status:'cancelled', message:'Cancelled before preview verification was submitted.', cancel_requested:true};
      finish(e); return Promise.resolve(snapshot(e));
    }
    if (!snapshot(e).canCancel) return Promise.resolve(snapshot(e));
    stop(e); e.pending = true; e.restartable = false; emit(e);
    const work = (async () => {
      try {
        const payload = await api(`/api/jobs/${encodeURIComponent(e.op.job_id)}/cancel`, {method:'POST', body:'{}'});
        if (!destroyed && !receipt(e, payload?.job)) { unknown(e, 'Cancellation is not confirmed. Checking status.'); await lookup(e); }
      } catch { if (!destroyed) { unknown(e, 'Cancellation is not confirmed. Checking status.'); await lookup(e); } }
    })().finally(() => {
      if (e.flight === work) { e.flight = null; e.pending = false; emit(e); poll(e); }
    }).then(() => snapshot(e));
    e.flight = work; return work;
  }
  function observe(jobs) {
    if (destroyed || !Array.isArray(jobs)) return [];
    const accepted = [];
    for (const job of jobs) {
      const op = parsedJob(job);
      if (!op) continue;
      // Old terminal history is not a new intent. Prefer the newest retained job
      // (the jobs endpoint is newest first), and never replace a local operation.
      if (!entries.has(op.operation_token) && TERMINAL.has(op.status) && forEntry(op.project_id, op.asset_id)) continue;
      const result = adopt(op); if (result) accepted.push(result);
    }
    for (const e of entries.values()) if (activeEntry(e) && e.timer === null) poll(e);
    return accepted;
  }
  readStored();
  return {start, check:(p, a) => checkEntry(forEntry(p, a)), cancel,
    forAsset:(p, a) => snapshot(forEntry(p, a)),
    active:projectId => [...entries.values()].filter(e => activeEntry(e) && (projectId === undefined || e.op.project_id === projectId)).map(snapshot),
    observe,
    destroy() { if (destroyed) return; destroyed = true; for (const e of entries.values()) { stop(e); e.settling = false; e.context = undefined; } }};
}
