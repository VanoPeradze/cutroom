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



function layers(){const h=app();h.run(`state.project.assets={v:{id:'v',kind:'video',status:'ready',duration:10},a:{id:'a',kind:'audio',status:'ready',duration:10},i:{id:'i',kind:'image',status:'ready'}};
 state.project.manual.media_clips=[{id:'media_a',asset_id:'v',start:1,end:3,source_start:1,video_source_start:2,speed:.5,motion:'pan',fade_in:.2,fade_out:.2},{id:'media_sound',asset_id:'a',start:0,end:5},{id:'media_b',asset_id:'i',start:2,end:4},{id:'media_c',asset_id:'v',start:4,end:5}];
 state.project.manual.text_clips=[{id:'text_t',start:1,end:3,text:'Upper title'}];
 state.timeline.mediaSelection='media_a';state.timeline.playhead=2.25;
 globalThis.selected=[];globalThis.mediaFlush=0;globalThis.textFlush=0;
 state.timeline.selectIndexEntry=()=>{throw Error('Do not bypass guarded navigation');};
 selectTimelineMedia=async id=>{if(state.manualEditBusy)throw Error('Selection before save finished');selected.push(id);state.timeline.mediaSelection=id;return true;};
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){}};state.textStudio={flush:async()=>{textFlush++;return true;},render(){}};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});const old=state.project.manual.media_clips,slots=old.map((r,i)=>state.project.assets[r.asset_id].kind==='audio'?-1:i).filter(i=>i>=0),visuals=slots.map(i=>old[i]),index=visuals.findIndex(r=>r.id===body.clip_id),plan=layerStackPlan(body.clip_id,body.position);
 visuals.splice(plan.destination-1,0,visuals.splice(index,1)[0]);const rows=[...old];slots.forEach((slot,i)=>rows[slot]=visuals[i]);return {project:{...state.project,revision:state.project.revision+1,manual:{...state.project.manual,media_clips:rows}}};};`);return h;}
