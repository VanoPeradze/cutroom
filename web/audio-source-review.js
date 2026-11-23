// A local Source audition, not an edit queue. The host owns all saved-state
// admission, canonical time arithmetic, placement receipts and shared-slot focus.
export function initAudioSourceReview(root, options) {
  const doc = root?.ownerDocument, win = doc?.defaultView;
  if (!doc || typeof options?.snapshot !== 'function') throw new Error('Audio Source is unavailable.');
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const read = () => { try { return options.snapshot(); } catch { return null; } };
  const valid = s => s && typeof s.projectId === 'string' && s.projectId && typeof s.assetId === 'string' && s.assetId
    && s.viewToken != null && (typeof s.viewToken !== 'number' || finite(s.viewToken))
    && Number.isInteger(s.revision) && s.revision >= 0 && typeof s.sourceIdentity === 'string' && s.sourceIdentity
    && typeof s.url === 'string' && s.url && finite(s.duration) && s.duration >= .08 && s.duration <= 14400
    && typeof s.issue === 'string';
  const initial = read();
  if (!valid(initial)) throw new Error('The imported audio identity is unavailable.');
  const source = {projectId:initial.projectId, viewToken:initial.viewToken, assetId:initial.assetId,
    sourceIdentity:initial.sourceIdentity, duration:initial.duration};
  let reviewed = initial.revision, boundUrl = initial.url, closed = false, operation = null, unknown = false;
  let metadata = false, metadataError = '', seenMetadata = false, selectedPlayback = null, playPending = false, playRequest = 0;
  let frame = null, epoch = 0, repairRestore = null, message = '', focusTicket = null, focusFrame = null, syncing = false;
  const listeners = [], make = (tag, text, attr) => {
    const node = doc.createElement(tag); if (text != null) node.textContent = text;
    if (attr) node.setAttribute(attr, ''); return node;
  };
  const listen = (target, type, fn, capture = false) => {
    target?.addEventListener?.(type, fn, capture); listeners.push(() => target?.removeEventListener?.(type, fn, capture));
  };
  const text = (node, value) => { if (node.textContent !== value) node.textContent = value; };
  root.classList.add('audio-source-review'); root.dataset.editorShortcuts = 'off';
  root.setAttribute('role', 'region'); root.setAttribute('aria-label', 'Audio Source monitor'); root.tabIndex = -1;
  const header = make('header'); header.className = 'library-source-monitor-header';
  const title = make('h3', 'Audio Source'), closeButton = make('button', 'Close source', 'data-audio-close');
  closeButton.type = 'button'; header.append(title, closeButton);
  const name = make('p', initial.name || 'Imported audio'); name.className = 'library-shot-name'; name.dir = 'auto';
  const audio = make('audio', null, 'data-audio-source'); audio.controls = true; audio.preload = 'metadata';
  audio.setAttribute('aria-label', `Source audio: ${initial.name || 'Imported audio'}`);
  audio.defaultPlaybackRate = 1; audio.playbackRate = 1;
  const disclosure = make('p', 'Audition original-speed prepared audio, without the track, Music or Master mix. Browser-timed playback is not sample-accurate.');
  disclosure.className = 'audio-source-disclosure';
  const form = make('form'); form.className = 'audio-source-range';
  const fields = {}, marks = {}, jumps = {};
  for (const key of ['in', 'out']) {
    const label = make('label', `Source ${key === 'in' ? 'In' : 'Out'} (seconds)`);
    const input = make('input', null, `data-audio-${key}`); input.type = 'number'; input.required = true;
    input.min = '0'; input.max = String(initial.duration); input.step = 'any'; label.append(input); fields[key] = input;
    const actions = make('div'); actions.className = 'audio-source-point-actions';
    const mark = make('button', `Set ${key === 'in' ? 'In' : 'Out'} here`); mark.type = 'button'; mark.dataset.audioMark = key;
    mark.setAttribute('aria-keyshortcuts', key === 'in' ? 'I' : 'O'); marks[key] = mark;
    const jump = make('button', `Jump to ${key === 'in' ? 'In' : 'Out'}`); jump.type = 'button'; jump.dataset.audioJump = key; jumps[key] = jump;
    actions.append(mark, jump); label.append(actions); form.append(label);
  }
  const preview = make('button', 'Play selected audio', 'data-audio-preview'); preview.type = 'button';
  const destination = make('p', '', 'data-audio-destination'); destination.className = 'audio-source-destination';
  const add = make('button', 'Add selected audio', 'data-audio-add'); add.type = 'submit';
  const status = make('p', '', 'data-audio-status'); status.className = 'audio-source-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.tabIndex = -1; status.dataset.sourceDrag='true';
  status.title='Drag this selection to the timeline, or use Add selected audio.';
  const refresh = make('button', 'Use current edit', 'data-audio-refresh'); refresh.type = 'button';
  form.append(preview);
  if (options.destinationControl) form.append(options.destinationControl);
  form.append(destination, add);
  const help = make('details'); help.className = 'audio-source-help';
  const summary = make('summary', 'Audio marks & help'), markActions = make('div'); markActions.className = 'audio-source-mark-actions';
  const save = make('button', 'Save source marks', 'data-audio-save-marks'), clear = make('button', 'Clear saved marks', 'data-audio-clear-marks');
  save.type = clear.type = 'button'; markActions.append(save, clear);
  const marksStatus = make('p', '', 'data-audio-marks-status'); marksStatus.setAttribute('role', 'status');
  const localCopy = 'Marks are stored only in this browser, separately from video marks. They do not change the project.';
  help.append(summary, markActions, marksStatus, make('p', 'I / O set marks outside text fields. Changing or jumping to marks pauses audition. Add creates one Music occurrence without ripple or extending the edit; destination track levels apply. One Undo removes it.'));
  root.append(header, name, audio, disclosure, form, status, refresh, help);
  let remembered;
  try { remembered = options.readMarks?.(); } catch { remembered = {state:'unavailable'}; }
  fields.in.value = String(remembered?.range?.source_start ?? 0);
  fields.out.value = String(remembered?.range?.source_end ?? initial.duration);
  text(marksStatus, remembered?.state === 'saved' ? `Saved audio marks restored. ${localCopy}`
    : ['stale', 'invalid'].includes(remembered?.state) ? `Saved audio marks do not match this source or are unreadable. Review the selection. ${localCopy}`
    : remembered?.state === 'unavailable' ? 'Browser storage is unavailable. Local audition and selection are still available.' : localCopy);

  const sameSource = s => valid(s) && Object.keys(source).every(key => s[key] === source[key]);
  const mounted = s => !closed && root.isConnected !== false && sameSource(s) && s.visible !== false;
  const range = () => {
    if (!fields.in.value.trim() || !fields.out.value.trim()) return {issue:'Enter both source In and Out.'};
    try {
      const result = options.range?.(Number(fields.in.value), Number(fields.out.value));
      if (!result || typeof result.issue !== 'string' || !result.issue && (![result.source_start,result.source_end,result.length].every(finite)
        || result.source_start < 0 || result.source_end > source.duration || result.source_end <= result.source_start || result.length <= 0))
        return {issue:'The audio range could not be verified.'};
      return result;
    } catch (error) { return {issue:error?.message || 'The audio range could not be verified.'}; }
  };
  const plan = selected => {
    if (selected.issue) return {issue:selected.issue};
    try {
      const value = options.plan?.(selected), s = read();
      if (!value || typeof value.issue !== 'string' || !value.issue && (!mounted(s)
        || value.projectId !== source.projectId || value.assetId !== source.assetId || value.revision !== s.revision
        || ![value.start,value.end,value.length].every(finite) || value.start < 0 || value.end <= value.start
        || value.end > s.editDuration || value.length <= 0 || value.source_start !== selected.source_start || value.source_end !== selected.source_end
        || !finite(value.destinationAudio?.gain_db) || typeof value.destinationAudio?.muted !== 'boolean'))
        return {issue:'Audio placement could not be verified.'};
      return value;
    } catch (error) { return {issue:error?.message || 'Audio placement could not be verified.'}; }
  };
  const equalRange = (a, b) => !a?.issue && !b?.issue && a.source_start === b.source_start && a.source_end === b.source_end && a.length === b.length;
  const previewRangeIssue = selected => !selected.issue && metadata && finite(audio.duration) && selected.source_end > audio.duration
    ? 'Selected Out is beyond the prepared preview. Choose an earlier Out or use Verify & repair preview.' : '';
  const readyIssue = (s, allowPending = false) => !mounted(s) ? 'This source is no longer current.'
    : unknown ? message || 'The placement outcome is unconfirmed. Reopen this project before adding again. Nothing is replayed.'
    : operation && !allowPending ? 'Adding the selected audio. Please wait.'
    : s.issue || (s.revision !== reviewed && !operation ? 'The edit changed. Use current edit to review its destination; your source marks are kept.' : '')
      || (!metadata ? metadataError || 'Loading prepared audio preview...' : '');
  const stopFrame = () => { if (frame != null) win?.cancelAnimationFrame?.(frame); frame = null; };
  function pausePreview() {
    ++playRequest; playPending = false; selectedPlayback = null; stopFrame();
    try { audio.pause(); } catch { /* A detached native player may already be released. */ }
  }
  function clearFocus() {
    focusTicket = null;
    if (focusFrame != null) win?.cancelAnimationFrame?.(focusFrame); focusFrame = null;
  }
  function finishFocus() {
    if (!focusTicket || focusFrame != null || closed || operation || typeof win?.requestAnimationFrame !== 'function') return;
    focusFrame = win.requestAnimationFrame(() => {
      focusFrame = null; const ticket = focusTicket, s = read();
      if (!ticket || !mounted(s) || epoch !== ticket.epoch || s.revision !== ticket.revision) { clearFocus(); return; }
      if (doc.activeElement !== doc.body && doc.activeElement !== ticket.node) { clearFocus(); return; }
      if (readyIssue(s) && !unknown) return;
      const target = !add.disabled ? add : status;
      clearFocus(); target.focus?.({preventScroll:true});
    });
  }
  function sync() {
    if (closed || syncing) return;
    syncing = true;
    try {
      const s = read();
      if (!mounted(s) || s.url !== boundUrl) { close(false); return; }
      const issue = readyIssue(s), selected = range(), proposed = plan(selected), previewIssue = previewRangeIssue(selected);
      if ((issue || previewIssue) && (!audio.paused || playPending || selectedPlayback)) pausePreview();
      const blocked = Boolean(issue), playing = playPending || !audio.paused;
      for (const input of Object.values(fields)) input.disabled = blocked;
      for (const button of Object.values(marks)) button.disabled = blocked;
      for (const button of Object.values(jumps)) button.disabled = blocked || Boolean(selected.issue || previewIssue);
      audio.controls = !blocked;
      preview.textContent = playing ? 'Pause source audio' : 'Play selected audio';
      preview.disabled = blocked || Boolean(selected.issue || previewIssue) && !playing;
      save.disabled = blocked || Boolean(selected.issue); clear.disabled = blocked;
      add.disabled = blocked || Boolean(previewIssue || proposed.issue);
      add.title = issue || previewIssue || proposed.issue || 'Add this whole selection once, without changing the edit duration.';
      add.textContent = !proposed.issue && finite(proposed.start) ? `Add selected audio at ${proposed.start} s` : 'Add selected audio';
      refresh.hidden = s.revision === reviewed || Boolean(operation) || unknown;
      refresh.disabled = Boolean(operation || unknown || s.issue);
      const audioLevel = proposed.destinationAudio;
      const mix = !proposed.issue && audioLevel ? audioLevel.muted ? ' Destination track is muted; the new occurrence will be silent.'
        : audioLevel.gain_db !== 0 ? ` Destination track gain: ${audioLevel.gain_db} dB.` : ' Destination track levels are neutral.' : '';
      text(destination, previewIssue || proposed.issue || `Edit ${proposed.start} to ${proposed.end} s. ${proposed.length} s selected. No ripple or end extension.${mix}`);
      text(status, issue || previewIssue || message || (selected.issue || `Source ${selected.source_start} to ${selected.source_end} s selected. Audition does not change the edit.`));
      status.draggable=!blocked&&!selected.issue&&!previewIssue;
      status.setAttribute('aria-disabled',String(!status.draggable));
      if(status.draggable)text(status,`Drag selection · Source ${selected.source_start.toFixed(3)}–${selected.source_end.toFixed(3)} s · ${selected.length.toFixed(3)} s selected${message?' · '+message:''}`);
      closeButton.disabled = false;
      finishFocus();
    } finally { syncing = false; }
  }
  function canUse() { const s = read(); const issue = readyIssue(s); if (issue) { sync(); return false; } return true; }
  function checkedPlayback() {
    if (closed) return;
    if (!canUse()) { pausePreview(); return; }
    if (selectedPlayback && (audio.currentTime >= selectedPlayback.source_end || audio.currentTime < selectedPlayback.source_start)) {
      const end = selectedPlayback.source_end, reachedEnd = audio.currentTime >= end;
      pausePreview(); if (reachedEnd) { try { audio.currentTime = end; } catch { /* Keep paused. */ } }
    }
    sync();
  }
  function tick() {
    frame = null;
    // Only the local media clock is inspected per frame. Full host readiness,
    // track validation and placement plans belong to events/sync, not playback.
    if (closed || !selectedPlayback || audio.paused) return;
    if (audio.currentTime >= selectedPlayback.source_end || audio.currentTime < selectedPlayback.source_start) {
      const end = selectedPlayback.source_end, reachedEnd = audio.currentTime >= end;
      pausePreview(); if (reachedEnd) { try { audio.currentTime = end; } catch { /* Keep paused. */ } }
      sync(); return;
    }
    if (typeof win?.requestAnimationFrame === 'function') frame = win.requestAnimationFrame(tick);
  }
  function requestTick() { if (frame == null && typeof win?.requestAnimationFrame === 'function') frame = win.requestAnimationFrame(tick); }
  function inputChanged() { ++epoch; clearFocus(); message = ''; pausePreview(); text(marksStatus, `Selection changed. Use Save source marks to remember it. ${localCopy}`); sync(); }
  function markAt(key) {
    if (!canUse() || !finite(audio.currentTime)) return false;
    fields[key].value = String(audio.currentTime); inputChanged(); return true;
  }
  function checkMetadata() {
    if (closed) return;
    // Conservative availability tolerance only. Prepared AAC keeps the source
    // sample rate; this is not a sample-identity or packet-count guarantee.
    metadata = finite(audio.duration) && Math.abs(audio.duration - source.duration) <= .05;
    metadataError = metadata ? '' : 'Prepared audio duration does not match the source. Verify its preview before using this selection.';
    if (metadata && repairRestore) {
      const restore = repairRestore; repairRestore = null;
      if (mounted(read()) && restore.epoch === epoch && finite(restore.time) && restore.time >= 0 && restore.time <= source.duration) {
        try { audio.currentTime = restore.time; } catch { /* Never autoplay or force a later seek. */ }
      }
    }
    if (!metadata) pausePreview(); sync();
  }
  function owns(ticket, admission = false) {
    const s = read();
    return operation === ticket && mounted(s) && s.url === boundUrl && epoch === ticket.epoch
      && s.trackId === ticket.trackId && s.at === ticket.at && equalRange(range(), ticket.range)
      && (!admission || s.revision === ticket.revision && !s.issue && metadata && !previewRangeIssue(ticket.range));
  }
  async function submit(event) {
    event.preventDefault();
    if (operation || unknown || !canUse() || form.reportValidity?.() === false) return;
    const s = read(), selected = range(), proposed = plan(selected);
    if (selected.issue || previewRangeIssue(selected) || proposed.issue) { message = selected.issue || previewRangeIssue(selected) || proposed.issue; sync(); return; }
    pausePreview(); message = '';
    const ticket = {epoch, revision:reviewed, trackId:s.trackId, at:s.at, range:{...selected}};
    operation = ticket;
    if (root.contains?.(doc.activeElement)) focusTicket = {node:doc.activeElement,epoch,revision:reviewed};
    sync();
    try {
      const result = await options.place(proposed, {isCurrent:() => owns(ticket), admissionCurrent:() => owns(ticket, true)});
      if (!owns(ticket)) return;
      const current = read();
      if (result?.status === 'saved' && result.projectId === source.projectId && result.revision === current.revision
        && Number.isInteger(result.revision) && result.revision > ticket.revision && typeof result.clipId === 'string' && result.clipId) {
        reviewed = result.revision; message = result.message || 'Selected audio added. The edit cursor and source marks are unchanged. Undo removes this occurrence.';
        if (focusTicket) focusTicket.revision = reviewed;
      } else if (result?.status === 'saved' && result.projectId === source.projectId && Number.isInteger(result.revision)
        && result.revision > ticket.revision && typeof result.clipId === 'string' && result.clipId) {
        unknown = true; message = 'Audio was saved, but this view could not confirm the current edit. Reopen before adding again.';
      } else if (result?.status === 'refused') message = result.message || 'Audio was not added. Review the current edit and try again.';
      else { unknown = true; message = 'The placement outcome is unconfirmed. Reopen this project before adding again. Nothing is replayed.'; }
    } catch { if (owns(ticket)) { unknown = true; message = 'The placement outcome is unconfirmed. Reopen this project before adding again. Nothing is replayed.'; } }
    finally { if (operation === ticket) operation = null; sync(); }
  }
  async function play() {
    if (!canUse()) return;
    if (playPending || !audio.paused) { pausePreview(); sync(); return; }
    const selected = range(); if (selected.issue || previewRangeIssue(selected)) { message = selected.issue || previewRangeIssue(selected); sync(); return; }
    const request = ++playRequest; selectedPlayback = {...selected}; playPending = true; message = '';
    try {
      options.pauseProgram?.(audio); audio.defaultPlaybackRate = 1; audio.playbackRate = 1; audio.currentTime = selected.source_start;
      sync(); await audio.play();
      if (closed || request !== playRequest) { if (closed || !selectedPlayback) audio.pause(); return; }
      playPending = false; checkedPlayback(); requestTick();
    } catch (error) { if (!closed && request === playRequest) { pausePreview(); message = `Audio preview could not play: ${error?.message || 'Playback was refused.'}`; sync(); } }
  }
  function close(restoreFocus = false) {
    if (closed) return false;
    const active = doc.activeElement;
    const ownedFocus = Boolean(root.contains?.(active) || active === doc.body && focusTicket && focusTicket.epoch === epoch);
    closed = true; ++epoch; operation = null; pausePreview(); clearFocus(); repairRestore = null;
    for (const remove of listeners.splice(0)) remove();
    try { audio.removeAttribute('src'); audio.load(); } catch { /* The host removes the owned region. */ }
    try { options.closed?.(controller, {restoreFocus:restoreFocus === true,ownedFocus}); } catch { /* Do not revive a closed source. */ }
    return true;
  }
  function captureRepair(assetId) {
    const s = read();
    return assetId === source.assetId && mounted(s) && s.url === boundUrl && !operation
      ? {controller,epoch,time:audio.currentTime,projectId:source.projectId,viewToken:source.viewToken,assetId:source.assetId,
        sourceIdentity:source.sourceIdentity,url:boundUrl,revision:reviewed,reviewed:s.revision === reviewed} : null;
  }
  function acceptRepair(capture, nextAsset, nextRevision, reload) {
    const s = read();
    if (!capture || capture.controller !== controller || !mounted(s) || operation || capture.projectId !== source.projectId
      || capture.viewToken !== source.viewToken || capture.assetId !== source.assetId || capture.sourceIdentity !== source.sourceIdentity
      || capture.url !== boundUrl || capture.revision !== reviewed || nextAsset?.id !== source.assetId || nextAsset.kind !== 'audio'
      || nextAsset.status !== 'ready' || nextAsset.duration !== source.duration || nextAsset.url !== s.url
      || !Number.isInteger(nextRevision) || nextRevision !== s.revision || nextRevision < capture.revision || typeof reload !== 'boolean') return false;
    pausePreview(); boundUrl = s.url;
    if (capture.reviewed) reviewed = nextRevision;
    if (reload) {
      metadata = false; seenMetadata = false; metadataError = ''; repairRestore = capture.epoch === epoch ? capture : null;
      audio.src = boundUrl; audio.load();
    }
    sync(); return true;
  }
  const controller = {get open() { return !closed; }, get pending() { return Boolean(operation); }, close,
    pausePreview:() => {pausePreview();sync();}, sync, captureRepair, acceptRepair,
    sourceSelection(assetId) {
      if(assetId!==source.assetId)return null;
      const s=read(),selected=range();
      if(!mounted(s)||s.url!==boundUrl||s.revision!==reviewed||!metadata||operation||unknown)
        return {issue:'Review the current audio source and edit before dragging its selection.'};
      return selected.issue?selected:previewRangeIssue(selected)?{issue:previewRangeIssue(selected)}:selected;
    }};
  // Real newer interaction cancels completion focus and repair-clock adoption.
  const interact = event => { if (closed) return; ++epoch; clearFocus(); };
  listen(doc, 'pointerdown', interact, true); listen(doc, 'keydown', interact, true);
  listen(doc, 'focusin', event => { if (focusTicket && event.target !== focusTicket.node && event.target !== doc.body) clearFocus(); }, true);
  listen(form, 'submit', submit); listen(preview, 'click', play); listen(closeButton, 'click', () => close(true));
  for (const key of ['in', 'out']) {
    listen(fields[key], 'input', inputChanged);
    listen(marks[key], 'click', () => markAt(key));
    listen(jumps[key], 'click', () => { if (!canUse()) return; const selected = range(); if (selected.issue || previewRangeIssue(selected)) return;
      ++epoch; clearFocus(); pausePreview(); audio.currentTime = key === 'in' ? selected.source_start : selected.source_end; sync(); });
  }
  if (options.destinationControl) listen(options.destinationControl, 'change', () => { ++epoch; clearFocus(); message = ''; pausePreview(); sync(); });
  listen(refresh, 'click', () => { const s = read(); if (!mounted(s) || operation || unknown || s.issue || s.url !== boundUrl) return;
    ++epoch; clearFocus(); pausePreview(); reviewed = s.revision; message = ''; sync(); });
  listen(save, 'click', () => { if (!canUse() || form.reportValidity?.() === false) return; const selected = range(); if (selected.issue) return;
    pausePreview(); try { const stored = options.saveMarks?.(selected); if (!stored || typeof stored.then === 'function') throw new Error('Audio marks could not be saved.');
      text(marksStatus, `Audio marks saved: ${stored.source_start} to ${stored.source_end} s. ${localCopy}`); }
    catch (error) { text(marksStatus, error?.message || 'Audio marks could not be saved.'); } sync(); });
  listen(clear, 'click', () => { if (!canUse()) return;
    try { if (typeof options.clearMarks !== 'function') throw new Error('Audio marks could not be cleared.');
      const result = options.clearMarks(); if (result?.then) throw new Error('Audio marks could not be cleared.');
      fields.in.value = '0'; fields.out.value = String(source.duration); ++epoch; clearFocus(); pausePreview(); text(marksStatus, `Saved audio marks cleared. ${localCopy}`); }
    catch (error) { text(marksStatus, error?.message || 'Audio marks could not be cleared.'); } sync(); });
  listen(root, 'keydown', event => {
    if (event.defaultPrevented || event.isComposing) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); return; }
    if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.getModifierState?.('AltGraph')) return;
    const target = event.composedPath?.()[0] || event.target;
    if (target?.isContentEditable || target?.closest?.('input,textarea,select,[contenteditable],[role="textbox"],[role="combobox"]')) return;
    const key = String(event.key || '').toLowerCase();
    if ((key === 'i' || key === 'o') && markAt(key === 'i' ? 'in' : 'out')) { event.preventDefault(); event.stopPropagation(); }
  });
  listen(audio, 'loadedmetadata', () => { seenMetadata = true; checkMetadata(); });
  listen(audio, 'durationchange', () => { if (seenMetadata) checkMetadata(); });
  listen(audio, 'emptied', () => { metadata = false; seenMetadata = false; metadataError = ''; pausePreview(); sync(); });
  listen(audio, 'error', () => { if (audio.error?.code === 1) return; metadata = false;
    metadataError = 'Audio preview is unavailable. Use Verify & repair preview for this file in the Media pool.'; pausePreview(); sync(); });
  listen(audio, 'ratechange', () => { if (audio.defaultPlaybackRate !== 1) audio.defaultPlaybackRate = 1; if (audio.playbackRate !== 1) audio.playbackRate = 1; });
  for (const type of ['play', 'playing']) listen(audio, type, () => {
    if (!canUse()) { pausePreview(); return; } options.pauseProgram?.(audio); checkedPlayback(); if (selectedPlayback) requestTick();
  });
  for (const type of ['timeupdate', 'seeking']) listen(audio, type, checkedPlayback);
  listen(audio, 'ended', () => { pausePreview(); sync(); });
  listen(audio, 'pause', () => { if (audio.paused) { if (playPending) ++playRequest; playPending = false; stopFrame(); sync(); } });
  audio.src = boundUrl; sync(); return controller;
}
