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



function layers(){const h=app();h.run(`state.project.assets={v:{id:'v',kind:'video',status:'ready',duration:10}};
 state.project.manual.media_clips=[{id:'media_a',asset_id:'v',start:1.123456,end:3.234567,source_start:1,video_source_start:2,speed:.5,motion:'pan',fade_in:.2,fade_out:.2}];
 state.project.manual.text_clips=[{id:'text_b',start:1.123456,end:3.234567,text:'Saved title',kind:'caption',style:'boxed',scale:125,template:'lower_third',subtext:'Second line'}];
 state.timeline.mediaSelection='media_a';state.timeline.playhead=3;state.timeline.onMediaAction=editLayerAction;
 globalThis.selected=[];globalThis.mediaFlush=0;globalThis.textFlush=0;
 state.timeline.selectIndexEntry=()=>{throw Error('Do not bypass guarded navigation');};
 selectTimelineMedia=async id=>{if(state.manualEditBusy)throw Error('Selection before save finished');selected.push(id);state.timeline.mediaSelection=id;return true;};
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){}};state.textStudio={flush:async()=>{textFlush++;return true;},render(){}};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});const key=String(body.clip_id).startsWith('text_')?'text_clips':'media_clips',plan=layerMovePlan(body.clip_id,body.start);
 const manual={...state.project.manual,[key]:state.project.manual[key].map(r=>r.id===body.clip_id?{...r,...plan.patch}:r)};
 return {project:{...state.project,revision:state.project.revision+1,manual}};};`);return h;}
