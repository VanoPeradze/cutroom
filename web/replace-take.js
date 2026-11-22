// One occurrence, one different imported file. Never relink a shared original.
import {layerTrackState} from './layer-tracks.js?v=20261116-track-levels2';

const assetId=s=>typeof s==='string' && /^asset_[0-9a-f]{32}$/.test(s);
const clipId=s=>typeof s==='string' && /^media_[0-9a-f]{32}$/.test(s);
const valid=a=>assetId(a?.id) && a.status==='ready' && ['image','video','audio'].includes(a.kind);
const fail=issue=>({issue});
const equal=(a,b)=>a===b || (a!==null&&b!==null&&typeof a==='object'&&typeof b==='object'
  && Array.isArray(a)===Array.isArray(b) && Object.keys(a).length===Object.keys(b).length
  && Object.keys(a).every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k])));
const omit=(o,keys)=>Object.fromEntries(Object.entries(o||{}).filter(([k])=>!keys.includes(k)));
const ns=n=>Math.round(n*1e9)/1e9;
const sec=n=>Number.isFinite(n)?Number(n.toFixed(6))+' s':'unknown';

export function takeContext(project, selected) {
  if(!project?.id || !project.draft || !Number.isInteger(project.revision) || !clipId(selected) || !Array.isArray(project.manual?.media_clips))
    return fail('Select one saved imported video, audio clip or still image.');
  if(project.editor_sequence?.error)return fail(project.editor_sequence.error);
  const model=layerTrackState(project);if(model.issue)return fail(model.issue);
  const rows=project.manual.media_clips.filter(r=>r?.id===selected),clip=rows.length===1?rows[0]:null;
  const old=project.assets?.[clip?.asset_id],duration=project.editor_sequence?.duration??project.manual?.sequence?.duration??project.draft.output_duration;
  if(!clip || !valid(old) || old.id!==clip.asset_id)return fail('The selected clip needs a ready original project file.');
  if(![clip.start,clip.end,duration,clip.speed].every(Number.isFinite) || clip.start<0 || clip.end-clip.start<.08-1e-9
     || clip.end>duration || clip.speed<.25 || clip.speed>4 || old.kind!=='video'&&clip.speed!==1)
    return fail('The selected clip has invalid saved timing. Reopen the current edit.');
  if(old.kind!=='image' && (!Number.isFinite(old.duration) || !Number.isFinite(clip.source_start) || clip.source_start<0
    || clip.source_start+clip.end-clip.start>old.duration+1e-8 || old.kind==='video'&&(!Number.isFinite(clip.video_source_start??clip.source_start)||(clip.video_source_start??clip.source_start)<0)))
    return fail('The original source clock is invalid. Reopen the clip before replacing it.');
  const result={clip,old,length:clip.end-clip.start,track:model.tracks.find(t=>t.id===clip.track_id),
    choices:Object.entries(project.assets).filter(([id,a])=>id===a?.id && valid(a) && id!==old.id && a.kind===old.kind).map(([,a])=>a)};
  if(result.track?.locked)return {...result,issue:'Unlock this clip’s track before replacing its take.'};
  if(!result.choices.length)return {...result,issue:'Import another '+(old.kind==='image'?'still image':old.kind)+' into this project first.'};
  return {...result,issue:''};
}

