// Absolute edit-clock notes. Frame/rate pairs preserve their time if output FPS changes.
const rates = new Set([24,25,30,50,60]);
const colors = Object.freeze({amber:'#e8ac43',teal:'#30af9b',violet:'#a988e6',coral:'#e87d71'});
const validText=(s,n,required)=>typeof s==='string' && s.trim()===s && [...s].length<=n && (!required || (s.length>0&&!s.includes('\n'))) && !/[\u0000-\u0009\u000b-\u001f]/.test(s);
export function reviewMarkerRows(reg) {
  if (reg === undefined) return [];
  if (!reg || reg.version !== 1 || Object.keys(reg).length !== 2 || !Array.isArray(reg.items) || reg.items.length > 200) return null;
  const ids=new Set();
  for (const m of reg.items) {
    if (!m || Object.keys(m).length!==6 || typeof m.id!=='string' || !/^marker_[a-f0-9]{12}$/.test(m.id) || ids.has(m.id)
        || !Number.isSafeInteger(m.frame) || m.frame<0 || m.frame>100000000 || !rates.has(m.fps)
        || typeof m.color!=='string' || !Object.hasOwn(colors,m.color) || !validText(m.label,80,true) || !validText(m.note,320,false)) return null;
    ids.add(m.id);
  }
  return [...reg.items].sort((a,b)=>a.frame/a.fps-b.frame/b.fps||a.id.localeCompare(b.id));
}
export function markerFrame(time, duration, fps, atPlayhead=false) {
  if(!rates.has(fps)||!Number.isFinite(duration)||duration<=0||!Number.isFinite(time)||time<0||time>duration||(!atPlayhead && time>=duration)) return null;
  const total=Math.floor(duration*fps+.5);
  return total>0 ? Math.min(total-1,Math.floor(time*fps+.5)) : null;
}
export function markerNavigation(rows, duration, fps, current) {
  let before=null,after=null;
  for(const m of rows||[]) {
    const f=markerFrame(m.frame/m.fps,duration,fps);
    if(f===null)continue;
    if(f<current)before=m;
    if(f>current && !after)after=m;
  }
  return {before,after};
}
const tc=(frame,fps)=>{const s=Math.floor(frame/fps);return [Math.floor(s/3600),Math.floor(s/60)%60,s%60,frame%fps].map(n=>String(n).padStart(2,'0')).join(':');};
const same=(a,b)=>!!a&&!!b&&a.id===b.id&&a.view===b.view&&a.revision===b.revision&&a.fps===b.fps&&a.duration===b.duration;
const shape=o=>({label:o.label,note:o.note,color:o.color});
export function initReviewMarkers(bar, dialog, {snapshot, write, seek, pause, notify}) {
  if (!bar?.ownerDocument || !dialog?.showModal) return null;
  const doc=bar.ownerDocument, make=(tag,cls,txt)=>{const e=doc.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e;};
  const button=(cls,name,title)=>{const b=make('button',cls,name);b.type='button';b.title=title;b.setAttribute('aria-label',title);return b;};
  const wrap=make('span','marker-controls'),prev=button('marker-arrow','‹','Previous review marker'),launch=button('','Markers','Open timeline review markers'),next=button('marker-arrow','›','Next review marker');
  launch.id='timelineMarkersButton';prev.id='timelinePreviousMarker';next.id='timelineNextMarker';
  const readout=make('span','marker-readout'),announcement=make('span','sr-only');readout.hidden=true;announcement.setAttribute('role','status');
  launch.setAttribute('aria-haspopup','dialog');wrap.append(prev,launch,next,readout,announcement);bar.insertBefore(wrap,bar.querySelector('.timeline-timecode-form'));
  const el=Object.fromEntries(['close','count','empty','list','form','heading','position','label','note','color','save','new','move','remove','reset','status'].map(k=>[k,dialog.querySelector('[data-marker-'+k+']')]));
  let owner=null,editing=null,original=null,busy=false,confirmRemove=false,origin=null,cacheReg=Symbol('empty'),cacheRows=null,epoch=0,navKey='';
  function model(s){if(cacheReg!==s?.registry){cacheReg=s?.registry;cacheRows=reviewMarkerRows(cacheReg);}return cacheRows;}
  const dirty=()=>!!original && (original.label!==el.label.value || original.note!==el.note.value || original.color!==el.color.value);
  const status=m=>{el.status.textContent=m||'';};
  const focus=e=>{if(e?.isConnected!==false)e?.focus?.({preventScroll:true});};
  function ready(s){return !!s?.editor && !!s.id && Number.isSafeInteger(s.revision) && s.revision>0 && s.editMode && !s.busy && model(s)!==null && markerFrame(s.time,s.duration,s.fps,true)!==null;}
  function updateForm(){
    if(!owner||!dialog.open)return;
    const s=snapshot(), usable=same(owner,s)&&ready(s)&&!busy,changed=dirty();
    el.save.disabled=!usable || !el.label.value.trim() || (!!editing&&!changed);
    const row=(model(s)||[]).find(m=>m.id===editing);
    el.move.disabled=!usable||changed||!row||row.frame*owner.fps===owner.frame*row.fps;el.remove.disabled=!usable||changed;
    el.label.disabled=el.note.disabled=el.color.disabled=busy;
    el.move.hidden=el.remove.hidden=el.new.hidden=!editing;
    el.reset.hidden=!changed;el.reset.disabled=busy;
    el.new.disabled=busy||changed;el.remove.textContent=confirmRemove?'Confirm removal':'Remove marker';
  }
  function renderList(s){
    const rows=model(s)||[];el.count.textContent=String(rows.length);el.empty.hidden=!!rows.length;el.list.replaceChildren();
    for(const m of rows){
      const frame=markerFrame(m.frame/m.fps,s.duration,s.fps),inside=frame!==null;
      const row=make('li','marker-row');row.dataset.markerId=m.id;row.style.setProperty('--mark',colors[m.color]);
      const jump=button('marker-jump','',inside?'Go to '+m.label:'Outside this edit: '+m.label);
      jump.dataset.markerGo=m.id;jump.disabled=!inside;jump.append(make('b','',m.label),make('small','',inside?tc(frame,s.fps)+' · '+m.color:tc(m.frame,m.fps)+' · outside edit'));
      if(m.note)jump.append(make('span','marker-note',m.note));
      const edit=button('button ghost compact','Edit','Edit marker '+m.label);edit.dataset.markerEdit=m.id;
      jump.addEventListener('click',()=>jumpTo(m));edit.addEventListener('click',()=>{if(!changeAllowed())return;form(m);focus(el.label);});
      row.append(jump,edit);el.list.append(row);
    }
  }
  function form(m=null){
    editing=m?.id||null;confirmRemove=false;original=m?shape(m):{label:'Marker '+((model(snapshot())?.length||0)+1),note:'',color:'amber'};
    el.label.value=original.label;el.note.value=original.note;el.color.value=original.color;
    el.heading.textContent=m?'Edit marker':'Add at playhead';el.save.textContent=m?'Save changes':'Add marker';
    el.position.textContent=m?'Saved at '+tc(m.frame,m.fps)+' ('+m.fps+' FPS). Playhead: '+tc(owner.frame,owner.fps)+'.':'Playhead '+tc(owner.frame,owner.fps)+' · '+owner.fps+' FPS';
    status('');updateForm();
  }
  function changeAllowed(){
    if(busy)return false;
    if(dirty()){status('Save your changes or choose Discard changes first.');focus(el.reset);return false;}
    if(!same(owner,snapshot()) || !ready(snapshot())){status('The saved timeline changed or is busy. Close and reopen the project before editing this note.');return false;}
    return true;
  }
  function close(force=false){
    if(!dialog.open)return;
    if(!force&&!busy&&dirty()){status('Save your changes or choose Discard changes before closing.');focus(el.reset);return;}
    dialog.close();
  }
  function open(){
    if(dialog.open)return false;
    const s=snapshot();
    if(!ready(s)){notify?.(model(s)===null?'Unsupported marker collection. Saved notes were left unchanged.':'Open a saved, idle Edited video timeline first.');return false;}
    const f=markerFrame(s.time,s.duration,s.fps,true);if(f===null)return false;
    pause(); owner={...s,frame:f};origin=doc.activeElement;epoch++;busy=false;
    renderList(s);if(!dialog.open)dialog.showModal();form();focus(el.label);el.label.select?.();return true;
  }
  function jumpTo(m){
    if(dialog.open&&!changeAllowed())return false;
    const s=snapshot(),found=(model(s)||[]).find(x=>x.id===m?.id),f=found&&markerFrame(found.frame/found.fps,s.duration,s.fps);
    if(!found||f==null||!ready(s))return false;
    close(true);pause();seek(f/s.fps);announcement.textContent='Marker: '+found.label;return true;
  }
  function adjacent(direction){const s=snapshot(),f=markerFrame(s.time,s.duration,s.fps,true);if(f==null || !ready(s))return false;return jumpTo(markerNavigation(model(s),s.duration,s.fps,f)[direction]);}
  function sync(){
    const s=snapshot(),rows=model(s),f=markerFrame(s.time,s.duration,s.fps,true),can=ready(s),nav=markerNavigation(rows,s.duration,s.fps,f);
    const at=can&&f!==null?(rows||[]).find(m=>markerFrame(m.frame/m.fps,s.duration,s.fps)===f):null;
    const key=JSON.stringify([s.id,s.editor,s.editMode,can,rows?.length,!!nav.before,!!nav.after,at?.id,at?.label,at?.note]);
    if(key!==navKey){navKey=key;wrap.hidden=!s.editor;launch.disabled=!can;launch.textContent=rows?.length?'Markers ('+rows.length+')':'Markers';
      launch.title=can?'Open timeline review markers':!s.editMode?'Choose Edited video to review timeline markers.':rows===null?'Unsupported marker collection; saved notes are unchanged.':'Choose a frame on a saved, idle edit first.';
      prev.hidden=next.hidden=!rows?.length;prev.disabled=!can||!nav.before;next.disabled=!can||!nav.after;
      readout.hidden=!at;readout.textContent=at?.label||'';readout.title=at?.note||at?.label||'';}
    if(dialog.open&&owner && (owner.id!==s.id||owner.view!==s.view)){close(true);return;}
    if(dialog.open&&owner&&!same(owner,s)&&!busy){status('The saved timeline changed. Close and reopen the marker panel before saving.');updateForm();}
  }
  async function commit(action){
    const s=snapshot(),ticket=owner,token=epoch;if(!ticket||busy||!same(ticket,s)||!ready(s)){status('The saved edit changed. Reopen the project before saving.');return;}
    if((action==='move'||action==='remove')&&(!editing||dirty()))return;
    if(action==='remove'&&!confirmRemove){confirmRemove=true;status('Remove this review note only? Press Confirm removal.');updateForm();return;}
    const body={action,expected_revision:ticket.revision};
    if(action!=='add')body.id=editing;
    if(action==='add'||action==='move')Object.assign(body,{frame:ticket.frame,fps:ticket.fps});
    if(action==='add'||action==='edit'){
      if(!el.label.value.trim())return;
      Object.assign(body,{label:el.label.value.trim(),note:el.note.value.trim(),color:el.color.value});
    }
    busy=true;updateForm();status('Saving marker…');
    try{
      const accepted=await write(ticket,body);
      if(epoch!==token || !dialog.open)return;
      const now=snapshot();
      if(!accepted || now.id!==ticket.id||now.view!==ticket.view){status('Marker response no longer belongs to this view. Reopen the project to verify.');return;}
      busy=false;owner={...now,frame:ticket.frame};renderList(now);form();
      status(action==='remove'?'Marker removed.':action==='move'?'Marker moved to the playhead.':'Marker saved.');focus(el.label);el.label.select?.();
    }catch(e){if(epoch===token&&dialog.open)status('Not confirmed. '+(e?.message||'Reopen the project to verify before retrying.'));}
    finally{if(epoch===token){busy=false;confirmRemove=false;updateForm();sync();}}
  }
  launch.addEventListener('click',open);prev.addEventListener('click',()=>adjacent('before'));next.addEventListener('click',()=>adjacent('after'));
  el.close.addEventListener('click',()=>close());dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
  dialog.addEventListener('close',()=>{if(dialog.open)return;const s=snapshot(),sameView=owner?.id===s.id&&owner?.view===s.view;epoch++;owner=null;editing=null;busy=false;original=null;const target=origin;origin=null;if(sameView&&!doc.querySelector('dialog[open]'))focus(target);});
  el.form.addEventListener('submit',e=>{e.preventDefault();if(!el.save.disabled)void commit(editing?'edit':'add');});
  el.reset.addEventListener('click',()=>{form((model(snapshot())||[]).find(x=>x.id===editing));focus(el.label);});
  el.new.addEventListener('click',()=>{if(changeAllowed()){form();focus(el.label);el.label.select?.();}});
  el.move.addEventListener('click',()=>void commit('move'));el.remove.addEventListener('click',()=>void commit('remove'));
  for(const event of ['input','change'])el.form.addEventListener(event,()=>{confirmRemove=false;updateForm();});
  function draw(ctx,px,duration){
    const s=snapshot(),rows=model(s);if(!s.editor||!s.editMode||!rows?.length)return;
    ctx.save();
    for(const m of rows){const f=markerFrame(m.frame/m.fps,duration,s.fps);if(f==null)continue;const x=Math.round(f/s.fps*px);
      ctx.fillStyle=colors[m.color];ctx.beginPath();ctx.moveTo(x-4,17);ctx.lineTo(x+4,17);ctx.lineTo(x+4,22);ctx.lineTo(x,27);ctx.lineTo(x-4,22);ctx.closePath();ctx.fill();}
    ctx.restore();
  }
  function hit(time,px){const s=snapshot();if(!ready(s)||!Number.isFinite(px)||px<=0)return false;let best=null,d=6.1;
    for(const m of model(s)||[]){const f=markerFrame(m.frame/m.fps,s.duration,s.fps);if(f==null)continue;const delta=Math.abs(f/s.fps-time)*px;if(delta<d){best=m;d=delta;}}return best?jumpTo(best):false;}
  sync();return {open,sync,draw,hit,adjacent};
}
