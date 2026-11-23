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
 state.project.manual.media_clips=[{id:'media_a',asset_id:'v',start:1,end:5,source_start:1,video_source_start:2,speed:.5,motion:'none',fade_in:.2,fade_out:.2}];
 state.project.manual.text_clips=[{id:'text_b',start:1,end:5,text:'Saved title',kind:'title'}];
 state.timeline.mediaSelection='media_a';state.timeline.playhead=3;state.timeline.onMediaAction=editLayerAction;
 globalThis.selected=[];globalThis.mediaFlush=0;globalThis.textFlush=0;
 state.timeline.selectIndexEntry=()=>{throw Error('User navigation must remain guarded while saving');};
 selectTimelineMedia=async id=>{if(state.manualEditBusy)throw Error('Selection started before save finished');selected.push('media::'+id);state.timeline.mediaSelection=id;return true;};
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){}};state.textStudio={flush:async()=>{textFlush++;return true;},render(){}};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});
 const key=body.action==='text_trim'?'text_clips':'media_clips';const rows=state.project.manual[key];const old=rows.find(r=>r.id===body.clip_id);
 const plan=old?layerTrimPlan(old.id,body.edge,body.time):null;
 const manual=old?{...state.project.manual,[key]:rows.map(r=>r.id===old.id?{...r,...plan.patch}:r)}:state.project.manual;
 return {project:{...state.project,revision:state.project.revision+1,manual}};};`);return h;
}
for(const id of ['media_a','text_b'])for(const edge of ['start','end'])test(`trim ${id} ${edge} changes only the selected occurrence and retains selection`,async()=>{
 const {run}=layers();run(`state.timeline.mediaSelection='${id}';state.manualSelection={start:0,end:2};globalThis.originalTracks=JSON.stringify(state.project.editor_sequence.source_tracks);`);
 const result=await run(`trimTimelineSelection('${edge}')`);assert.ok(result);
 assert.deepEqual(plain(run('requests[0].body')),{action:id.startsWith('text_')?'text_trim':'media_trim',clip_id:id,edge,time:3,expected_revision:7});
 assert.equal(run('requests.length'),1);assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('state.timeline.mediaSelection'),id);assert.equal(run('state.manualSelection'),null);
 assert.equal(run('JSON.stringify(state.project.editor_sequence.source_tracks)===originalTracks'),true);assert.equal(run('state.project.editor_sequence.duration'),6);assert.equal(run('state.manualEditBusy'),false);
 assert.equal(run('seeks.at(-1)'),3);
});
test('canonical head patch retains independent picture/audio clock and opposite legacy endpoint',()=>{
 const {run}=layers();run('state.project.manual.media_clips[0].end=5.123456;');
 assert.deepEqual(plain(run('layerTrimPlan("media_a","start",3.012)')),{issue:'',patch:{start:3,fade_in:0,source_start:3,video_source_start:3}});
 assert.equal(run('state.project.manual.media_clips[0].end'),5.123456);
 assert.deepEqual(plain(run('layerTrimPlan("media_a","end",3.012)')),{issue:'',patch:{end:3,fade_out:0}});
 run('state.project.assets.v.kind="image";');assert.deepEqual(plain(run('layerTrimPlan("media_a","start",3)')),{issue:'',patch:{start:3,fade_in:0}});
});
test('unfaded static extension preserves opposite envelope and independent source clock',()=>{
 const {run}=layers();run('state.project.manual.media_clips[0].fade_in=0;');
 assert.deepEqual(plain(run('layerTrimPlan("media_a","start",0)')),{issue:'',patch:{start:0,source_start:0,video_source_start:1.5}});
 run('state.project.manual.media_clips[0].fade_out=0;');assert.deepEqual(plain(run('layerTrimPlan("media_a","end",6)')),{issue:'',patch:{end:6}});
});
for(const [edge,time,patch,reason] of [
 ['start',1.1,{},/fade/],['end',4.9,{},/fade/],['start',0,{},/envelope/],['end',6,{},/envelope/],
 ['start',3,{motion:'pan'},/pan\/zoom/],['end',3,{motion:'zoom_in'},/pan\/zoom/],
 ['start',0,{fade_in:0,source_start:.5},/earlier source/],['start',0,{fade_in:0,video_source_start:.25},/earlier picture/],
 ['start',4.97,{},/0\.08/],['end',1.03,{},/0\.08/],['start',-1,{},/inside/],['end',7,{},/inside/],
 ['left',3,{},/edge/]])test(`trim blocks ${edge} ${time} ${JSON.stringify(patch)} without API writes`,async()=>{
 const {run}=layers();run(`Object.assign(state.project.manual.media_clips[0],${JSON.stringify(patch)});`);
 const plan=run(`layerTrimPlan('media_a','${edge}',${time})`);assert.match(plan.issue,reason);assert.equal(plan.patch,null);
 assert.equal(await run(`applyManualEdit('media_trim',{clip_id:'media_a',edge:'${edge}',time:${time}})`),null);assert.equal(run('requests.length'),0);
});
test('source end, unavailable media, unsaved caption text and text overlap remain guarded',()=>{
 for(const [setup,id,edge,time,reason] of [
  ['state.project.assets.v.duration=4.5','media_a','end',6,/source footage/],
  ['state.project.assets.v.status="failed"','media_a','start',3,/not ready/],
  ['state.captionDirty=true','media_a','start',3,/Save or discard/],
  ['state.project.manual.text_clips=[{id:"text_b",start:1,end:2},...Array.from({length:16},(_,i)=>({id:"text_"+i,start:3,end:5}))]','text_b','end',4,/16 custom text/]]){
  const {run}=layers();run(setup+';state.project.manual.media_clips[0].fade_out=0;');assert.match(run(`layerTrimPlan('${id}','${edge}',${time}).issue`),reason);
 }
});
test('no-op faded or animated edges never flush or consume a history write',async()=>{
 const {run}=layers();run('state.project.manual.media_clips[0].motion="pan";');
 assert.deepEqual(plain(run('layerTrimPlan("media_a","start",1)')),{issue:'',patch:{}});
 assert.ok(await run('trimTimelineLayer("media_a","start",1)'));assert.equal(run('requests.length'),0);assert.equal(run('textFlush'),0);assert.equal(run('mediaFlush'),0);
});
for(const [code,edge,id] of [['KeyQ','start','media_a'],['KeyW','end','media_a'],['KeyQ','start','text_b'],['KeyW','end','text_b']])test(`native ${code} trims selected ${id}, never underlying Together footage`,async()=>{
 const {run,nodes}=layers();nodes.get('previewStage').tagName='DIV';nodes.get('previewStage').closest=()=>null;
 run(`state.keyboardProfile='cutroom';state.timeline.mediaSelection='${id}';globalThis.prevented=0;handleEditorShortcut({key:'${code.at(-1).toLowerCase()}',code:'${code}',target:elements.previewStage,preventDefault(){prevented++;},stopPropagation(){}});`);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(run('prevented'),1);assert.equal(run('requests.length'),1);assert.equal(run('requests[0].body.action'),id.startsWith('text_')?'text_trim':'media_trim');assert.equal(run('requests[0].body.edge'),edge);
});
test('trim shortcut protects text inputs, buttons, repeat keys and automatic captions',async()=>{
 for(const mode of ['input','button','repeat','caption','stale']){
  const {run,nodes}=layers();nodes.get('previewStage').tagName=mode==='input'?'INPUT':mode==='button'?'BUTTON':'DIV';nodes.get('previewStage').closest=()=>['input','button'].includes(mode)?nodes.get('previewStage'):null;
  if(mode==='caption')run('state.timeline.mediaSelection=null;state.timeline.captionSelection="automatic";');if(mode==='stale')run('state.timeline.mediaSelection="missing";');
  run(`state.keyboardProfile='cutroom';handleEditorShortcut({key:'q',code:'KeyQ',repeat:${mode==='repeat'},target:elements.previewStage,preventDefault(){},stopPropagation(){}});`);
  await new Promise(resolve=>setImmediate(resolve));assert.equal(run('requests.length'),0,mode);
 }
});
test('without layer selection source Q/W retains the existing Together ripple command',async()=>{
 const {run,nodes}=layers();nodes.get('previewStage').tagName='DIV';nodes.get('previewStage').closest=()=>null;
 run(`state.timeline.mediaSelection=null;state.timeline.playhead=2;state.keyboardProfile='cutroom';state.timeline.clipAtPlayhead=()=>({id:'a1',start:0,end:3});handleEditorShortcut({key:'q',code:'KeyQ',target:elements.previewStage,preventDefault(){},stopPropagation(){}});`);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(run('requests[0].body.action'),'sequence_ripple_delete');
});
test('changed geometry or project during pending saves cancels the old trim coordinate',async()=>{
 for(const setup of ['state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].start=2;return true;}','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}']){
  const {run}=layers();run(setup);assert.equal(await run('trimTimelineSelection("start")'),null);assert.equal(run('requests.length'),0);
 }
});
test('revision conflict loads latest exactly once but never repeats the stale trim',async()=>{
 const {run}=layers();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const error=new Error('conflict');error.status=409;error.code='revision_conflict';throw error;}return {project:{...state.project,revision:12}};};`);
 assert.equal(await run('trimTimelineSelection("start")'),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.match(run('messages.at(-1)'),/review the trim point/);
});
test('trim keeps independent selection while the edge gesture awaits, without unlocking public navigation',async()=>{
 const {run}=layers();run('state.timeline.editPending=true;state.trackProtection={lockedNames:()=>["A","B"],render(){}};');await run('trimTimelineSelection("start")');assert.equal(run('state.timeline.mediaSelection'),'media_a');assert.equal(run('state.timeline.editPending'),true);assert.equal(run('state.manualEditBusy'),false);assert.equal(run('selected.length'),1);
});
function studioClass(name,file){
 const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,'')+`;globalThis.Class=${name};`,context);return context.Class;
}
for(const [name,file,prefix] of [['MediaStudio','media-studio.js','media'],['TextStudio','text-studio.js','text']]){
 test(`${name} trim readiness follows seek and busy/pending/no-op without repaint`,()=>{
  const Class=studioClass(name,file),studio=Object.create(Class.prototype),buttons={start:{},end:{}};let time=1,busy=false;const calls=[];
  Object.assign(studio,{selected:prefix+'_a',pending:new Map(),root:{scrollTop:143,querySelector:selector=>buttons[selector.includes('start')?'start':'end']},options:{time:()=>time,busy:()=>false,trimBusy:()=>busy,trimPreview:(id,edge,at)=>{calls.push([id,edge,at]);return at<2?{issue:'Inside fade',patch:null}:at===4?{issue:'',patch:{}}:{issue:'',patch:{[edge]:at}};}},render(){throw Error('Do not repaint inspector');}});
  studio.updateTrimAvailability();assert.equal(buttons.start.disabled,true);assert.match(buttons.start.title,/fade/);
  time=3;studio.updateTrimAvailability();assert.equal(buttons.start.disabled,false);assert.match(buttons.start.title,/Undo/);
  busy=true;studio.updateTrimAvailability();assert.equal(buttons.end.disabled,true);busy=false;studio.pending.set('a',{});studio.updateTrimAvailability();assert.equal(buttons.start.disabled,true);
  studio.pending.clear();studio.updateTrimAvailability(4);assert.equal(buttons.start.disabled,true);assert.match(buttons.start.title,/already/);
  studio.updateTrimAvailability(3);assert.equal(buttons.start.disabled,false);assert.equal(studio.root.scrollTop,143);
 });
 test(`${name} trim dispatch pins selected occurrence and cursor before the shared save flush`,async()=>{
  const Class=studioClass(name,file),studio=Object.create(Class.prototype),calls=[];let release;
  Object.assign(studio,{selected:prefix+'_a',project:()=>({id:'p'}),status:{},options:{busy:()=>false,trimBusy:()=>false,time:()=>3,trim:(...args)=>{calls.push(args);return new Promise(r=>release=r);}}});
  const promise=prefix==='media'?studio.action('trim_start'):studio.trim('start');studio.selected=prefix+'_other';release('saved');assert.equal(await promise,'saved');assert.deepEqual(calls,[[prefix+'_a','start',3]]);
 });
 test(`${name} hosts without trim callbacks keep their old contract`,()=>{
  const Class=studioClass(name,file),studio=Object.create(Class.prototype);Object.assign(studio,{options:{time:()=>{throw Error('Do not read a clock without a native trim host');}}});assert.doesNotThrow(()=>studio.updateTrimAvailability());
 });
}


test('Full source audition does not replace inspector trim/split readiness with original source seconds',()=>{
 const Class=studioClass('MediaStudio','media-studio.js'),studio=Object.create(Class.prototype),calls=[];
 Object.assign(studio,{options:{time:()=>3},project:()=>({id:'p'}),updateSplitAvailability:at=>calls.push(['split',at]),updateTrimAvailability:at=>calls.push(['trim',at]),pause(){calls.push(['paused']);}});
 studio.sync(18,false,{sourceMode:true});assert.deepEqual(calls,[['split',3],['trim',3],['paused']]);
});
test('canonical head preview rejects a negative nanosecond instead of clamping independent picture time',()=>{
 const {run}=layers();run('state.project.manual.media_clips[0].fade_in=0;state.project.manual.media_clips[0].video_source_start=.499999999;');assert.match(run('layerTrimPlan("media_a","start",0).issue'),/earlier picture/);
 run('state.project.manual.media_clips[0].video_source_start=57600;');assert.match(run('layerTrimPlan("media_a","start",3).issue'),/limit/);
});
