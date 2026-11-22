const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/request-review.js'),'utf8').replace(/^export /gm,'');
class Node {
  constructor(tag){this.tag=tag;this.dataset={};this.children=[];this.events={};this.classList={add(){}};}
  append(...nodes){for(const n of nodes)n.parentElement=this;this.children.push(...nodes);}
  setAttribute(k,v){this[k]=v;}
  addEventListener(k,fn){(this.events[k]||=[]).push(fn);}
  async fire(k){for(const fn of this.events[k]||[])await fn({preventDefault(){}});}
  reportValidity(){return all(this).filter(e=>e.type==='number'&&!e.disabled).every(e=>{
    const v=Number(e.value),min=e.min==null?-Infinity:Number(e.min),max=e.max==null?Infinity:Number(e.max);
    if(!String(e.value??'').trim()||!Number.isFinite(v)||v<min||v>max)return false;
    const steps=(v-(Number.isFinite(min)?min:0))/Number(e.step||1);
    return e.step==='any'||Math.abs(steps-Math.round(steps))<1e-7;
  });}showModal(){this.open=true;}close(){this.open=false;this.fire('close');}remove(){this.removed=true;}
}
const all=e=>[e,...e.children.flatMap(all)],flush=()=>new Promise(setImmediate);
function harness(text='Make one video.',extra={}){
  const body=new Node('body'),c=vm.createContext({document:{body,createElement:t=>new Node(t)}});vm.runInContext(source,c);
  let current=true,blocked=false;const calls=[];
  const base={instruction:text,output_count:1,source_continuity:'unspecified',target_duration:60,duration_mode:'target',aspect:'9:16',edit_style:'smart',goal:'short',...(extra.settings||{})};
  c.options={...extra,settings:base,projectId:'p',revision:4,isCurrent:()=>current,check:async value=>{calls.push(JSON.parse(JSON.stringify(value)));return{project_id:'p',revision:4,ready:!blocked,contract:{selection_controls:{source_continuity:value.source_continuity},issues:blocked?[{reason:'Conflicting instructions.'}]:[]},duration_bounds:{minimum_seconds:45,maximum_seconds:60,origin:'explicit_user_range'}};}};
  const pending=vm.runInContext('reviewEditingRequest(options)',c),dialog=body.children[0];
  return{base,body,c,dialog,pending,calls,field:key=>all(dialog).find(e=>e.dataset.requestField===key),button:key=>all(dialog).find(e=>e.dataset[key]),form:all(dialog).find(e=>e.tag==='form'),setCurrent:v=>current=v,setBlocked:v=>blocked=v};
}
test('Hebrew original remains verbatim; confirmed controls are the exact generated settings',async()=>{
  const h=harness('בחר קטע אחד. כוון ל45-60 שניות.');await flush();
  h.field('source_continuity').value='required';h.field('aspect').value='16:9';await h.field('source_continuity').fire('change');
  assert.equal(h.button('requestGenerate').disabled,true);await h.button('requestCheck').fire('click');
  assert.equal(h.button('requestGenerate').disabled,false);await h.form.fire('submit');const result=await h.pending;
  assert.equal(result.instruction,h.base.instruction);assert.equal(result.source_continuity,'required');assert.equal(result.aspect,'16:9');assert.equal(result.output_count,1);assert.equal(h.dialog.removed,true);
});
test('one output alone keeps source arrangement independent of style',async()=>{
  const h=harness();await flush();await h.form.fire('submit');const result=await h.pending;assert.equal(result.source_continuity,'unspecified');assert.equal(result.edit_style,'smart');
});
test('blocked request cannot be submitted; keeping current returns no settings',async()=>{
  const h=harness();await flush();h.setBlocked(true);await h.button('requestCheck').fire('click');assert.equal(h.button('requestGenerate').disabled,true);
  await h.form.fire('submit');await h.button('requestKeep').fire('click');assert.equal(await h.pending,null);
});
test('stale project cannot generate from a formerly valid summary',async()=>{
  const h=harness();await flush();h.setCurrent(false);await h.form.fire('submit');assert.equal(h.button('requestGenerate').disabled,true);await h.button('requestKeep').fire('click');assert.equal(await h.pending,null);
});
test('editing checked fields invalidates confirm; Escape cancels without mutation',async()=>{
  const h=harness();await flush();h.field('instruction').value='New exact instruction.';await h.field('instruction').fire('input');assert.equal(h.button('requestGenerate').disabled,true);await h.dialog.fire('cancel');assert.equal(await h.pending,null);assert.equal(h.base.instruction,'Make one video.');
});
test('actual application posts reviewed settings and request review precedes model readiness',()=>{
  const app=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');const code=app.slice(app.indexOf('async function generateDraft()'),app.indexOf('async function ensureStoryAIReady'));
  assert.ok(code.indexOf('reviewEditingRequest(')<code.indexOf('await ensureStoryAIReady'));
  assert.match(code,/const settings = reviewed/);assert.match(code,/director\/request-review/);assert.match(code,/JSON\.stringify\(settings\)/);
});

