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
 const key=body.action==='text_split'?'text_clips':'media_clips';const rows=state.project.manual[key];const old=rows.find(r=>r.id===body.clip_id);
 const manual=old?{...state.project.manual,[key]:rows.flatMap(r=>r.id===old.id?[{...r,end:body.time},{...r,id:r.id+'_right',start:body.time}]:[r])}:state.project.manual;
 return {project:{...state.project,revision:state.project.revision+1,manual}};};`);return h;
}
for(const id of ['media_a','text_b'])test(`main Split targets selected ${id}, not stale underlying A/B selection; right piece is selected`,async()=>{
 const {run}=layers();run(`state.timeline.mediaSelection='${id}';state.manualSelection={start:0,end:2};globalThis.originalTracks=JSON.stringify(state.project.editor_sequence.source_tracks);`);
 const result=await run('splitTimelineSelection()');assert.ok(result);assert.deepEqual(plain(run('requests[0].body')),{action:id.startsWith('text_')?'text_split':'media_split',clip_id:id,time:3,expected_revision:7});
 assert.equal(run('requests.length'),1);assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('state.timeline.mediaSelection'),id+'_right');assert.equal(run('state.manualSelection'),null);
 assert.equal(run('JSON.stringify(state.project.editor_sequence.source_tracks)===originalTracks'),true);assert.equal(run('state.project.editor_sequence.duration'),6);assert.equal(run('state.manualEditBusy'),false);
});
test('selected layer split ignores source-only locks while toolbar explains its actual scope',async()=>{
 const {run,nodes}=layers();run(`state.trackProtection={lockedNames:()=>['A','B'],render(){}};realRenderManualControls();`);
 assert.equal(nodes.get('manualSplit').disabled,false);assert.match(nodes.get('manualSplit').title,/selected media or custom text/);
 await run('splitTimelineSelection()');assert.equal(run('requests[0].body.action'),'media_split');
});
test('native split point is aligned to output frames before policy and API dispatch',async()=>{
 const {run}=layers();run('state.project.settings.fps=24;state.timeline.playhead=3.02;');await run('splitTimelineSelection()');assert.equal(run('requests[0].body.time'),3);
});
for(const [patch,reason] of [[{motion:'pan'},/pan\/zoom/],[{motion:'zoom_in'},/pan\/zoom/],[{fade_in:2.1},/fade/],[{fade_out:2.1},/fade/],[{start:2.94},/0\.08/],[{end:3.06},/0\.08/]])test(`all native split paths block unsafe ${JSON.stringify(patch)}`,async()=>{
 const {run}=layers();run(`Object.assign(state.project.manual.media_clips[0],${JSON.stringify(patch)});`);
 assert.match(run('layerSplitIssue("media_a",3)'),reason);assert.equal(await run('applyManualEdit("media_split",{clip_id:"media_a",time:3})'),null);assert.equal(run('requests.length'),0);
});
test('automatic-caption and missing-layer selection never fall through to A/B Split',async()=>{
 const {run}=layers();run(`state.timeline.mediaSelection='removed';state.manualSelection={start:0,end:1};`);assert.equal(await run('splitTimelineSelection()'),null);assert.equal(run('requests.length'),0);assert.equal(run('state.manualSelection'),null);
 run(`state.timeline.mediaSelection=null;state.timeline.captionSelection='automatic';`);assert.equal(await run('splitTimelineSelection()'),null);assert.equal(run('requests.length'),0);assert.match(run('messages.at(-1)'),/Automatic captions/);
});
test('plain source Split retains its existing command when no independent layer is selected',async()=>{
 const {run}=layers();run(`state.timeline.mediaSelection=null;state.timeline.playhead=2;state.timeline.canSplitAt=()=>true;`);await run('splitTimelineSelection()');assert.equal(run('requests[0].body.action'),'sequence_split_all');
});
test('Resolve Split shortcut from eligible preview focus uses the selected layer once, not sources',async()=>{
 const {run,nodes}=layers();nodes.get('previewStage').tagName='DIV';nodes.get('previewStage').closest=()=>null;
 run(`state.keyboardProfile='resolve';globalThis.prevented=0;handleEditorShortcut({key:'b',code:'KeyB',ctrlKey:true,metaKey:false,altKey:false,shiftKey:false,target:elements.previewStage,preventDefault(){prevented++;},stopPropagation(){}});`);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(run('prevented'),1);assert.equal(run('requests.length'),1);assert.equal(run('requests[0].body.action'),'media_split');
});
test('Split shortcut never hijacks text input, repeated keys or automatic-caption selection',async()=>{
 for(const mode of ['input','button','repeat','caption']){
  const {run,nodes}=layers();nodes.get('previewStage').tagName=mode==='input'?'INPUT':mode==='button'?'BUTTON':'DIV';nodes.get('previewStage').closest=()=>['input','button'].includes(mode)?nodes.get('previewStage'):null;if(mode==='caption')run(`state.timeline.mediaSelection=null;state.timeline.captionSelection='automatic';`);
  run(`state.keyboardProfile='resolve';handleEditorShortcut({key:'b',code:'KeyB',ctrlKey:true,repeat:${mode==='repeat'},target:elements.previewStage,preventDefault(){},stopPropagation(){}});`);
  await new Promise(resolve=>setImmediate(resolve));assert.equal(run('requests.length'),0,mode);
 }
});
test('unsaved caption wording, unavailable assets and clip capacity stay protected',()=>{
 for(const [patch,reason] of [[`state.captionDirty=true`,/Save or discard/],[`state.project.assets.v.status='failed'`,/not ready/],[`state.project.manual.media_clips=Array.from({length:200},(_,i)=>({...state.project.manual.media_clips[0],id:i?'other'+i:'media_a'}))`,/200 media/]]){
  const {run}=layers();run(patch);assert.match(run('layerSplitIssue("media_a",3)'),reason);
 }
});
test('pending layer changes flush but changed geometry cannot silently split old coordinates',async()=>{
 const {run}=layers();run(`state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].start=2;state.project.revision++;return true;};`);
 assert.equal(await run('splitTimelineSelection()'),null);assert.equal(run('requests.length'),0);assert.match(run('messages.at(-1)'),/changed while saving/);
});
test('project navigation during a layer flush cancels the split and late asset failure is rechecked',async()=>{
 const first=layers();first.run(`state.textStudio.flush=async()=>{state.project={...state.project,id:'other'};return true;};`);assert.equal(await first.run('splitTimelineSelection()'),null);assert.equal(first.run('requests.length'),0);
 const second=layers();second.run(`flushProjectSaves=async()=>{state.project.assets.v.status='failed';};`);assert.equal(await second.run('splitTimelineSelection()'),null);assert.equal(second.run('requests.length'),0);
});
test('split revision conflict fetches latest exactly once and never retries old split time',async()=>{
 const {run}=layers();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const error=new Error('conflict');error.status=409;error.code='revision_conflict';throw error;}return {project:{...state.project,revision:12}};};`);
 assert.equal(await run('splitTimelineSelection()'),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('state.project.revision'),12);assert.match(run('messages.at(-1)'),/review the split point/);
});


