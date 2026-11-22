// A single named-track level strip. The host owns validation, preview and saving.
// No project mutation, network access or persistence belongs in this controller.
export function initTrackLevelControls(root, {snapshot, change, interaction, stateChanged}) {
  const doc = root.ownerDocument, win = doc.defaultView;
  const make = (tag, cls, text) => {
    const node = doc.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const details = make('details', 'track-level-controls');
  details.dataset.editorShortcuts = 'off';
  const heading = make('summary', 'track-level-heading', 'Named track levels');
  const content = make('div', 'track-level-body');
  const selectorLabel = make('label', 'track-level-selector', 'Named track');
  const selector = make('select'); selector.dataset.trackLevelSelect = ''; selectorLabel.append(selector);
  const members = make('p', 'track-level-members'); members.dataset.trackLevelSummary = '';
  const strip = make('div', 'track-level-strip');
  const rangeLabel = make('label', 'track-level-fader', 'Level');
  const range = make('input'); range.type = 'range'; range.min = '-60'; range.max = '12'; range.step = 'any';
  range.dataset.trackLevelGain = ''; rangeLabel.append(range);
  const numberLabel = make('label', 'track-level-number', 'dB');
  const number = make('input'); number.type = 'number'; number.min = '-60'; number.max = '12'; number.step = 'any'; number.required = true;
  number.dataset.trackLevelNumber = ''; numberLabel.append(number);
  const muteLabel = make('label', 'track-level-mute');
  const mute = make('input'); mute.type = 'checkbox'; mute.dataset.trackLevelMuted = '';
  muteLabel.append(mute, make('span', '', 'Mute'));
  const reset = make('button', 'track-level-reset', '0 dB'); reset.type = 'button'; reset.dataset.trackLevelReset = '';
  reset.title = 'Reset only this track level to 0 dB. Mute is unchanged.';
  strip.append(rangeLabel, numberLabel, muteLabel, reset);
  const help = make('p', 'track-level-help', 'Applies to sound on this named track before role faders and ducking. Source A/B stays in the Original mixer. Normalization and Master still apply.');
  const lockHelp = make('p', 'track-level-help', 'Locks protect clip edits and placement, not track or role levels. These levels are saved and support Undo.');
  const compatibility = make('p', 'track-level-help', 'The first non-default level uses a newer saved track format. Older CUTROOM versions cannot open this upgraded track format. Undo is available.');
  const status = make('p', 'track-level-status'); status.dataset.trackLevelStatus = '';
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  content.append(selectorLabel, members, strip, help, lockHelp, compatibility, status);
  details.append(heading, content); root.append(details);
  let destroyed = false, scopeId = null, scopeView, selected = '', optionKey = '', initialized = false;
  let dirty = false, active = null, message = '', lastState = false, focusTicket = null;
  let syncing = false, resync = false;
  const subscriptions = [];
  const listen = (node, name, fn, options) => {
    node?.addEventListener?.(name, fn, options);
    subscriptions.push(() => node?.removeEventListener?.(name, fn, options));
  };
  function read() {
    try { const s = snapshot(); return s && typeof s === 'object' ? s : {}; }
    catch { return {issue: 'Track levels are unavailable.'}; }
  }
  function tracks(s) { return Array.isArray(s.tracks) ? s.tracks : []; }
  function track(s) { return tracks(s).find(t => t?.id === selected) || null; }
  function level(s) {
    const value = s.levels?.[selected];
    return value && typeof value.gain_db === 'number' && Number.isFinite(value.gain_db)
      && value.gain_db >= -60 && value.gain_db <= 12 && typeof value.muted === 'boolean' ? value : null;
  }
  function pending(s) {
    return typeof s.pendingTrackIds?.has === 'function' ? s.pendingTrackIds.has(selected)
      : Array.isArray(s.pendingTrackIds) && s.pendingTrackIds.includes(selected);
  }
  function scopeMatches(s) { return s.project?.id === scopeId && s.viewToken === scopeView; }
  function isCurrent(s, ticket) {
    return !destroyed && s.project?.id === ticket.projectId && s.viewToken === ticket.viewToken
      && selected === ticket.trackId && Boolean(track(s)) && Boolean(level(s));
  }
  function modelIdentity(s) { try { return JSON.stringify(s.project?.manual?.layer_tracks ?? null); } catch { return ''; } }
  function issue(s) {
    if (!s.project?.id) return 'Open a project to adjust track levels.';
    if (typeof s.issue === 'string' && s.issue) return s.issue;
    if (!Array.isArray(s.tracks)) return 'Saved track levels could not be validated.';
    if (!s.tracks.length) return s.project.manual?.layer_tracks
      ? 'Add a visual or audio track in the Media Tracks section.'
      : 'Enable editable tracks in the Media Tracks section to adjust named-track levels.';
    if (!track(s)) return 'This track is no longer available. Choose another track.';
    if (!level(s)) return 'Saved track levels could not be validated.';
    if (s.busy) return 'Finish the current edit before adjusting track levels.';
    if (pending(s)) return 'Saving this track level.';
    return '';
  }
  function localState() { return dirty || Boolean(active); }
  function notify() {
    const value = localState();
    if (lastState === value) return;
    lastState = value;
    try { stateChanged?.(); } catch { /* Host notification must not discard input. */ }
  }
  function finishFocus() {
    if (!focusTicket) return;
    const ticket = focusTicket, s = read();
    if (!isCurrent(s, ticket) || !ticket.owned || !ticket.node.isConnected) { clearFocus(); return; }
    // The host clears its per-track pending marker before releasing the shared
    // save lock. Keep ownership through that final disabled readiness paint.
    if (pending(s) || ticket.node.disabled) return;
    clearFocus();
    if (doc.activeElement === doc.body && !ticket.node.disabled && ticket.node.getClientRects?.().length)
      ticket.node.focus({preventScroll: true});
  }
  function clearFocus() {
    if (focusTicket) for (const name of ['pointerdown', 'keydown', 'focusin']) doc.removeEventListener?.(name, focusTicket.listener, true);
    focusTicket = null;
  }
  function ownFocus(node, s) {
    clearFocus();
    if (doc.activeElement !== node) return;
    const ticket = {node, projectId: s.project.id, viewToken: s.viewToken, trackId: selected, owned: true};
    ticket.listener = event => {
      if (event.type === 'focusin' ? event.target !== node && event.target !== doc.body : true) ticket.owned = false;
    };
    focusTicket = ticket;
    for (const name of ['pointerdown', 'keydown', 'focusin']) doc.addEventListener?.(name, ticket.listener, true);
  }
  function callInteraction(ticket, phase, value) {
    try { return interaction?.(ticket.trackId, {phase, token: ticket.token, ...(value === undefined ? {} : {gain_db: value})}) === true; }
    catch { return false; }
  }
  function releaseCapture(ticket) {
    if (ticket.pointerId !== undefined) {
      try { if (range.hasPointerCapture?.(ticket.pointerId)) range.releasePointerCapture(ticket.pointerId); } catch { /* Detached control. */ }
    }
  }
  function cancelActive(reason = '') {
    const ticket = active;
    if (!ticket) return false;
    active = null; releaseCapture(ticket); callInteraction(ticket, 'cancel');
    message = reason; notify(); return true;
  }
  function resetScope(s) {
    cancelActive(); clearFocus(); dirty = false; message = ''; selected = ''; initialized = false; optionKey = '';
    scopeId = s.project?.id || null; scopeView = s.viewToken; number.setCustomValidity?.(''); notify();
  }
  function checkScope(s) {
    if (scopeMatches(s)) return true;
    resetScope(s); sync(); return false;
  }
  function numericValue() {
    const text = number.value.trim(), value = text === '' ? NaN : Number(text);
    return Number.isFinite(value) && value >= -60 && value <= 12 && !number.validity?.badInput ? value : null;
  }
  function numericIssue() { return numericValue() === null ? 'Enter a level from -60 to 12 dB, or press Escape to discard this input.' : ''; }
  function draftInput() {
    const s = read(); if (destroyed || !checkScope(s) || number.disabled || active) return;
    const value = numericValue(), current = level(s);
    dirty = value === null || !current || value !== current.gain_db;
    message = ''; notify(); sync();
  }
  function queue(patch, node) {
    const s = read(); if (destroyed || !checkScope(s)) return false;
    const blocked = issue(s);
    if (blocked) { message = blocked; sync(); return false; }
    ownFocus(node, s);
    let accepted = false;
    try { accepted = change?.(selected, patch) === true; } catch { /* Fail closed. */ }
    if (!accepted) { clearFocus(); message = issue(read()) || 'Track level was not queued. Check the current edit and try again.'; }
    else message = '';
    return accepted;
  }
  function commitNumber() {
    const s = read(); if (destroyed || !checkScope(s) || active || number.disabled) return false;
    if (!dirty) { sync(); return true; }
    const value = numericValue();
    if (value === null) { number.setCustomValidity?.(numericIssue()); number.reportValidity?.(); sync(); return false; }
    number.setCustomValidity?.('');
    if (value === level(s)?.gain_db) { dirty = false; message = ''; notify(); sync(); return true; }
    // Release only this local draft before synchronous host admission; put it back on refusal.
    const typed = number.value;
    dirty = false; notify();
    if (!queue({gain_db: value}, number)) { dirty = true; number.value = typed; notify(); }
    sync(); return !dirty;
  }
  function begin(kind, pointerId) {
    const s = read(); if (destroyed || !checkScope(s) || active || dirty) return false;
    const blocked = issue(s); if (blocked) { message = blocked; sync(); return false; }
    let token;
    try { token = interaction?.(selected, {phase: 'begin'}); } catch { token = null; }
    if (!token || typeof token?.then === 'function') { message = issue(read()) || 'Finish the current save before adjusting the fader.'; sync(); return false; }
    active = {token, kind, pointerId, projectId: s.project.id, viewToken: s.viewToken,
      trackId: selected, identity: modelIdentity(s), value: level(s).gain_db};
    message = ''; notify(); sync(); return true;
  }
  function preview(value) {
    const ticket = active, s = read();
    if (!ticket) return false;
    if (!isCurrent(s, ticket) || modelIdentity(s) !== ticket.identity || !Number.isFinite(value) || value < -60 || value > 12) {
      cancelActive('The saved track changed. Review its current level before trying again.'); sync(); return false;
    }
    ticket.value = value;
    if (!callInteraction(ticket, 'preview', value)) {
      cancelActive(issue(read()) || 'Track preview was refused. No level was saved.'); sync(); return false;
    }
    sync(); return true;
  }
  function commitActive() {
    const ticket = active, s = read(); if (!ticket) return false;
    if (!isCurrent(s, ticket) || modelIdentity(s) !== ticket.identity) {
      cancelActive('The saved track changed. No level was saved.'); sync(); return false;
    }
    active = null; releaseCapture(ticket); notify(); ownFocus(range, s);
    const accepted = callInteraction(ticket, 'commit', ticket.value);
    if (!accepted) { clearFocus(); callInteraction(ticket, 'cancel'); message = issue(read()) || 'Track level was not queued. No automatic retry was made.'; }
    else message = '';
    sync(); return accepted;
  }
  const keys = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown']);
  function stepped(value, event) {
    if (event.key === 'Home') return -60;
    if (event.key === 'End') return 12;
    const direction = ['ArrowDown', 'ArrowLeft', 'PageDown'].includes(event.key) ? -1 : 1;
    const step = event.shiftKey ? .1 : event.key.startsWith('Page') ? 3 : .5;
    return Math.max(-60, Math.min(12, Number((value + direction * step).toFixed(10))));
  }
  listen(selector, 'change', () => {
    const s = read(); if (destroyed || !checkScope(s)) return;
    const next = selector.value;
    if (dirty || active || !tracks(s).some(t => t.id === next)) { selector.value = selected; message = 'Finish or discard the current level input before changing tracks.'; sync(); return; }
    selected = next; message = ''; clearFocus(); sync();
  });
  listen(number, 'input', draftInput);
  listen(number, 'change', commitNumber);
  listen(number, 'keydown', event => {
    if (event.isComposing || destroyed) return;
    if (event.key === 'Escape' && dirty) {
      event.preventDefault(); event.stopPropagation(); dirty = false; message = ''; number.setCustomValidity?.(''); notify(); sync();
    } else if (event.key === 'Enter') { event.preventDefault(); event.stopPropagation(); commitNumber(); }
    else if (keys.has(event.key) && !number.disabled) {
      event.preventDefault(); const value = numericValue();
      if (value !== null) { number.value = String(stepped(value, event)); draftInput(); }
    }
  });
  listen(mute, 'change', () => {
    const s = read(), requested = mute.checked;
    if (destroyed || !checkScope(s)) return;
    mute.checked = level(s)?.muted === true;
    if (!mute.disabled && !dirty && !active && requested !== mute.checked) queue({muted: requested}, mute);
    sync();
  });
  listen(reset, 'click', () => { if (!destroyed && !reset.disabled && !dirty && !active) { queue({gain_db: 0}, reset); sync(); } });
  listen(range, 'pointerdown', event => {
    if ((event.button !== undefined && event.button !== 0) || event.isPrimary === false || !begin('pointer', event.pointerId)) { event.preventDefault(); return; }
    try { range.setPointerCapture?.(event.pointerId); } catch { cancelActive('Fader interaction could not start.'); sync(); event.preventDefault(); }
  });
  listen(range, 'input', () => {
    if (active?.kind === 'pointer') preview(Math.max(-60, Math.min(12, Math.round(Number(range.value) * 10) / 10)));
    else sync(); // Unowned synthetic/native change must never write.
  });
  listen(range, 'pointerup', event => { if (active?.kind === 'pointer' && active.pointerId === event.pointerId) commitActive(); });
  for (const name of ['pointercancel', 'lostpointercapture']) listen(range, name, event => {
    if (active?.kind === 'pointer' && active.pointerId === event.pointerId) { cancelActive('Fader change discarded.'); sync(); }
  });
  listen(range, 'keydown', event => {
    if (event.isComposing || destroyed) return;
    if (event.key === 'Escape' && active) { event.preventDefault(); event.stopPropagation(); cancelActive('Fader change discarded.'); sync(); }
    else if (keys.has(event.key)) {
      event.preventDefault(); event.stopPropagation();
      if ((!active && !begin('keyboard')) || active?.kind !== 'keyboard') return;
      preview(stepped(active.value, event));
    }
  });
  listen(range, 'keyup', event => { if (!event.isComposing && keys.has(event.key) && active?.kind === 'keyboard') { event.preventDefault(); commitActive(); } });
  listen(range, 'blur', () => { if (active) { cancelActive('Fader change discarded.'); sync(); } });
  listen(win, 'blur', () => { if (active) { cancelActive('Fader change discarded.'); sync(); } });
  function disable(node, blocked) { node.disabled = Boolean(blocked); if (node !== reset) node.title = blocked || ''; }
  function sync() {
    if (destroyed) return;
    if (syncing) { resync = true; return; }
    syncing = true;
    try {
      const s = read();
      if (!scopeMatches(s)) resetScope(s);
      const list = tracks(s);
      if (!initialized && list.length) {
        const clip = Array.isArray(s.project?.manual?.media_clips) ? s.project.manual.media_clips.find(c => c.id === s.selectedClipId) : null;
        selected = list.some(t => t.id === clip?.track_id) ? clip.track_id : list[0].id;
        initialized = true;
      }
      if (active && (!isCurrent(s, active) || active.identity !== modelIdentity(s))) cancelActive('The saved track changed. No level was saved.');
      const current = track(s), value = level(s), blocked = issue(s);
      const key = JSON.stringify(list.map(t => [t.id, t.name, t.kind, t.locked === true])) + '|' + selected;
      if (key !== optionKey) {
        const options = list.map(t => { const o = make('option', '', `${t.name} (${t.kind}${t.locked ? ', edits locked' : ''})`); o.value = t.id; return o; });
        if (selected && !current) { const o = make('option', '', 'Previously chosen track (unavailable)'); o.value = selected; options.push(o); }
        if (!options.length) { const o = make('option', '', 'No named sound tracks'); o.value = ''; options.push(o); }
        selector.replaceChildren(...options); optionKey = key;
      }
      selector.value = selected;
      disable(selector, dirty || active ? 'Finish or discard the current level input first.' : s.busy || !list.length);
      const fieldIssue = blocked || (active ? 'Finish the fader adjustment first.' : '');
      disable(number, fieldIssue);
      disable(range, active ? '' : blocked || (dirty ? 'Finish or discard the numeric level first.' : ''));
      disable(mute, fieldIssue || (dirty ? 'Finish or discard the numeric level first.' : ''));
      disable(reset, fieldIssue || (dirty ? 'Finish or discard the numeric level first.' : value?.gain_db === 0 ? 'Level is already 0 dB.' : ''));
      root.hidden = !s.project?.id;
      strip.hidden = !list.length || !current || !value;
      const displayValue = active?.value ?? value?.gain_db;
      range.value = String(displayValue ?? 0);
      if (!dirty) number.value = value ? String(displayValue) : '';
      mute.checked = value?.muted === true;
      number.setCustomValidity?.(dirty ? numericIssue() : '');
      number.setAttribute('aria-invalid', String(dirty && numericValue() === null));
      const label = current?.name || 'Named track';
      range.setAttribute('aria-label', `${label} level`); range.setAttribute('aria-valuetext', `${displayValue ?? 0} dB`);
      number.setAttribute('aria-label', `${label} level in dB`); mute.setAttribute('aria-label', `Mute sound on ${label}`);
      const summary = s.summariesByTrack?.[selected];
      if (summary && Number.isInteger(summary.eligible) && summary.eligible >= 0) {
        const parts = [`${summary.eligible} sound-enabled clip${summary.eligible === 1 ? '' : 's'}`];
        if (value?.muted) parts.push('track muted');
        if (summary.disabled > 0) parts.push(`${summary.disabled} disabled`);
        if (summary.clipMuted > 0) parts.push(`${summary.clipMuted} clip-muted`);
        if (Array.isArray(summary.roles) && summary.roles.length) parts.push(summary.roles.join(' / '));
        members.textContent = summary.eligible === 0 ? 'No sound-enabled clips on this track. Its level will apply to future sound placed here.' : parts.join(' · ');
      } else members.textContent = current ? 'Sound membership is unavailable.' : '';
      status.textContent = dirty ? numericIssue() || message || 'Unapplied level input. Press Enter or leave the field to save; Escape discards it.'
        : active ? 'Auditioning track level. Release to save once; Escape discards it.' : message || blocked || (value?.muted ? 'Track sound is muted in preview and export. Picture stays visible.' : 'Saved track levels apply in preview and export.');
      finishFocus();
    } finally {
      syncing = false;
      if (resync) { resync = false; sync(); }
    }
  }
  sync();
  return {
    sync,
    hasDraft: () => !destroyed && localState(),
    focusDraft() {
      if (destroyed || !localState()) return false;
      details.open = true;
      for (let ancestor = root.parentElement; ancestor; ancestor = ancestor.parentElement) if (ancestor.tagName === 'DETAILS') ancestor.open = true;
      const node = active ? range : number; node.scrollIntoView?.({block: 'nearest'}); node.focus?.({preventScroll: true}); return true;
    },
    destroy() {
      if (destroyed) return;
      cancelActive(); clearFocus(); dirty = false; notify(); destroyed = true;
      for (const remove of subscriptions) remove(); details.remove();
    }
  };
}
