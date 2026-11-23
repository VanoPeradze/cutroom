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
      replaceChildren(...children){this.children=children;this.options=children;},
      setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];},
      addEventListener(key,fn){this.listeners[key]=fn;},
      querySelector(key){if(!nested.has(key))nested.set(key,element(key));return nested.get(key);},
      querySelectorAll(){return [];},focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;},
    };
  };
  const document = {createElement:()=>element(),body:{tagName:'BODY'},activeElement:null,getElementById(id){if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id);},
    querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context = vm.createContext({document,console,dictionaries:{en:{}},setTimeout,clearTimeout,
    window:{addEventListener(){}},requestAnimationFrame:fn=>fn(),performance:{now:()=>0}});
  const run = code=>vm.runInContext(code,context);
  for(const file of ['source-tracks.js','timeline.js','keyboard.js','layer-tracks.js','layer-selection.js','layer-group-tracks.js']) run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/^export /gm,''));
  run('Object.assign(globalThis,(function(){'+fs.readFileSync(path.join(__dirname,'../web/layer-group-frame.js'),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/^export /gm,'')+';return {planLayerGroupFrame,verifyLayerGroupFrame};})());');
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
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});
 const shift=rows=>rows.filter(row=>!body.clip_ids.includes(row.id));
 return {project:{...state.project,revision:state.project.revision+1,manual:{...state.project.manual,media_clips:shift(state.project.manual.media_clips),text_clips:shift(state.project.manual.text_clips)}}};};
 `);return h;}

test('one atomic group Remove preserves duration/source/other layers/assets and clears selection after success',async()=>{
 const {run}=groups();run(`state.project.manual.media_clips.push({id:'media_'+'d'.repeat(32),start:4,end:5,asset_id:'v',enabled:false});globalThis.before=JSON.stringify(state.project);state.trackProtection={lockedNames:()=>['A','B']};`);
 assert.ok(await run('editLayerAction("layers_remove",{clip_ids:ids})'));
 assert.deepEqual(plain(run('requests[0].body')),{action:'layers_remove',clip_ids:[MID,AID,TID],expected_revision:7});
 const before=JSON.parse(run('before')),after=plain(run('state.project'));
 assert.deepEqual(after.manual.media_clips,[before.manual.media_clips[2]]);assert.deepEqual(after.manual.text_clips,[]);
 for(const key of ['sources','assets','settings','editor_sequence','draft','analysis'])assert.deepEqual(after[key],before[key]);
 for(const key of ['source_mixer','crop'])assert.deepEqual(after.manual[key],before.manual[key]);
 assert.deepEqual(plain(run('members')),[]);assert.equal(run('state.timeline.mediaSelection'),null);assert.equal(run('seeks.at(-1)'),2);
 assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('state.manualEditBusy'),false);
});
test('last independent occurrences leave the saved duration and sources intact for Undo/reassembly',async()=>{const {run}=groups();run('state.project.manual.source_tracks={A:[],B:[]};state.project.manual.sequence={duration:6};');assert.ok(await run('removeTimelineLayerGroup(ids)'));assert.deepEqual(plain(run('state.project.manual.source_tracks')),{A:[],B:[]});assert.equal(run('state.project.manual.sequence.duration'),6);assert.equal(run('state.project.editor_sequence.duration'),6);assert.equal(run('Object.keys(state.project.assets).length'),2);assert.deepEqual(plain(run('state.project.manual.media_clips')),[]);assert.deepEqual(plain(run('state.project.manual.text_clips')),[]);});
for(const setup of ['state.project.assets={}','state.project.assets.v.status="failed"','state.project.manual.media_clips[0].enabled=false','state.project.manual.media_clips[0].start=-1','state.project.manual.media_clips[0].speed=99'])test('Remove does not require media readiness or move normalization: '+setup,async()=>{const {run}=groups();run(setup);assert.equal(run('planLayerGroupRemove(state.project,ids).issue'),'');assert.ok(await run('removeTimelineLayerGroup(ids)'));assert.equal(run('requests.length'),1);});
for(const expression of ['[]','[ids[0]]','[ids[0],ids[0]]','[ids[0],"A"]','[ids[0],"caption_x"]','[ids[0],"media_"+"f".repeat(32)]','null','"all"','Array.from({length:201},(_,i)=>"media_"+i.toString(16).padStart(32,"0"))'])test('invalid removal selection fails closed: '+expression,async()=>{const {run}=groups();const before=run('JSON.stringify(state.project)');assert.ok(run(`planLayerGroupRemove(state.project,${expression}).issue`));assert.equal(await run(`removeTimelineLayerGroup(${expression})`),null);assert.equal(run('requests.length'),0);assert.equal(run('JSON.stringify(state.project)'),before);});
for(const setup of ['state.project.manual.media_clips.push(null)','state.project.manual.media_clips.push({...state.project.manual.media_clips[0]})','state.project.manual.media_clips[0].id="media_bad"','state.project.manual.media_clips[0].id=ids[2]','state.project.manual.text_clips={}','state.project.draft=null','state.project.editor_sequence.error="Unsupported timeline"','state.project.editor_sequence.duration=NaN'])test('ambiguous saved identity/sequence refuses removal: '+setup,async()=>{const {run}=groups();run(setup);assert.ok(run('planLayerGroupRemove(state.project,ids).issue'));assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('requests.length'),0);});
test('pure removal validation is read-only and returns a detached membership list',()=>{const {run}=groups();run('globalThis.before=JSON.stringify(state.project);globalThis.plan=planLayerGroupRemove(state.project,ids);plan.clip_ids.pop();');assert.equal(run('ids.length'),3);assert.equal(run('JSON.stringify(state.project)'),run('before'));});
for(const setup of ['state.manualEditBusy=true','state.transcriptSaving=true','state.captionDirty=true','state.captionContextSave=true','state.timeline.gesture={kind:"media_group"}','state.timeline.scrubbing=true','state.timeline.libraryDragActive=true','state.timeline.mediaSelectionPending=true','state.timeline.mediaSourceOpening=true','state.chromaStudio={projectId:"p",pendingDrafts:()=>[{slot:"media",issue:"Apply Chroma draft first"}]}'])test('pending work cannot be removed underneath: '+setup,async()=>{const {run}=groups();run(setup);assert.ok(run('layerGroupRemoveIssue(ids)'));assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('requests.length'),0);assert.deepEqual(plain(run('members')),[MID,AID,TID]);});
test('canvas own editPending token does not reject its admitted group Remove',async()=>{const {run}=groups();run('state.timeline.editPending=true;');assert.ok(await run('editLayerAction("layers_remove",{clip_ids:ids})'));assert.equal(run('requests.length'),1);});
for(const setup of ['state.textStudio.flush=async()=>false','state.mediaStudio.flush=async()=>false','state.textStudio.flush=async()=>{members=ids.slice(1);return true;}','state.textStudio.flush=async()=>{state.projectViewToken=99;return true;}','state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].source_start++;return true;}','flushProjectSaves=async()=>{state.timeline.gesture={kind:"media_group"};}','flushProjectSaves=async()=>{state.project.assets.v.path="changed";}'])test('preflush cancellation cannot remove a different saved selection: '+setup,async()=>{const {run}=groups();run(setup);assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('requests.length'),0);});
test('repeated removal during preflush commits once',async()=>{const {run}=groups();run('let release;const wait=new Promise(r=>release=r);state.textStudio.flush=()=>wait;globalThis.first=removeTimelineLayerGroup(ids);globalThis.second=removeTimelineLayerGroup(ids);release(true);');await run('Promise.all([first,second])');assert.equal(run('requests.length'),1);});
test('failed save retains original selection and content; success retry removes once',async()=>{const {run}=groups();run('globalThis.savedApi=api;api=async()=>{throw Error("offline");};globalThis.before=JSON.stringify(state.project);');assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('JSON.stringify(state.project)'),run('before'));assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.match(run('messages.at(-1)'),/offline/);run('api=savedApi');assert.ok(await run('removeTimelineLayerGroup(ids)'));});
test('stale removal refreshes current history once without replay or clearing surviving selection',async()=>{const {run}=groups();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:15}};};`);assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('requests.length'),2);assert.equal(run('state.project.revision'),15);assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.match(run('messages.at(-1)'),/selected clips before removing/);assert.equal(run('seeks.at(-1)'),2);});
for(const setup of ['state.projectViewToken=88','members=ids.slice(1)','state.project={...state.project,id:"other"}'])test('late conflict refresh cannot overwrite newer navigation: '+setup,async()=>{const {run}=groups();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}const project={...state.project,revision:15};${setup};return {project};};`);assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('state.project.revision'),7);assert.equal(run('renderCount'),0);});
test('older or foreign conflict GET cannot replace the currently saved project',async()=>{for(const value of ['{...state.project,revision:6}','{...state.project,id:"other",revision:20}']){const {run}=groups();run(`api=async(url,options)=>{if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:${value}};};`);assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('state.project.id'),'p');assert.equal(run('state.project.revision'),7);}});
test('late accepted response cannot clear a newer view or selection',async()=>{for(const setup of ['state.projectViewToken=88','members=ids.slice(1)','state.project={...state.project,id:"other"}']){const {run}=groups();run(`const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);${setup};return result;};`);assert.ok(await run('removeTimelineLayerGroup(ids)'));assert.equal(run('state.project.revision'),7);assert.equal(run('renderCount'),0);assert.ok(run('members.length')>0);}});
test('main Delete routing ignores stale source range when a group exists',async()=>{const {run}=groups();run('state.manualSelection={start:0,end:4};');assert.ok(await run('runManualRangeEdit("delete_range","A")'));assert.equal(run('requests[0].body.action'),'layers_remove');assert.equal(run('requests[0].body.slot'),undefined);assert.equal(run('requests[0].body.start'),undefined);});
test('group source Restore stays blocked rather than opening primary source review',()=>{const {run}=groups();run('openSourceReview=()=>{throw Error("source fallback")};');assert.equal(run('runManualRangeEdit("restore_range")'),null);});
for(const key of ['Delete','Backspace'])test('eligible host '+key+' is one group transaction; repeat never replays',async()=>{const {run}=groups();run(`state.keyboardProfile='cutroom';globalThis.commands=[];removeTimelineLayerGroup=(...args)=>commands.push(args);elements.timelineCanvas.tagName='CANVAS';elements.timelineCanvas.closest=()=>null;globalThis.e={key:'${key}',code:'${key}',target:elements.timelineCanvas,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;}};handleEditorShortcut(e);e.repeat=true;handleEditorShortcut(e);`);assert.equal(run('commands.length'),1);assert.equal(run('e.prevented'),true);assert.equal(run('e.stopped'),true);assert.deepEqual(plain(run('commands[0][0]')),[MID,AID,TID]);});
test('unbound or protected Delete never removes primary, source, or group',()=>{for(const setup of ["state.keyboardProfile='premiere';e.key=e.code='Delete'","e.target={tagName:'INPUT',closest:()=>({})}","e.target={tagName:'BUTTON',closest:()=>({})}"]){const {run}=groups();run(`globalThis.commands=[];removeTimelineLayerGroup=(...args)=>commands.push(args);elements.timelineCanvas.tagName='CANVAS';elements.timelineCanvas.closest=()=>null;globalThis.e={key:'Delete',code:'Delete',target:elements.timelineCanvas,preventDefault(){},stopPropagation(){}};${setup};handleEditorShortcut(e);`);assert.equal(run('commands.length'),0);}});
test('group inspector focus returns only for its successful hidden action and current view',async()=>{for(const mode of ['owned','other','foreign','failure']){const {run}=groups();run(`state.layerGroupPanel=document.getElementById("groups");state.layerGroupPanel.hidden=true;globalThis.button={};document.activeElement=button;const originalApi=api;api=async(...args)=>{${mode==='failure'?'throw Error("offline")':''};const result=await originalApi(...args);${mode==='other'?'document.activeElement={tagName:"INPUT"}':mode==='foreign'?'state.projectViewToken=99':'document.activeElement=document.body'};return result;};`);await run('removeTimelineLayerGroup(ids,{focusOwner:button})');assert.equal(Boolean(run('elements.timelineCanvas.focused')),mode==='owned');}});
test('header/inspector Remove wording and accessible scope never describe ripple removal',()=>{assert.match(source,/mediaGroupRemoveIssue: layerGroupRemoveIssue/);assert.match(source,/button\.setAttribute\("aria-describedby",\s*"layerGroupRemoveHelp"\)/);assert.match(source,/manualDelete\.setAttribute\("aria-describedby",\s*"timelineRangeImpactDetails"\)/);assert.match(source,/data-group-remove aria-describedby="layerGroupRemoveHelp"/);assert.match(source,/Remove selected occurrences without ripple/);assert.match(source,/Other clips, edit duration and original files stay unchanged/);});

test('older successful response cannot overwrite newer same-view content or history',async()=>{const {run}=groups();run(`const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);state.project={...state.project,revision:20,name:'Newer saved edit'};return result;};`);assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('state.project.revision'),20);assert.equal(run('state.project.name'),'Newer saved edit');assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.equal(run('renderCount'),0);assert.match(run('messages.at(-1)'),/newer saved edit/);});
for(const change of ['result.project.id="foreign"','result.project.revision=NaN'])test('invalid success identity never installs the removal response: '+change,async()=>{const {run}=groups();run(`const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);${change};return result;};`);assert.equal(await run('removeTimelineLayerGroup(ids)'),null);assert.equal(run('state.project.id'),'p');assert.equal(run('state.project.revision'),7);assert.equal(run('renderCount'),0);});

test('selection pending release immediately restores main group Remove without a full repaint',()=>{const {run}=groups();run('state.timeline.mediaSelectionPending=true;renderLayerGroupControls();');assert.equal(run('elements.manualDelete.disabled'),true);assert.match(run('elements.manualDelete.title'),/gesture or selection/);run('state.timeline.mediaSelectionPending=false;renderLayerGroupControls();');assert.equal(run('elements.manualDelete.disabled'),false);assert.equal(run('elements.manualDelete.textContent'),'Remove 3 selected clips');assert.match(run('elements.manualDelete.title'),/without ripple/);assert.equal(run('elements.manualDelete.attrs["aria-describedby"]'),'layerGroupRemoveHelp');});
test('main group Remove follows edit pending and gesture transitions with the same precise scope',()=>{const {run}=groups();for(const flag of ['editPending','gesture']){run(`state.timeline.${flag}=true;renderLayerGroupControls();`);assert.equal(run('elements.manualDelete.disabled'),true);run(`state.timeline.${flag}=false;renderLayerGroupControls();`);assert.equal(run('elements.manualDelete.disabled'),false);}});

test('empty edited timeline disables only its Play/Restart controls with a recovery explanation',()=>{const {run}=groups();run('editorProject=()=>state.project;trackClips=()=>[];state.project.manual.media_clips=[];state.project.manual.text_clips=[];state.preview.mode="edit";renderPreviewAvailability();');for(const id of ['playButton','previewPlay','restartPreview']){assert.equal(run(`elements.${id}.disabled`),true);assert.match(run(`elements.${id}.title`),/empty.*Undo.*Full source/);}assert.equal(run('elements.studioRenderButton.disabled'),undefined);});
test('Full source remains available on an empty edit and switching back restores the empty gate',()=>{const {run}=groups();run('editorProject=()=>state.project;trackClips=()=>[];state.project.manual.media_clips=[];state.project.manual.text_clips=[];state.preview.mode="edit";renderPreviewAvailability();setPreviewMode("source");');assert.equal(run('elements.playButton.disabled'),false);assert.equal(run('elements.previewPlay.disabled'),false);run('setPreviewMode("edit")');assert.equal(run('elements.playButton.disabled'),true);});
for(const kind of ['video','audio','text','disabled','source'])test('restoring '+kind+' content restores empty-timeline Play readiness',()=>{const {run}=groups();run('editorProject=()=>state.project;trackClips=()=>[];globalThis.savedMedia=state.project.manual.media_clips;globalThis.savedText=state.project.manual.text_clips;state.project.manual.media_clips=[];state.project.manual.text_clips=[];state.preview.mode="edit";renderPreviewAvailability();');run(kind==='text'?'state.project.manual.text_clips=savedText':kind==='source'?'trackClips=()=>[{start:0,end:6}]':`state.project.manual.media_clips=[savedMedia[${kind==='audio'?1:0}]]`);run('renderPreviewAvailability()');assert.equal(run('elements.playButton.disabled'),false);assert.equal(run('elements.previewPlay.disabled'),false);assert.equal(run('elements.restartPreview.disabled'),false);});
test('non-sequence playback readiness does not gain new empty-edit restrictions',()=>{const {run}=groups();run('state.project.editor_sequence=null;renderPreviewAvailability()');assert.equal(run('elements.playButton.disabled'),undefined);});

test('explicit Chroma save-state callback refreshes main and group Remove immediately without rerendering',()=>{const {run}=groups();run('state.layerGroupPanel=document.getElementById("groups");state.chromaStudio={projectId:"p",pendingDrafts:()=>[{slot:"A",issue:"Apply Chroma draft first"}]};renderProjectSaveState();');assert.equal(run('elements.manualDelete.disabled'),true);assert.match(run('elements.manualDelete.title'),/Chroma draft/);assert.equal(run('state.layerGroupPanel.querySelector("[data-group-remove]").disabled'),true);assert.match(run('state.layerGroupPanel.querySelector("#layerGroupStatus").textContent'),/Chroma draft/);assert.equal(run('renderCount'),0);run('state.chromaStudio.pendingDrafts=()=>[];renderProjectSaveState();');assert.equal(run('elements.manualDelete.disabled'),false);assert.equal(run('state.layerGroupPanel.querySelector("[data-group-remove]").disabled'),false);assert.equal(run('requests.length'),0);});
test('caption save-state changes disable and recover grouped Remove without another project render',()=>{const {run}=groups();run('state.captionDirty=true;renderProjectSaveState();');assert.equal(run('elements.manualDelete.disabled'),true);assert.match(run('elements.manualDelete.title'),/caption/);run('state.captionDirty=false;renderProjectSaveState();');assert.equal(run('elements.manualDelete.disabled'),false);assert.equal(run('requests.length'),0);});
