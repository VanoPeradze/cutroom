/* Batch: hand CUTROOM several recordings (for example before bed) and get a
   project for each with its transcript, a first edit and the Clips board.
   Each recording becomes its own project; they run one after another so the
   computer is never asked to do two heavy jobs at once. Everything stays on
   this computer. The page has to stay open while the queue runs; a job that
   has already started finishes on its own. */

export const GOALS = [
  { value: 'clean', label: 'Clean up: remove pauses and mistakes (no Story AI needed)' },
  { value: 'short', label: 'Short: a vertical edit of the best part' },
  { value: 'youtube', label: 'YouTube: a full-length edit' },
  { value: 'podcast', label: 'Podcast: a long conversation' },
];
const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'interrupted']);
const CARRY = ['aspect', 'pace', 'caption_style', 'caption_position', 'caption_scale', 'caption_accent', 'quality', 'resolution', 'spoken_language'];

/** Settings for every new project: the chosen goal plus the look of the open project. */
export function batchSettings(goal, current = {}) {
  const out = { goal: GOALS.some((g) => g.value === goal) ? goal : 'clean' };
  for (const key of CARRY) if (current?.[key] !== undefined && current[key] !== null && current[key] !== '') out[key] = current[key];
  // A style belongs to its goal; only keep it when the goal is the same.
  if (current?.edit_style && current.goal === out.goal) out.edit_style = current.edit_style;
  if (out.goal === 'short' && !current?.aspect) out.aspect = '9:16';
  if ((out.goal === 'youtube' || out.goal === 'podcast') && out.aspect === '9:16' && current?.goal !== out.goal) out.aspect = '16:9';
  return out;
}

/** "Interview take 2.mp4" → "Interview take 2". */
export function projectName(fileName) {
  return String(fileName || 'Recording').replace(/\.[a-z0-9]{2,5}$/i, '').replace(/[_]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120) || 'Recording';
}

