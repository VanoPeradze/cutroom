// Public-receipt verification. Raw transcript/provenance preservation is a
// server/private-state invariant; public words and ASS-derived events cannot
// be reconstructed exactly from a previously corrected public transcript.
import { frozenBatchBinding, pythonStrip } from "./transcript-batch.js?v=20261117-transcript-batch1";
const record = v => v !== null && typeof v === "object" && !Array.isArray(v);
const own = (v,k) => Object.hasOwn(v,k);
const copy = v => structuredClone(v);
const freeze = v => {if(v&&typeof v==="object"){for(const child of Object.values(v))freeze(child);Object.freeze(v);}return v;};
const finite = v => typeof v === "number" && Number.isFinite(v);
const canon = v => Array.isArray(v) ? v.map(canon) : record(v) ? Object.fromEntries(Object.keys(v).sort().map(k=>[k,canon(v[k])])) : v;
const equal = (a,b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));
const key = (row,index) => String(own(row,"id") ? row.id : index);
const fail = message => { throw new Error(message); };
function segments(project) {
  const rows = project?.analysis?.transcript?.segments;
  if (!Array.isArray(rows)) fail("Original transcript unavailable");
  return rows;
}
function unique(rows,id) {
  const matches=rows.filter((row,index)=>record(row) && key(row,index)===id);
  if(matches.length!==1)fail("Ambiguous or missing segment identity");
  return matches[0];
}
function stale(project) {
  const value=project.caption_corrections_stale;
  if(value===undefined)return [];
  if(!Array.isArray(value)||value.some(v=>typeof v!=="string")||new Set(value).size!==value.length)fail("Invalid stale correction identity");
  return [...value].sort();
}
function history(project) {
  const value=project.manual?.history;
  if(value===undefined)return {undo_count:0,redo_count:0};
  if(!record(value)||Object.keys(value).sort().join("|")!=="redo_count|undo_count"
    ||[value.undo_count,value.redo_count].some(n=>!Number.isInteger(n)||n<0||n>20))fail("Invalid history counts");
  return value;
}
export function planPublicBatch(before,items) {
  const binding=frozenBatchBinding(before?.id,before?.revision,items);
  if(before.caption_alternative_status?.active_id!=="original")fail("Original captions are not active");
  if(own(before,"manual")&&!record(before.manual))fail("Invalid saved manual state");
  history(before);
  const rows=segments(before),raw=before.manual?.caption_corrections ?? {};
  if(!record(raw)||own(before.manual||{},"caption_corrections")&&before.manual.caption_corrections===null)fail("Invalid corrections");
  const fixes=copy(raw),changed=[];const oldStale=new Set(stale(before));
  for(const item of binding.items){
    const row=unique(rows,item.segment_id),fix=raw[item.segment_id];
    if(typeof row.text!=="string"||row.text!==item.base_text||!finite(row.start)||!finite(row.end)
      ||row.start!==item.start||row.end!==item.end)fail("Reviewed transcript changed");
    if(fix!==undefined && (!record(fix)||Object.keys(fix).sort().join("|")!=="original|text"
      ||typeof fix.original!=="string"||typeof fix.text!=="string"))fail("Invalid selected correction");
    const text=pythonStrip(item.text),current=pythonStrip(row.text);
    if(text===current)continue;
    const original=fix&&!oldStale.has(item.segment_id)?pythonStrip(fix.original):current;
    if(text===original)delete fixes[item.segment_id];
    else fixes[item.segment_id]={original,text};
    changed.push(item.segment_id);
  }
  return freeze({before:copy(before),binding,corrections:fixes,changed,stale:stale(before).filter(id=>!changed.includes(id))});
}
const tokens = text => pythonStrip(text).split(/[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+/u);
function maskTargetRows(beforeRows,afterRows,ids,desired=null,retained=null) {
  if(!Array.isArray(beforeRows)||!Array.isArray(afterRows)||beforeRows.length!==afterRows.length)fail("Transcript rows changed");
  for(let i=0;i<beforeRows.length;i++){
    const a=beforeRows[i],b=afterRows[i];
    if(!record(a)||!ids.has(key(a,i)))continue;
    if(!record(b)||key(a,i)!==key(b,i)||typeof b.text!=="string")fail("Transcript identity changed");
    if(desired && pythonStrip(b.text)!==desired.get(key(a,i)))fail("Submitted text was not saved");
    if(own(a,"normalized")!==own(b,"normalized"))fail("Normalized metadata presence changed");
    if(retained?.has(key(a,i))){
      if(own(b,"normalized")&&b.normalized!==b.text)fail("Incorrect normalized correction text");
      if(own(b,"words")){
        const expected=tokens(b.text);
        if(!Array.isArray(b.words)||b.words.length!==expected.length||b.words.some((w,n)=>!record(w)||w.word!==expected[n]))fail("Incorrect corrected word tokens");
      }
    }
    // Removing a correction reveals original normalized/word values, which
    // may have been filtered or overwritten in the public before snapshot.
    // Their raw preservation is checked by the private API corpus, not guessed.
    for(const name of ["text","normalized","words"]){delete a[name];delete b[name];}
  }
}
function validEditorCaptions(items) {
  const ids=new Set();
  return Array.isArray(items)&&items.length<=200000&&items.every(row=>{
    if(!record(row)||typeof row.id!=="string"||!row.id||ids.has(row.id)
      ||typeof row.text!=="string"||typeof row.source_text!=="string"
      ||!["ltr","rtl"].includes(row.direction)||typeof row.language!=="string"
      ||["hidden","corrected","local_text","timing_changed","estimated_words"].some(k=>typeof row[k]!=="boolean")
      ||["start","end","natural_start","natural_end","source_start","source_end"].some(k=>!finite(row[k]))
      ||row.end<=row.start||!Array.isArray(row.words)||row.words.some(w=>!Array.isArray(w)||w.length!==3||!finite(w[0])||!finite(w[1])||w[1]<w[0]||typeof w[2]!=="string"))return false;
    ids.add(row.id);return true;
  });
}
export function verifyPublicBatch(before,plan,response,{captionPreviewIssue}={}) {
  try{
    if(!equal(before,plan.before))fail("The reviewed baseline changed");
    const after=response?.project;
    if(!record(after)||after.id!==before.id||!Number.isSafeInteger(after.revision))fail("Wrong project receipt");
    if(!plan.changed.length){if(!equal(before,after))fail("No-op changed saved state");return {outcome:"unchanged"};}
    if(after.revision!==before.revision+1)fail("Unexpected batch revision");
    if(!equal(after.manual?.caption_corrections,plan.corrections))fail("Correction map differs");
    const count=history(before),next=history(after);
    if(next.undo_count!==Math.min(20,count.undo_count+1)||next.redo_count!==0)fail("Not one Undo step");
    if(!validEditorCaptions(after.editor_captions))fail("Invalid generated caption items");
    const scene=after.caption_preview;
    if(!record(scene)||scene.version!==1||scene.project_id!==after.id||scene.revision!==after.revision
      ||scene.clock!=="edited"||typeof scene.available!=="boolean"||typeof scene.issue!=="string")fail("Invalid caption preview binding");
    if(scene.available){if(typeof captionPreviewIssue!=="function"||captionPreviewIssue(scene))fail("Invalid generated caption preview");}
    else if(before.caption_preview?.available!==false||scene.issue!==before.caption_preview.issue)fail("Caption preview became unavailable");
    if(before.caption_preview?.available && !equal(Object.fromEntries(["width","height","fps","settings"].map(k=>[k,before.caption_preview[k]])),
      Object.fromEntries(["width","height","fps","settings"].map(k=>[k,scene[k]]))))fail("Caption render settings changed");
    if(!equal(stale(after),plan.stale))fail("Unrelated correction provenance changed");
    const a=copy(before),b=copy(after),ids=new Set(plan.changed),desired=new Map(plan.binding.items.map(row=>[row.segment_id,pythonStrip(row.text)]));
    a.manual ??= {};a.manual.caption_corrections=copy(plan.corrections);
    if(typeof b.updated_at!=="string")fail("Missing saved timestamp");
    delete a.updated_at;delete b.updated_at;delete a.revision;delete b.revision;
    delete a.manual.history;delete b.manual.history;
    if(record(a.draft)){if(!record(b.draft)||typeof b.draft.edited_at!=="string")fail("Invalid draft receipt");delete a.draft.edited_at;delete b.draft.edited_at;}
    for(const name of ["story_hierarchy","editorial_cache"]){delete a.analysis[name];if(own(b.analysis||{},name))fail("Semantic cache not invalidated");}
    const retained=new Set(plan.changed.filter(id=>own(plan.corrections,id)));
    const outputRows=b.analysis?.transcript?.segments;
    if(Object.values(plan.corrections).some(record)){
      if(typeof b.analysis?.transcript?.text!=="string")fail("Invalid aggregate transcript");
      if(Array.isArray(outputRows)&&outputRows.every(row=>!record(row)||row.text==null||typeof row.text==="string")){
        const aggregate=outputRows.filter(record).map(row=>pythonStrip(row.text||"")).join(" ").replace(/^ +| +$/g,"");
        if(b.analysis.transcript.text!==aggregate)fail("Incorrect aggregate corrected transcript");
      }
    }
    maskTargetRows(a.analysis.transcript.segments,outputRows,ids,desired,retained);
    delete a.analysis.transcript.text;delete b.analysis.transcript.text;
    if(own(a.analysis,"segments"))maskTargetRows(a.analysis.segments,b.analysis.segments,ids);
    for(const name of ["caption_corrections_stale","editor_captions","caption_preview"]){delete a[name];delete b[name];}
    if(record(a.timeline_bindings)&&!a.timeline_bindings.error){
      if(!record(b.timeline_bindings)||b.timeline_bindings.revision!==after.revision)fail("Invalid timeline binding revision");
      delete a.timeline_bindings.revision;delete b.timeline_bindings.revision;
    }
    if(!equal(a,b))fail("Unrelated public saved state changed");
    return {outcome:"changed"};
  }catch(error){return {outcome:"invalid",issue:error.message};}
}
export function classifySavedBatch(before,plan,response,options={}) {
  const latest=response?.project;
  let reviewable=false;
  try {
    const scene=latest?.caption_preview;
    reviewable=Boolean(record(latest)&&latest.id===before.id&&Number.isSafeInteger(latest.revision)
      &&latest.revision>before.revision&&latest.revision>=Math.max(before.revision,options.minimumRevision||before.revision)
      &&record(latest.sources)&&record(latest.settings)&&record(latest.manual)&&record(latest.analysis)
      &&(!own(latest.analysis,"transcript") || record(latest.analysis.transcript)
        &&(!own(latest.analysis.transcript,"segments") || Array.isArray(latest.analysis.transcript.segments)
          && latest.analysis.transcript.segments.every(row => record(row) && typeof row.text === "string"
            && finite(row.start) && finite(row.end) && row.end > row.start
            && (!own(row,"id") || typeof row.id === "string" || Number.isSafeInteger(row.id)))))
      &&record(scene)&&scene.version===1&&scene.project_id===latest.id&&scene.revision===latest.revision
      &&scene.clock==="edited"&&typeof scene.available==="boolean"&&typeof scene.issue==="string"
      &&(!scene.available||typeof options.captionPreviewIssue==="function"&&!options.captionPreviewIssue(scene))
      &&validEditorCaptions(latest.editor_captions)
      &&(!latest.timeline_bindings||latest.timeline_bindings.error||latest.timeline_bindings.revision===latest.revision));
    if(reviewable)history(latest);
  }catch{reviewable=false;}
  try{
    if(!equal(before,plan.before))fail("The reviewed baseline changed");
    if(!record(latest)||latest.id!==before.id||!Number.isSafeInteger(latest.revision)
      ||latest.revision<Math.max(before.revision,options.minimumRevision||before.revision))fail("Stale saved snapshot");
    if(latest.revision===before.revision)return equal(latest,before)?{outcome:"baseline"}:{outcome:"conflict"};
    if(!reviewable)fail("Malformed newer saved project cannot resolve or reload this batch");
    if(verifyPublicBatch(before,plan,response,options).outcome==="changed")return {outcome:"saved-now"};
    history(latest);
    const scene=latest.caption_preview;
    if(!validEditorCaptions(latest.editor_captions)||!record(scene)||scene.version!==1||scene.project_id!==latest.id
      ||scene.revision!==latest.revision||scene.clock!=="edited"||typeof scene.available!=="boolean"||typeof scene.issue!=="string"
      ||(scene.available ? typeof options.captionPreviewIssue!=="function"||options.captionPreviewIssue(scene)
        : before.caption_preview?.available!==false||scene.issue!==before.caption_preview.issue))fail("Invalid saved caption projection");
    if(before.timeline_bindings&&!before.timeline_bindings.error && (!record(latest.timeline_bindings)
      ||latest.timeline_bindings.error||latest.timeline_bindings.revision!==latest.revision))fail("Invalid saved timeline binding");
    if(latest.caption_alternative_status?.active_id!=="original"||!equal(latest.sources,before.sources))fail("Original source identity changed");
    const oldMeta=copy(before.analysis.transcript),newMeta=copy(latest.analysis?.transcript);
    for(const name of ["text","segments"]){delete oldMeta[name];delete newMeta[name];}
    if(!equal(oldMeta,newMeta))fail("Transcript provenance changed");
    const rows=segments(latest);
    for(const item of plan.binding.items){
      const row=unique(rows,item.segment_id);
      if(row.start!==item.start||row.end!==item.end||typeof row.text!=="string"||pythonStrip(row.text)!==pythonStrip(item.text))fail("Not every reviewed text is saved");
    }
    return {outcome:"saved-now"};
  }catch(error){return {outcome:"conflict",issue:error.message,reviewable,revision:reviewable?latest.revision:null};}
}
