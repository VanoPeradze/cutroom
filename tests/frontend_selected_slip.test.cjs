const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const plain = value => JSON.parse(JSON.stringify(value));
const source = fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8')
  .replace(/^import .*;\r?\n/gm,'').replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/,'');

function app() {
  const nodes = new Map();
  const element = (id='') => {
    const nested = new Map();
    return {id,value:'',dataset:{},hidden:false,attrs:{},listeners:{},style:{setProperty(){}},
      classList:{add(){},remove(){},toggle(){}},
      replaceChildren(...children){this.children=children;},
      setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];},
      addEventListener(key,fn){this.listeners[key]=fn;},
      querySelector(key){if(!nested.has(key))nested.set(key,element(key));return nested.get(key);},
      querySelectorAll(){return [];},focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;},
    };
  };
  const document = {getElementById(id){if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id);},
    querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context = vm.createContext({document,console,dictionaries:{en:{}},setTimeout,clearTimeout,
    window:{addEventListener(){}},requestAnimationFrame:fn=>fn(),performance:{now:()=>0}});
  const run = code=>vm.runInContext(code,context);
  for(const file of ['source-tracks.js','timeline.js','keyboard.js']) run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,''));
  run(source);
  run(`cacheElements();
    state.project={id:'p',name:'Sequence test',revision:7,settings:{fps:30},
      sources:{A:{duration:20,has_audio:true,fps:30},B:{duration:30,has_audio:true}},
      manual:{source_mixer:{audio_slot:'B'},crop:{A:{x:.5}}},
      analysis:{audio_source:'B',audio_timeline_offset:0,transcript:{segments:[{id:'s',start:6,end:8,text:'Speech'}]}},
      draft:{keep_ranges:[{start:4,end:7},{start:14,end:17}],cuts:[{start:0,end:4},{start:7,end:14},{start:17,end:20}],output_duration:6},
      editor_sequence:{duration:6,active:false,sequence:{duration:6,camera_plan:[{start:0,end:6,camera:'stacked'}]},
        source_tracks:{A:[{id:'a1',start:0,end:3,source_start:4},{id:'a2',start:3,end:6,source_start:14}],
          B:[{id:'b1',start:0,end:6,source_start:6}]}}};
    state.studio.open=true;
    globalThis.requests=[];globalThis.selections=[];globalThis.seeks=[];globalThis.messages=[];
    globalThis.savedRevision=7;globalThis.renderCount=0;globalThis.flushCount=0;
    state.timeline={playhead:1,tool:'select',cancelPendingCut(){},setEditTarget(){},
      selectRange(start,end){state.manualSelection={start,end};selections.push({start,end});},
      clearSelection(){state.manualSelection=null;},setProject(){},draw(){}};
    globalThis.realRenderManualControls=renderManualControls;
    renderManualControls=renderSourceMixer=renderReadiness=hydrateSettings=hydrateSourceMixerLayout=highlightTranscriptSelection=()=>{};
    renderDraft=()=>renderCount++;
    pausePreview=pauseAllMedia=()=>{state.preview.playing=false;};
    previewTimelineTime=()=>state.timeline.playhead;
    seekSourcePreview=time=>seeks.push(time);
    openStudioTab=()=>true;
    toast=message=>messages.push(message);
    flushProjectSaves=async()=>{flushCount++;};
    saveQueueFor=()=>({revision:savedRevision});
    rememberProjectRevision=project=>savedRevision=project.revision;
    api=async(url,options)=>{requests.push({url,...options,body:options?.body?JSON.parse(options.body):null});
      return {project:{...state.project,revision:state.project.revision+1}};};
  `);
  return {run,nodes,context};
}