for(const id of ['media_a','text_b'])test(`native Move relocates only ${id}, keeps length/clocks/phase/ID and selects it after save`,async()=>{
 const {run}=layers();run(`state.timeline.mediaSelection='${id}';globalThis.before=JSON.stringify(state.project);state.timeline.editPending=true;state.trackProtection={lockedNames:()=>['A','B'],render(){}};`);
 assert.ok(await run(`editLayerAction('media_move',{clip_id:'${id}',start:3})`));assert.deepEqual(plain(run('requests[0].body')),{action:id.startsWith('text_')?'text_move':'media_move',clip_id:id,start:3,expected_revision:7});
 const before=JSON.parse(run('before')),after=plain(run('state.project')),key=id.startsWith('text_')?'text_clips':'media_clips',other=key==='text_clips'?'media_clips':'text_clips';assert.deepEqual(after.manual[key],[{...before.manual[key][0],start:3,end:5.111111}]);assert.deepEqual(after.manual[other],before.manual[other]);assert.deepEqual(after.sources,before.sources);assert.deepEqual(after.assets,before.assets);assert.deepEqual(after.editor_sequence,before.editor_sequence);
 assert.equal(run('state.timeline.mediaSelection'),id);assert.deepEqual(plain(run('selected')),[id]);assert.equal(run('state.manualEditBusy'),false);assert.equal(run('state.timeline.editPending'),true);assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('seeks.at(-1)'),3);
});
test('canonical Move preserves fractional destination rather than reanchoring to a frame',async()=>{
 const {run}=layers();await run('moveTimelineLayer("media_a",1.123456+1/24)');assert.equal(run('requests[0].body.start'),1.165122667);assert.equal(run('state.project.manual.media_clips[0].end'),3.276233667);assert.equal(run('seeks.at(-1)'),3);
});
for(const [setup,start,reason] of [
 ['',-1,/whole clip/],['',-1e-10,/whole clip/],['',5,/whole clip/],['',NaN,/whole clip/],['','null',/whole clip/],['',true,/whole clip/],['','undefined',/whole clip/],
 ['state.project.assets.v.status="failed"',2,/not ready/],['state.captionDirty=true',2,/Save or discard/],['state.project.manual.media_clips=[]',2,/no longer/],['state.project.draft=null',2,/no longer/]
])test(`Move rejects ${setup||start} before changing duration, content or history`,async()=>{
 const {run}=layers();run(setup);const before=run('JSON.stringify(state.project)'),plan=run(`layerMovePlan('media_a',${start})`);assert.match(plan.issue,reason);assert.equal(plan.patch,null);assert.equal(await run(`moveTimelineLayer('media_a',${start})`),null);assert.equal(run('requests.length'),0);assert.equal(run('JSON.stringify(state.project)'),before);
});
test('whole-occurrence Move supports existing fades/motion and no-op consumes no flush/history',async()=>{
 const {run}=layers();assert.deepEqual(plain(run('layerMovePlan("media_a",1.123456)')),{issue:'',patch:{}});assert.ok(await run('moveTimelineLayer("media_a",1.123456)'));assert.equal(run('requests.length'),0);assert.equal(run('textFlush'),0);assert.equal(run('mediaFlush'),0);
});
test('Move remains available at occurrence capacity and text overlap excludes the moved original',()=>{
 const {run}=layers();run('state.project.manual.media_clips=Array.from({length:200},(_,i)=>({...state.project.manual.media_clips[0],id:i?"media_"+i:"media_a"}));');assert.equal(run('layerMovePlan("media_a",3).issue'),'');
 run('state.project.manual.text_clips=Array.from({length:16},(_,i)=>({id:i?"text_"+i:"text_b",start:1,end:3}));');assert.equal(run('layerMovePlan("text_b",1.5).issue'),'');
 run('state.project.manual.text_clips.push({id:"text_extra",start:4,end:5});');assert.match(run('layerMovePlan("text_extra",1).issue'),/16 custom/);assert.equal(run('layerMovePlan("text_extra",3).issue'),'');
});
test('unsupported A/B or automatic-caption IDs never become source relocation',async()=>{
 for(const id of ['A:sequence:0:0','automatic_caption','removed']){const {run}=layers();assert.equal(await run(`editLayerAction('media_move',{clip_id:'${id}',start:2})`),null);assert.equal(run('requests.length'),0);}
});
test('pending geometry/asset/project changes cancel an old placement before write',async()=>{
 for(const setup of ['state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].end=4;return true;}','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}','flushProjectSaves=async()=>{state.project.assets.v.name="Replaced file";}']){const {run}=layers();run(setup);assert.equal(await run('moveTimelineLayer("media_a",3)'),null);assert.equal(run('requests.length'),0);}
});
test('late unrelated text overlap rechecks after saving instead of moving into an invalid composition',async()=>{
 const {run}=layers();run('flushProjectSaves=async()=>{state.project.manual.text_clips.push(...Array.from({length:16},(_,i)=>({id:"text_"+i,start:3,end:6})));};');assert.equal(await run('moveTimelineLayer("text_b",3)'),null);assert.equal(run('requests.length'),0);assert.match(run('messages.at(-1)'),/16 custom/);
});
test('Move conflict fetches latest once without replay or wrong-project selection',async()=>{
 const {run}=layers();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12}};};`);assert.equal(await run('moveTimelineLayer("media_a",3)'),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('selected.length'),0);assert.match(run('messages.at(-1)'),/review the placement/);
});
test('rapid requests waiting on shared inspector flush produce only one Move',async()=>{
 const {run}=layers();run('globalThis.release=null;const wait=new Promise(r=>release=r);state.textStudio.flush=()=>wait;globalThis.first=moveTimelineLayer("media_a",3);globalThis.second=moveTimelineLayer("media_a",2);release(true);');await run('Promise.all([first,second])');assert.equal(run('requests.length'),1);assert.equal(run('requests[0].body.start'),3);assert.equal(run('selected.length'),1);
});
function studioClass(name,file){const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,'')+`;globalThis.Class=${name};`,context);return context.Class;}
function studio(name,file,prefix){const Class=studioClass(name,file),value=Object.create(Class.prototype),buttons={playhead:{},'-1':{},'1':{}};let time=2.52,busy=false;const clip={id:prefix+'_a',start:1.123456,end:3.234567};
 Object.assign(value,{selected:clip.id,clips:()=>[clip],pending:new Map(),project:()=>({id:'p'}),status:{},root:{scrollTop:143,querySelector:s=>buttons[s.match(/data-move="(.*?)"/)?.[1]]},options:{frame:()=>1/24,time:()=>time,busy:()=>busy,movePreview:(id,start)=>start<0||start>3.8?{issue:'Whole clip must fit',patch:null}:{issue:'',patch:Math.abs(start-clip.start)<1e-9?{}:{start,end:start+2.111111}}},render(){throw Error('Do not repaint');}});return {value,buttons,clip,setTime:v=>time=v,setBusy:v=>busy=v};}
for(const [name,file,prefix] of [['MediaStudio','media-studio.js','media'],['TextStudio','text-studio.js','text']]){
 test(`${name} frame placement retains fractional anchor, while Move to playhead aligns only start`,()=>{
  const {value,clip}=studio(name,file,prefix);assert.equal(value.moveDestination('playhead'),2.5);assert.equal(value.moveDestination('-1'),clip.start-1/24);assert.equal(value.moveDestination('1'),clip.start+1/24);assert.ok(Number.isNaN(value.moveDestination('bad')));
 });
 test(`${name} placement readiness follows seek, no-op and saving without repaint or scroll reset`,()=>{
  const {value,buttons,setTime,setBusy,clip}=studio(name,file,prefix);value.updateMoveAvailability();assert.equal(buttons.playhead.disabled,false);assert.match(buttons.playhead.title,/2.500/);setTime(5);value.updateMoveAvailability();assert.equal(buttons.playhead.disabled,true);assert.match(buttons.playhead.title,/Whole clip/);setTime(2);setBusy(true);value.updateMoveAvailability();assert.equal(buttons['1'].disabled,true);setBusy(false);value.pending.set('a',{});value.updateMoveAvailability();assert.equal(buttons['1'].disabled,true);value.pending.clear();value.updateMoveAvailability();assert.equal(buttons['1'].disabled,false);clip.start=2;value.updateMoveAvailability();assert.equal(buttons.playhead.disabled,true);assert.match(buttons.playhead.title,/already/);assert.equal(value.root.scrollTop,143);
 });
 test(`${name} native placement pins ID/destination before await and delegates one central save`,async()=>{
  const {value}=studio(name,file,prefix),calls=[];let release;value.flush=()=>{throw Error('Central transaction owns flush');};value.options.move=(...args)=>{calls.push(args);return new Promise(r=>release=r);};const pending=value.movePlacement('playhead');value.selected='other';release('saved');assert.equal(await pending,'saved');assert.deepEqual(calls,[[prefix+'_a',2.5]]);
 });
 test(`${name} moving after project navigation cannot overwrite its status with an old failure`,async()=>{
  const {value}=studio(name,file,prefix);let pid='p',reject;value.project=()=>({id:pid});value.status.textContent='Current project';value.options.move=()=>new Promise((_,r)=>reject=r);const pending=value.movePlacement('1');pid='other';reject(Error('Old failure'));assert.equal(await pending,null);assert.equal(value.status.textContent,'Current project');
 });
 test(`${name} hosts without native Move callback retain their existing contract`,()=>{
  const Class=studioClass(name,file),value=Object.create(Class.prototype);value.options={time:()=>{throw Error('Do not create a playback clock');}};assert.doesNotThrow(()=>value.updateMoveAvailability());
 });
}
test('Media Full source readiness uses mapped edit cursor for placement, not original seconds',()=>{
 const Class=studioClass('MediaStudio','media-studio.js'),value=Object.create(Class.prototype),calls=[];Object.assign(value,{options:{time:()=>3},project:()=>({id:'p'}),updateSplitAvailability(){},updateTrimAvailability(){},updateMoveAvailability:at=>calls.push(at),pause(){}});value.sync(18,false,{sourceMode:true});assert.deepEqual(calls,[3]);
});
test('Text placement readiness updates without repainted overlay even when visible clip signature is unchanged',()=>{
 const Class=studioClass('TextStudio','text-studio.js'),value=Object.create(Class.prototype),calls=[];Object.assign(value,{options:{dimensions:()=>[160,90]},project:()=>({id:'p'}),layer:{},stage:{clientHeight:90},signature:JSON.stringify([[],160,90,90]),updateTrimAvailability(){},updateMoveAvailability:at=>calls.push(at)});value.sync(3,true);assert.deepEqual(calls,[3]);
});
