// Frame-only viewer gestures. The host owns saved geometry, readiness and the
// revision-pinned transaction; this module never writes project/clip objects.
const EDGES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
const EPSILON = 1e-9;
const BOUNDS_EPSILON = 1e-8;
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const sameRect = (a, b) => ['x', 'y', 'w', 'h'].every(key => Math.abs(a[key] - b[key]) <= EPSILON);

export function validMediaFrame(rect) {
  return Boolean(rect && ['x', 'y', 'w', 'h'].every(key => typeof rect[key] === 'number' && Number.isFinite(rect[key]))
    && rect.x >= 0 && rect.y >= 0 && rect.x <= 1 && rect.y <= 1
    && rect.w >= .01 && rect.h >= .01 && rect.w <= 1 && rect.h <= 1
    && rect.x + rect.w <= 1 + BOUNDS_EPSILON && rect.y + rect.h <= 1 + BOUNDS_EPSILON);
}

export function dragMediaFrame(rect, handle, dx, dy) {
  if (!validMediaFrame(rect) || !['move', ...EDGES].includes(handle) || !Number.isFinite(dx) || !Number.isFinite(dy)) return null;
  const {x, y, w, h} = rect;
  if (handle === 'move') return {x: clamp(x + dx, 0, 1 - w), y: clamp(y + dy, 0, 1 - h), w, h};
  const left = handle.includes('w') ? clamp(x + dx, 0, x + w - .01) : x;
  const top = handle.includes('n') ? clamp(y + dy, 0, y + h - .01) : y;
  const right = handle.includes('e') ? clamp(x + w + dx, x + .01, 1) : x + w;
  const bottom = handle.includes('s') ? clamp(y + h + dy, y + .01, 1) : y + h;
  return {x: left, y: top, w: Math.max(.01, right - left), h: Math.max(.01, bottom - top)};
}

