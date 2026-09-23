// Additional footage and sound are edit-clock layers, not replacement A/B sources.
export function clipEnvelope(clip, time) {
  const elapsed = time - clip.start, remaining = clip.end - time;
  if (elapsed < 0 || remaining <= 0 || clip.muted) return 0;
  return Math.min(1, clip.fade_in > 0 ? elapsed / clip.fade_in : 1,
    clip.fade_out > 0 ? remaining / clip.fade_out : 1);
}

export function mediaGain(clip, mixer, time) {
  const role = clip.role || 'music';
  if (mixer[`${role}_muted`]) return 0;
  return clipEnvelope(clip, time) * 10 ** ((Number(clip.volume_db || 0) + Number(mixer[`${role}_db`] || 0)) / 20);
}

export function visualMotion(clip, time) {
  const progress = Math.max(0, Math.min(1, (time - clip.start) / Math.max(.001, clip.end - clip.start)));
  if (clip.motion === 'zoom_in') return `scale(${1 + .12 * progress})`;
  if (clip.motion === 'pan') return `scale(1.12) translateX(${(.5-progress)*100*.12/1.12}%)`;
  return 'none';
}

export class MediaStudio {
  constructor(root, stage, options) {
    this.root = root; this.stage = stage; this.options = options;
    this.selected = null; this.projectId = null; this.players = new Map(); this.overrides = new Map();
    this.pending = new Map(); this.timer = null; this.saving = null; this.uploading = false;
    this.root.innerHTML = `
      <header class="studio-tool-intro"><div><p>MEDIA & AUDIO</p><h3>Build on your edit</h3></div><span>Add B-roll, images, music or voiceover. Original footage stays untouched.</span></header>
      <button type="button" class="media-import button primary" data-import>Add media</button><input type="file" accept="video/*,audio/*,image/png,image/jpeg,image/webp" hidden>
      <p class="media-status" role="status" aria-live="polite">Import a file, then add it at the yellow playhead.</p>
      <div class="media-library" aria-label="Project media"></div>
      <section class="media-inspector" hidden data-editor-shortcuts="off">
        <h4 class="media-selected-name"></h4>
        <div class="media-fields">
          <label>Start (seconds)<input data-media="start" type="number" min="0" step="0.01"></label>
          <label>End (seconds)<input data-media="end" type="number" min="0" step="0.01"></label>
          <label data-kind="timed">Source in<input data-media="source_start" type="number" min="0" step="0.01"></label>
          <label data-kind="video">Picture speed<select data-media="speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="4">4×</option></select></label>
          <label data-kind="sound">Audio group<select data-media="role"><option value="music">Music</option><option value="voice">Voiceover</option><option value="effects">Effects</option></select></label>
          <label data-kind="sound">Clip volume (dB)<input data-media="volume_db" type="range" min="-60" max="12" step="1"><output data-value="volume_db"></output></label>
          <label data-kind="sound">Fade in (seconds)<input data-media="fade_in" type="number" min="0" step="0.1"></label>
          <label data-kind="sound">Fade out (seconds)<input data-media="fade_out" type="number" min="0" step="0.1"></label>
          <label data-kind="video"><input data-media="audio_enabled" type="checkbox"> Use clip audio</label>
          <label data-kind="visual">Framing<select data-media="fit"><option value="cover">Fill frame</option><option value="contain">Fit entire image</option></select></label>
          <label data-kind="image">Motion<select data-media="motion"><option value="none">Still</option><option value="zoom_in">Slow zoom</option><option value="pan">Slow pan</option></select></label>
        </div>
        <details class="media-placement"><summary>Position & size</summary><div class="media-fields">
          <label>Left (%)<input data-media="x" type="number" min="0" max="100" step="1"></label>
          <label>Top (%)<input data-media="y" type="number" min="0" max="100" step="1"></label>
          <label>Width (%)<input data-media="w" type="number" min="1" max="100" step="1"></label>
          <label>Height (%)<input data-media="h" type="number" min="1" max="100" step="1"></label>
        </div></details>
        <p class="media-help">Drag the clip or its edges in the timeline. Changes save automatically. Picture speed does not change the main speech or music.</p>
        <div class="media-actions"><button type="button" data-action="split">Split at playhead</button><button type="button" data-action="duplicate">Duplicate</button><button type="button" data-action="remove">Remove</button></div>
      </section>
      <details class="audio-mixer" open data-editor-shortcuts="off"><summary>Audio mixer</summary>
        <p class="media-help">Balance the original speech and added sound. Mute affects preview and export; Solo is preview-only.</p>
        <div class="mixer-channels"></div>
        <label class="ducking-choice"><input type="checkbox" data-ducking> Lower music while speech plays</label>
        <p class="media-help">The live meter monitors browser playback. Export loudness normalization and peak limiting may change final loudness.</p>
        <label>Output level <meter class="mixer-meter" min="0" max="1" high="0.9" optimum="0.5" value="0"></meter></label>
        <p class="mixer-level-text" role="status">Play to monitor the mix. Keep peaks below the red zone.</p>
      </details>`;
    this.status = root.querySelector('.media-status');
    for (const [role, name] of [['source','Original'],['voice','Voiceover'],['music','Music'],['effects','Effects'],['master','Master']]) {
      const row = document.createElement('div'); row.className = 'mixer-channel';
      const label = document.createElement('label'); label.textContent = name;
      const range = document.createElement('input'); range.type = 'range'; range.min = '-60'; range.max = '12'; range.step = '1'; range.dataset.mix = `${role}_db`; range.setAttribute('aria-label', `${name} volume`);
      const out = document.createElement('output'); out.dataset.mixValue = `${role}_db`;
      label.append(range, out); row.append(label);
      if (role !== 'master') {
        const mute = document.createElement('button'); mute.type = 'button'; mute.textContent = 'Mute'; mute.dataset.mute = role; mute.setAttribute('aria-label', `Mute ${name}`); row.append(mute);
        const solo = document.createElement('button'); solo.type = 'button'; solo.textContent = 'Solo'; solo.dataset.solo = role; solo.setAttribute('aria-label', `Solo ${name}`); row.append(solo);
      }
      root.querySelector('.mixer-channels').append(row);
    }
    root.querySelector('input[type=file]').addEventListener('change', event => { const file = event.target.files[0]; event.target.value = ''; if (file) this.upload(file); });
    root.addEventListener('input', event => { if (event.target.matches('input[type=range]')) this.change(event.target); });
    root.addEventListener('change', event => { if (!event.target.matches('input[type=range],input[type=file]')) this.change(event.target); });
    root.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button) return;
      if (button.hasAttribute('data-import')) root.querySelector('input[type=file]').click();
      if (button.dataset.retry) this.retry(button.dataset.retry);
      if (button.dataset.asset) this.add(button.dataset.asset);
      if (button.dataset.select) this.select(button.dataset.select);
      if (button.dataset.mute) { const key = `${button.dataset.mute}_muted`; this.queueMixer({[key]: !this.mixer()[key]}); }
      if (button.dataset.solo) { this.solo = this.solo === button.dataset.solo ? null : button.dataset.solo; this.renderMixer(); this.options.preview(); }
      if (button.dataset.action) this.action(button.dataset.action);
    });
  }
  project() { return this.options.project(); }
  clips() { return (this.project()?.manual?.media_clips || []).map(clip => ({...clip,...this.overrides.get(clip.id)})); }
  mixer() { return {...this.project()?.manual?.audio_mixer,...this.mixerOverride}; }
  async upload(file) {
    if (this.options.busy() || this.uploading || !this.project()?.draft) return;
    const projectId = this.project().id;
    this.options.pause(); this.status.textContent = `Importing ${file.name}…`;
    try {
      if (!(await this.flush())) return;
      this.uploading = true;
      this.options.busyChanged?.();
      await this.options.flushSettings(projectId);
      const form = new FormData(); form.append('file', file);
      const result = await this.options.api(`/api/projects/${encodeURIComponent(projectId)}/assets`, {method:'POST',body:form});
      this.status.textContent = 'Preparing preview and waveform… Use Stop process to cancel.';
      await this.options.acceptUpload(result, projectId);
      if (this.project()?.id === projectId) { this.render(); this.status.textContent = 'Ready. Add the file at the yellow playhead.'; }
    } catch (error) { if (this.project()?.id === projectId) this.status.textContent = error.message; }
    finally { this.uploading = false; this.options.busyChanged?.(); }
  }
  async add(assetId) {
    if (this.options.busy()) return;
    this.options.pause();
    try {
      if (!(await this.flush())) return;
      const result = await this.options.edit('media_add', {asset_id:assetId,start:Math.min(this.options.time(), Math.max(0,this.options.duration()-.1))});
      if (result) { this.selected = result.manual?.media_clips?.at(-1)?.id; this.render(); }
    } catch (error) { this.status.textContent = error.message; }
  }
  select(id) { this.selected = id; this.render(); }
  render() {
    const project = this.project();
    if (this.projectId !== project?.id) { this.pause(); this.clearPlayers(); this.pending.clear(); this.overrides.clear(); this.saving=null; this.mixerOverride = null; this.selected = null; this.solo = null; clearTimeout(this.timer); this.projectId = project?.id; }
    const library = this.root.querySelector('.media-library'); library.replaceChildren();
    for (const asset of Object.values(project?.assets || {})) {
      const card = document.createElement('div'); card.className = 'media-asset';
      if (asset.thumbnail_url) { const image = document.createElement('img'); image.src = asset.thumbnail_url; image.alt = ''; image.loading = 'lazy'; card.append(image); }
      const title = document.createElement('span'); title.textContent = `${asset.name} · ${asset.kind}`; title.title = asset.name; card.append(title);
      const button = document.createElement('button'); button.type = 'button'; button.dataset.asset = asset.id;
      button.textContent = asset.status === 'ready' ? '+ Add' : asset.status || 'Preparing'; button.disabled = asset.status !== 'ready'; card.append(button); library.append(card);
      if (['failed','cancelled'].includes(asset.status)) { delete button.dataset.asset; button.dataset.retry=asset.id;button.textContent='Retry';button.disabled=false; }
    }
    if (!library.children.length) { const note = document.createElement('p'); note.className = 'media-help'; note.textContent = 'Video, PNG/JPG/WebP images, music and voiceover. Files are processed locally; no AI needed.'; library.append(note); }
    const clip = this.clips().find(item => item.id === this.selected), asset = project?.assets?.[clip?.asset_id];
    this.root.querySelector('.media-inspector').hidden = !clip;
    if (clip && asset) {
      this.root.querySelector('.media-selected-name').textContent = asset.name;
      for (const input of this.root.querySelectorAll('[data-media]')) {
        if (document.activeElement === input) continue;
        const key = input.dataset.media;
        if (input.type === 'checkbox') input.checked = Boolean(clip[key]);
        else input.value = ['x','y','w','h'].includes(key) ? Math.round(Number(clip[key] ?? (['w','h'].includes(key) ? 1 : 0))*100) : clip[key] ?? '';
      }
      this.root.querySelector('[data-value=volume_db]').textContent = `${clip.volume_db || 0} dB`;
      for (const node of this.root.querySelectorAll('[data-kind]')) node.hidden = !({timed:asset.kind !== 'image',visual:asset.kind !== 'audio',sound:asset.kind !== 'image',video:asset.kind === 'video',image:asset.kind === 'image'}[node.dataset.kind]);
      this.root.querySelector('.media-placement').hidden = asset.kind === 'audio';
    }
    this.renderMixer();
  }
  renderMixer() {
    const mixer = this.mixer();
    this.root.querySelector('[data-ducking]').checked=Boolean(mixer.ducking);
    for (const input of this.root.querySelectorAll('[data-mix]')) { if (document.activeElement !== input) input.value = mixer[input.dataset.mix] || 0; }
    for (const out of this.root.querySelectorAll('[data-mix-value]')) out.textContent = `${mixer[out.dataset.mixValue] || 0} dB`;
    for (const button of this.root.querySelectorAll('[data-mute]')) button.setAttribute('aria-pressed', String(Boolean(mixer[`${button.dataset.mute}_muted`])));
    for (const button of this.root.querySelectorAll('[data-solo]')) button.setAttribute('aria-pressed', String(this.solo === button.dataset.solo));
  }
  change(input) {
    if (this.options.busy()) { this.render(); return; }
    if (input.hasAttribute('data-ducking')) { this.queueMixer({ducking:input.checked}); return; }
    if (input.dataset.mix) { this.queueMixer({[input.dataset.mix]:Number(input.value)}); return; }
    const key = input.dataset.media; if (!key || !this.selected || !input.checkValidity()) return;
    let value = input.type === 'checkbox' ? input.checked : ['role','fit','motion'].includes(key) ? input.value : Number(input.value);
    if (['x','y','w','h'].includes(key)) value /= 100;
    this.queueClip(this.selected, {[key]:value});
  }
  queueClip(id, patch) {
    this.overrides.set(id, {...this.overrides.get(id),...patch});
    this.pending.set(id, {...this.pending.get(id),...patch}); this.schedule(); this.render(); this.options.preview();
  }
  previewClip(id, patch) { if (patch) this.overrides.set(id,patch); else this.overrides.delete(id); this.options.preview(); }
  queueMixer(patch) { this.mixerOverride = {...this.mixerOverride,...patch}; this.pending.set('mixer',{...this.pending.get('mixer'),...patch}); this.schedule(); this.renderMixer(); this.options.preview(); }
  schedule() { clearTimeout(this.timer); this.status.textContent = 'Saving…'; this.timer = setTimeout(()=>this.flush(),400); }
  async flush() {
    clearTimeout(this.timer); if (this.saving) return this.saving;
    const projectId = this.project()?.id;
    const task = Promise.resolve().then(async()=>{
      while (this.pending.size && this.project()?.id === projectId) {
        const [key, patch] = this.pending.entries().next().value; this.pending.delete(key);
        try {
          const result = await this.options.edit(key === 'mixer' ? 'set_audio_mixer' : 'media_update',key === 'mixer' ? patch : {clip_id:key,...patch});
          if (this.project()?.id !== projectId) return false;
          if (!result) throw new Error('The edit is busy. Try the change again.');
          if (!this.pending.has(key)) { if (key === 'mixer') this.mixerOverride = null; else this.overrides.delete(key); }
        } catch(error) {
          if (this.project()?.id !== projectId) return false;
          this.pending.clear(); this.overrides.clear(); this.mixerOverride = null;
          if (this.project()?.id === projectId) { this.status.textContent = `Not saved: ${error.message} Previous settings restored.`; this.render(); this.options.preview(); }
          return false;
        }
      }
      if (this.project()?.id === projectId) { this.status.textContent = 'Saved'; this.render(); this.options.preview(); }
      return true;
    }).finally(()=>{if(this.saving===task)this.saving = null;});
    this.saving=task;
    return task;
  }
  async retry(assetId) {
    if(this.options.busy() || this.uploading)return;
    const projectId=this.project().id;this.uploading=true;this.options.busyChanged?.();
    try {const result=await this.options.api(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/prepare`,{method:'POST',body:'{}'});await this.options.acceptUpload(result,projectId);}
    catch(error){if(this.project()?.id===projectId)this.status.textContent=error.message;}finally{this.uploading=false;this.render();this.options.busyChanged?.();}
  }
  async action(action) {
    if (!this.selected || this.options.busy() || !(await this.flush())) return;
    this.options.pause();
    try { await this.options.edit(`media_${action}`, {clip_id:this.selected,...(action === 'split' ? {time:this.options.time()} : {})}); this.render(); }
    catch(error) { this.status.textContent = error.message; }
  }
  async resumeAudio() {
    try {
      if (!this.context) {
        const Audio = window.AudioContext || window.webkitAudioContext; if (!Audio) return;
        this.context = new Audio(); this.master = this.context.createGain(); this.limiter = this.context.createDynamicsCompressor();
        this.limiter.threshold.value = 20*Math.log10(.98); this.limiter.knee.value = 0; this.limiter.ratio.value = 20;
        this.limiter.attack.value = .005; this.limiter.release.value = .05;
        this.analyser = this.context.createAnalyser(); this.analyser.fftSize = 256;
        this.master.connect(this.limiter).connect(this.analyser).connect(this.context.destination);
      }
      if (this.context.state !== 'running') await this.context.resume();
    } catch { /* Browsers without Web Audio still support attenuation via volume. */ }
  }
  player(key, kind, url) {
    let item = this.players.get(key);
    if (item && (item.url !== url || item.element.tagName.toLowerCase() !== kind)) { this.releasePlayer(key,item); item = null; }
    if (!item) {
      const element = document.createElement(kind); element.src = url; element.preload = 'metadata'; element.playsInline = true;
      element.className = kind === 'audio' ? 'media-audio-player' : 'media-overlay-content';
      item = {element,url,gain:null,node:null,token:0};
      if (kind !== 'audio') { item.frame = document.createElement('div'); item.frame.className = 'media-overlay'; item.frame.append(element); this.stage.append(item.frame); }
      else this.root.append(element);
      this.players.set(key,item);
    }
    if (kind === 'audio' && this.context && !item.node) { item.node = this.context.createMediaElementSource(item.element); item.gain = this.context.createGain(); item.analyser=this.context.createAnalyser();item.analyser.fftSize=256;item.node.connect(item.gain).connect(item.analyser).connect(this.master); }
    return item;
  }
  syncPlayer(item, time, speed, playing, gain = 0) {
    const element = item.element; element.playbackRate = speed; element.preservesPitch = true;
    if (item.gain) item.gain.gain.value = gain; else element.volume = Math.max(0,Math.min(1,gain*10**(Number(this.mixer().master_db||0)/20)));
    if (Math.abs(element.currentTime-time) > .12) { try { element.currentTime = Math.max(0,time); } catch {} }
    item.wanted = playing;
    if (!playing) { item.token++; element.pause(); return; }
    if (element.paused && !item.pending) {
      const token = ++item.token; item.pending = true;
      Promise.resolve(element.play()).then(()=>{ if (token !== item.token || !item.wanted) element.pause(); }).catch(()=>{}).finally(()=>{item.pending=false;});
    }
  }
  sync(time, playing, source = {}) {
    const project = this.project(); if (!project || source.sourceMode) { this.pause(); return; }
    const mixer = this.mixer(), active = new Set(), clips = this.clips();
    let speechRms=0;
    for(const item of this.players.values()) if(item.analyser && ['source','voice'].includes(item.role) && item.wanted) {
      const samples=new Float32Array(256);item.analyser.getFloatTimeDomainData(samples);speechRms+=Math.sqrt(samples.reduce((sum,v)=>sum+v*v,0)/samples.length);
    }
    const desiredDuck=mixer.ducking && speechRms>.025 ? (speechRms/.025)**(1/8-1) : 1;
    const now=performance.now(),elapsed=Math.max(0,Math.min(.2,(now-(this.duckTime||now))/1000));this.duckTime=now;
    this.duckGain=(this.duckGain??1)+(desiredDuck-(this.duckGain??1))*(1-Math.exp(-elapsed/(desiredDuck < (this.duckGain??1) ? .02 : .35)));
    if (this.master) this.master.gain.value = 10 ** (Number(mixer.master_db || 0)/20);
    const soloGain = role => !this.solo || this.solo === role ? 1 : 0;
    for (const [index,clip] of clips.entries()) {
      const asset = project.assets?.[clip.asset_id]; if (!asset?.url || asset.status !== 'ready' || time < clip.start || time >= clip.end) continue;
      const local = time-clip.start, speed = Number(clip.speed)||1;
      if (asset.kind !== 'audio') {
        const key = `v:${clip.id}`, item = this.player(key,asset.kind === 'image' ? 'img' : 'video',asset.url); active.add(key);
        item.frame.hidden = false; Object.assign(item.frame.style,{left:`${clip.x*100}%`,top:`${clip.y*100}%`,width:`${clip.w*100}%`,height:`${clip.h*100}%`,zIndex:String(3+index)});
        item.frame.style.background=clip.fit==='contain' ? '#000':'transparent';
        Object.assign(item.element.style,{objectFit:clip.fit === 'contain' ? 'contain':'cover',transform:visualMotion(clip,time)});
        if (asset.kind === 'video') { item.element.muted = true; const target = Number(clip.video_source_start ?? clip.source_start ?? 0)+local*speed; this.syncPlayer(item,Math.min(target,Math.max(0,asset.duration-.04)),speed,playing && target < asset.duration,0); }
      }
      if (asset.kind === 'audio' || (asset.has_audio && clip.audio_enabled)) {
        const key=`a:${clip.id}`, item=this.player(key,'audio',asset.url); active.add(key);
        const rate = asset.kind === 'video' ? 1 : speed, target=Number(clip.source_start||0)+local*rate;
        item.role=clip.role||'music';
        this.syncPlayer(item,target,rate,playing && target < asset.duration,mediaGain(clip,mixer,time)*soloGain(item.role)*(item.role==='music' ? this.duckGain:1));
      }
    }
    if (source.url && source.point && source.hasAudio) {
      const key='source', item=this.player(key,'audio',source.url); active.add(key);
      item.role='source';
      this.syncPlayer(item,source.point.sourceTime,1,playing,(mixer.source_muted ? 0 : 10**(Number(mixer.source_db||0)/20))*soloGain('source'));
    }
    for (const [key,item] of this.players) if (!active.has(key)) this.releasePlayer(key,item);
    if (this.analyser && playing) {
      const bins = new Float32Array(this.analyser.fftSize); this.analyser.getFloatTimeDomainData(bins);
      const peak = bins.reduce((value, sample)=>Math.max(value,Math.abs(sample)),0);
      this.root.querySelector('.mixer-meter').value=peak;
      this.root.querySelector('.mixer-level-text').textContent=peak>.9 ? 'High output level — lower a channel to leave headroom.' : `${peak>0 ? (20*Math.log10(peak)).toFixed(1) : '−∞'} dBFS · preview output`;
    }
  }
  pause() { for(const item of this.players.values()){ item.wanted=false; item.token++; item.element.pause?.(); if(item.frame)item.frame.hidden=true; } }
  releasePlayer(key,item) {
    item.wanted=false; item.token++; item.element.pause?.();
    item.node?.disconnect(); item.gain?.disconnect(); item.analyser?.disconnect();
    item.element.removeAttribute?.('src'); item.element.load?.();
    (item.frame||item.element).remove?.(); this.players.delete(key);
  }
  clearPlayers() { for(const [key,item] of this.players)this.releasePlayer(key,item); }
}
