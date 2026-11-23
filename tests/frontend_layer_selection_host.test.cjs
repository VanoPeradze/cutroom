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
  for(const file of ['source-tracks.js','timeline.js','keyboard.js','layer-selection.js']) run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,''));
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



const MID='media_'+'a'.repeat(32), AID='media_'+'b'.repeat(32), TID='text_'+'c'.repeat(32);
function groups(){const h=app();h.run(`
 globalThis.ids=${JSON.stringify([MID,AID,TID])};
 state.project.assets={v:{id:'v',kind:'video',status:'ready',duration:10},a:{id:'a',kind:'audio',status:'ready',duration:10}};
 state.project.manual.media_clips=[{id:ids[0],asset_id:'v',start:1.123456789,end:3.23456789,source_start:1,video_source_start:2,speed:.5,motion:'pan',fade_in:.2,fade_out:.2,enabled:false},{id:ids[1],asset_id:'a',start:.5,end:2,source_start:3,speed:1,volume_db:-7.5}];
 state.project.manual.text_clips=[{id:ids[2],start:1.123456,end:3.234567,text:'Saved title',kind:'caption',style:'boxed',scale:125,template:'lower_third',subtext:'Second line'}];
 globalThis.members=[...ids];state.timeline.mediaSelection=ids[0];
 state.timeline.selectedMediaIds=()=>[...members];state.timeline.setMediaSelection=(next,primary)=>{members=[...next];state.timeline.mediaSelection=primary||null;};
 state.timeline.playhead=2;state.timeline.onMediaAction=editLayerAction;
 globalThis.mediaFlush=0;globalThis.textFlush=0;globalThis.previewCount=0;globalThis.groupPreviews=[];
 updateMediaPreview=()=>previewCount++;
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){},select(id){this.selected=id;},previewGroup:p=>groupPreviews.push(['media',p])};
 state.textStudio={flush:async()=>{textFlush++;return true;},render(){},select:async id=>{state.textStudio.selected=id;return true;},previewGroup:p=>groupPreviews.push(['text',p])};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});const plan=layerGroupMovePlan(body.clip_ids,body.delta),map=new Map(plan.patches.map(row=>[row.clip_id,row]));
 const shift=rows=>rows.map(row=>map.has(row.id)?{...row,start:map.get(row.id).start,end:map.get(row.id).end}:row);
 return {project:{...state.project,revision:state.project.revision+1,manual:{...state.project.manual,media_clips:shift(state.project.manual.media_clips),text_clips:shift(state.project.manual.text_clips)}}};};
 `);return h;}
