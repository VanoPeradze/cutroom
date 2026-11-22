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
 state.project.manual.media_clips=[{id:'media_a',asset_id:'v',start:1.123456,end:3.234567,source_start:1,video_source_start:2,speed:.5,motion:'pan',fade_in:.2,fade_out:.2}];
 state.project.manual.text_clips=[{id:'text_b',start:1.123456,end:3.234567,text:'Saved title',kind:'caption',style:'boxed',scale:125,template:'lower_third',subtext:'Saved second line'}];
 state.timeline.mediaSelection='media_a';state.timeline.playhead=3;state.timeline.onMediaAction=editLayerAction;
 globalThis.selected=[];globalThis.mediaFlush=0;globalThis.textFlush=0;
 state.timeline.selectIndexEntry=()=>{throw Error('Do not bypass guarded navigation');};
 selectTimelineMedia=async id=>{if(state.manualEditBusy)throw Error('Selection before save finished');selected.push(id);state.timeline.mediaSelection=id;return true;};
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){}};state.textStudio={flush:async()=>{textFlush++;return true;},render(){}};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});
 const key=String(body.clip_id).startsWith('text_')?'text_clips':'media_clips',old=state.project.manual[key].find(r=>r.id===body.clip_id);
 let manual=state.project.manual;
 if(body.action.endsWith('_duplicate')&&old){const plan=layerDuplicatePlan(body.clip_id,body.start);manual={...manual,[key]:[...manual[key],{...old,...plan.patch,id:old.id+'_copy'}]};}
 return {project:{...state.project,revision:state.project.revision+1,manual}};};`);return h;
}
function bindMain(h){const start=source.indexOf('  elements.clipDuplicate.addEventListener("click",');const end=source.indexOf('\n  });',start);assert.ok(start>0&&end>start);h.run(source.slice(start,end+6));return h.nodes.get('clipDuplicate').listeners.click;}
for(const id of ['media_a','text_b'])test(`main Duplicate targets ${id}, copies intact and selects the new ID only after save`,async()=>{
 const h=layers(),{run}=h;run(`state.timeline.mediaSelection='${id}';selectedTimelineClip=()=>{throw Error('Do not fall through to source footage');};globalThis.before=JSON.stringify(state.project);state.timeline.editPending=true;`);
 const result=await bindMain(h)();assert.ok(result);assert.deepEqual(plain(run('requests[0].body')),{action:id.startsWith('text_')?'text_duplicate':'media_duplicate',clip_id:id,start:3,expected_revision:7});
 const before=JSON.parse(run('before')),after=plain(run('state.project')),key=id.startsWith('text_')?'text_clips':'media_clips',other=key==='text_clips'?'media_clips':'text_clips';
 assert.deepEqual(after.manual[key][0],before.manual[key][0]);assert.deepEqual(after.manual[key][1],{...before.manual[key][0],id:id+'_copy',start:3,end:5.111111});
 assert.deepEqual(after.manual[other],before.manual[other]);assert.deepEqual(after.editor_sequence,before.editor_sequence);assert.deepEqual(after.sources,before.sources);assert.deepEqual(after.assets,before.assets);
 assert.equal(run('state.timeline.mediaSelection'),id+'_copy');assert.equal(run('selected.length'),1);assert.equal(run('seeks.at(-1)'),3);assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('state.manualEditBusy'),false);assert.equal(run('state.timeline.editPending'),true);
});
test('native destination aligns only its start, preserving original fractional duration',async()=>{const {run}=layers();await run('duplicateTimelineLayer("media_a",2.516)');assert.equal(run('requests[0].body.start'),2.5);assert.equal(run('state.project.manual.media_clips[1].end'),4.611111);});
for(const [setup,start,reason] of [
 ['',-1,/whole copy/],['',5,/whole copy/],['',NaN,/whole copy/],['',true,/whole copy/],['','null',/whole copy/],
 ['state.project.assets.v.status="failed"',2,/not ready/],['state.captionDirty=true',2,/Save or discard/],
 ['state.project.manual.media_clips=[]',2,/no longer/],['state.project.draft=null',2,/no longer/],
 ['state.project.manual.media_clips=Array.from({length:200},(_,i)=>({...state.project.manual.media_clips[0],id:i?"media_"+i:"media_a"}))',2,/200 media/]
])test(`Duplicate rejects ${setup||start} without shortening, extending or writing`,async()=>{
 const {run}=layers();run(setup);const before=run('JSON.stringify(state.project)');const plan=run(`layerDuplicatePlan('media_a',${start})`);assert.match(plan.issue,reason);assert.equal(plan.patch,null);assert.equal(await run(`duplicateTimelineLayer('media_a',${start})`),null);assert.equal(run('requests.length'),0);assert.equal(run('JSON.stringify(state.project)'),before);
});
test('text count and overlap limits match backend with end-before-start adjacency',async()=>{
 const {run}=layers();run('state.project.manual.text_clips=Array.from({length:16},(_,i)=>({id:i?"text_"+i:"text_b",start:0,end:2,text:"Saved"}));');assert.match(run('layerDuplicatePlan("text_b",1).issue'),/16 custom/);assert.equal(await run('duplicateTimelineLayer("text_b",1)'),null);assert.equal(run('requests.length'),0);assert.equal(run('layerDuplicatePlan("text_b",2).issue'),'');
 run('state.project.manual.text_clips=Array.from({length:2000},(_,i)=>({id:i?"text_"+i:"text_b",start:0,end:1,text:"Saved"}));');assert.match(run('layerDuplicatePlan("text_b",2).issue'),/2000 text/);
});
test('stale layer and automatic captions never redirect main Duplicate to A/B',async()=>{
 for(const selection of ['state.timeline.mediaSelection="missing";','state.timeline.mediaSelection=null;state.timeline.captionSelection="automatic_caption";']){const h=layers();h.run(selection+'selectedTimelineClip=()=>{throw Error("Must not touch underlying footage");};');assert.equal(await bindMain(h)(),null);assert.equal(h.run('requests.length'),0);assert.match(h.run('messages.at(-1)'),/no longer|Automatic captions/);}
});
test('existing source-only Duplicate still uses the original source scope action',async()=>{
 for(const target of ['A','edit']){const h=layers();h.run(`state.timeline.mediaSelection=null;activeEditTarget=()=>"${target}";selectedTimelineClip=()=>({id:'a1',start:0,end:2});`);await bindMain(h)();assert.equal(h.run('requests[0].body.action'),target==='A'?'sequence_duplicate':'sequence_duplicate_range');}
});
test('main independent copy readiness ignores unrelated A/B locks but follows fit, busy and caption gates',()=>{
 const {run,nodes}=layers();run('state.trackProtection={lockedNames:()=>["A","B"],render(){}};previewTimelineTime=()=>{throw Error("Do not create playback clock to render readiness");};renderDuplicateAvailability();');assert.equal(nodes.get('clipDuplicate').disabled,false);assert.match(nodes.get('clipDuplicate').title,/new copy is selected/);
 run('renderDuplicateAvailability(5)');assert.equal(nodes.get('clipDuplicate').disabled,true);assert.match(nodes.get('clipDuplicate').title,/whole copy/);
 run('state.manualEditBusy=true;renderDuplicateAvailability(2)');assert.equal(nodes.get('clipDuplicate').disabled,true);run('state.manualEditBusy=false;renderDuplicateAvailability(2)');assert.equal(nodes.get('clipDuplicate').disabled,false);
 run('state.timeline.captionSelection="auto";renderDuplicateAvailability(2)');assert.equal(nodes.get('clipDuplicate').disabled,true);
});
test('playback/Full source publication uses mapped edit time for Duplicate fit readiness',()=>{
 const {run,nodes}=layers();run('elements.studioPanelFraming.hidden=true;publishPreviewPlayhead(17,3)');assert.equal(nodes.get('clipDuplicate').disabled,false);run('publishPreviewPlayhead(17,5)');assert.equal(nodes.get('clipDuplicate').disabled,true);assert.equal(run('requests.length'),0);
});
test('pending occurrence, asset or project changes cancel an old copy request before writing',async()=>{
 for(const setup of ['state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].end=4;return true;}','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}','flushProjectSaves=async()=>{state.project.assets.v.name="Replaced file";}']){const {run}=layers();run(setup);assert.equal(await run('duplicateTimelineLayer("media_a",3)'),null);assert.equal(run('requests.length'),0);}
});
test('capacity and overlap are rechecked after pending unrelated layers finish saving',async()=>{
 const {run}=layers();run('flushProjectSaves=async()=>{state.project.manual.media_clips.push(...Array.from({length:199},(_,i)=>({...state.project.manual.media_clips[0],id:"media_"+i})));};');assert.equal(await run('duplicateTimelineLayer("media_a",3)'),null);assert.equal(run('requests.length'),0);assert.match(run('messages.at(-1)'),/200 media/);
 const h=layers();h.run('flushProjectSaves=async()=>{state.project.manual.text_clips.push(...Array.from({length:16},(_,i)=>({id:"text_"+i,start:3,end:6})));};');assert.equal(await h.run('duplicateTimelineLayer("text_b",3)'),null);assert.equal(h.run('requests.length'),0);assert.match(h.run('messages.at(-1)'),/16 custom/);
});
test('revision conflict loads latest once without retrying or selecting an unrelated new copy',async()=>{
 const {run}=layers();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const error=new Error('conflict');error.status=409;error.code='revision_conflict';throw error;}return {project:{...state.project,revision:12}};};`);assert.equal(await run('duplicateTimelineLayer("media_a",3)'),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('selected.length'),0);assert.match(run('messages.at(-1)'),/review the copy destination/);
});
test('duplicate dispatch during an active manual edit does not create a second copy',async()=>{const {run}=layers();run('state.manualEditBusy=true;');assert.equal(await run('duplicateTimelineLayer("media_a",3)'),null);assert.equal(run('requests.length'),0);});
test('two rapid copy requests waiting on inspector flush commit only once',async()=>{
 const {run}=layers();run('globalThis.releaseFlush=null;globalThis.waitFlush=new Promise(r=>releaseFlush=r);state.textStudio.flush=()=>waitFlush;globalThis.firstCopy=duplicateTimelineLayer("media_a",3);globalThis.secondCopy=duplicateTimelineLayer("media_a",3);releaseFlush(true);');await run('Promise.all([firstCopy,secondCopy])');assert.equal(run('requests.length'),1);assert.equal(run('selected.length'),1);
});
function studioClass(name,file){const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,'')+`;globalThis.Class=${name};`,context);return context.Class;}
for(const [name,file,prefix] of [['MediaStudio','media-studio.js','media'],['TextStudio','text-studio.js','text']]){
 test(`${name} copy readiness follows mapped seek and pending saves without repaint or scroll reset`,()=>{
  const Class=studioClass(name,file),studio=Object.create(Class.prototype),button={};let time=2,busy=false;
  Object.assign(studio,{selected:prefix+'_a',pending:new Map(),root:{scrollTop:143,querySelector:()=>button},options:{time:()=>time,busy:()=>false,trimBusy:()=>busy,duplicatePreview:(id,at)=>at>4?{issue:'Whole copy must fit',patch:null}:{issue:'',patch:{start:at,end:at+2}}},render(){throw Error('No inspector repaint');}});
  studio.updateDuplicateAvailability();assert.equal(button.disabled,false);assert.match(button.title,/2.000/);time=5;studio.updateDuplicateAvailability();assert.equal(button.disabled,true);assert.match(button.title,/Whole copy/);
  time=2;busy=true;studio.updateDuplicateAvailability();assert.equal(button.disabled,true);busy=false;studio.pending.set('a',{});studio.updateDuplicateAvailability();assert.equal(button.disabled,true);assert.match(button.title,/finish saving/);studio.pending.clear();studio.updateDuplicateAvailability(3);assert.equal(button.disabled,false);assert.equal(studio.root.scrollTop,143);
 });
 test(`${name} copy dispatch pins selected ID/time and shares the central flush`,async()=>{
  const Class=studioClass(name,file),studio=Object.create(Class.prototype),calls=[];let release;
  Object.assign(studio,{selected:prefix+'_a',project:()=>({id:'p'}),status:{},flush(){throw Error('Central transaction owns flush');},options:{busy:()=>false,trimBusy:()=>false,time:()=>3,duplicate:(...args)=>{calls.push(args);return new Promise(r=>release=r);}}});
  const pending=prefix==='media'?studio.action('duplicate'):studio.duplicate();studio.selected=prefix+'_other';release('saved');assert.equal(await pending,'saved');assert.deepEqual(calls,[[prefix+'_a',3]]);
 });
 test(`${name} late copy errors cannot overwrite another project status`,async()=>{
  const Class=studioClass(name,file),studio=Object.create(Class.prototype);let id='p',reject;
  Object.assign(studio,{selected:prefix+'_a',project:()=>({id}),status:{textContent:'Other project'},options:{busy:()=>false,time:()=>2,duplicate:()=>new Promise((_,r)=>reject=r)}});
  const pending=prefix==='media'?studio.action('duplicate'):studio.duplicate();id='other';reject(Error('Old project failure'));assert.equal(await pending,null);assert.equal(studio.status.textContent,'Other project');
 });
 test(`${name} host without native copy callbacks does not read a clock or assume readiness`,()=>{
  const Class=studioClass(name,file),studio=Object.create(Class.prototype);Object.assign(studio,{options:{time:()=>{throw Error('No clock without native host');}}});assert.doesNotThrow(()=>studio.updateDuplicateAvailability());
 });
}
test('media Full source sync sends mapped edit time, not original seconds, to copy readiness',()=>{
 const Class=studioClass('MediaStudio','media-studio.js'),studio=Object.create(Class.prototype),calls=[];Object.assign(studio,{options:{time:()=>3},project:()=>({id:'p'}),updateSplitAvailability(){},updateTrimAvailability(){},updateDuplicateAvailability:at=>calls.push(at),pause(){}});studio.sync(18,false,{sourceMode:true});assert.deepEqual(calls,[3]);
});
test('text copy readiness updates even if overlay paint signature is unchanged',()=>{
 const Class=studioClass('TextStudio','text-studio.js'),studio=Object.create(Class.prototype),calls=[];Object.assign(studio,{options:{dimensions:()=>[160,90]},project:()=>({id:'p'}),layer:{},stage:{clientHeight:90},signature:JSON.stringify([[],160,90,90]),updateTrimAvailability(){},updateDuplicateAvailability:at=>calls.push(at)});studio.sync(3,{sourceMode:true});assert.deepEqual(calls,[3]);
});
test('legacy media duplicate callback contract is unchanged without a native playhead host',async()=>{
 const Class=studioClass('MediaStudio','media-studio.js'),studio=Object.create(Class.prototype),calls=[];Object.assign(studio,{selected:'m',status:{},options:{busy:()=>false,pause(){},edit:async(...args)=>calls.push(args)},flush:async()=>true,render(){}});await studio.action('duplicate');assert.deepEqual(plain(calls),[['media_duplicate',{clip_id:'m'}]]);
});
