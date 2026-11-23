// First recording is an editor-only view. The media library still owns all
// validation, reservations, progress, cancellation and project writes.
export function needsFirstRecording(project, editorOpen, retained = false) {
  return Boolean(editorOpen && project?.id && project.settings?.workflow === 'manual'
    && !project.sources?.A && !project.sources?.B && !project.draft && !project.editor_sequence && !retained);
}

export function initFirstRecordingGuide(root, { snapshot, importFiles, notice = () => '' }) {
  if (!root) return null;
  const choose = root.querySelector('[data-first-choose]'), picker = root.querySelector('input[type=file]');
  const status = root.querySelector('[data-first-status]');
  if (!choose || !picker || !status) return null;
  const listeners = [];
  const on = (node, type, fn) => { node.addEventListener(type, fn); listeners.push(() => node.removeEventListener(type, fn)); };
  let owner = null, view = null, pickerOwner = null, dragOwner = null, pending = null, message = '', disposed = false;
  const sync = () => {
    if (disposed) return null;
    const s = snapshot();
    const id = needsFirstRecording(s.project, s.open, s.retained) ? s.project.id : null;
    if (owner !== id || view !== s.view) {
      owner = id; view = s.view; pickerOwner = null; dragOwner = null; pending = null; message = '';
      delete root.dataset.dragging;
    }
    root.hidden = !owner;
    const busy = Boolean(owner && (pending || s.busy));
    choose.disabled = !owner || busy;
    const text = !owner ? '' : pending ? 'Importing your recording. The timeline opens when it is ready.'
      : busy ? 'Wait for the current operation to finish.' : message;
    if (text !== status.textContent) status.textContent = text;
    return owner ? {id: owner, view} : null;
  };
  const matches = (a, b) => Boolean(a && b && a.id === b.id && a.view === b.view);
  const importSelection = async (files, origin) => {
    const current = sync(), items = Array.from(files || []);
    if (!matches(origin, current) || choose.disabled || !items.length) return;
    const request = {}; pending = request; message = ''; sync();
    let resultText = '';
    try {
      const queue = await importFiles(items);
      const problem = queue?.items?.find(row => row.status === 'failed' || row.status === 'cancelled');
      resultText = problem?.message || (queue?.stopRequested ? queue.reason : '') || (!queue ? notice() || 'The recording was not imported. Try another video.' : '');
    } catch (error) { resultText = error?.message || 'The recording was not imported. Try again.'; }
    finally {
      if (!disposed && matches(current, sync()) && pending === request) {
        pending = null; message = resultText; sync();
      }
    }
  };
  on(choose, 'click', () => {
    const current = sync();
    if (!current || choose.disabled) return;
    pickerOwner = current; picker.value = ''; picker.click();
  });
  on(picker, 'change', () => {
    const origin = pickerOwner, files = Array.from(picker.files || []); pickerOwner = null; picker.value = '';
    void importSelection(files, origin);
  });
  on(picker, 'cancel', () => { pickerOwner = null; });
  const localFiles = e => Array.from(e.dataTransfer?.types || []).includes('Files');
  const drag = e => {
    if (!localFiles(e)) return;
    const current = sync(); if (!current) return;
    e.preventDefault(); e.stopPropagation();
    if (!dragOwner) dragOwner = current;
    e.dataTransfer.dropEffect = choose.disabled ? 'none' : 'copy';
    if (!choose.disabled) root.dataset.dragging = 'true';
  };
  on(root, 'dragenter', drag); on(root, 'dragover', drag);
  on(root, 'dragleave', e => { if (!root.contains(e.relatedTarget)) { delete root.dataset.dragging; dragOwner = null; } });
  on(root, 'drop', e => {
    if (!localFiles(e)) return;
    const current = sync(); if (!current) return;
    e.preventDefault(); e.stopPropagation();
    const origin = dragOwner || current; dragOwner = null; delete root.dataset.dragging;
    void importSelection(e.dataTransfer.files, origin);
  });
  sync();
  return {sync, destroy() { disposed = true; pending = null; pickerOwner = null; dragOwner = null; listeners.forEach(off => off()); root.hidden = true; delete root.dataset.dragging; }};
}