export function planTake(project, context, detail) {
  if(!context || context.issue)return fail(context?.issue||'Choose an imported clip.');
  const {clip,old,length}=context;
  if(!detail || Object.keys(detail).some(k=>!['clip_id','previous_asset_id','asset_id','source_start','source_end'].includes(k)) || detail.clip_id!==clip.id || detail.previous_asset_id!==old.id || !assetId(detail.asset_id) || detail.asset_id===old.id)
    return fail('Choose a different project file for this clip.');
  const next=project.assets?.[detail.asset_id];
  if(!valid(next) || next.id!==detail.asset_id || next.kind!==old.kind)return fail('Choose a ready file of the same media type.');
  if(next.kind==='video'){
    if([old.id,next.id].some(id=>project.manual.chroma_key?.[id]?.enabled))return fail('An active Chroma Key belongs to one of these files. Choose unkeyed takes; shared keys are not copied.');
    if(typeof old.has_audio!=='boolean'||typeof next.has_audio!=='boolean')return fail('Both videos need known source sound information.');
    if(clip.audio_enabled && old.has_audio!==next.has_audio)return fail('This take would add or remove source sound. Turn off Include source sound on this clip first.');
  }
  const patch={asset_id:next.id};
  if(next.kind==='image'){
    if(Object.hasOwn(detail,'source_start')||Object.hasOwn(detail,'source_end'))return fail('Still images do not use Source In or Out.');
    return {issue:'',patch,description:'Replace the still for the full '+sec(length)+' clip.'};
  }
  if(![old.duration,next.duration].every(v=>Number.isFinite(v)&&v>=.08&&v<=14400))return fail('Both timed files need valid source durations.');
  const point=v=>Number.isFinite(v)&&v>=0&&v<=next.duration;
  if(!point(detail.source_start)||Object.hasOwn(detail,'source_end')&&!point(detail.source_end))return fail('Enter a Source In inside the replacement file.');
  const start=ns(detail.source_start),out=Object.hasOwn(detail,'source_end')?ns(detail.source_end):next.duration,normalEnd=start+length;
  if(out<=start || normalEnd>out+1e-8)return fail('The source range is too short for the whole clip at normal speed. Choose an earlier In or longer take.');
  patch.source_start=start;
  if(next.kind==='video'){
    const pictureEnd=start+length*clip.speed;
    if(pictureEnd>out+1e-8)return fail('Not enough picture for '+clip.speed+'× speed. Choose an earlier In or a longer take; no frozen frames are added.');
    patch.video_source_start=start;
    return {issue:'',patch,description:'Picture '+sec(start)+' to '+sec(pictureEnd)+' ('+clip.speed+'×). '+(clip.audio_enabled&&next.has_audio?'Source sound':'Normal source clock')+' '+sec(start)+' to '+sec(normalEnd)+' (1×).'};
  }
  return {issue:'',patch,description:'Source sound '+sec(start)+' to '+sec(normalEnd)+' (1×).'};
}

export function verifyTake(before,after,detail) {
  const p=planTake(before,takeContext(before,detail?.clip_id),detail);
  if(p.issue || after?.id!==before.id || after.revision!==before.revision+1 || !after.manual || layerTrackState(after).issue)return 'Unexpected clip, track, project or revision.';
  const expected=before.manual.media_clips.map(r=>r.id===detail.clip_id?{...r,...p.patch}:r);
  if(!equal(expected,after.manual.media_clips))return 'A clip, source clock, order or edit edge changed unexpectedly.';
  if(!equal(omit(before.manual,['history','media_clips']),omit(after.manual,['history','media_clips']))
    || !equal(omit(before.draft,['status','edited_at']),omit(after.draft,['status','edited_at']))
    || ['sources','assets','settings','exports','review_markers','editor_sequence','editor_captions'].some(k=>!equal(before[k],after[k])))
    return 'Other saved content changed.';
  if(after.manual.history?.undo_count!==Math.min(20,(before.manual.history?.undo_count??0)+1) || after.manual.history?.redo_count!==0)
    return 'The edit did not confirm one Undo step.';
  return '';
}