export function initMediaFrameEditor(stage, {snapshot, preview, commit, changed = () => {}} = {}) {
  const doc = stage.ownerDocument, win = doc.defaultView;
  const root = doc.createElement('div'), box = doc.createElement('div'), label = doc.createElement('span');
  root.className = 'media-frame-editor'; root.hidden = true; root.tabIndex = -1;
  root.setAttribute('role', 'group');
  root.setAttribute('aria-label', 'Edit picture frame. Drag to move or resize. Use the inspector percentage fields for keyboard editing. Escape cancels.');
  box.className = 'media-frame-box'; box.dataset.frameHandle = 'move';
  label.className = 'media-frame-label'; label.textContent = 'Frame'; label.setAttribute('aria-hidden', 'true');
  box.append(label);
  for (const edge of EDGES) {
    const handle = doc.createElement('span');
    handle.className = 'media-frame-handle'; handle.dataset.frameHandle = edge;
    handle.setAttribute('aria-hidden', 'true'); handle.title = `Resize frame (${edge.toUpperCase()})`;
    box.append(handle);
  }
  root.append(box); stage.append(root);
  let active = false, pending = false, gesture = null, saved = null, issue = '', destroyed = false;
  let previewId = null, inHost = false, syncing = false, epoch = 0, lastNotice = '', previousFocus = null;
  const listeners = [];
  const listen = (target, type, fn, options) => {
    target.addEventListener(type, fn, options);
    listeners.push(() => target.removeEventListener(type, fn, options));
  };
  const notify = () => {
    const state = {active, pending, dragging: Boolean(gesture?.moved), issue};
    const notice = JSON.stringify(state);
    if (notice !== lastNotice) { lastNotice = notice; changed(state); }
  };
  const read = () => {
    try { const value = snapshot?.() || {}; return {...value, rect: value.rect ? {...value.rect} : null}; }
    catch { return {issue: 'Frame readiness could not be confirmed.'}; }
  };
  const valid = state => Boolean(state.projectId && state.clipId && typeof state.token === 'string' && validMediaFrame(state.rect) && !state.issue);
  const identity = state => `${state.projectId}\n${state.clipId}`;
  const viewport = () => {
    const bounds = stage.getBoundingClientRect();
    return {left: bounds.left + stage.clientLeft, top: bounds.top + stage.clientTop, width: stage.clientWidth, height: stage.clientHeight};
  };
  const sameViewport = (a, b) => ['left', 'top', 'width', 'height'].every(key => Math.abs(a[key] - b[key]) < .1);
  const paint = rect => {
    if (validMediaFrame(rect)) for (const [key, property] of [['x', 'left'], ['y', 'top'], ['w', 'width'], ['h', 'height']]) box.style[property] = `${rect[key] * 100}%`;
    root.dataset.state = pending ? 'pending' : gesture?.moved ? 'dragging' : saved?.busy ? 'busy' : 'ready';
    root.setAttribute('aria-busy', String(pending || Boolean(saved?.busy)));
  };
  const callPreview = (id, rect) => {
    inHost = true;
    try { return preview?.(id, rect); }
    finally { inHost = false; }
  };
  const clearPreview = () => {
    const id = previewId; previewId = null;
    if (id) { try { callPreview(id, null); } catch { /* saved geometry remains authoritative */ } }
  };
  const release = item => {
    if (item && box.hasPointerCapture?.(item.pointerId)) box.releasePointerCapture(item.pointerId);
  };
  const cancelGesture = (reason = '') => {
    const item = gesture; gesture = null; release(item); clearPreview(); issue = reason;
    if (active) paint(read().rect); notify();
  };
  const hide = (reason = '') => {
    active = false; epoch++; issue = reason;
    const restoreFocus = root.contains(doc.activeElement);
    cancelGesture(reason); root.hidden = true; stage.classList.remove('media-frame-editing'); saved = null;
    if (restoreFocus && previousFocus?.isConnected) previousFocus.focus({preventScroll: true});
    previousFocus = null; notify();
  };
  const sync = () => {
    if (destroyed || inHost || syncing || !active) return;
    syncing = true;
    try {
      const next = read();
      if (!valid(next) || identity(next) !== identity(saved)) { hide(next.issue || 'The selected frame changed.'); return; }
      if (gesture && (next.busy || next.token !== gesture.token || !sameViewport(viewport(), gesture.viewport))) {
        cancelGesture(next.busy ? 'Wait for current edits to finish.' : 'The viewer or edit changed. Drag again.');
      }
      saved = next;
      paint(gesture?.rect || (pending && previewId ? null : next.rect)); notify();
    } finally { syncing = false; }
  };
  const open = () => {
    if (destroyed || pending) return false;
    const next = read(), view = viewport();
    if (!valid(next) || next.busy || view.width <= 0 || view.height <= 0) { issue = next.issue || 'Wait for the edited viewer to be ready.'; notify(); return false; }
    if (active) { sync(); return active; }
    saved = next; issue = ''; previousFocus = doc.activeElement;
    active = true; epoch++; root.hidden = false; stage.classList.add('media-frame-editing');
    paint(next.rect); root.focus({preventScroll: true}); notify(); return true;
  };
  const close = () => {
    if (pending) return false;
    hide(); return true;
  };
  const currentGesture = item => {
    const now = read();
    return active && valid(now) && !now.busy && identity(now) === item.identity && now.token === item.token && sameViewport(viewport(), item.viewport);
  };
  const down = event => {
    if (event.button !== 0 || event.isPrimary === false || pending || gesture) return;
    const target = event.target.closest?.('[data-frame-handle]');
    if (!target || !box.contains(target)) return;
    sync();
    if (!active || saved?.busy) return;
    const view = viewport(); if (view.width <= 0 || view.height <= 0) return;
    issue = '';
    gesture = {pointerId: event.pointerId, handle: target.dataset.frameHandle, viewport: view, token: saved.token,
      identity: identity(saved), clipId: saved.clipId, original: {...saved.rect}, rect: {...saved.rect}, x: event.clientX, y: event.clientY, moved: false};
    box.setPointerCapture?.(event.pointerId); root.focus({preventScroll: true});
    event.preventDefault(); event.stopPropagation(); notify();
  };
  const move = event => {
    const item = gesture;
    if (!item || event.pointerId !== item.pointerId) return;
    event.preventDefault(); event.stopPropagation();
    if (!currentGesture(item)) { cancelGesture('The viewer or edit changed. Drag again.'); sync(); return; }
    const dx = event.clientX - item.x, dy = event.clientY - item.y;
    if (!item.moved && Math.hypot(dx, dy) < 3) return;
    const candidate = dragMediaFrame(item.original, item.handle, dx / item.viewport.width, dy / item.viewport.height);
    if (!candidate) { cancelGesture('This frame could not be adjusted.'); return; }
    let result;
    // Mark ownership before invoking the host: its preview may synchronously sync.
    previewId = item.clipId;
    try { result = callPreview(item.clipId, candidate); }
    catch { result = {issue: 'This frame could not be previewed.'}; }
    if (result?.issue || !validMediaFrame(result?.rect)) { cancelGesture(result?.issue || 'This frame could not be previewed.'); return; }
    item.rect = {...result.rect}; item.moved = true; paint(item.rect); notify();
  };
  const up = event => {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    move(event);
    const item = gesture; if (!item) return;
    if (!currentGesture(item)) { cancelGesture('The viewer or edit changed. Drag again.'); sync(); return; }
    gesture = null; release(item);
    if (!item.moved || sameRect(item.rect, item.original)) { clearPreview(); paint(read().rect); notify(); return; }
    pending = true; issue = ''; const generation = epoch; paint(item.rect); notify();
    // One release, one native transaction. Keep the transient picture until the
    // host settles, without optimistically altering saved geometry/history.
    void (async () => {
      try {
        const result = await commit(item.clipId, {...item.rect}, item.token);
        if (!result && epoch === generation) issue = 'Frame was not saved. Drag again when the edit is ready.';
      } catch (error) {
        if (epoch === generation) issue = error?.message || 'Frame could not be saved.';
      } finally {
        pending = false; clearPreview();
        if (!destroyed) { sync(); notify(); }
      }
    })();
  };
  const cancelPointer = event => {
    if (gesture && event.pointerId === gesture.pointerId) { cancelGesture(); sync(); }
  };
  listen(box, 'pointerdown', down);
  listen(box, 'pointermove', move);
  listen(box, 'pointerup', up);
  listen(box, 'pointercancel', cancelPointer);
  listen(box, 'lostpointercapture', cancelPointer);
  listen(win, 'keydown', event => {
    if (!active || event.key !== 'Escape' || event.target?.closest?.('input,textarea,select,[contenteditable=true],dialog')) return;
    event.preventDefault(); event.stopPropagation();
    if (pending) return;
    if (gesture) cancelGesture(); else close();
  }, true);
  listen(win, 'blur', () => { if (gesture) cancelGesture(); });
  listen(win, 'resize', sync);
  listen(win, 'scroll', sync, true);
  const observer = typeof win.ResizeObserver === 'function' ? new win.ResizeObserver(sync) : null;
  observer?.observe(stage);
  return {
    open, close, sync,
    get active() { return active; }, get pending() { return pending; },
    destroy() {
      if (destroyed) return;
      hide(); destroyed = true; observer?.disconnect(); listeners.forEach(remove => remove()); root.remove();
    },
  };
}