test('seek/playback uses identical layer readiness and never re-enables an unsafe split or obeys unrelated A/B gaps',()=>{
 const {run,nodes}=layers();run(`state.timeline.canSplitAt=()=>false;state.trackProtection={lockedNames:()=>['A'],render(){}};publishPreviewPlayhead(3,3);`);assert.equal(nodes.get('manualSplit').disabled,false);
 run(`state.project.manual.media_clips[0].motion='pan';publishPreviewPlayhead(3,3);`);assert.equal(nodes.get('manualSplit').disabled,true);assert.match(nodes.get('manualSplit').title,/pan\/zoom/);
 run(`state.project.manual.media_clips[0].motion='none';state.project.manual.media_clips[0].fade_in=.5;publishPreviewPlayhead(1.2,1.2);`);assert.equal(nodes.get('manualSplit').disabled,true);assert.match(nodes.get('manualSplit').title,/fade/);
 run(`publishPreviewPlayhead(2,2);`);assert.equal(nodes.get('manualSplit').disabled,false);
 run(`state.timeline.mediaSelection=null;publishPreviewPlayhead(2,2);`);assert.equal(nodes.get('manualSplit').disabled,true);assert.match(nodes.get('manualSplit').title,/locked/);
});


function mediaClass() {
 const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'')+';globalThis.Class=MediaStudio;',context);return context.Class;
}
test('inspector Split availability follows seek, saves and busy state without repainting fields or queue',()=>{
 const MediaStudio=mediaClass(),studio=Object.create(MediaStudio.prototype),button={disabled:false,title:''};let time=1,busy=false;const calls=[];
 Object.assign(studio,{selected:'media_a',pending:new Map(),root:{scrollTop:143,querySelector:selector=>selector==='[data-action="split"]'?button:null},options:{time:()=>time,busy:()=>busy,splitIssue:(id,at)=>{calls.push([id,at]);return at<2?'Choose a point outside the fade.':'';}},render(){throw Error('Do not repaint inspector');}});
 studio.updateSplitAvailability();assert.equal(button.disabled,true);assert.match(button.title,/fade/);
 time=3;studio.updateSplitAvailability();assert.equal(button.disabled,false);assert.match(button.title,/one Undo/);assert.deepEqual(calls.at(-1),['media_a',3]);
 busy=true;studio.updateSplitAvailability();assert.equal(button.disabled,true);busy=false;studio.pending.set('media_a',{});studio.updateSplitAvailability();assert.equal(button.disabled,true);assert.match(button.title,/saving/);
 studio.pending.clear();studio.updateSplitAvailability(4);assert.equal(button.disabled,false);assert.equal(studio.root.scrollTop,143);assert.deepEqual(calls.at(-1),['media_a',4]);
});
test('older media hosts without a split-readiness callback keep their existing rendering contract',()=>{
 const MediaStudio=mediaClass(),studio=Object.create(MediaStudio.prototype);Object.assign(studio,{options:{time:()=>1},root:null});assert.doesNotThrow(()=>studio.updateSplitAvailability());
});