function layers() {
 const h=app();h.run(`state.project.assets={v:{id:'v',kind:'video',status:'ready',duration:10}};
 state.project.manual.media_clips=[{id:'media_a',asset_id:'v',start:1.123456,end:5.123456,source_start:1,video_source_start:2,speed:.5,motion:'pan',fade_in:.2,fade_out:.2}];
 state.project.manual.text_clips=[{id:'text_b',start:1,end:5,text:'Saved title',kind:'title'}];
 state.timeline.mediaSelection='media_a';state.timeline.playhead=3;state.timeline.onMediaAction=editLayerAction;
 globalThis.selected=[];globalThis.mediaFlush=0;globalThis.textFlush=0;
 state.timeline.selectIndexEntry=()=>{throw Error('Do not bypass guarded navigation');};
 selectTimelineMedia=async id=>{if(state.manualEditBusy)throw Error('Selection before save finished');selected.push(id);state.timeline.mediaSelection=id;return true;};
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){}};state.textStudio={flush:async()=>{textFlush++;return true;},render(){}};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});const plan=layerSlipPlan(body.clip_id,body.source_start);
 const manual={...state.project.manual,media_clips:state.project.manual.media_clips.map(r=>r.id===body.clip_id?{...r,...plan.patch}:r)};
 return {project:{...state.project,revision:state.project.revision+1,manual}};};`);return h;
}
test('Slip changes selected source content but preserves ID, fixed legacy endpoints, other layers, fades and motion',async()=>{
 const {run}=layers();run('globalThis.before=JSON.stringify(state.project);');const result=await run('slipTimelineLayer("media_a",2)');assert.ok(result);
 assert.deepEqual(plain(run('requests[0].body')),{action:'media_slip',clip_id:'media_a',source_start:2,expected_revision:7});assert.equal(run('requests.length'),1);
 const before=JSON.parse(run('before')),after=plain(run('state.project'));assert.deepEqual(after.manual.media_clips[0],{...before.manual.media_clips[0],source_start:2,video_source_start:2.5});
 assert.deepEqual(after.manual.text_clips,before.manual.text_clips);assert.deepEqual(after.editor_sequence,before.editor_sequence);assert.equal(run('state.timeline.mediaSelection'),'media_a');assert.equal(run('seeks.at(-1)'),3);
 assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('state.manualEditBusy'),false);
});
test('native absolute Source in retains fractional legacy origin rather than rounding it to a frame',async()=>{
 const {run}=layers();run('state.project.manual.media_clips[0].source_start=.512345;');await run('slipTimelineLayer("media_a",.512345+1/30)');assert.equal(run('requests[0].body.source_start'),.545678333);
 assert.equal(run('state.project.manual.media_clips[0].video_source_start'),2.016666667);
});
for(const [setup,source,reason] of [
 ['',-1,/beginning/],['',8,/complete occurrence/],['',NaN,/finite/],
 ['state.project.manual.media_clips[0].video_source_start=.1',0,/earlier picture/],
 ['state.project.manual.media_clips[0].video_source_start=57600',2,/limit/],
 ['state.project.assets.v.kind="image"',2,/still images/],['state.project.assets.v.status="failed"',2,/not ready/],['state.captionDirty=true',2,/Save or discard/]
])test(`Slip rejects ${setup||source} without resizing, clamping or API writes`,async()=>{
 const {run}=layers();run(setup);const before=run('JSON.stringify(state.project)');const plan=run(`layerSlipPlan('media_a',${source})`);assert.match(plan.issue,reason);assert.equal(plan.patch,null);
 assert.equal(await run(`slipTimelineLayer('media_a',${source})`),null);assert.equal(run('requests.length'),0);assert.equal(run('JSON.stringify(state.project)'),before);
});
test('image/text/source or stale target never falls through to source move or trim',async()=>{
 for(const id of ['text_b','A:sequence:0:0','removed']){const {run}=layers();assert.equal(await run(`editLayerAction('media_slip',{clip_id:'${id}',source_start:2})`),null);assert.equal(run('requests.length'),0);}
});
test('Slip no-op consumes no save or history even with fades and pan motion',async()=>{
 const {run}=layers();assert.deepEqual(plain(run('layerSlipPlan("media_a",1)')),{issue:'',patch:{}});assert.ok(await run('slipTimelineLayer("media_a",1)'));assert.equal(run('requests.length'),0);assert.equal(run('textFlush'),0);
});
test('audio Slip shifts only its sound in-point and supports exact source-out boundary',()=>{
 const {run}=layers();run('state.project.assets.v.kind="audio";state.project.manual.media_clips[0].speed=1;');assert.deepEqual(plain(run('layerSlipPlan("media_a",6)')),{issue:'',patch:{source_start:6}});
});
test('pending clip, asset or project changes cancel stale Slip after flush',async()=>{
 for(const setup of ['state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].source_start=2;return true;}','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}','flushProjectSaves=async()=>{state.project.assets.v.status="failed";}']){
  const {run}=layers();run(setup);assert.equal(await run('slipTimelineLayer("media_a",3)'),null);assert.equal(run('requests.length'),0);
 }
});
test('Slip revision conflict fetches latest once but never reapplies an old in-point',async()=>{
 const {run}=layers();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12}};};`);
 assert.equal(await run('slipTimelineLayer("media_a",2)'),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.match(run('messages.at(-1)'),/review the source point/);
});
test('Slip retains same selected occurrence while gesture waits and source A is locked',async()=>{
 const {run}=layers();run('state.timeline.editPending=true;state.trackProtection={lockedNames:()=>["A"],render(){}};');await run('slipTimelineLayer("media_a",2)');assert.equal(run('selected.length'),1);assert.equal(run('selected[0]'),'media_a');assert.equal(run('state.timeline.editPending'),true);
});
function mediaClass(){const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'')+';globalThis.Class=MediaStudio;',context);return context.Class;}
function studio(){const Class=mediaClass(),value=Object.create(Class.prototype),input={value:'1'},buttons={'-1':{},'1':{}};let project={id:'p',manual:{media_clips:[{id:'m',source_start:1}]}};
 Object.assign(value,{selected:'m',pending:new Map(),overrides:new Map(),status:{},project:()=>project,root:{querySelector:q=>q.includes('source_start')?input:q.includes('-1')?buttons['-1']:buttons['1']},options:{busy:()=>false,frame:()=>1/24,slipPreview:(id,source)=>source<1?{issue:'No earlier picture',patch:null}:{issue:'',patch:{source_start:source}},slip:async()=>project}});return {value,input,buttons,setProject:p=>project=p};}
test('Source in change routes native Slip once instead of generic media_update or double-flush',async()=>{
 const {value}=studio();const calls=[];value.queueClip=()=>{throw Error('Source in must not use queued media_update');};value.options.slip=async(...args)=>{calls.push(args);};
 const input={dataset:{media:'source_start'},type:'number',value:'2.5',hasAttribute:()=>false,checkValidity:()=>true};value.change(input);await new Promise(r=>setImmediate(r));assert.deepEqual(calls,[['m',2.5]]);
});
test('blank Source in is not silently interpreted as zero',async()=>{
 const {value}=studio();let source;value.options.slip=async(id,at)=>{source=at;return null;};const input={dataset:{media:'source_start'},type:'number',value:'',hasAttribute:()=>false,checkValidity:()=>true};value.change(input);await new Promise(r=>setImmediate(r));assert.ok(Number.isNaN(source));assert.equal(input.value,'1');
});
test('frame nudge preserves fractional origin and output frame interval without changing timing fields',async()=>{
 const {value}=studio();const calls=[];value.options.slip=async(...args)=>calls.push(args);await value.nudgeSlip(1);await value.nudgeSlip(-1);assert.deepEqual(calls,[['m',1.041666667],['m',.958333333]]);
});
test('Slip readiness disables blocked source direction and saving controls without rebuilding inspector',()=>{
 const {value,input,buttons}=studio();value.render=()=>{throw Error('No repaint');};value.updateSlipAvailability();assert.equal(buttons['-1'].disabled,true);assert.match(buttons['-1'].title,/earlier picture/);assert.equal(buttons['1'].disabled,false);assert.equal(input.disabled,false);
 value.pending.set('m',{});value.updateSlipAvailability();assert.equal(buttons['1'].disabled,true);assert.equal(input.disabled,true);value.pending.clear();value.updateSlipAvailability();assert.equal(buttons['1'].disabled,false);
});
test('Slip result cannot overwrite later typing, a changed selection or another project',async()=>{
 for(const kind of ['typing','selection','project']){const {value,input,setProject}=studio();let release;input.value='2';value.options.slip=()=>new Promise(r=>release=r);const pending=value.slipTo(2,input);
  if(kind==='typing')input.value='3';else if(kind==='selection')value.selected='other';else setProject({id:'other',manual:{media_clips:[{id:'m',source_start:9}]}});release(null);await pending;assert.equal(input.value,kind==='typing'?'3':'2');}
});
test('legacy media hosts without native Slip callback keep old Source in queue contract',()=>{
 const {value}=studio();delete value.options.slip;delete value.options.slipPreview;const calls=[];value.queueClip=(...args)=>calls.push(args);value.change({dataset:{media:'source_start'},type:'number',value:'2',hasAttribute:()=>false,checkValidity:()=>true});assert.deepEqual(plain(calls),[['m',{source_start:2}]]);assert.doesNotThrow(()=>value.updateSlipAvailability());
});


test('Source in accepts the exact fractional source time produced by frame nudges',()=>{assert.match(fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8'),/data-media="source_start"[^>]*step="any"/);});
