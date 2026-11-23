// A compositing property of one occurrence, never an asset or audio gain.
import {layerTrackState} from './layer-tracks.js?v=20261116-track-levels2-opacity1';
const valid=n=>Number.isInteger(n)&&n>=0&&n<=100,fail=issue=>({issue});
const equal=(a,b)=>a===b||(a!==null&&b!==null&&typeof a==='object'&&typeof b==='object'&&Array.isArray(a)===Array.isArray(b)&&Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k])));
const omit=(o,keys)=>Object.fromEntries(Object.entries(o||{}).filter(([k])=>!keys.includes(k)));
export function parsedOpacity(s){if(typeof s!=='string'||!/^\d{1,3}$/.test(s.trim()))return null;const n=Number(s);return valid(n)?n:null;}
export function planClipOpacity(p,id,value){
  if(!p?.id||!p.draft||!Number.isInteger(p.revision)||p.revision<1||p.editor_sequence?.error)return fail('Open the saved edit before changing picture opacity.');
  if(!valid(value))return fail('Enter a whole opacity percentage from 0 to 100.');
  const rows=p.manual?.media_clips;if(!Array.isArray(rows))return fail('Select one imported video or image occurrence.');
  const matched=rows.filter(c=>c.id===id);if(matched.length!==1)return fail('Select one existing timeline occurrence.');
  const clip=matched[0],asset=p.assets?.[clip.asset_id];
  if(!asset||asset.id!==clip.asset_id||asset.status!=='ready'||!['video','image'].includes(asset.kind))return fail('Opacity is for a ready imported video or image, not audio, original A/B or text.');
  const tracks=layerTrackState(p);if(tracks.issue)return fail(tracks.issue);
  if(tracks.enabled){const t=tracks.tracks.find(t=>t.id===clip.track_id);if(!t||t.kind!=='visual')return fail('The selected occurrence has no valid visual track.');if(t.locked)return fail('Unlock '+t.name+' before changing opacity.');}
  const before=Object.hasOwn(clip,'opacity_percent')?clip.opacity_percent:100;
  if(!valid(before))return fail('The saved opacity is invalid. Reopen the edit before changing it.');
  return {issue:'',clip,asset,before,value,noop:before===value,detail:{clip_id:id,opacity_percent:value}};
}
export function verifyClipOpacity(before,after,d){
 const plan=planClipOpacity(before,d?.clip_id,d?.opacity_percent);if(plan.issue)return plan.issue;
 if(after?.id!==before.id||after.revision!==before.revision+(plan.noop?0:1)||!after.manual)return 'Unexpected project or revision.';
 const history=before.manual.history||{},h=after.manual.history||{};
 if(plan.noop){if(!equal(before.manual,after.manual))return 'A no-op made an unexpected edit.';}
 else{
  const want=before.manual.media_clips.map(c=>{if(c.id!==d.clip_id)return c;const n={...c};if(d.opacity_percent===100)delete n.opacity_percent;else n.opacity_percent=d.opacity_percent;return n;});
  if(!equal(want,after.manual.media_clips)||!equal(omit(before.manual,['media_clips','history']),omit(after.manual,['media_clips','history'])))return 'Another clip, clock, audio setting, or track changed.';
  if(h.undo_count!==Math.min(20,(history.undo_count||0)+1)||h.redo_count!==0)return 'The save did not create exactly one Undo step.';
 }
 if(!equal(omit(before.draft,['edited_at','status']),omit(after.draft,['edited_at','status']))||['assets','sources','settings','editor_sequence','editor_captions','review_markers','exports'].some(k=>!equal(before[k],after[k])))return 'Unrelated project content changed.';
 return '';
}
export function initClipOpacity(root,{snapshot,commit,paint}){
 if(!root||typeof snapshot!=='function'||typeof commit!=='function'||typeof paint!=='function')return null;
 const q=k=>root.querySelector('[data-opacity-'+k+']'),field=q('value'),slide=q('slider'),hold=q('preview'),apply=q('apply'),reset=q('reset'),status=q('status');
 if(!field||!slide||!hold||!apply||!reset||!status)return null;
 const doc=root.ownerDocument,win=doc.defaultView,teardowns=[];
 const on=(node,t,f,opt)=>{node?.addEventListener(t,f,opt);teardowns.push(()=>node?.removeEventListener(t,f,opt));};
 const put=(el,t)=>{if(el.textContent!==t)el.textContent=t;};
 let model='',review='',scratch='',held=null,working=false,dead=false,accepted=null;
 const identity=s=>JSON.stringify([s.project?.id,s.project?.revision,s.view,s.selected]);
 const release=()=>{if(!held)return false;const old=held;held=null;hold.setAttribute('aria-pressed','false');paint(old.id);return true;};
 const ink=(p,id)=>held&&root.open&&!root.closest?.('[hidden],[inert]')&&held.project===p?.id&&held.revision===p?.revision&&held.id===id?held.value:null;
 function refresh(){
  if(dead)return null;
  if(!root.open||root.closest?.('[hidden],[inert]')){release();model='';review='';accepted=null;return null;}
  const s=snapshot(),key=identity(s),probe=planClipOpacity(s.project,s.selected,100);
  if(key!==model){release();model=key;const value=probe.issue?'':String(probe.before);scratch=value;field.value=value;slide.value=value||'100';if(accepted?.key!==key)accepted=null;}
  const value=parsedOpacity(scratch),plan=probe.issue?probe:planClipOpacity(s.project,s.selected,value);
  const issue=s.issue||plan.issue||'',clip=plan.clip||probe.clip;
  const active=Boolean(clip&&clip.enabled!==false&&Number.isFinite(s.time)&&s.time>=clip.start-5.1e-10&&s.time<clip.end-5.1e-10);
  if(held&&(working||issue||!active||held.value!==value))release();
  const nochange=!issue&&plan.noop,dirty=!probe.issue&&value!==probe.before;
  field.disabled=slide.disabled=working||Boolean(s.issue||probe.issue);
  reset.disabled=field.disabled||value===100;hold.disabled=working||Boolean(issue||nochange)||!active;apply.disabled=working||Boolean(issue||nochange);
  field.setAttribute('aria-invalid',String(!probe.issue&&value===null));
  if(working)put(status,'Saving picture opacity for this occurrence…');
  else if(issue)put(status,issue);
  else if(held)put(status,'Auditioning '+value+'% in Program only. Release to compare with the saved '+plan.before+'%.');
  else if(dirty)put(status,'Saved '+plan.before+'%. '+value+'% is not applied.'+(active?' Hold Preview to compare.':' Place the edit playhead inside the enabled clip to audition.'));
  else put(status,(accepted?.key===key?'Saved ':'Current ')+plan.before+'% picture opacity. Sound and other occurrences are unchanged.');
  review=issue?'':JSON.stringify([key,value]);return {s,key,value,plan,active,issue};
 }
 const set=(value,fromField=false)=>{release();scratch=value;accepted=null;if(!fromField)field.value=value;const n=parsedOpacity(value);if(n!==null&&slide.value!==String(n))slide.value=String(n);refresh();};
 function begin(){
  if(dead||working||held)return false;const seen=review,v=refresh();if(!v||v.issue||v.plan.noop||!v.active||!seen||seen!==review)return false;
  held={project:v.s.project.id,revision:v.s.project.revision,id:v.s.selected,value:v.value};hold.setAttribute('aria-pressed','true');paint(held.id);refresh();return true;
 }
 function end(){if(release())refresh();}
 async function save(){
  if(dead||working)return;release();const seen=review,v=refresh();if(!v||v.issue||v.plan.noop||!seen||seen!==review)return;
  const owner={id:v.s.project.id,revision:v.s.project.revision,view:v.s.view,selected:v.s.selected};
  const owns=()=>!dead&&root.open&&!root.closest?.('[hidden],[inert]');
  working=true;refresh();
  try{const saved=await commit(owner,v.plan.detail,owns);if(owns()&&saved?.id===owner.id&&saved.revision===owner.revision+1){
    const now=snapshot();if(now.project?.id===saved.id&&now.project.revision===saved.revision&&now.view===owner.view&&now.selected===owner.selected)accepted={key:identity(now)};
  }}finally{working=false;refresh();}
 }
 on(root,'toggle',refresh);on(field,'input',()=>set(field.value,true));on(slide,'input',()=>set(slide.value));on(reset,'click',()=>set('100'));
 on(hold,'pointerdown',e=>{if(e.button!==0||e.isPrimary===false)return;if(begin()){e.preventDefault();hold.focus({preventScroll:true});try{hold.setPointerCapture(e.pointerId);}catch{};}});
 on(hold,'keydown',e=>{if(![' ','Enter','Spacebar'].includes(e.key)||e.isComposing||e.altKey||e.ctrlKey||e.metaKey||e.shiftKey)return;e.preventDefault();e.stopPropagation();if(!e.repeat)begin();});
 on(hold,'keyup',e=>{if([' ','Enter','Spacebar'].includes(e.key)){e.preventDefault();e.stopPropagation();end();}});
 on(win,'pointerup',end,true);on(win,'pointercancel',end,true);on(hold,'lostpointercapture',end);on(hold,'blur',end);on(win,'blur',end);
 on(doc,'visibilitychange',()=>{if(doc.hidden)end();});
 // Timeline Index completes its selection promise first, then closes its native
 // dialog. The close event does not bubble; capture it after that last guard falls.
 on(doc,'close',e=>{if(e.target?.tagName==='DIALOG')refresh();},true);
 if(typeof win?.MutationObserver==='function'){
  const o=new win.MutationObserver(refresh),panel=doc.getElementById?.('studioPanelMedia'),inspector=doc.getElementById?.('studioInspector');
  if(panel)o.observe(panel,{attributes:true,attributeFilter:['hidden','inert']});if(inspector)o.observe(inspector,{attributes:true,attributeFilter:['data-workbench-pane']});
  teardowns.push(()=>o.disconnect());
 }
 on(hold,'click',e=>e.preventDefault());
 on(apply,'click',()=>{void save().catch(()=>{if(!dead)put(status,'The save could not be confirmed. Reopen the saved edit before repeating it.');});});
 refresh();return {get open(){return !dead&&root.open&&!root.closest?.('[hidden],[inert]');},refresh,previewFor:ink,release:end,destroy(){release();dead=true;teardowns.forEach(f=>f());}};
}