for(const [id,position,order] of [['media_a','front',['media_b','media_sound','media_c','media_a']],['media_b','back',['media_b','media_sound','media_a','media_c']],['media_b','forward',['media_a','media_sound','media_c','media_b']],['media_b','backward',['media_b','media_sound','media_a','media_c']]])test(`native ${position} ${id} preserves every field and audio slot with selected identity/cursor`,async()=>{
 const {run}=layers();run(`state.timeline.mediaSelection='${id}';state.timeline.editPending=true;state.trackProtection={lockedNames:()=>['A','B']};globalThis.before=JSON.stringify(state.project);`);
 assert.ok(await run(`stackTimelineLayer('${id}','${position}')`));assert.deepEqual(plain(run('requests[0].body')),{action:'media_reorder',clip_id:id,position,expected_revision:7});
 const before=JSON.parse(run('before')),after=plain(run('state.project'));assert.deepEqual(after.manual.media_clips,order.map(id=>before.manual.media_clips.find(r=>r.id===id)));assert.deepEqual(after.manual.text_clips,before.manual.text_clips);assert.deepEqual(after.sources,before.sources);assert.deepEqual(after.assets,before.assets);assert.deepEqual(after.editor_sequence,before.editor_sequence);
 assert.equal(run('state.timeline.mediaSelection'),id);assert.deepEqual(plain(run('selected')),[id]);assert.equal(run('state.manualEditBusy'),false);assert.equal(run('state.timeline.editPending'),true);assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('seeks.at(-1)'),2.25);
});
test('global visual rank counts non-overlapping visuals but excludes audio',()=>{
 const {run}=layers();assert.deepEqual(plain(run('layerStackPlan("media_a","front")')),{issue:'',patch:{position:'front'},rank:1,count:3,destination:3});assert.equal(run('layerStackPlan("media_b","forward").destination'),3);
});
for(const position of ['back','backward'])test(`boundary ${position} is no-op without flush/history`,async()=>{
 const {run}=layers();assert.deepEqual(plain(run(`layerStackPlan('media_a','${position}').patch`)),{});assert.ok(await run(`stackTimelineLayer('media_a','${position}')`));assert.equal(run('requests.length'),0);assert.equal(run('textFlush'),0);assert.equal(run('mediaFlush'),0);
});
for(const position of ['front','forward'])test(`front boundary ${position} is no-op`,async()=>{const {run}=layers();assert.ok(await run(`stackTimelineLayer('media_c','${position}')`));assert.equal(run('requests.length'),0);});
for(const id of ['media_sound','text_t','A:sequence:0:0','automatic_caption','missing'])test(`unsupported ${id} never falls through to source or text actions`,async()=>{
 const {run}=layers();assert.equal(await run(`stackTimelineLayer('${id}','front')`),null);assert.equal(run('requests.length'),0);
});
for(const [setup,position,reason] of [
 ['','null',/Choose/],['','true',/Choose/],['',"'up'",/Choose/],['','undefined',/Choose/],
 ['state.captionDirty=true',"'front'",/Save or discard/],['state.captionContextSave={}',"'front'",/Save or discard/],
 ['delete state.project.assets.i',"'front'",/missing or not ready/],['state.project.assets.i.status="failed"',"'front'",/missing or not ready/],['state.project.assets.i.kind="unknown"',"'front'",/missing or not ready/],
 ['state.project.manual.media_clips[3].id="media_a"',"'front'",/unique/],['state.project.draft=null',"'front'",/no longer/]
])test(`stack fails closed ${setup||position}`,async()=>{const {run}=layers();run(setup);const before=run('JSON.stringify(state.project)'),plan=run(`layerStackPlan('media_a',${position})`);assert.match(plan.issue,reason);assert.equal(plan.patch,null);assert.equal(await run(`stackTimelineLayer('media_a',${position})`),null);assert.equal(run('requests.length'),0);assert.equal(run('JSON.stringify(state.project)'),before);});
test('single visual stack and full occurrence capacity remain truthful without creating an item',()=>{
 const {run}=layers();run('state.project.manual.media_clips=state.project.manual.media_clips.slice(0,2);');assert.equal(run('layerStackPlan("media_a","front").count'),1);assert.deepEqual(plain(run('layerStackPlan("media_a","front").patch')),{});
 run('state.project.manual.media_clips=Array.from({length:200},(_,i)=>({...state.project.manual.media_clips[0],id:i?"media_"+i:"media_a"}));');assert.equal(run('layerStackPlan("media_a","front").destination'),200);
});
test('all affected visual identities/order are pinned across flush, not only selected clip',async()=>{
 for(const mutate of ['state.project.manual.media_clips.reverse();','state.project.manual.media_clips[2].start=1;','state.project.manual.media_clips.pop();','state.project.assets.i.name="Other image";','state.project.assets.i.status="failed";']){const {run}=layers();run(`flushProjectSaves=async()=>{${mutate}};`);assert.equal(await run('stackTimelineLayer("media_a","front")'),null);assert.equal(run('requests.length'),0);assert.equal(run('selected.length'),0);}
});
test('project navigation and failed pending save cancel old relative order before mutation',async()=>{
 for(const setup of ['state.textStudio.flush=async()=>false;','state.mediaStudio.flush=async()=>false;','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}']){const {run}=layers();run(setup);assert.equal(await run('stackTimelineLayer("media_a","front")'),null);assert.equal(run('requests.length'),0);}
});
test('revision conflict fetches latest once and never retries a relative stack command',async()=>{
 const {run}=layers();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12}};};`);assert.equal(await run('stackTimelineLayer("media_a","forward")'),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('selected.length'),0);assert.match(run('messages.at(-1)'),/review the visual order/);
});
test('rapid stack commands waiting on common flush submit only one reorder',async()=>{
 const {run}=layers();run('globalThis.release=null;const wait=new Promise(r=>release=r);state.textStudio.flush=()=>wait;globalThis.first=stackTimelineLayer("media_a","front");globalThis.second=stackTimelineLayer("media_a","forward");release(true);');await run('Promise.all([first,second])');assert.equal(run('requests.length'),1);assert.equal(run('requests[0].body.position'),'front');
});
function studioClass(){const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'')+';globalThis.Class=MediaStudio;',context);return context.Class;}
function studio(){const Class=studioClass(),value=Object.create(Class.prototype),buttons=Object.fromEntries(['backward','forward','back','front'].map(k=>[k,{}])),status={};let busy=false,rank=2;Object.assign(value,{selected:'media_a',pending:new Map(),project:()=>({id:'p'}),status:{},root:{scrollTop:143,querySelector:s=>s==='[data-stack-status]'?status:buttons[s.match(/data-stack="(.*?)"/)?.[1]]},options:{busy:()=>busy,stackPreview:(id,position)=>({issue:'',patch:rank===1&&['back','backward'].includes(position)?{}:{position},rank,count:3,destination:position==='front'?3:1})},render(){throw Error('Do not repaint');}});return {value,buttons,status,setBusy:v=>busy=v,setRank:v=>rank=v};}
test('inspector stack readiness/rank update without repainting disclosure or resetting scroll',()=>{
 const {value,buttons,status,setBusy,setRank}=studio();value.updateStackAvailability();assert.equal(buttons.front.disabled,false);assert.match(status.textContent,/2 of 3/);assert.match(buttons.front.title,/3 of 3/);setRank(1);value.updateStackAvailability();assert.equal(buttons.back.disabled,true);assert.match(buttons.back.title,/Already/);setBusy(true);value.updateStackAvailability();assert.equal(buttons.front.disabled,true);setBusy(false);value.pending.set('a',{});value.updateStackAvailability();assert.equal(buttons.front.disabled,true);value.pending.clear();value.updateStackAvailability();assert.equal(buttons.front.disabled,false);assert.equal(value.root.scrollTop,143);
});
test('inspector native stacking pins selected ID/direction and delegates exactly once',async()=>{
 const {value}=studio(),calls=[];let release;value.flush=()=>{throw Error('Central transaction owns flush');};value.options.stack=(...args)=>{calls.push(args);return new Promise(r=>release=r);};const promise=value.stackPlacement('forward');value.selected='other';release('saved');assert.equal(await promise,'saved');assert.deepEqual(calls,[['media_a','forward']]);
});
test('late stack failure never replaces another project status',async()=>{const {value}=studio();let pid='p',reject;value.project=()=>({id:pid});value.status.textContent='Current';value.options.stack=()=>new Promise((_,r)=>reject=r);const promise=value.stackPlacement('front');pid='other';reject(Error('Old failure'));assert.equal(await promise,null);assert.equal(value.status.textContent,'Current');});
test('absent native stacking callback leaves legacy hosts untouched and unavailable plan fails closed',()=>{
 const Class=studioClass(),value=Object.create(Class.prototype);value.options={};assert.doesNotThrow(()=>value.updateStackAvailability());const h=studio();h.value.options.stackPreview=()=>null;h.value.updateStackAvailability();assert.equal(h.buttons.front.disabled,true);
});
