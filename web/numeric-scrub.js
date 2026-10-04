// Stage numeric gestures in the control, then use its existing save path once.
// This keeps a long drag (or a wheel burst) a single undoable edit.
export function numericStep(field) {
  const step = Number(field.step);
  return Number.isFinite(step) && step > 0 ? step : 1;
}

export function steppedValue(field, value, steps) {
  const step = numericStep(field);
  const min = field.min === '' ? -Infinity : Number(field.min);
  const max = field.max === '' ? Infinity : Number(field.max);
  const base = Number.isFinite(min) ? min : Number(field.getAttribute('value')) || 0;
  const next = base + Math.round((value + steps * step - base) / step) * step;
  return String(Number(Math.max(Number.isFinite(min) ? min : -Infinity,
    Math.min(Number.isFinite(max) ? max : Infinity, next)).toFixed(10)));
}

export function initNumericScrub({document:doc = document, window:win = window, canEdit = () => true, context = () => '', onCommit = () => {}} = {}) {
  let gesture = null, wheelTimer = null;
  const listeners = [];
  const listen = (target, type, fn, options) => {
    target.addEventListener(type, fn, options);
    listeners.push(() => target.removeEventListener(type, fn, options));
  };
  const control = target => {
    if (target?.matches?.('input[type=number],input[type=range]')) return target;
    if (target?.matches?.('output')) return target.closest('label')?.querySelector('input[type=range]') || null;
    return null;
  };
  const available = field => field?.isConnected && !field.disabled && !field.readOnly
    && !field.matches(':disabled') && !field.closest('[hidden],[inert]') && canEdit()
    && field.value !== '' && Number.isFinite(Number(field.value));
  const sameContext = item => item.context === context();
  const show = (item, value) => {
    item.field.value = value;
    if (item.output) item.output.textContent = item.outputText.replace(/-?\d+(?:\.\d+)?/, Number(Number(value) * item.displayScale).toFixed(item.displayDecimals));
  };
  const finish = (commit = false) => {
    const item = gesture;
    if (!item) return;
    gesture = null; win.clearTimeout(wheelTimer); wheelTimer = null;
    doc.documentElement.classList.remove('numeric-scrubbing');
    if (item.pointerId !== undefined && item.field.hasPointerCapture?.(item.pointerId)) item.field.releasePointerCapture(item.pointerId);
    const current = sameContext(item);
    if (commit && current && available(item.field) && item.changed && item.field.value !== item.original) {
      // Input handles preview/draft-only controls; change handles committed fields.
      item.field.dispatchEvent(new win.Event('input', {bubbles:true}));
      item.field.dispatchEvent(new win.Event('change', {bubbles:true}));
      onCommit(item.field);
    } else if (current && item.changed) show(item, item.original);
  };
  const start = (field, kind, handle = field) => {
    finish(true);
    const output = handle.matches?.('output') ? handle : field.closest('label')?.querySelector('output');
    const outputText = output?.textContent || '', shown = outputText.match(/-?\d+(?:\.\d+)?/)?.[0];
    const displayScale = Number(field.value) && shown !== undefined ? Number(shown) / Number(field.value)
      : outputText.includes('%') && Number(field.max) <= 1 ? 100 : 1;
    return gesture = {field, kind, output, outputText:output?.textContent || '', original:field.value,
      displayScale:displayScale || 1, displayDecimals:shown?.split('.')[1]?.length || 0,
      context:context(), remainder:0, changed:false, active:false};
  };
  const advance = (item, units) => {
    item.remainder += units;
    const steps = Math.trunc(item.remainder);
    if (!steps) return;
    item.remainder -= steps;
    const next = steppedValue(item.field, Number(item.field.value), steps);
    if (next !== item.field.value) { show(item,next); item.changed = true; }
  };
  listen(doc, 'pointerdown', event => {
    const field = control(event.target);
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || !available(field)) return;
    // Horizontal range dragging and native number steppers keep their own behavior.
    if (field.type === 'range' && event.target === field) return;
    if (field.type === 'number' && event.target === field) {
      const rect = field.getBoundingClientRect();
      if (doc.documentElement.dir === 'rtl' ? event.clientX < rect.left + 18 : event.clientX > rect.right - 18) return;
    }
    const item = start(field,'drag',event.target);
    item.pointerId = event.pointerId; item.startY = item.lastY = event.clientY;
    if (event.target !== field) { event.preventDefault(); field.focus({preventScroll:true}); }
  }, true);
  listen(doc, 'pointermove', event => {
    const item = gesture;
    if (!item || item.kind !== 'drag' || item.pointerId !== event.pointerId) return;
    if (!available(item.field) || !sameContext(item)) { finish(false); return; }
    if (!item.active && Math.abs(event.clientY - item.startY) < 4) return;
    if (!item.active) {
      item.active = true; item.field.setPointerCapture?.(item.pointerId);
      doc.documentElement.classList.add('numeric-scrubbing');
    }
    event.preventDefault();
    advance(item, (item.lastY - event.clientY) / (event.shiftKey ? 40 : 4));
    item.lastY = event.clientY;
  }, {capture:true, passive:false});
  listen(doc, 'pointerup', event => {
    if (gesture?.kind !== 'drag' || gesture.pointerId !== event.pointerId) return;
    if (gesture.active) event.preventDefault();
    finish(true);
  }, true);
  for (const type of ['pointercancel','lostpointercapture']) listen(doc,type,event => {
    if (gesture?.kind === 'drag' && gesture.pointerId === event.pointerId) finish(false);
  }, true);
  listen(doc, 'wheel', event => {
    const field = control(event.target);
    if (!available(field) || doc.activeElement !== field || event.ctrlKey || event.metaKey || event.altKey
      || !event.deltaY || Math.abs(event.deltaX || 0) > Math.abs(event.deltaY) || gesture?.kind === 'drag') return;
    event.preventDefault();
    let item = gesture;
    if (!item || item.field !== field || !sameContext(item)) item = start(field,'wheel',event.target);
    const pixels = event.deltaY * (event.deltaMode === 1 ? 40 : event.deltaMode === 2 ? 400 : 1);
    advance(item, -pixels / (event.shiftKey ? 1000 : 100));
    win.clearTimeout(wheelTimer); wheelTimer = win.setTimeout(() => finish(true), 300);
  }, {capture:true, passive:false});
  listen(doc,'keydown',event => {
    if (!gesture) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); finish(false); }
    else if (gesture.kind === 'wheel') finish(true);
  }, true);
  listen(doc,'focusout',event => {
    if (gesture?.field === event.target) finish(gesture.kind === 'wheel');
  }, true);
  listen(win,'blur',() => finish(false));
  listen(doc,'visibilitychange',() => { if (doc.hidden) finish(false); });
  return {cancel:() => finish(false), destroy() { finish(false); listeners.forEach(remove => remove()); }};
}
