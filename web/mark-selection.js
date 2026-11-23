// Marking is navigation. Read exact saved occurrence times, never source offsets,
// target-track primary blocks, or their rounded timecode display.
const bad=issue=>({issue}),entryId=/^(media|text)_[0-9a-f]{32}$/,finite=Number.isFinite;
export function planMarkedLayers(project,ids){
 const seq=project?.editor_sequence,duration=seq?.duration;
 if(!project?.id||!project.draft||!Number.isInteger(project.revision)||project.revision<1||!seq||seq.error||!finite(duration)||duration<=0)return bad('Open a saved edit with a valid edit clock.');
 if(!Array.isArray(ids)||!ids.length||ids.length>200||ids.some(i=>typeof i!=='string'||!entryId.test(i))||new Set(ids).size!==ids.length)return bad('Select one or more saved media or text occurrences on the timeline.');
 const media=project.manual?.media_clips,text=project.manual?.text_clips;if(!Array.isArray(media)||!Array.isArray(text))return bad('The saved layer collection is unavailable.');
 const wanted=new Set(ids),rows=[],found=new Set();
 for(const [list,kind] of [[media,'media'],[text,'text']])for(const row of list){
   if(!row||!wanted.has(row.id))continue;
   if(!row.id.startsWith(kind+'_')||found.has(row.id)||!finite(row.start)||!finite(row.end)||row.start<0||row.end<=row.start||row.end>duration)return bad('A selected occurrence has invalid or ambiguous saved boundaries.');
   const name=kind==='media'?(project.assets?.[row.asset_id]?.name||'Imported clip'):(row.text||row.kind||'Text');
   rows.push({id:row.id,start:row.start,end:row.end,name:String(name).replace(/\s+/g,' ').trim().slice(0,70),disabled:row.enabled===false,track:row.track_id||''});found.add(row.id);
 }
 if(found.size!==wanted.size)return bad('A selected occurrence is no longer in this saved edit.');
 rows.sort((a,b)=>a.start-b.start||a.end-b.end||a.id.localeCompare(b.id));
 const start=rows[0].start;let end=rows[0].end,gapCount=0,gapDuration=0;
 for(const r of rows.slice(1)){if(r.start>end+1e-9){gapCount++;gapDuration+=r.start-end;}end=Math.max(end,r.end);}
 if(end-start<1/60-1e-9)return bad('The selected span is shorter than a supported timeline range.');
 return {issue:'',range:{start,end},ids:rows.map(r=>r.id),count:rows.length,hasGaps:gapCount>0,gapCount,gapDuration,
   duration:end-start,names:rows.map(r=>r.name),disabledCount:rows.filter(r=>r.disabled).length,
   token:JSON.stringify([project.id,project.revision,duration,rows.map(r=>[r.id,r.start,r.end])])};
}
const seconds=t=>Number(t.toFixed(9)).toString()+' s';
export function describeMarkedLayers(p,saved=false){
 if(p.issue)return p.issue;
 return (saved?'Marked ':'Mark ')+(p.count===1?p.names[0]||'selected layer':p.count+' selected layers')+': '+seconds(p.range.start)+' to '+seconds(p.range.end)+'. One range across all tracks'+(p.hasGaps?', including '+p.gapCount+(p.gapCount===1?' gap':' gaps')+' ('+seconds(p.gapDuration)+') between the selected layers.':'.')+(p.disabledCount?' Disabled occurrences stay disabled.':'');
}
export function initMarkedLayers(bar,{snapshot,mark,notify,focus}){
 if(!bar||typeof snapshot!=='function'||typeof mark!=='function')return null;
 const d=bar.ownerDocument,b=d.createElement('button');b.id='markSelectedRange';b.type='button';b.hidden=true;
 const description=d.createElement('span');description.id='markSelectedRangeDescription';description.className='sr-only';b.setAttribute('aria-describedby',description.id);
 bar.insertBefore(b,bar.querySelector('#timelineLoopRange')||bar.querySelector('.timeline-timecode-form'));bar.append(description);
 let dead=false,last='';
 function sync(){
  if(dead)return null;const s=snapshot(),shown=Array.isArray(s.ids)&&s.ids.length>0;b.hidden=!shown;
  if(!shown){last='';return null;}const p=s.issue?bad(s.issue):planMarkedLayers(s.project,s.ids);b.disabled=!!p.issue;
  const label=s.ids.length===1?'Mark clip range':'Mark '+s.ids.length+' clips';if(b.textContent!==label)b.textContent=label;
  const tip=(p.issue||describeMarkedLayers(p))+(p.issue?'':' Keeps the playhead and project unchanged.');if(b.title!==tip)b.title=tip;if(description.textContent!==tip)description.textContent=tip;
  if(s.profile==='cutroom')b.setAttribute('aria-keyshortcuts','Shift+X');else b.removeAttribute('aria-keyshortcuts');
  last=p.issue?'':JSON.stringify([s.view,p.token]);return {s,p,token:last};
 }
 function apply(keyboard=false){
  const seen=last,v=sync();if(!v||v.p.issue||!v.token)return false;if(!keyboard&&seen!==v.token)return false;
  if(!mark(v.s,v.p))return false;
  notify?.(describeMarkedLayers(v.p,true));focus?.();sync();return true;
 }
 const click=()=>apply(false),close=e=>{if(e.target?.tagName==='DIALOG')sync();};
 b.addEventListener('click',click);d.addEventListener('close',close,true);sync();
 return {sync,apply,destroy(){dead=true;b.removeEventListener('click',click);d.removeEventListener('close',close,true);b.remove();description.remove();}};
}