test('actual generateDraft sends the reviewed snapshot, never original UI defaults',async()=>{
  const app=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
  const code=app.slice(app.indexOf('async function generateDraft()'),app.indexOf('async function ensureStoryAIReady'));
  const reviewed={instruction:'צור סרטון אחד בלי חיתוכים.',source_continuity:'required',output_count:1,aspect:'16:9',target_duration:45,goal:'short'};
  const calls=[],state={project:{id:'p',revision:4,sources:{A:{}}},projectViewToken:1,saveQueues:new Map()};
  const c=vm.createContext({state,encodeURIComponent,JSON,DIRECTOR_INSTRUCTION_LIMIT:8000,
    elements:{directorInstruction:{value:'Old defaults.'}},requireSavedTranscript:()=>true,
    requireResumedEdit:()=>true,requireResolvedExplicitDrafts:()=>true,requireCompatibleLayerTracks:()=>true,renderReadiness(){},editorAiRequestContext:()=>false,beginEditorDirectorSession:()=>null,flushCurrentProjectSaves:async()=>true,
    foregroundBusy:()=>false,liveEmbeddedCameraRequest:()=>false,flushProjectSaves:async()=>{},
    directorRequestSettings:()=>({instruction:'Old defaults.',goal:'short'}),currentSettings:()=>({instruction:'Old defaults.',goal:'short'}),reviewEditingRequest:async()=>reviewed,
    acquireJobStartLock:()=>({}),releaseJobStartLock:()=>{},pauseAllMedia(){},showAnalysis(){},assertJobStartNotCancelled(){},
    ensureStoryAIReady:async()=>calls.push('ready'),pollJob:async()=>calls.push('polled'),
    api:async(url,opts)=>{calls.push({url,body:JSON.parse(opts.body),headers:JSON.parse(JSON.stringify(opts.headers))});return{job:{id:'j'}};},
    toast:msg=>assert.fail(msg),t:x=>x,reconcileDirectorOutcome:async(_id,e)=>assert.fail(e.message)});
  vm.runInContext(code,c);await vm.runInContext('generateDraft()',c);
  assert.deepEqual(calls,['ready',{url:'/api/projects/p/director',body:reviewed,headers:{'X-Cutroom-Reviewed-Revision':'4'}},'polled']);
  assert.equal(state.project.revision,4);
});

test('protected current edit review keeps output aspect fixed and explains source-only proposal scope',async()=>{
 const h=harness('Keep my topic.',{preserveCurrentEdit:true});await flush();
 assert.equal(h.field('aspect').disabled,true);
 assert.ok(all(h.dialog).some(n=>String(n.textContent).includes('separate source-cut proposal')));
 await h.button('requestKeep').fire('click');assert.equal(await h.pending,null);
});

for(const duration of [8.125,60.001,86400])test(`request review accepts exact backend-valid fractional length ${duration}`,async()=>{
 const h=harness('Review this duration.',{settings:{target_duration:duration}});await flush();
 assert.equal(h.field('target_duration').step,'any');assert.equal(h.form.reportValidity(),true);assert.equal(h.calls.length,1);assert.equal(h.calls[0].target_duration,duration);
 await h.form.fire('submit');const result=await h.pending;assert.equal(result.target_duration,duration);
});
for(const duration of [7.999,86400.25,NaN])test(`request review still rejects invalid length ${duration} before checking`,async()=>{
 const h=harness('Review this duration.',{settings:{target_duration:duration}});await flush();
 assert.equal(h.form.reportValidity(),false);assert.equal(h.calls.length,0);assert.equal(h.button('requestGenerate').disabled,true);
 await h.button('requestKeep').fire('click');assert.equal(await h.pending,null);
});
test('fractional duration support does not make output count fractional',async()=>{
 const h=harness('Review this duration.',{settings:{target_duration:8.125}});await flush();const count=h.calls.length;
 assert.equal(h.field('output_count').step,'1');h.field('output_count').value='1.5';await h.field('output_count').fire('input');await h.button('requestCheck').fire('click');
 assert.equal(h.form.reportValidity(),false);assert.equal(h.calls.length,count);assert.equal(h.button('requestGenerate').disabled,true);
 await h.button('requestKeep').fire('click');assert.equal(await h.pending,null);
});
