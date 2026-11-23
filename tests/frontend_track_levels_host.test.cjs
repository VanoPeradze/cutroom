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
  const document = {body:{tagName:'BODY'},activeElement:null,getElementById(id){if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id);},
    querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context = vm.createContext({document,console,structuredClone,dictionaries:{en:{}},setTimeout,clearTimeout,
    window:{addEventListener(){}},requestAnimationFrame:fn=>fn(),performance:{now:()=>0}});
  const run = code=>vm.runInContext(code,context);
  for(const file of ['source-tracks.js','timeline.js','keyboard.js','layer-tracks.js','layer-selection.js']) run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,''));
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




const T='track_'+'1'.repeat(32),M='media_'+'2'.repeat(32);
function levels(){const h=app();h.run(`
 globalThis.trackId=${JSON.stringify(T)};state.project.assets={a:{id:'a',kind:'audio',status:'ready',duration:10}};
 state.project.manual.layer_tracks={version:2,tracks:[{id:trackId,name:'Protected sound',kind:'audio',locked:true}]};
 state.project.manual.media_clips=[{id:${JSON.stringify(M)},asset_id:'a',track_id:trackId,start:0,end:3}];state.project.manual.text_clips=[];
 state.mediaStudio={pending:new Map(),saving:null,trackLevelGesture:null,trackLevels:{hasDraft:()=>false,focusDraft(){globalThis.focusedDraft=true;}},flush:async()=>true,render(){globalThis.mediaRenders=(globalThis.mediaRenders||0)+1;}};
 state.textStudio={flush:async()=>true,render(){}};state.timeline.scheduleDraw=()=>{};state.timeline.selectedMediaIds=()=>[];
 updateMediaPreview=()=>{globalThis.previewCount=(globalThis.previewCount||0)+1;};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});const result=structuredClone(state.project);result.revision++;
 const model=result.manual.layer_tracks;if(model.version!==3){model.protection_version=model.version;model.version=3;model.tracks=model.tracks.map(t=>({...t,locked:t.locked===true,...(t.kind==='text'?{}:{audio:{gain_db:0,muted:false}})}));}
 const track=model.tracks.find(t=>t.id===body.track_id);for(const key of ['gain_db','muted'])if(Object.hasOwn(body,key))track.audio[key]=body[key];return {project:result};};
 `);return h;}
test('real host admits mix on protected track without forcing selection or pausing audition',async()=>{const h=levels();h.run('state.preview.playing=true;state.mediaStudio.saving=Promise.resolve();');await h.run('applyManualEdit("layer_track_audio",{track_id:trackId,gain_db:-6})');assert.equal(h.run('requests.length'),1);assert.deepEqual(plain(h.run('requests[0].body')),{action:'layer_track_audio',track_id:T,gain_db:-6,expected_revision:7});assert.equal(h.run('state.project.manual.layer_tracks.version'),3);assert.equal(h.run('state.project.manual.layer_tracks.protection_version'),2);assert.equal(h.run('state.project.manual.layer_tracks.tracks[0].locked'),true);assert.equal(h.run('state.preview.playing'),true);assert.equal(h.run('seeks.length'),0);assert.equal(h.run('renderCount'),0);});
test('neutral legacy gain is local no-op, no version, request or history change',async()=>{const h=levels();await h.run('applyManualEdit("layer_track_audio",{track_id:trackId,gain_db:0})');assert.equal(h.run('requests.length'),0);assert.equal(h.run('state.project.manual.layer_tracks.version'),2);});
test('current numeric unfinished draft is actionable and blocks Copy and clip edits without dropping text',async()=>{const h=levels();h.run('state.mediaStudio.trackLevels.hasDraft=()=>true;');assert.equal(h.run('explicitPendingDraft().target'),'track-level');assert.equal(h.run('projectSaveStatus().kind'),'unsaved');assert.equal(h.run('copyExplicitDraft().target'),'track-level');assert.equal(h.run('canEditTimeline()'),false);await h.run('applyManualEdit("media_remove",{clip_id:'+JSON.stringify(M)+'})');assert.equal(h.run('requests.length'),0);assert.equal(h.run('focusedDraft'),true);assert.equal(h.run('state.mediaStudio.trackLevels.hasDraft()'),true);assert.equal(h.run('trackLevelIssue()'),'');});
test('active fader blocks structural/copy while its own control remains correctable',()=>{const h=levels();h.run('state.mediaStudio.trackLevelGesture={};');assert.equal(h.run('projectCopyGestureActive()'),true);assert.equal(h.run('hasUnsavedProjectWork()'),true);assert.equal(h.run('trackLevelIssue()'),'');assert.equal(h.run('canEditTimeline()'),false);});
test('unrelated explicit caption draft blocks track level admission',async()=>{const h=levels();h.run('state.captionDirty=true;');await h.run('applyManualEdit("layer_track_audio",{track_id:trackId,muted:true})');assert.equal(h.run('requests.length'),0);assert.match(h.run('messages.at(-1)'),/caption/);});
test('queued settings block new mix instead of borrowing a changed revision after flush',()=>{const h=levels();h.run('state.saveQueues.set(state.project.id,{pending:{settings:{fps:24}}});');assert.match(h.run('trackLevelIssue()'),/save/);});
test('malformed v3 fails closed before any preview/save',async()=>{const h=levels();h.run('state.project.manual.layer_tracks.version=3;');await h.run('applyManualEdit("layer_track_audio",{track_id:trackId,gain_db:-5})');assert.equal(h.run('requests.length'),0);assert.match(h.run('messages.at(-1)'),/malformed/);});
test('wrong mix receipt is not installed or called saved',async()=>{const h=levels();h.run('const originalApi=api;api=async(...args)=>{const r=await originalApi(...args);r.project.manual.layer_tracks.tracks[0].audio.gain_db=-9;return r;};');assert.equal(await h.run('applyManualEdit("layer_track_audio",{track_id:trackId,gain_db:-6})'),null);assert.match(h.run('messages.at(-1)'),/could not be verified/);assert.equal(h.run('state.project.manual.layer_tracks.version'),2);assert.equal(h.run('requests.length'),1);});
test('actual strict409 refresh never replays, seeks or steals later view',async()=>{const h=levels();h.run(`api=async(url,options)=>{requests.push({url,body:options?.body?JSON.parse(options.body):null});if(options){state.timeline.playhead=5;state.studio.activeTab='audio';const e=new Error('stale');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:8}};};`);assert.equal(await h.run('applyManualEdit("layer_track_audio",{track_id:trackId,gain_db:-6})'),null);assert.match(h.run('messages.at(-1)'),/not repeated/);assert.equal(h.run('requests.filter(r=>r.body).length'),1);assert.equal(h.run('seeks.length'),0);assert.equal(h.run('state.timeline.playhead'),5);assert.equal(h.run('state.project.revision'),8);assert.equal(h.run('renderCount'),0);});
test('late result cannot overwrite a copied branch with same track identity',async()=>{const h=levels();h.run('const originalApi=api;api=async(...args)=>{const r=await originalApi(...args);state.project={...state.project,id:"copy"};state.projectViewToken++;return r;};');await h.run('applyManualEdit("layer_track_audio",{track_id:trackId,gain_db:-6})');assert.equal(h.run('state.project.id'),'copy');assert.equal(h.run('state.project.manual.layer_tracks.version'),2);assert.equal(h.run('seeks.length'),0);});