test('verified right-piece selection runs after save completion even while Blade awaits, without unlocking user navigation',async()=>{
 const {run}=layers();run(`state.timeline.editPending=true;`);await run('splitTimelineSelection()');assert.equal(run('state.manualEditBusy'),false);assert.equal(run('state.timeline.editPending'),true);assert.equal(run('state.timeline.mediaSelection'),'media_a_right');assert.equal(run('selected.length'),1);
});

test('Chapter Split is disabled in the real toolbar, main/Blade paths post nothing and never flush',async()=>{
  const {run,nodes}=layers();run(`state.project.manual.text_clips[0].template="chapter";state.timeline.mediaSelection="text_b";state.timeline.playhead=119/30;realRenderManualControls();`);
  assert.equal(nodes.get('manualSplit').disabled,true);assert.match(nodes.get('manualSplit').title,/Chapter.*fade/i);
  assert.equal(await run('splitTimelineSelection()'),null);assert.equal(await run('editLayerAction("media_split",{clip_id:"text_b",time:119/30})'),null);
  assert.deepEqual(plain(run('[requests.length,mediaFlush,textFlush,state.timeline.playhead]')),[0,0,0,119/30]);
});
for(const fps of [24,25,30,50,60])test('Native static title sends exactly the chosen frame at '+fps+' FPS',async()=>{
  const {run}=layers();run(`state.project.settings.fps=${fps};state.timeline.mediaSelection="text_b";state.timeline.playhead=(4*${fps}-1)/${fps};`);
  await run('splitTimelineSelection()');assert.equal(run('requests[0].body.action'),'text_split');assert.equal(run('requests[0].body.time'),(4*fps-1)/fps);
});
for(const fps of [24,30,60])test('Old stored title frame accepted only for exact static six-decimal spelling at '+fps+' FPS',async()=>{
  const {planGroupJoin}=await import('../web/group-join.js'),frame=4*fps-1,z=Math.round(frame/fps*1e6)/1e6;
  const make=(kind,template,delta=0)=>{const text=kind!=='video',prefix=text?'text_':'media_',a=prefix+'a'.repeat(32),b=prefix+'b'.repeat(32),
    base=text?{text:'Static',kind,template,style:'bold'}:{asset_id:'asset',source_start:0,speed:1,fade_in:0,fade_out:0,motion:'none'},
    left={...base,id:a,start:3,end:z+delta},right={...base,id:b,start:z+delta,end:5};
    if(!text)right.source_start=z+delta-3;return [{id:'project',revision:3,settings:{fps},editor_sequence:{duration:9},draft:{status:'ready'},assets:{asset:{id:'asset',kind:'video',duration:9,status:'ready'}},manual:{text_clips:text?[left,right]:[],media_clips:text?[]:[left,right]}},[a,b]];};
  for(const t of ['plain','lower_third','callout','highlight']){const x=make('title',t),plan=planGroupJoin(...x);assert.equal(plan.issue,'');assert.equal(plan.seam,z);assert.equal(plan.frame,frame);}
  for(const x of [make('title','chapter'),make('caption','plain'),make('video',null),make('title','plain',1e-7)])assert.ok(planGroupJoin(...x).issue);
});