export function summary(rows) {
  const done = rows.filter((r) => r.state === 'done').length, failed = rows.filter((r) => r.state === 'failed').length;
  const left = rows.length - done - failed;
  return [done && `${done} ready`, failed && `${failed} need attention`, left && `${left} waiting`].filter(Boolean).join(' · ');
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Runs one recording: create → import → prepare → (optional) edit.
 * `host` supplies api(path, options) and uploadSourceTo(projectId, file, onProgress).
 * `report(row)` is called on every change. Returns the row.
 */
export async function runOne(host, row, { settings, draft = true, poll = 1500, cancelled = () => false } = {}) {
  const set = (patch) => { Object.assign(row, patch); row.report?.(row); };
  const follow = async (job, label) => {
    let current = job;
    while (current && !TERMINAL.has(current.status)) {
      if (cancelled()) throw new Error('Stopped');
      set({ detail: `${label}${current.progress ? ` ${Math.round(current.progress * 100)}%` : ''}` });
      await wait(poll);
      current = (await host.api(`/api/jobs/${encodeURIComponent(current.id)}`)).job;
    }
    if (current && current.status !== 'completed') throw new Error(current.error || current.message || `${label} did not finish`);
  };
  try {
    set({ state: 'running', detail: 'Creating project' });
    const created = await host.api('/api/projects', { method: 'POST', body: JSON.stringify({ name: projectName(row.file.name), initial_settings: settings }) });
    const id = created.project.id;
    set({ projectId: id, detail: 'Importing 0%' });
    const imported = await host.uploadSourceTo(id, row.file, (value) => set({ detail: `Importing ${Math.round((Number(value) || 0) * 100)}%` }));
    if (cancelled()) throw new Error('Stopped');
    let job = imported?.job || null;
    if (!job && imported?.preparation_deferred) {
      await wait(1200);
      job = (await host.api(`/api/projects/${encodeURIComponent(id)}/sources/A/prepare`, { method: 'POST' })).job;
    }
    await follow(job, 'Preparing');
    if (draft) {
      set({ detail: 'Transcribing and editing' });
      const started = await host.api(`/api/projects/${encodeURIComponent(id)}/director`, { method: 'POST', body: '{}' });
      await follow(started.job, 'Transcribing and editing');
    }
    let detail = 'Imported and prepared';
    if (draft) {
      const saved = (await host.api(`/api/projects/${encodeURIComponent(id)}`).catch(() => null))?.project;
      const spoken = (saved?.analysis?.segments || []).length;
      detail = spoken ? `Transcript (${spoken} line${spoken === 1 ? '' : 's'}), edit and Clips ready` : 'Edit ready. No speech was found to transcribe.';
    }
    set({ state: 'done', detail });
  } catch (error) {
    set({ state: 'failed', detail: String(error?.message || error || 'Failed') });
  }
  return row;
}

export function initBatch(doc = document) {
  const anchor = doc.getElementById('dialogNewProject');
  if (!anchor || doc.getElementById('batchDialog')) return null;
  const button = doc.createElement('button');
  button.type = 'button'; button.id = 'batchButton'; button.className = 'button ghost full';
  button.textContent = 'Process several recordings…';
  anchor.after(button);

  const dialog = doc.createElement('dialog');
  dialog.id = 'batchDialog';
  dialog.className = 'cleanup-dialog batch-dialog';
  dialog.setAttribute('aria-labelledby', 'batchTitle');
  dialog.innerHTML = `
    <header><h2 id="batchTitle">Process several recordings</h2><button type="button" class="cleanup-close" aria-label="Close">×</button></header>
    <p class="cleanup-intro">Choose recordings and leave the computer on. Each one becomes its own project with a transcript, a first edit and Clips ideas, one after another. Keep this window open until the list is done.</p>
    <div class="batch-options">
      <label class="batch-files button ghost">Choose recordings…<input type="file" accept="video/*,.mkv,.mov,.mp4,.webm,.m4v" multiple hidden></label>
      <label>What to make <select class="batch-goal">${GOALS.map((g) => `<option value="${g.value}">${g.label}</option>`).join('')}</select></label>
      <label class="batch-draft"><input type="checkbox" checked> Transcribe and make a first edit</label>
    </div>
    <ul class="cleanup-list batch-list" aria-label="Recordings"></ul>
    <footer><span class="cleanup-total batch-status" aria-live="polite"></span><button type="button" class="cleanup-cancel">Close</button><button type="button" class="cleanup-apply batch-start" disabled>Start</button></footer>`;
  doc.body.append(dialog);
  const host = () => doc.defaultView.cutroomCleanupHost;
  const $ = (s) => dialog.querySelector(s);
  const input = $('input[type=file]'), list = $('.batch-list'), status = $('.batch-status'), start = $('.batch-start');
  const goal = $('.batch-goal'), draft = $('.batch-draft input'), close = $('.cleanup-cancel');
  let rows = [], running = false, stop = false, lock = null;

  const paint = () => {
    list.replaceChildren(...rows.map((row) => {
      const li = doc.createElement('li'); li.dataset.state = row.state;
      const name = doc.createElement('div'); name.className = 'batch-name'; name.dir = 'auto';
      const strong = doc.createElement('strong'); strong.textContent = row.file.name;
      const small = doc.createElement('small'); small.textContent = row.detail;
      name.append(strong, small);
      li.append(name);
      if (row.state === 'waiting' && !running) {
        const drop = doc.createElement('button'); drop.type = 'button'; drop.textContent = 'Remove';
        drop.addEventListener('click', () => { rows = rows.filter((r) => r !== row); paint(); });
        li.append(drop);
      }
      return li;
    }));
    status.textContent = rows.length ? summary(rows) : '';
    start.disabled = running || !rows.some((r) => r.state === 'waiting');
    start.textContent = running ? 'Working…' : 'Start';
    close.textContent = running ? 'Stop after this one' : 'Close';
  };

  input.addEventListener('change', () => {
    for (const file of input.files || []) {
      const issue = host()?.validateFile?.(file);
      rows.push({ file, state: issue ? 'failed' : 'waiting', detail: issue || 'Waiting', report: paint });
    }
    input.value = '';
    paint();
  });

  start.addEventListener('click', async () => {
    const h = host();
    if (!h || running) return;
    running = true; stop = false; paint();
    try { lock = await doc.defaultView.navigator?.wakeLock?.request?.('screen'); } catch { lock = null; }
    const settings = batchSettings(goal.value, h.project?.()?.settings);
    for (const row of rows) {
      if (stop) break;
      if (row.state !== 'waiting') continue;
      await runOne(h, row, { settings, draft: draft.checked, cancelled: () => false });
      h.refreshProjects?.()?.catch?.(() => {});
    }
    running = false;
    try { await lock?.release?.(); } catch { /* already released */ }
    lock = null;
    paint();
    status.textContent = `${summary(rows)}. Open them from Projects.`;
  });

  close.addEventListener('click', () => { if (running) { stop = true; close.textContent = 'Stopping after this one…'; } else dialog.close(); });
  $('.cleanup-close').addEventListener('click', () => { if (running) stop = true; dialog.close(); });
  dialog.addEventListener('cancel', (e) => { if (running) e.preventDefault(); });
  button.addEventListener('click', () => {
    const current = host()?.project?.()?.settings?.goal;
    if (!running && GOALS.some((g) => g.value === current)) goal.value = current;
    doc.getElementById('projectsDialog')?.close?.();
    paint();
    dialog.showModal();
  });
  return { open: () => button.click() };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initBatch(document), { once: true });
  else initBatch(document);
}
