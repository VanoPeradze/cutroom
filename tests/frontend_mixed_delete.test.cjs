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

function mixed() {
 const h=app();h.run(`state.project.assets={v:{kind:'video',status:'ready'},a:{kind:'audio',status:'ready'},i:{kind:'image',status:'ready'}};
 state.project.manual.media_clips=[{id:'media_1',asset_id:'v',start:1,end:5,motion:'none',fade_in:.2,fade_out:.2}];
 state.project.manual.text_clips=[{id:'text_1',start:1,end:5}];
 state.manualSelection={start:2,end:4};state.editTarget='edit';
 state.mediaStudio={flush:async()=>true};`);return h;
}
test('Together readiness supports static video, music, images and text without mutating them',()=>{
 const {run}=mixed();run(`state.project.manual.media_clips.push(...['a','i'].map(asset_id=>({asset_id,start:1,end:5,motion:'none',fade_in:0,fade_out:0})));globalThis.before=JSON.stringify(state.project);`);
 assert.equal(run(`rangeDeleteIssue(2,4,'edit')`),'');assert.equal(run(`JSON.stringify(state.project)===before`),true);
});
for(const [patch,reason] of [[{motion:'pan'},/pan\/zoom/],[{motion:'zoom_in'},/pan\/zoom/],[{fade_in:1.1},/fade/],[{fade_out:1.1},/fade/],[{start:1.921},/shorter/],[{end:4.079},/shorter/]])test(`partial retained effects/fragments rejected: ${JSON.stringify(patch)}`,()=>{
 const {run}=mixed();run(`Object.assign(state.project.manual.media_clips[0],${JSON.stringify(patch)})`);assert.match(run(`rangeDeleteIssue(2,4,'edit')`),reason);
 assert.equal(run(`rangeDeleteIssue(2,4,'A')`),'','source-only semantics remain independent');
});
test('full animated/faded occurrence removal and downstream movement do not need effect approximation',()=>{
 const {run}=mixed();run(`Object.assign(state.project.manual.media_clips[0],{start:2,end:4,motion:'pan',fade_in:1,fade_out:1});state.project.manual.media_clips.push({asset_id:'i',start:4,end:6,motion:'zoom_in'});`);
 assert.equal(run(`rangeDeleteIssue(2,4,'edit')`),'');
});
test('exact .08 retained fragments and fade boundaries pass; capacities count split pieces',()=>{
 const {run}=mixed();run(`Object.assign(state.project.manual.media_clips[0],{start:1.92,end:4.08,fade_in:.08,fade_out:.08});state.project.manual.text_clips=[{start:1.92,end:4.08}];`);
 assert.equal(run(`rangeDeleteIssue(2,4,'edit')`),'');
 run(`state.project.manual.media_clips=Array.from({length:200},()=>({asset_id:'v',start:1,end:5}));`);assert.match(run(`rangeDeleteIssue(2,4)`),/200 media/);
 run(`state.project.manual.media_clips=[];state.project.manual.text_clips=Array.from({length:2000},()=>({start:1,end:5}));`);assert.match(run(`rangeDeleteIssue(2,4)`),/2000 text/);
});
test('timed plans, edited captions, asset readiness and affected locks are explicitly gated',()=>{
 for(const [change,reason] of [[`state.project.draft.audio_plan=[{}]`,/audio plan/],[`state.project.caption_alternative_status={active_id:'other'}`,/alternative/],[`state.project.manual.caption_dormant_overrides={old:{}}`,/uncertain/],[`state.project.manual.caption_overrides={unknown:{}}`,/owner/],[`state.project.manual.caption_overrides={c:{start_delta:.2}};state.project.editor_captions=[{id:'c',start:0,end:1}]`,/custom timing/],[`state.project.manual.caption_overrides={c:{text:'Mine'}};state.project.editor_captions=[{id:'c',start:2.2,end:2.5}]`,/overlaps/],[`state.project.assets.v.status='failed'`,/not ready/],[`state.project.manual.track_locks={A:true}`,/locked/]]){
  const {run}=mixed();run(change);assert.match(run(`rangeDeleteIssue(2,4)`),reason);
 }
 const {run}=mixed();run(`state.project.manual.caption_overrides={c:{text:'Mine'}};state.project.editor_captions=[{id:'c',start:4,end:5}];`);assert.equal(run(`rangeDeleteIssue(2,4)`),'');
});
test('legacy/source-only behavior is not silently replaced by the new mixed-layer policy',()=>{
 const {run}=mixed();run(`state.project.manual.media_clips=[];state.project.manual.text_clips=[];state.project.draft.audio_plan=[{}];`);assert.equal(run(`rangeDeleteIssue(2,4)`),'');
 run(`state.project.editor_sequence=null;state.project.manual.media_clips=[{motion:'pan',start:1,end:5}];`);assert.equal(run(`rangeDeleteIssue(2,4)`),'');
});
test('native range action saves pending layers then submits one revision-bound sequence_ripple_delete',async()=>{
 const {run}=mixed();run(`globalThis.mediaFlushes=0;state.mediaStudio.flush=async()=>{mediaFlushes++;return true;};`);
 await run(`runManualRangeEdit('delete_range','edit')`);
 assert.equal(run('requests.length'),1);assert.equal(run('mediaFlushes'),1);assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_ripple_delete',start:2,end:4,expected_revision:7});
 assert.equal(run('state.manualSelection'),null);assert.equal(run('state.manualEditBusy'),false);
});
test('all native Together callers reject unsupported retained motion before any edit request',async()=>{
 const {run}=mixed();run(`state.project.manual.media_clips[0].motion='pan';`);
 assert.equal(await run(`applyManualEdit('sequence_ripple_delete',{start:2,end:4})`),null);assert.equal(run('requests.length'),0);assert.match(run('messages.at(-1)'),/pan\/zoom/);
});
test('range geometry changed by layer-save cannot silently cut stale time',async()=>{
 const {run}=mixed();run(`state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].start=1.5;state.project.revision++;return true;};`);
 assert.equal(await run(`applyManualEdit('sequence_ripple_delete',{start:2,end:4})`),null);assert.equal(run('requests.length'),0);assert.match(run('messages.at(-1)'),/changed while saving/);assert.equal(run('state.manualSelection'),null);
});
test('late protected audio-plan state is rechecked after flushing settings, and navigation cancels',async()=>{
 const h=mixed();h.run(`flushProjectSaves=async()=>{state.project.draft.audio_plan=[{}];};`);
 assert.equal(await h.run(`applyManualEdit('sequence_ripple_delete',{start:2,end:4})`),null);assert.equal(h.run('requests.length'),0);assert.match(h.run('messages.at(-1)'),/audio plan/);
 const x=mixed();x.run(`state.mediaStudio.flush=async()=>{state.project={...state.project,id:'elsewhere'};return true;};`);
 assert.equal(await x.run(`applyManualEdit('sequence_ripple_delete',{start:2,end:4})`),null);assert.equal(x.run('requests.length'),0);
});
test('revision conflict fetches latest once and never replays stale range removal',async()=>{
 const {run}=mixed();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:9}};};`);
 assert.equal(await run(`applyManualEdit('sequence_ripple_delete',{start:2,end:4})`),null);assert.equal(run('requests.length'),2);assert.equal(run(`requests.filter(r=>r.options?.method==='POST').length`),1);assert.equal(run('state.project.revision'),9);assert.match(run('messages.at(-1)'),/changed elsewhere/);
});
test('native buttons expose the same issue while source-only removal remains available',()=>{
 const {run,nodes}=mixed();run(`state.project.manual.media_clips[0].motion='pan';realRenderManualControls();`);
 assert.equal(nodes.get('manualDelete').disabled,true);assert.match(nodes.get('manualDelete').title,/pan\/zoom/);
 run(`state.editTarget='A';realRenderManualControls();`);assert.equal(nodes.get('manualDelete').disabled,false);assert.match(nodes.get('manualDelete').title,/other tracks and added layers stay still/);
});


test('impact wrapper explains existing busy, short-range and source-lock states without changing source-only policy',()=>{
 const {run}=mixed();run(`state.manualEditBusy=true;`);assert.match(run(`rangeDeletePreviewIssue(2,4,'A')`),/Wait/);
 run(`state.manualEditBusy=false;`);assert.match(run(`rangeDeletePreviewIssue(2,2.001,'edit')`),/one output frame/);
 run(`state.trackProtection={lockedNames:()=>['A']};`);assert.match(run(`rangeDeletePreviewIssue(2,4,'A')`),/locked/);
 assert.equal(run(`rangeDeleteIssue(2,4,'A')`),'');
});

for(const [a,b] of [[2,4],[.5,2],[4,5.5]])test('Whole-edit Cut out preflight blocks any partially retained Chapter: '+a+'-'+b,async()=>{
 const {run}=mixed();run(`state.project.manual.media_clips=[];state.project.manual.text_clips[0].template='chapter';state.manualSelection={start:${a},end:${b}};`);
 for(const enabled of [true,false]){
   run(`state.project.manual.text_clips[0].enabled=${enabled}`);assert.match(run(`rangeDeleteIssue(${a},${b},'edit')`),/fade.*Chapter/i);
   assert.match(run(`rangeDeletePreviewIssue(${a},${b},'edit')`),/Chapter/i);
   assert.equal(run(`rangeDeleteIssue(${a},${b},'A')`),'','source-only removal never ripples text');
   assert.equal(await run(`applyManualEdit('sequence_ripple_delete',{start:${a},end:${b}})`),null);assert.equal(run('requests.length'),0);
 }
});
test('Deleting an entire Chapter or shifting it as one intact clip is not blocked',()=>{
 const {run}=mixed();run(`state.project.manual.media_clips=[];Object.assign(state.project.manual.text_clips[0],{start:2,end:4,template:'chapter'});`);
 for(const [a,b] of [[1,2],[4,5],[2,4],[1,5]])assert.equal(run(`rangeDeleteIssue(${a},${b},'edit')`),'');
});