export function initTakeReplacement(root,host) {
  if(!root)return null;
  const get=k=>root.querySelector('[data-take-'+k+']'),file=get('file'),input=get('in'),timed=get('timed'),use=get('marks'),
    apply=get('apply'),status=get('status'),where=get('summary');
  let owner=null,cached=null,range=null,candidate='',notice='',pending=false,shown=null,markKey='',markValue=null;
  const say=(node,value)=>{if(node.textContent!==value)node.textContent=value;};
  function refresh(){
    if(!root.open){shown=null;return;}
    const s=host.snapshot(),p=s.project,key=JSON.stringify([p?.id,p?.revision,s.view,s.selected]);
    if(key!==owner || cached?.project!==p){
      const changed=owner!==key;
      if(changed){range=null;candidate='';input.value='0';notice='';}
      owner=key;cached={project:p,c:takeContext(p,s.selected)};
      const opts=[],choice=(value,title)=>{const o=document.createElement('option');o.value=value;o.textContent=title;return o;};
      opts.push(choice('','Choose a replacement…'));
      const choices=cached.c.choices||[],names=new Set(),dups=new Set();
      for(const a of choices){if(names.has(a.name))dups.add(a.name);names.add(a.name);}
      for(const a of choices)opts.push(choice(a.id,(a.name||'Untitled')+(dups.has(a.name)?' · '+a.id.slice(6):'')+(a.kind==='image'?'':' · '+sec(a.duration||0))));
      file.replaceChildren(...opts);file.value=candidate;if(file.value!==candidate){candidate='';range=null;}
    }
    const c=cached.c,asset=p?.assets?.[candidate],clock=asset?.kind==='audio'||asset?.kind==='video';
    const block=s.issue||c.issue||'',locked=pending||!!block;
    say(where,c.clip?(c.old.name||'Untitled')+' · edit '+sec(c.clip.start)+' to '+sec(c.clip.end)+(c.track?' · '+c.track.name:''):'Choose a clip on the edited timeline.');
    file.disabled=locked;timed.hidden=!clock;input.disabled=locked||!clock;use.hidden=!clock;
    const markId=clock?key+asset.id:'';
    if(markId!==markKey){markKey=markId;markValue=clock?host.marks(p,asset):null;}
    const marks=markValue?.state==='saved'?markValue.range:null;
    use.disabled=locked||!marks;use.title=marks?'Use saved Source In '+sec(marks.source_start)+' and Out '+sec(marks.source_end)+'.':'No saved In / Out for this file in this browser.';
    const detail={clip_id:c.clip?.id,previous_asset_id:c.old?.id,asset_id:candidate};
    if(clock){detail.source_start=input.value.trim()===''?NaN:Number(input.value);if(range)detail.source_end=range.source_end;}
    const plan=planTake(p,c,detail),issue=block||plan.issue||'';
    apply.disabled=pending||!!issue;apply.title=issue||'Change this occurrence only; one Undo restores its previous take.';
    say(status,pending?'Replacing this take…':[notice,block||plan.issue||plan.description,range?'Saved Out limit: '+sec(range.source_end)+'. Editing Source In clears that limit.':''].filter(Boolean).join(' '));
    shown={id:p?.id,view:s.view,revision:p?.revision,selected:s.selected,key,detail,ready:!issue&&!pending};
  }
  file.addEventListener('change',()=>{candidate=file.value;input.value='0';range=null;notice='';refresh();});
  input.addEventListener('input',()=>{range=null;notice='';refresh();});
  use.addEventListener('click',()=>{if(use.disabled||pending)return;const s=host.snapshot(),a=s.project?.assets?.[candidate],r=a&&host.marks(s.project,a);if(r?.state!=='saved'){markKey='';refresh();return;}
    input.value=String(r.range.source_start);range={source_end:r.range.source_end};notice='';refresh();});
  apply.addEventListener('click',async()=>{
    if(!root.open||apply.disabled||pending)return;
    const prev=shown;refresh();
    if(!prev?.ready || !shown?.ready || prev.key!==shown.key || !equal(prev.detail,shown.detail))return;
    pending=true;notice='';refresh();
    try{const result=await host.commit(prev,prev.detail),now=host.snapshot();
      if(now.project?.id===prev.id&&now.view===prev.view&&now.selected===prev.selected){refresh();notice=result?'Take replaced. One Undo restores the previous take.':'Replacement was not confirmed. Review the current take before trying again.';}}
    catch(e){const now=host.snapshot();if(now.project?.id===prev.id&&now.view===prev.view&&now.selected===prev.selected)notice=e?.message||'Replacement not confirmed.';}
    finally{pending=false;refresh();}
  });
  root.addEventListener('toggle',()=>{markKey='';refresh();});
  return {refresh};
}
