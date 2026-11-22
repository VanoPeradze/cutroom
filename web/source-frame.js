// Exact decoded-original still review. Browser video and the edit grid stay separate.
export function projectFrameStep(time, direction, fps, duration) {
  if (![time,fps,duration].every(Number.isFinite) || ![-1,1].includes(direction) || fps<1 || fps>240 || duration<0) return null;
  // Same 0.51 ns tolerance as frame_rates.stored_frame; real subframes stay distinct.
  const nearest=Math.round(time*fps),onGrid=Math.abs(time-nearest/fps)<=5.1e-10;
  const frame=onGrid?nearest+direction:direction>0?Math.floor(time*fps)+1:Math.ceil(time*fps)-1;
  return Math.min(duration,Math.max(0,frame/fps));
}

export function initSourceFrameReview(root,video,options) {
  const doc=root.ownerDocument,win=doc.defaultView||globalThis;
  const make=(tag,text)=>{const n=doc.createElement(tag);if(text)n.textContent=text;return n;};
  const bar=make('div');bar.className='source-frame-controls';
  const previous=make('button','Previous frame'),next=make('button','Next frame'),back=make('button','Return to playback');
  for(const b of [previous,next,back])b.type='button';
  previous.dataset.sourceFrameStep='previous';next.dataset.sourceFrameStep='next';back.dataset.sourceFramePlayback='true';
  previous.setAttribute('aria-keyshortcuts','ArrowLeft');next.setAttribute('aria-keyshortcuts','ArrowRight');
  const info=make('p','Original-frame steps decode the original, not the proxy. In starts at the shown frame; Out includes it.');
  info.className='source-frame-info';info.setAttribute('role','status');info.setAttribute('aria-live','polite');
  let image=make('img');image.className='library-source-frame';image.hidden=true;image.alt='';
  bar.append(previous,next,back,info);video.after(image,bar);
  let frame=null,ticket=null,closed=false,message='',epoch=0;
  const listeners=[],listen=(n,event,fn,capture=false)=>{n.addEventListener(event,fn,capture);listeners.push(()=>n.removeEventListener(event,fn,capture));};
  const read=()=>{try{return options.snapshot();}catch{return null;}};
  const valid=s=>s&&typeof s.key==='string'&&s.key&&typeof s.projectId==='string'&&typeof s.assetId==='string'&&Number.isFinite(s.time)&&Number.isFinite(s.duration)&&s.duration>0;
  const owned=t=>!closed&&ticket===t&&valid(read())&&read().key===t.key&&read().available===true;
  function clear(notify=true) {
    ++epoch;ticket?.abort.abort();ticket=null;frame=null;image.hidden=true;image.removeAttribute('src');video.hidden=false;delete root.dataset.decodedFrame;
    if(notify){sync();options.changed?.();}
  }
  function sync() {
    if(closed)return;const s=read();
    if((frame||ticket)&&(!valid(s)||s.key!==(ticket?.key||frame.key)))clear(false);
    const available=valid(s)&&s.available===true&&!ticket;
    previous.disabled=!available||frame?.index===0;next.disabled=!available||frame?.index===frame?.count-1;
    back.hidden=!frame&&!ticket;back.disabled=false;
    if(ticket)info.textContent='Decoding an original frame. In / Out wait for the picture.';
    else if(message)info.textContent=message+(frame?` Still showing original frame ${frame.index+1}, ${frame.time.toFixed(9)} s.`:'');
    else if(frame)info.textContent=`Original frame ${frame.index+1} of ${frame.count} · ${frame.time.toFixed(9)} s${frame.end==null?' · Last picture end is unverified; set Out manually.':` · Out after this frame: ${frame.end.toFixed(9)} s`}`;
    else info.textContent='Original-frame steps decode the original, not the proxy. In starts at the shown frame; Out includes it. Arrow keys work outside fields and player controls.';
  }
  function responseValid(value,s,before,direction) {
    return value&&value.project_id===s.projectId&&value.asset_id===s.assetId&&/^[a-f0-9]{64}$/.test(value.token)
      &&Number.isInteger(value.index)&&Number.isInteger(value.count)&&value.count>0&&value.count<=50000&&value.index>=0&&value.index<value.count
      &&Number.isFinite(value.time)&&value.time>=0&&value.time<value.duration&&Math.abs(value.duration-s.duration)<1e-6
      &&(value.end===null||Number.isFinite(value.end)&&value.end>value.time&&value.end<=value.duration)
      &&typeof value.image==='string'&&value.image.startsWith('data:image/png;base64,')&&value.image.length<2800000
      &&(!before||value.token===before.token&&value.count===before.count&&value.index===Math.max(0,Math.min(before.count-1,before.index+(direction==='next'?1:-1))));
  }
  async function step(direction) {
    const s=read();if(closed||ticket||!['previous','next'].includes(direction)||!valid(s)||s.available!==true)return false;
    if(frame&&frame.key!==s.key)clear(false);
    if(frame&&(direction==='previous'&&frame.index===0||direction==='next'&&frame.index===frame.count-1))return false;
    options.pause?.();
    const before=frame,t={key:s.key,epoch:++epoch,abort:new AbortController()};ticket=t;message='';sync();options.changed?.();
    try {
      const request={time:before?.time??s.time,direction,...(before?{index:before.index,token:before.token}:{})};
      const value=await options.load(request,{signal:t.abort.signal});if(!owned(t))return false;
      if(!responseValid(value,s,before,direction))throw Object.assign(Error('The original-frame response could not be verified. Return to playback and retry.'),{invalidateFrame:true});
      const decoded=make('img');decoded.className='library-source-frame';decoded.hidden=true;decoded.alt=`Decoded original frame ${value.index+1}, source ${value.time.toFixed(9)} seconds`;decoded.src=value.image;
      if(typeof decoded.decode!=='function')throw Error('This browser cannot verify the decoded still. Ordinary source playback remains available.');
      let timer,onAbort;
      try {
        await Promise.race([decoded.decode(),new Promise((resolve,reject)=>{
          timer=win.setTimeout(()=>reject(Error('Original picture decoding timed out. Return to playback and retry.')),10000);
          onAbort=()=>reject(Object.assign(Error('Review cancelled'),{name:'AbortError'}));
          t.abort.signal.addEventListener('abort',onAbort,{once:true});
        })]);
      } finally {win.clearTimeout(timer);if(onAbort)t.abort.signal.removeEventListener('abort',onAbort);}
      if(!owned(t))return false;
      // Commit this very decoded element, not a different IMG with an unproven load.
      image.replaceWith(decoded);image=decoded;frame={...value,key:s.key};
      image.hidden=false;video.hidden=true;root.dataset.decodedFrame='true';return true;
    } catch(error) {
      if(owned(t)&&error?.name!=='AbortError'){
        const reason=error?.message||'Original frame is unavailable. Ordinary playback remains available.';
        // A known-invalid original must never leave its last still eligible for
        // exact marks. Conservatively clear any API 4xx, including decoder-busy.
        // Local decode timeouts can retain a still whose ownership is unchanged.
        if(error?.invalidateFrame||Number(error?.status)>=400&&Number(error?.status)<500){clear(false);message=reason;sync();options.changed?.();}
        else message=reason;
      }
      return false;
    } finally {
      if(ticket===t){ticket=null;sync();options.changed?.();}
    }
  }
  listen(previous,'click',()=>{void step('previous');});listen(next,'click',()=>{void step('next');});
  listen(back,'click',()=>{const time=frame?.time;message='';clear();if(Number.isFinite(time))video.currentTime=time;});
  listen(root,'keydown',event=>{
    if(!['ArrowLeft','ArrowRight'].includes(event.key)||event.defaultPrevented||event.isComposing||event.keyCode===229||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey||event.getModifierState?.('AltGraph'))return;
    const target=event.composedPath?.()[0]||event.target;
    if(target?.isContentEditable||target?.closest?.('input,textarea,select,[contenteditable],video[controls],audio[controls],[role="textbox"],[role="combobox"]'))return;
    event.preventDefault();event.stopPropagation();if(!event.repeat)void step(event.key==='ArrowLeft'?'previous':'next');
  },true);
  for(const event of ['play','seeking','emptied','error','loadedmetadata'])listen(video,event,()=>{if(frame||ticket){message='';clear();}});
  const controller={get pending(){return Boolean(ticket);},get active(){return Boolean(frame);},get canMarkOut(){return !frame||Number.isFinite(frame.end);},
    mark(key){const s=read();if(ticket)return {issue:'Wait for the original frame to finish decoding.'};if(!frame)return null;
      if(!valid(s)||s.key!==frame.key||!s.available)return {issue:'The source changed; review a current frame.'};
      const value=key==='out'?frame.end:frame.time;return Number.isFinite(value)?{value}:{issue:'The last picture endpoint is unverified. Set Out manually.'};},
    clear:()=>{message='';clear();},sync,step,
    destroy(){if(closed)return;closed=true;clear(false);listeners.forEach(remove=>remove());image.remove();bar.remove();}};
  sync();return controller;
}