test('one native group move preserves relative timing/content/order and restores entire selection',async()=>{
 const {run}=groups();run('globalThis.before=JSON.stringify(state.project);state.trackProtection={lockedNames:()=>["A","B"],render(){}};state.timeline.editPending=true;');
 assert.ok(await run('editLayerAction("layers_move",{clip_ids:ids,delta:1/30})'));
 assert.deepEqual(plain(run('requests[0].body')),{action:'layers_move',clip_ids:[MID,AID,TID],delta:1/30,expected_revision:7});
 const before=JSON.parse(run('before')),after=plain(run('state.project'));
 for(const key of ['media_clips','text_clips'])after.manual[key].forEach((row,i)=>{const original=before.manual[key][i],precision=key==='text_clips'?1e6:1e9;assert.deepEqual({...row,start:original.start,end:original.end},original);assert.equal(row.start,Math.round((original.start+1/30)*precision)/precision);assert.equal(row.end,Math.round((original.end+1/30)*precision)/precision);});
 assert.deepEqual(after.sources,before.sources);assert.deepEqual(after.assets,before.assets);assert.deepEqual(after.editor_sequence,before.editor_sequence);assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.equal(run('state.timeline.mediaSelection'),MID);assert.equal(run('seeks.at(-1)'),2);assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('state.manualEditBusy'),false);
});
test('zero group move consumes neither saves nor history and keeps fractional anchors',async()=>{const {run}=groups(),before=run('JSON.stringify(state.project)');assert.ok(await run('moveTimelineLayerGroup(ids,0)'));assert.equal(run('requests.length'),0);assert.equal(run('mediaFlush+textFlush'),0);assert.equal(run('JSON.stringify(state.project)'),before);assert.deepEqual(plain(run('layerGroupMovePlan(ids,0).patches')),[]);});
for(const [ids,delta,reason] of [
 ['[]','1',/2 and 200/],['["media_missing","text_missing"]','1',/2 and 200/],['[...ids,ids[0]]','1',/distinct/],['[ids[0]]','1',/2 and 200/],['[ids[0],"A"]','1',/2 and 200/],['ids','NaN',/finite/],['ids','true',/finite/],['ids','Infinity',/finite/],['ids','604801',/finite/],['ids','-.6',/whole selection/],['ids','4',/whole selection/]
])test(`invalid group request ${ids}/${delta} leaves all data unchanged`,async()=>{const {run}=groups(),before=run('JSON.stringify(state.project)');const plan=run(`layerGroupMovePlan(${ids},${delta})`);assert.match(plan.issue,reason);assert.equal(plan.patches,null);assert.equal(await run(`applyManualEdit('layers_move',{clip_ids:${ids},delta:${delta}})`),null);assert.equal(run('requests.length'),0);assert.equal(run('JSON.stringify(state.project)'),before);});
for(const setup of ['state.project.assets.v.status="failed"','state.project.assets.a.kind="unknown"','state.project.manual.media_clips.push(null)','state.project.manual.text_clips.push({...state.project.manual.text_clips[0]})','state.project.manual.media_clips[0].end=NaN','state.project.draft=null','state.project.editor_sequence.error="Unsupported sequence version"','state.captionDirty=true'])test(`invalid saved context blocks group: ${setup}`,async()=>{const {run}=groups();run(setup);const before=run('JSON.stringify(state.project)');assert.ok(run('layerGroupMovePlan(ids,1).issue'));assert.equal(await run('moveTimelineLayerGroup(ids,1)'),null);assert.equal(run('requests.length'),0);assert.equal(run('JSON.stringify(state.project)'),before);});
test('whole final text arrangement is validated, not sequential intermediate moves',()=>{const {run}=groups();run(`state.project.manual.media_clips=[];state.project.manual.text_clips=Array.from({length:16},(_,i)=>({id:'text_'+i.toString(16).padStart(32,'0'),start:1,end:2}));ids=state.project.manual.text_clips.map(row=>row.id);`);assert.equal(run('layerGroupMovePlan(ids,.5).issue'),'');run(`state.project.manual.text_clips.push({id:'text_'+'f'.repeat(32),start:3,end:4,enabled:false});`);assert.match(run('layerGroupMovePlan(ids,1.5).issue'),/16 custom/);assert.equal(run('layerGroupMovePlan(ids,1).issue'),'');});
test('group movement never calls singular source or media actions',async()=>{const {run}=groups();for(const action of ['media_remove','text_remove','media_split','text_trim','sequence_split','track_move','delete_range','media_duplicate','media_slip'])assert.equal(await run(`applyManualEdit('${action}',{clip_id:ids[0],time:2,start:3})`),null);assert.equal(run('requests.length'),0);assert.match(run('messages.at(-1)'),/Several clips/);});
test('Split and Trim do not target a primary member; Duplicate now offers the atomic group path',async()=>{const {run}=groups();for(const call of ['splitTimelineSelection(2)','trimTimelineSelection("start",2)'])assert.equal(await run(call),null);run('renderSplitAvailability(2);renderDuplicateAvailability(2);');assert.equal(run('elements.manualSplit.disabled'),true);assert.equal(run('elements.clipDuplicate.disabled'),false);assert.match(run('elements.clipDuplicate.textContent'),/3 clips/);assert.equal(run('requests.length'),0);});
test('group membership change during pending flush cancels without an edit',async()=>{const {run}=groups();run('state.textStudio.flush=async()=>{members=ids.slice(1);return true;};');assert.equal(await run('moveTimelineLayerGroup(ids,1)'),null);assert.equal(run('requests.length'),0);});
for(const setup of ['state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].source_start=7;return true;}','flushProjectSaves=async()=>{state.project.assets.v.path="new.mp4";}','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}'])test(`stale group content/project cannot move after ${setup}`,async()=>{const {run}=groups();run(setup);assert.equal(await run('moveTimelineLayerGroup(ids,1)'),null);assert.equal(run('requests.length'),0);});
test('group conflict refreshes once, never replays a delta on a different arrangement',async()=>{const {run}=groups();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:15}};};`);assert.equal(await run('moveTimelineLayerGroup(ids,1)'),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(row=>row.options?.method==="POST").length'),1);assert.match(run('messages.at(-1)'),/selection placement/);assert.deepEqual(plain(run('members')),[]);assert.equal(run('seeks.at(-1)'),2);});
test('repeated group commands waiting on same flush produce one mutation',async()=>{const {run}=groups();run('globalThis.release=null;const wait=new Promise(r=>release=r);state.textStudio.flush=()=>wait;globalThis.first=moveTimelineLayerGroup(ids,1);globalThis.second=moveTimelineLayerGroup(ids,2);release(true);');await run('Promise.all([first,second])');assert.equal(run('requests.length'),1);});
test('group preview batches both studios once and does not use queued single overrides',()=>{const {run}=groups();run('previewLayerGroup([{clip_id:ids[0],start:2,end:3},{clip_id:ids[2],start:2,end:3}]);');assert.equal(run('previewCount'),1);assert.deepEqual(plain(run('groupPreviews')),[['media',[{clip_id:MID,start:2,end:3}]],['text',[{clip_id:TID,start:2,end:3}]]]);run('previewLayerGroup(null)');assert.equal(run('previewCount'),2);assert.deepEqual(plain(run('groupPreviews.slice(-2)')),[['media',null],['text',null]]);});
test('group placement aligns only group head to playhead; nudges keep fractional spacing',()=>{const {run}=groups();assert.equal(run('layerGroupMoveDelta("playhead",2.52)'),2.533333333333333-.5);assert.equal(run('layerGroupMoveDelta("1")'),1/30);assert.equal(run('layerGroupMoveDelta("-1")'),-1/30);assert.ok(Number.isNaN(run('layerGroupMoveDelta("other")')));});
test('group selection flushes pending fields and clears singular inspectors only after acceptance',async()=>{const {run}=groups();run(`state.mediaStudio.selected=ids[0];state.textStudio.selected=ids[2];prepareInspectorSelection=async()=>true;clearCaptionInspectorSelection=()=>{};selectAdvancedTab=()=>{};`);assert.equal(await run('selectTimelineLayers(ids,ids[1])'),true);assert.equal(run('state.mediaStudio.selected'),null);assert.equal(run('state.textStudio.selected'),null);assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.equal(run('state.timeline.mediaSelection'),AID);assert.equal(run('requests.length'),0);});
test('rejected group selection leaves pending text and old selection untouched',async()=>{const {run}=groups();run(`state.textStudio.selected=ids[2];prepareInspectorSelection=async()=>false;restoreInspectorSelection=()=>{};`);assert.equal(await run('selectTimelineLayers(ids,ids[1])'),false);assert.equal(run('state.textStudio.selected'),TID);assert.equal(run('state.timeline.mediaSelection'),MID);});
for(const [name,file,key] of [['MediaStudio','media-studio.js','media_clips'],['TextStudio','text-studio.js','text_clips']])test(`${name} transient group preview is separate from pending numeric values`,()=>{const c=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,'')+`;globalThis.Class=${name};`,c);const v=Object.create(c.Class.prototype),id=key==='media_clips'?MID:TID;Object.assign(v,{project:()=>({manual:{[key]:[{id,start:1,end:2,volume_db:0}]}}),overrides:new Map([[id,{volume_db:-7}]]),dragOverrides:new Map(),options:{preview(){throw Error('Host batches repaint');}}});v.previewGroup([{clip_id:id,start:2,end:3}]);assert.deepEqual(plain(v.clips()[0]),{id,start:2,end:3,volume_db:-7});v.previewGroup(null);assert.deepEqual(plain(v.clips()[0]),{id,start:1,end:2,volume_db:-7});assert.equal(v.overrides.get(id).volume_db,-7);});

test('group canonical endpoints use half-up precision at half-microsecond and half-nanosecond boundaries',()=>{const {run}=groups();run('state.project.manual.text_clips[0].start=4;state.project.manual.text_clips[0].end=4.5;state.project.manual.media_clips[0].start=4;state.project.manual.media_clips[0].end=4.5;');assert.equal(run('layerGroupMovePlan([ids[0],ids[2]],.0000005).patches[1].end'),4.500001);assert.equal(run('layerGroupMovePlan([ids[0],ids[1]],.0000000005).patches[0].start'),4.000000001);run('state.project.editor_sequence.duration=4.5');assert.match(run('layerGroupMovePlan([ids[0],ids[2]],.0000005).issue'),/whole selection/);});

test('mixed group viewer preview cannot rewrite timeline saved identity on successive pointer moves',()=>{const {run}=groups();run(`state.textStudio.sync=()=>{};state.textStudio.clips=includeGroup=>state.project.manual.text_clips.map(row=>({...row,...(includeGroup===false?{}:{start:row.start+1,end:row.end+1})}));editorProject=()=>state.project;state.timeline.scheduleDraw=()=>{};previewUsesSourceTime=()=>false;globalThis.saved=JSON.stringify(state.project.manual.text_clips);updateTextPreview();updateTextPreview();`);assert.equal(run('JSON.stringify(state.timeline.project.manual.text_clips)'),run('saved'));assert.equal(run('JSON.stringify(state.project.manual.text_clips)'),run('saved'));});

test('timeline selection and edit pending transitions refresh group command availability',()=>{assert.match(source,/onToolStateChange:\s*\(\)\s*=>\s*\{\s*renderTimelineToolStatus\(\);\s*renderLayerGroupControls\(\);/);});

test("missing group membership fails closed without a page error or dispatch",()=>{const {run}=groups();assert.equal(run("moveTimelineLayerGroup(undefined,1)"),null);assert.equal(run("requests.length"),0);});

test("live group preview pauses playback once without saving or changing the selected set",()=>{const {run}=groups();run("globalThis.pauses=0;pauseAllMedia=()=>{pauses++;state.preview.playing=false;};state.preview.playing=true;previewLayerGroup([{clip_id:ids[0],start:2,end:3}]);previewLayerGroup([{clip_id:ids[0],start:3,end:4}]);previewLayerGroup(null);");assert.equal(run("pauses"),1);assert.equal(run("requests.length"),0);assert.deepEqual(plain(run("members")),[MID,AID,TID]);});

test("reopening the same project while group preflush waits cannot apply an old gesture",async()=>{const {run}=groups();run("state.projectViewToken=1;state.textStudio.flush=async()=>{state.projectViewToken=2;return true;};");assert.equal(await run("moveTimelineLayerGroup(ids,1)"),null);assert.equal(run("requests.length"),0);});
