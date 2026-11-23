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
 state.project.manual.media_clips=[{id:'media_a',asset_id:'v',start:1,end:3,source_start:1,video_source_start:2,speed:.5,motion:'pan',fade_in:.2,fade_out:.2}];state.project.manual.text_clips=[{id:'text_b',start:1,end:3,text:'Title',style:'boxed',subtext:'Second line'}];
 state.timeline.mediaSelection='media_a';state.timeline.playhead=2.25;globalThis.selected=[];globalThis.mediaFlush=0;globalThis.textFlush=0;
 state.timeline.selectIndexEntry=()=>{throw Error('Do not bypass guarded navigation');};selectTimelineMedia=async id=>{if(state.manualEditBusy)throw Error('Selection before save finished');selected.push(id);state.timeline.mediaSelection=id;return true;};
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){}};state.textStudio={flush:async()=>{textFlush++;return true;},render(){}};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});const key=body.action.startsWith('text_')?'text_clips':'media_clips';const rows=state.project.manual[key].map(r=>{if(r.id!==body.clip_id)return r;const changed={...r};if(body.enabled)delete changed.enabled;else changed.enabled=false;return changed;});return {project:{...state.project,revision:state.project.revision+1,manual:{...state.project.manual,[key]:rows}}};};`);return h;}

function framed(){const h=layers();h.run(`Object.assign(state.project.manual.media_clips[0],{x:.1,y:.2,w:.5,h:.6,fit:'contain',volume_db:-3.123456789123});state.mediaStudio.selected='media_a';updateMediaPreview=()=>{globalThis.previewUpdated=(globalThis.previewUpdated||0)+1;};state.timeline.scheduleDraw=()=>{};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});const rows=state.project.manual.media_clips.map(r=>r.id===body.clip_id?{...r,x:body.x,y:body.y,w:body.w,h:body.h}:r);return {project:{...state.project,revision:state.project.revision+1,manual:{...state.project.manual,media_clips:rows}}};};`);return h;}
const rect={x:.123456789,y:.1,w:.4,h:.7};
for(const kind of ['video','image'])test(`${kind} frame action preserves all content fields, ID, selection and edit cursor`,async()=>{
 const {run}=framed();run(`state.project.assets.v.kind='${kind}';globalThis.before=JSON.stringify(state.project);state.trackProtection={lockedNames:()=>['A','B']};`);
 assert.ok(await run(`frameTimelineLayer('media_a',${JSON.stringify(rect)})`));
 const old=JSON.parse(run('before')),now=plain(run('state.project'));
 assert.deepEqual(now.manual.media_clips,[{...old.manual.media_clips[0],...rect}]);
 for(const key of ['sources','assets','settings','editor_sequence'])assert.deepEqual(now[key],old[key]);
 assert.deepEqual(now.manual.text_clips,old.manual.text_clips);assert.equal(run('state.timeline.mediaSelection'),'media_a');assert.equal(run('state.mediaStudio.selected'),'media_a');assert.equal(run('state.timeline.playhead'),2.25);assert.equal(run('selected.length'),0,'do not re-reveal or scroll the inspector');assert.equal(run('seeks.length'),0,'geometry never resets or reseeks the edit clock');assert.equal(run('renderCount'),0,'do not rebuild the draft or media players');assert.equal(run('previewUpdated'),1);
 assert.deepEqual(plain(run('requests[0].body')),{action:'media_transform',clip_id:'media_a',...rect,expected_revision:7});
 assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);
});
// Test values are passed as data into the sandbox, never compiled as a JavaScript expression.
const fullPlan={x:0,y:0,w:1,h:1};
const invalidFramePlans=[
 ['null',null], ['array',[]], ['empty object',{}], ['missing height',{x:0,y:0,w:1}],
 ['unknown enabled field',{...fullPlan,enabled:false}], ['boolean coordinate',{...fullPlan,x:true}],
 ['string coordinate',{...fullPlan,x:'0'}], ['NaN coordinate',{...fullPlan,x:NaN}],
 ['infinite width',{...fullPlan,w:Infinity}], ['negative x',{...fullPlan,x:-.1}],
 ['negative sub-frame x',{...fullPlan,x:-1e-10}], ['just below minimum width',{...fullPlan,w:.00999999999}],
 ['width below minimum',{...fullPlan,w:.001}], ['extends beyond right',{...fullPlan,x:.5}],
 ['extends beyond bottom',{...fullPlan,y:.7,h:.4}],
];
for(const [label,value] of invalidFramePlans)test('canonical frame plan rejects '+label,()=>{
 const{run,context}=framed();context.testFramePlan=value;
 const plan=plain(run("layerFramePlan('media_a',testFramePlan)"));
 assert.ok(plan.issue);assert.equal(plan.patch,null);assert.equal(run('requests.length'),0);
});
for(const setup of ['state.project.editor_sequence.error="Invalid saved sequence"','state.captionDirty=true','state.captionContextSave={}','state.project.draft=null','state.project.assets.v.status="failed"','state.project.assets.v.kind="audio"','delete state.project.assets.v','state.project.manual.media_clips[0].x=NaN'])test(`frame action refuses unsafe state ${setup}`,async()=>{const{run}=framed();run(setup);assert.equal(await run(`frameTimelineLayer('media_a',${JSON.stringify(rect)})`),null);assert.equal(run('requests.length'),0);});
for(const id of ['text_b','A:sequence:0:0','missing','automatic_caption'])test(`frame action never falls through from ${id} to source`,async()=>{const{run}=framed();assert.equal(await run(`frameTimelineLayer('${id}',${JSON.stringify(rect)})`),null);assert.equal(run('requests.length'),0);});
test('frame no-op skips saves and preserves existing redo',async()=>{const{run}=framed();run('state.project.manual.history={redo_count:2};globalThis.before=JSON.stringify(state.project)');assert.ok(await run(`frameTimelineLayer('media_a',{x:.1,y:.2,w:.5,h:.6})`));assert.equal(run('JSON.stringify(state.project)'),run('before'));assert.equal(run('mediaFlush'),0);assert.equal(run('requests.length'),0);});
test('canonical geometry has backend nine-decimal precision and incidental fields are never dropped silently',async()=>{const{run}=framed();assert.deepEqual(plain(run(`layerFramePlan('media_a',{x:.333333333333,y:0,w:.666666666666,h:1})`)),{issue:'',patch:{x:.333333333,y:0,w:.666666667,h:1}});assert.equal(await run(`frameTimelineLayer('media_a',{...${JSON.stringify(rect)},source_start:2})`),null);assert.equal(run('requests.length'),0);});
test('frame action pins selected row, asset, output shape and project across save flush',async()=>{
 for(const setup of ['state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].source_start=2;return true;}','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}','flushProjectSaves=async()=>{state.project.assets.v.name="Changed";}','flushProjectSaves=async()=>{state.project.settings.aspect="9:16";}','state.mediaStudio.flush=async()=>false']){const{run}=framed();run(setup);assert.equal(await run(`frameTimelineLayer('media_a',${JSON.stringify(rect)})`),null);assert.equal(run('requests.length'),0);}
});
test('frame conflict loads latest once without replaying stale geometry',async()=>{const{run}=framed();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12}};};`);assert.equal(await run(`frameTimelineLayer('media_a',${JSON.stringify(rect)})`),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.match(run('messages.at(-1)'),/frame geometry/);});
test('rapid frame commits across common flush dispatch only once',async()=>{const{run}=framed();run(`globalThis.release=null;const wait=new Promise(r=>release=r);state.textStudio.flush=()=>wait;globalThis.first=frameTimelineLayer('media_a',${JSON.stringify(rect)});globalThis.second=frameTimelineLayer('media_a',${JSON.stringify(rect)});release(true);`);await run('Promise.all([first,second])');assert.equal(run('requests.length'),1);});
test('entering viewer edit flushes pending work and rejects project/selection switches',async()=>{
 const{run}=framed();assert.equal(await run('prepareFrameEdit("media_a")'),true);assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);
 for(const setup of ['state.captionDirty=true','state.mediaStudio.selected="another"','state.textStudio.flush=async()=>false','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}']){const{run}=framed();run(setup);assert.equal(await run('prepareFrameEdit("media_a")'),false);assert.equal(run('requests.length'),0);}
});
function mediaClass(){const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,''),context);return vm.runInContext('MediaStudio',context);}
function studio(){
 const value=Object.create(mediaClass().prototype),button={attrs:{},setAttribute(k,v){this.attrs[k]=v;}},note={},clip={id:'media_x',asset_id:'a',start:1,end:4,x:.1,y:.2,w:.5,h:.6,source_start:1,video_source_start:2,speed:.5},project={id:'p',revision:7,draft:{},settings:{aspect:'16:9',fps:30},manual:{media_clips:[clip]},assets:{a:{id:'a',kind:'video',status:'ready',url:'/v',duration:10}}};
 const calls=[],state={time:2,sourceMode:false,busy:false,playing:false,visible:true};
 Object.assign(value,{selected:clip.id,project:()=>project,pending:new Map(),overrides:new Map(),status:{},root:{scrollTop:143,querySelector:s=>s==='[data-transform-viewer]'?button:s==='[data-transform-status]'?note:null},options:{busy:()=>state.busy,time:()=>state.time,sourceMode:()=>state.sourceMode,playing:()=>state.playing,viewerVisible:()=>state.visible,pause:()=>{state.playing=false;calls.push('pause');},preview:()=>calls.push('preview'),framePreview:(id,g)=>({issue:'',patch:{...g}}),frameEdit:async(id,g)=>{calls.push({id,g});Object.assign(clip,g);project.revision++;return project;},prepareFrameEdit:async()=>true},frameEditor:{active:false,pending:false,sync(){calls.push('sync');},open(){this.active=true;return true;},close(){this.active=false;}}});return{value,button,note,clip,project,calls,state};
}
test('viewer snapshot pins saved geometry/context while transient preview never changes token',()=>{const{value,clip,project,state}=studio();const saved=value.frameSnapshot();assert.equal(saved.issue,'');assert.equal(saved.busy,false);value.previewFrame(clip.id,rect);assert.equal(value.frameSnapshot().token,saved.token);assert.deepEqual(plain(value.frameSnapshot().rect),{x:.1,y:.2,w:.5,h:.6});assert.deepEqual(plain(value.clips()[0]),{...clip,...rect});
 for(const change of [()=>project.revision++,()=>{project.settings.aspect='9:16';},()=>{clip.source_start++;},()=>{project.assets.a.url='/changed';},()=>{state.time=2.5;}]){const before=value.frameSnapshot().token;change();assert.notEqual(value.frameSnapshot().token,before);}
});
for(const change of ['sourceMode','playing','off','inactive','end','audio','unready','hidden','missing'])test(`viewer context clearly refuses ${change}`,()=>{const{value,clip,project,state,button}=studio();if(change==='sourceMode')state.sourceMode=true;else if(change==='playing')state.playing=true;else if(change==='off')clip.enabled=false;else if(change==='inactive')state.time=0;else if(change==='end')state.time=4;else if(change==='audio')project.assets.a.kind='audio';else if(change==='unready')project.assets.a.status='failed';else if(change==='hidden')state.visible=false;else value.selected='missing';assert.ok(value.frameSnapshot().issue);value.updateFrameEditorButton();assert.equal(button.disabled,true);});
test('preview/cancel preserves independent numeric pending overrides and saved source data',()=>{const{value,clip,project,calls}=studio(),before=JSON.stringify(project);value.overrides.set(clip.id,{x:.25,volume_db:-8});value.pending.set(clip.id,{x:.25,volume_db:-8});assert.ok(value.previewFrame(clip.id,rect).issue,'pending field must block beginning a frame preview');value.pending.clear();assert.equal(value.previewFrame(clip.id,rect).issue,'');assert.equal(value.clips()[0].x,rect.x);value.previewFrame(clip.id,null);assert.equal(value.clips()[0].x,.25);assert.equal(value.clips()[0].volume_db,-8);assert.equal(value.overrides.size,1);assert.equal(JSON.stringify(project),before);assert.deepEqual(calls,['preview','preview']);});
test('frame commit rechecks token and clears only its transient layer after success/failure',async()=>{const{value,clip,project,calls}=studio();let token=value.frameSnapshot().token;value.previewFrame(clip.id,rect);assert.ok(await value.commitFrame(clip.id,rect,token));assert.equal(value.frameOverride,null);assert.equal(clip.x,rect.x);assert.equal(calls.filter(x=>typeof x==='object').length,1);token=value.frameSnapshot().token;value.previewFrame(clip.id,{...rect,x:.2});project.revision++;assert.equal(await value.commitFrame(clip.id,rect,token),null);assert.equal(value.frameOverride,null);assert.equal(calls.filter(x=>typeof x==='object').length,1);
 token=value.frameSnapshot().token;value.previewFrame(clip.id,{...rect,x:.2});value.options.frameEdit=async()=>{throw Error('synthetic save failed');};await assert.rejects(value.commitFrame(clip.id,rect,token),/synthetic save/);assert.equal(value.frameOverride,null);
});
test('viewer entry waits for preparation and cancels if selection changes while awaiting it',async()=>{const{value,button}=studio();let release;value.options.prepareFrameEdit=()=>new Promise(r=>release=r);const opening=value.toggleFrameEditor();assert.equal(button.disabled,true);assert.equal(await value.toggleFrameEditor(),false);value.selected='other';release(true);assert.equal(await opening,false);assert.equal(value.frameEditor.active,false);assert.equal(value.startingFrameEdit,false);});
test('viewer button tracks saved readiness without rebuilding or resetting inspector scroll',async()=>{const{value,button,note,state}=studio();value.updateFrameEditorButton();assert.equal(button.disabled,false);assert.equal(button.attrs['aria-pressed'],'false');assert.ok(await value.toggleFrameEditor());value.updateFrameEditorButton();assert.equal(button.attrs['aria-pressed'],'true');assert.match(note.textContent,/keyboard editing/);value.frameEditorState={active:true,issue:'The viewer size changed; drag again.'};value.updateFrameEditorButton();assert.equal(note.textContent,'The viewer size changed; drag again.');value.frameEditorState={active:true,issue:''};value.frameEditor.pending=true;value.updateFrameEditorButton();assert.equal(button.disabled,true);value.frameEditor.pending=false;await value.toggleFrameEditor();assert.equal(value.frameEditor.active,false);assert.equal(value.root.scrollTop,143);state.busy=true;value.updateFrameEditorButton();assert.equal(button.disabled,true);});
test('old inspector hosts without viewer factory preserve their original contract',()=>{const value=Object.create(mediaClass().prototype);value.options={};assert.doesNotThrow(()=>value.updateFrameEditorButton());assert.doesNotThrow(()=>value.syncFrameEditor());});
test('all four geometry fields accept exact fractions with explicit one-percent scrub/arrow steps',()=>{const source=fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8');for(const key of ['x','y','w','h'])assert.match(source,new RegExp('data-media="'+key+'"[^>]*step="any" data-scrub-step="1"'));assert.match(source,/Number\(\(Number\(clip\[key\].*\.toFixed\(7\)/);});


test('history frame sync sees restored cursor rather than intermediate renderer zero',async()=>{
 const{run}=framed();run(`globalThis.holding=false;globalThis.observed=[];state.mediaStudio.deferFrameSync=fn=>{holding=true;try{return fn();}finally{holding=false;observed.push(state.timeline.playhead);}};renderDraft=()=>{state.timeline.playhead=0;if(!holding)throw Error('transient cursor leaked');};seekSourcePreview=time=>{seeks.push(time);state.timeline.playhead=time;};api=async(url,options)=>({project:{...state.project,revision:state.project.revision+1}});`);
 assert.ok(await run(`applyManualEdit('undo')`));assert.deepEqual(plain(run('observed')),[2.25]);assert.equal(run('holding'),false);
});
test('synchronous history coalescing restores frame updates after success, nesting and exceptions',()=>{
 const{value,calls}=studio();value.deferFrameSync(()=>{value.syncFrameEditor();value.deferFrameSync(()=>value.syncFrameEditor());assert.equal(calls.length,0);});assert.deepEqual(calls,['sync']);
 assert.throws(()=>value.deferFrameSync(()=>{value.syncFrameEditor();throw Error('render failure');}),/render failure/);assert.equal(value.frameSyncDepth,0);assert.deepEqual(calls,['sync','sync']);
});


test('empty media flush does not manufacture a saving paint or disable available controls',async()=>{
 const{value,calls}=studio();value.render=()=>{throw Error('Empty flush must not repaint');};value.updateImportAvailability=()=>{throw Error('Empty flush must not mutate controls');};
 assert.equal(await value.flush(),true);assert.equal(value.saving,undefined);assert.equal(value.status.textContent,undefined);assert.equal(calls.length,0);
});
for(const success of [true,false])test(`real media flush clears stale disabled controls after ${success?'success':'failure'} without another render`,async()=>{
 const{value,clip}=studio(),input={},notes={},query=value.root.querySelector,states=[];let renders=0;
 value.root.querySelector=selector=>selector==='[data-media-enabled]'?input:selector==='[data-media-enabled-note]'?notes:query(selector);
 value.options.enabledPreview=(id,enabled)=>({issue:'',patch:{enabled}});
 value.options.edit=async()=>success?value.project():null;
 value.pending.set(clip.id,{volume_db:-8});value.overrides.set(clip.id,{volume_db:-8});
 value.updateImportAvailability=()=>{value.updateEnabledAvailability();states.push({saving:Boolean(value.saving),disabled:input.disabled});};
 value.render=()=>{renders++;value.updateImportAvailability();};
 assert.equal(await value.flush(),success);clearTimeout(value.savedTimer);
 assert.equal(value.saving,null);assert.equal(input.disabled,false);assert.equal(value.pending.size,0);assert.equal(value.overrides.size,0);assert.equal(renders,1);
 assert.deepEqual(states,[{saving:true,disabled:true},{saving:false,disabled:false}]);assert.equal(value.root.scrollTop,143);
});
