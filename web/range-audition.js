// Read-only transport. The native edited preview owns decoding, sound, seeks and its
// single animation clock. This controller never creates media, intervals or API calls.
function eligible(s) {
  if (!s || !s.editor || !s.id || !Number.isInteger(s.revision) || !Number.isFinite(s.duration) || s.duration <= 0)
    return 'Open a saved timeline to loop an edited range.';
  if (!s.editMode) return 'Choose Edited video to loop the timeline, not the original recording.';
  if (s.busy) return 'Finish the current operation before looping a range.';
  if (s.dirtyRange) return 'Apply or cancel the time entry before looping.';
  if (s.occurrence || !Number.isFinite(s.start) || !Number.isFinite(s.end) || s.start < 0 || s.end > s.duration || s.end <= s.start)
    return 'Mark a range on the timeline to audition the edited picture and mix.';
  // Tighter windows cannot usefully audition the browser's asynchronously seeking players.
  if (s.end - s.start < .25 - 1e-9) return 'Mark at least a quarter second to loop.';
  return '';
}
function sameRange(a, b) {
  return a.id === b.id && a.revision === b.revision && a.view === b.view && a.duration === b.duration
    && a.start === b.start && a.end === b.end;
}

export function initRangeAudition(bar, { snapshot, seek, play, pause, isPlaying, format, ready, notice, now = () => performance.now() }) {
  const doc = bar?.ownerDocument;
  if (!doc || !bar.querySelector('.timeline-timecode-form')) return null;
  const button = doc.createElement('button');
  button.id = 'timelineLoopRange'; button.type = 'button'; button.textContent = 'Loop range';
  button.setAttribute('aria-label', 'Loop range');
  bar.insertBefore(button, bar.querySelector('.timeline-timecode-form'));
  let ticket = null, destroyed = false, preparing = false, started = 0;
  function prepare() { preparing = typeof ready === 'function'; if (preparing) started = now(); }

  function paint(s = snapshot()) {
    const issue = eligible(s), active = Boolean(ticket);
    button.hidden = !s?.editor;
    button.disabled = !active && Boolean(issue);
    button.setAttribute('aria-pressed', String(active));
    button.title = active ? 'Stop looping the selected range and pause here.'
      : issue || `Loop ${format(s.start)} to ${format(s.end)} in the edited picture and mix. Click again or press Pause to stop.`;
  }
  function clear() {
    if (!ticket) return;
    ticket = null; preparing = false; paint();
  }
  function sync() {
    if (destroyed) return;
    const s = snapshot();
    if (ticket && (eligible(s) || !sameRange(ticket, s))) {
      ticket = null; preparing = false; paint(s); pause(); return;
    }
    paint(s);
  }
  function toggle() {
    if (destroyed) return;
    if (ticket) { clear(); pause(); return; }
    const s = snapshot();
    if (eligible(s)) { paint(s); return; }
    // Starting while ordinary playback runs should seek, not start a second clock.
    const owner = ticket = s;
    prepare(); // Native players seek once while paused, even if ordinary playback was running.
    seek(s.start);
    const after = snapshot();
    if (ticket !== owner || eligible(after) || !sameRange(s, after)) { clear(); paint(after); return; }
    paint(after);
    const failed = () => { if (ticket === owner) { clear(); pause(); } };
    try { Promise.resolve(play()).then(() => { if (ticket === owner && !isPlaying()) clear(); }, failed); }
    catch { failed(); }
  }
  function next(time) {
    if (!ticket) return null;
    const s = snapshot();
    if (eligible(s) || !sameRange(ticket, s) || !Number.isFinite(time) || time < ticket.start - 1e-6) {
      clear(); return false; // The host must pause before presenting a different edit.
    }
    if (preparing) {
      const at = ticket.start;
      let readyState;
      try { readyState = ready(); } catch { readyState = null; }
      if (readyState !== true) {
        if (readyState === false && now() - started < 5000) return { at, hold: true };
        clear();
        notice?.('The selected media is not ready to loop. Playback paused. Check its preview or choose a longer range.');
        return false;
      }
      preparing = false;
      return { at, hold: false }; // Resume every layer on the same edit clock.
    }
    // Restart at In, never skip its first frames after a late/background tick.
    if (time >= ticket.end) { prepare(); return ticket.start; }
    return null;
  }
  const onHide = () => { if (ticket && doc.hidden) { clear(); pause(); } };
  button.addEventListener('click', toggle);
  doc.addEventListener('visibilitychange', onHide);
  paint();
  return { clear, sync, next, get preparing() { return preparing; }, destroy() {
    if (destroyed) return; destroyed = true;
    if (ticket) { clear(); pause(); }
    button.removeEventListener('click', toggle);
    doc.removeEventListener('visibilitychange', onHide);
    button.remove();
  } };
}
