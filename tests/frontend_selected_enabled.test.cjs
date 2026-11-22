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
for(const id of ['media_a','text_b'])test(`disable/re-enable ${id} preserves content, ID, playhead, source and selection`,async()=>{
 const {run}=layers();run(`state.timeline.mediaSelection='${id}';state.trackProtection={lockedNames:()=>['A','B']};globalThis.before=JSON.stringify(state.project);`);
 const key=id.startsWith('text_')?'text_clips':'media_clips',action=id.startsWith('text_')?'text_set_enabled':'media_set_enabled';assert.ok(await run(`setTimelineLayerEnabled('${id}',false)`));assert.deepEqual(plain(run('requests[0].body')),{action,clip_id:id,enabled:false,expected_revision:7});
 const old=JSON.parse(run('before')),after=plain(run('state.project'));assert.deepEqual(after.manual[key][0],{...old.manual[key][0],enabled:false});assert.deepEqual(after.sources,old.sources);assert.deepEqual(after.assets,old.assets);assert.deepEqual(after.editor_sequence,old.editor_sequence);assert.deepEqual(plain(run('selected')),[id]);assert.equal(run('seeks.at(-1)'),2.25);
 assert.ok(await run(`setTimelineLayerEnabled('${id}',true)`));assert.deepEqual(plain(run(`state.project.manual.${key}`)),old.manual[key]);assert.equal(run('requests.length'),2);assert.equal(run('mediaFlush'),2);assert.equal(run('textFlush'),2);
});
for(const enabled of ['null','0','1',"'false'",'undefined','[]'])test(`enabled ${enabled} rejects rather than coercing`,async()=>{const {run}=layers();assert.equal(await run(`setTimelineLayerEnabled('media_a',${enabled})`),null);assert.equal(run('requests.length'),0);});
for(const id of ['A:sequence:0:0','automatic_caption','text_missing','media_missing'])test(`missing/unsupported ${id} never disables underlying source`,async()=>{const {run}=layers();assert.equal(await run(`setTimelineLayerEnabled('${id}',false)`),null);assert.equal(run('requests.length'),0);});
test('legacy enabled default and repeated saved state are no-ops before flush/history',async()=>{
 const {run}=layers();assert.deepEqual(plain(run('layerEnabledPlan("media_a",true)')),{issue:'',patch:{}});assert.ok(await run('setTimelineLayerEnabled("media_a",true)'));run('state.project.manual.media_clips[0].enabled=false');assert.ok(await run('setTimelineLayerEnabled("media_a",false)'));assert.equal(run('requests.length'),0);assert.equal(run('mediaFlush'),0);assert.equal(run('textFlush'),0);
});
test('unready occurrence may be disabled but enabling must wait for asset preparation',async()=>{
 const {run}=layers();run('state.project.assets.v.status="failed"');assert.ok(await run('setTimelineLayerEnabled("media_a",false)'));assert.equal(run('state.project.manual.media_clips[0].enabled'),false);assert.equal(await run('setTimelineLayerEnabled("media_a",true)'),null);assert.equal(run('requests.length'),1);assert.match(run('messages.at(-1)'),/before enabling/);
});
for(const setup of ['state.captionDirty=true','state.captionContextSave={}','state.project.manual.media_clips[0].enabled="false"','state.project.draft=null'])test(`enabled change blocks unsafe state ${setup}`,async()=>{const {run}=layers();run(setup);assert.equal(await run('setTimelineLayerEnabled("media_a",false)'),null);assert.equal(run('requests.length'),0);});
test('selected content/asset/project changes during flush cancel stale enable action',async()=>{
 for(const setup of ['state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].source_start=2;return true;}','state.textStudio.flush=async()=>{state.project={...state.project,id:"other"};return true;}','flushProjectSaves=async()=>{state.project.assets.v.name="Other";}','state.mediaStudio.flush=async()=>false']){const {run}=layers();run(setup);assert.equal(await run('setTimelineLayerEnabled("media_a",false)'),null);assert.equal(run('requests.length'),0);}
});
test('revision conflict loads latest once without retrying old enabled state',async()=>{
 const {run}=layers();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12}};};`);assert.equal(await run('setTimelineLayerEnabled("media_a",false)'),null);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('selected.length'),0);assert.match(run('messages.at(-1)'),/review the clip availability/);
});
test('rapid common-flush enabled commands dispatch once',async()=>{const {run}=layers();run('globalThis.release=null;const wait=new Promise(r=>release=r);state.textStudio.flush=()=>wait;globalThis.first=setTimelineLayerEnabled("media_a",false);globalThis.second=setTimelineLayerEnabled("media_a",false);release(true);');await run('Promise.all([first,second])');assert.equal(run('requests.length'),1);});
function classes(globals={}){const context=vm.createContext({window:{},document:{},performance:{now:()=>0},setTimeout,clearTimeout,...globals});for(const file of ['media-studio.js','text-studio.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,''),context);vm.runInContext('globalThis.api={MediaStudio,TextStudio,clipEnvelope,mediaGain,libraryVideoAt};',context);return context.api;}
function studio(kind){const api=classes(),Class=kind==='media'?api.MediaStudio:api.TextStudio,value=Object.create(Class.prototype),input={},note={},clip={id:kind+'_a',start:1,end:3};let pid='p',busy=false;
 Object.assign(value,{selected:clip.id,clips:()=>[clip],pending:new Map(),project:()=>({id:pid}),status:{},root:{scrollTop:143,querySelector:s=>s===`[data-${kind}-enabled]`?input:s===`[data-${kind}-enabled-note]`?note:null},options:{busy:()=>busy,enabledPreview:(id,enabled)=>({issue:'',patch:{enabled}})},render(){throw Error('Do not repaint');}});return{value,input,note,clip,setPid:p=>pid=p,setBusy:v=>busy=v};}
for(const kind of ['media','text']){
 test(`${kind} enabled switch reflects saved state, busy/pending readiness and accessible off explanation`,()=>{const{value,input,note,clip,setBusy}=studio(kind);value.updateEnabledAvailability();assert.equal(input.checked,true);assert.equal(input.disabled,false);clip.enabled=false;value.updateEnabledAvailability();assert.equal(input.checked,false);assert.match(note.textContent,/Disabled in preview and export/);value.pending.set('a',{});value.updateEnabledAvailability();assert.equal(input.disabled,true);value.pending.clear();setBusy(true);value.updateEnabledAvailability();assert.equal(input.disabled,true);setBusy(false);value.updateEnabledAvailability();assert.equal(input.disabled,false);assert.equal(value.root.scrollTop,143);});
 test(`${kind} switch pins intended bool/ID, blocks repeated clicks and reflects only confirmed result`,async()=>{const {value,input,clip}=studio(kind),calls=[];let release;value.options.setEnabled=(...args)=>{calls.push(args);return new Promise(r=>release=r);};const saving=value.setOccurrenceEnabled(false);assert.equal(input.checked,true);assert.equal(input.disabled,true);assert.equal(await value.setOccurrenceEnabled(true),null);clip.enabled=false;release('saved');assert.equal(await saving,'saved');assert.deepEqual(calls,[[kind+'_a',false]]);assert.equal(input.checked,false);assert.equal(input.disabled,false);});
 test(`${kind} failed toggle resets switch and old project error cannot overwrite new status`,async()=>{const{value,input,setPid}=studio(kind);let reject;value.options.setEnabled=()=>new Promise((_,r)=>reject=r);value.status.textContent='New project';const saving=value.setOccurrenceEnabled(false);setPid('other');reject(Error('Old failure'));assert.equal(await saving,null);assert.equal(value.status.textContent,'New project');assert.equal(input.checked,true);assert.equal(input.disabled,false);});
 test(`${kind} host without enabled callback retains old contract`,()=>{const api=classes(),value=Object.create((kind==='media'?api.MediaStudio:api.TextStudio).prototype);value.options={};assert.doesNotThrow(()=>value.updateEnabledAvailability());});
}
test('disabled source sound contributes neither envelope/gain nor active normalization channel',()=>{
 const {MediaStudio,clipEnvelope,mediaGain}=classes(),clip={id:'m',asset_id:'a',enabled:false,start:0,end:3,role:'voice',audio_enabled:true,volume_db:0};assert.equal(clipEnvelope(clip,1),0);assert.equal(mediaGain(clip,{},1),0);const s=Object.create(MediaStudio.prototype);Object.assign(s,{options:{},project:()=>({assets:{a:{kind:'video',has_audio:true}}}),clips:()=>[clip],mixer:()=>({})});assert.deepEqual([...s.audibleChannels()],[]);delete clip.enabled;assert.deepEqual([...s.audibleChannels()],['voice']);
});
test('disabled top library video is never chosen as active content fallback',()=>{
 const {libraryVideoAt}=classes(),p={assets:{a:{kind:'video',status:'ready'}},manual:{media_clips:[{id:'one',asset_id:'a',start:0,end:3},{id:'two',asset_id:'a',start:0,end:3,enabled:false}]}};assert.equal(libraryVideoAt(p,1).id,'one');p.manual.media_clips[0].enabled=false;assert.equal(libraryVideoAt(p,1),null);assert.equal(libraryVideoAt(p),null);p.manual.media_clips.push(null);assert.equal(libraryVideoAt(p),null,'malformed rows keep the prior harmless fallback behavior');
});
test('disabling active media releases picture/sound/chroma and re-enable keeps independent clocks',()=>{
 const{MediaStudio}=classes(),s=Object.create(MediaStudio.prototype),clip={id:'m',asset_id:'a',start:1,end:4,source_start:1,video_source_start:2,speed:.5,audio_enabled:true,role:'voice',x:0,y:0,w:1,h:1},project={assets:{a:{kind:'video',status:'ready',url:'/video',duration:9,has_audio:true}},manual:{media_clips:[clip]}};const created=[],calls=[];
 Object.assign(s,{players:new Map(),pending:new Map(),options:{},project:()=>project,clips:()=>[clip],mixer:()=>({}),player(key){let item=this.players.get(key);if(!item){const element={style:{},pause(){this.paused=true;},removeAttribute(){this.cleared=true;},load(){},remove(){this.removed=true;}},frame={style:{},remove(){this.removed=true;}};item={key,element,frame,token:0,wanted:true,chroma:{dispose(){this.disposed=true;}}};this.players.set(key,item);created.push(item);}return item;},syncPlayer(item,time,rate,playing){calls.push({key:item.key,time,rate,playing});},updateMeters(){}});
 s.sync(2,true);assert.equal(s.players.size,2);assert.equal(calls.find(x=>x.key==='v:m').time,2.5);assert.equal(calls.find(x=>x.key==='a:m').time,2);clip.enabled=false;calls.length=0;s.sync(2,true);assert.equal(s.players.size,0);assert.equal(calls.length,0);assert.ok(created.every(i=>i.element.paused&&i.frame.removed&&i.chroma.disposed&&!i.wanted&&i.token===1));delete clip.enabled;s.sync(2,true);assert.equal(s.players.size,2);assert.equal(calls.find(x=>x.key==='v:m').rate,.5);assert.equal(calls.find(x=>x.key==='a:m').rate,1);
});
test('release on disable invalidates an unresolved play promise so old audio cannot restart',async()=>{
 const{MediaStudio}=classes(),s=Object.create(MediaStudio.prototype);let resolve;const element={paused:true,currentTime:0,play(){return new Promise(r=>resolve=r);},pause(){this.paused=true;this.pauses=(this.pauses||0)+1;},removeAttribute(){},load(){},remove(){}};const item={element,token:0};Object.assign(s,{players:new Map([['a:m',item]]),mixer:()=>({})});s.syncPlayer(item,1,1,true,1);s.releasePlayer('a:m',item);element.paused=false;resolve();await new Promise(setImmediate);assert.equal(element.paused,true);assert.equal(item.wanted,false);assert.equal(s.players.size,0);
});
test('custom text preview filters only disabled occurrences and restores original styling without editing data',()=>{
 function node(){return{children:[],style:{setProperty(){}},dataset:{},append(...v){this.children.push(...v);},prepend(...v){this.children.unshift(...v);},replaceChildren(...v){this.children=v;}};}const{TextStudio}=classes({document:{createElement:()=>node()}}),s=Object.create(TextStudio.prototype),clips=[{id:'text_a',kind:'title',text:'Title',start:0,end:3,position:'center',style:'boxed',scale:100,template:'lower_third',subtext:'Second line'},{id:'text_b',kind:'caption',text:'Caption',start:0,end:3,position:'bottom',style:'clean',scale:100,enabled:false}],layer=node();
 Object.assign(s,{options:{dimensions:()=>[160,90]},project:()=>({draft:{}}),clips:()=>clips,layer,stage:{clientHeight:90,getBoundingClientRect:()=>({height:90})}});s.sync(1);assert.equal(layer.children.length,1);assert.equal(layer.children[0].children[0].textContent,'Title');clips[0].enabled=false;s.sync(1);assert.equal(layer.hidden,true);assert.equal(layer.children.length,0);delete clips[0].enabled;delete clips[1].enabled;s.sync(1);assert.equal(layer.hidden,false);assert.equal(layer.children.length,2);assert.equal(layer.children[0].dataset.template,'lower_third');assert.equal(layer.children[0].children[1].textContent,'Second line');assert.equal(clips.length,2);
});


test('retained disabled media or custom text does not become an empty editor',()=>{
 const {run}=layers();run(`state.project.editor_sequence.source_tracks={A:[],B:[]};state.project.manual.media_clips=[];state.project.manual.text_clips=[];state.mediaStudio.videoAt=()=>null;`);
 assert.equal(run('hasTimelineFootage()'),false,'pool assets alone are not an edit');
 for(const kind of ['video','image','audio']){
  run(`state.project.assets.v.kind='${kind}';state.project.manual.media_clips=[{id:'media_retained',asset_id:'v',start:1,end:3,enabled:false}];`);
  assert.equal(run('hasTimelineFootage()'),true,kind+' remains editable, playable and exportable');
 }
 run(`state.project.manual.media_clips=[];state.project.manual.text_clips=[{id:'text_retained',start:1,end:3,text:'Title',enabled:false}];`);
 assert.equal(run('hasTimelineFootage()'),true,'off custom text still belongs to the saved edit');
 run('state.project.manual.text_clips=[]');assert.equal(run('hasTimelineFootage()'),false);
 run(`state.project.editor_sequence.source_tracks.A=[{id:'a',start:0,end:1,source_start:0}];`);assert.equal(run('hasTimelineFootage()'),true);
 run('delete state.project.editor_sequence');assert.equal(run('hasTimelineFootage()'),true,'legacy draft behavior stays intact');
 run('state.project.draft=null');assert.equal(run('hasTimelineFootage()'),false);
});
