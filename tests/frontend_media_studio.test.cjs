const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function load(globals = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../web/media-studio.js'), 'utf8').replace(/^export /gm, '');
  const context = vm.createContext({window: {}, document: {}, FormData: class {append() {}}, performance: {now: () => 1000}, setTimeout: () => 1, clearTimeout() {}, ...globals});
  vm.runInContext(source + '\nglobalThis.api = {MediaStudio, clipEnvelope, mediaGain, libraryVideoAt};', context);
  return context.api;
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
}

function studioHarness(edit, globals) {
  const {MediaStudio} = load(globals);
  let project = {id:'one', manual:{media_clips:[]}};
  const studio = Object.create(MediaStudio.prototype);
  Object.assign(studio, {
    options: {project: () => project, edit, preview() {}, pause() {}, busy: () => false},
    selected:null, pending:new Map(), overrides:new Map(), players:new Map(), saving:null,
    status:{textContent:''}, render() {}, renderMixer() {},
  });
  return {studio, activate(next) {project = next;}};
}

function appendProject(overrides = {}) {
  return {id:'one', draft:{engine:'manual'}, assets:{video:{id:'video',kind:'video',status:'ready',duration:3}},
    manual:{media_clips:[]}, ...overrides};
}

test('append waits for saves, uses the native append action and selects the returned occurrence', async () => {
  const gate = deferred(), calls = [];
  let saved = appendProject();
  const {studio,activate} = studioHarness(async(action,payload)=>{
    calls.push({action,payload});
    saved = {...saved,manual:{media_clips:[...saved.manual.media_clips,{id:`occurrence-${calls.length}`,asset_id:'video'}]}};
    activate(saved);return saved;
  });
  activate(saved);
  let paused = 0, rendered = 0;
  studio.options.pause = ()=>paused++;
  studio.render = ()=>rendered++;
  studio.flush = ()=>gate.promise;
  const first = studio.append('video');
  assert.equal(paused,1);assert.equal(calls.length,0,'saving must finish before the append request');
  gate.resolve(true);await first;
  assert.deepEqual(JSON.parse(JSON.stringify(calls)),[{action:'media_append',payload:{asset_id:'video'}}]);
  assert.equal(studio.selected,'occurrence-1');assert.equal(rendered,1);
  await studio.append('video');
  assert.equal(calls.length,2);assert.equal(studio.selected,'occurrence-2');
  assert.equal(saved.manual.media_clips[0].asset_id,saved.manual.media_clips[1].asset_id);
  assert.notEqual(saved.manual.media_clips[0].id,saved.manual.media_clips[1].id,'repeated Append selects independent backend occurrences');
});

test('append refuses busy imports, missing drafts and assets that are not ready videos', async () => {
  for (const state of ['busy','uploading','no-draft','missing','audio','preparing','failed']) {
    let edits = 0, paused = 0, saves = 0;
    const {studio,activate} = studioHarness(async()=>{edits++;});
    const project = appendProject();
    if (state === 'no-draft') project.draft = null;
    if (state === 'missing') project.assets = {};
    if (state === 'audio') project.assets.video.kind = 'audio';
    if (['preparing','failed'].includes(state)) project.assets.video.status = state;
    activate(project);
    studio.uploading = state === 'uploading';
    studio.options.busy = ()=>state === 'busy';
    studio.options.pause = ()=>paused++;
    studio.flush = async()=>{saves++;return true;};
    await studio.append('video');
    assert.equal(edits,0,state);assert.equal(saves,0,state);assert.equal(paused,0,state);
  }
});

test('append rechecks project, readiness and busy state after pending saves', async () => {
  for (const changed of ['save-failed','project','asset-removed','not-ready','not-video','no-draft','busy']) {
    const gate = deferred();let edits = 0,busy = false;
    const {studio,activate} = studioHarness(async()=>{edits++;});
    const project = appendProject();activate(project);
    studio.options.busy = ()=>busy;studio.flush = ()=>gate.promise;
    const appending = studio.append('video');
    if (changed === 'project') activate(appendProject({id:'two'}));
    if (changed === 'asset-removed') project.assets = {};
    if (changed === 'not-ready') project.assets.video.status = 'preparing';
    if (changed === 'not-video') project.assets.video.kind = 'image';
    if (changed === 'no-draft') project.draft = null;
    if (changed === 'busy') busy = true;
    gate.resolve(changed !== 'save-failed');await appending;
    assert.equal(edits,0,changed);assert.equal(studio.selected,null,changed);
  }
});

test('late append results and errors cannot select or report into another project', async () => {
  for (const fails of [false,true]) {
    const gate = deferred(), entered = deferred();
    const {studio,activate} = studioHarness(()=>{entered.resolve();return gate.promise;});
    activate(appendProject());studio.flush = async()=>true;
    const appending = studio.append('video');await entered.promise;
    activate(appendProject({id:'two'}));studio.selected = 'new-project-clip';studio.status.textContent = 'new project';
    if (fails) gate.reject(new Error('old append failed'));
    else gate.resolve({id:'one',manual:{media_clips:[{id:'old-project-clip'}]}});
    await appending;
    assert.equal(studio.selected,'new-project-clip');assert.equal(studio.status.textContent,'new project');
  }
});

test('append failure stays visible in the owning project without claiming a selected clip', async () => {
  for (const result of ['busy','error','wrong-project']) {
    const {studio,activate} = studioHarness(async()=>{
      if (result === 'error') throw new Error('revision conflict');
      return result === 'busy' ? null : {id:'two',manual:{media_clips:[{id:'wrong'}]}};
    });
    activate(appendProject());studio.flush = async()=>true;
    await studio.append('video');
    assert.equal(studio.selected,null);
    if (result === 'busy') assert.match(studio.status.textContent,/busy.*appending/i);
    if (result === 'error') assert.match(studio.status.textContent,/revision conflict/);
  }
});

function mediaControlNode() {
  return {dataset:{},children:[],listeners:new Map(),style:{setProperty(){}},classList:{toggle(){}},
    setAttribute(){},hasAttribute(){return false;},
    append(...children){this.children.push(...children);},replaceChildren(){this.children=[];},
    addEventListener(event,callback){this.listeners.set(event,callback);},
    querySelector(selector){this.controls ??= new Map();if(!this.controls.has(selector))this.controls.set(selector,mediaControlNode());return this.controls.get(selector);},
    querySelectorAll(){return [];}};
}

test('video cards expose a separately gated append control and preserve Add overlay', () => {
  const document = {createElement:()=>mediaControlNode()};
  for (const state of ['ready','preparing','no-draft','busy','audio']) {
    const {studio,activate} = studioHarness(async()=>null,{document});
    const project = appendProject();
    if(state === 'preparing')project.assets.video.status='preparing';
    if(state === 'no-draft')project.draft=null;
    if(state === 'audio')project.assets.video.kind='audio';
    activate(project);studio.projectId=project.id;studio.root=mediaControlNode();studio.library=mediaControlNode();
    studio.options.busy=()=>state==='busy';
    Object.getPrototypeOf(studio).render.call(studio);
    const card=studio.library.children[0];
    const overlay=card.children.find(node=>node.dataset.asset);
    assert.equal(overlay.dataset.asset,'video');
    if(state === 'ready')assert.equal(overlay.textContent,'+ Overlay');
    const append=card.children.find(node=>node.dataset.append);
    if(state === 'audio')assert.equal(append,undefined);
    else {assert.equal(append.dataset.append,'video');assert.equal(append.textContent,'Append');assert.equal(Boolean(append.disabled),state!=='ready');}
  }
});

test('Append video click dispatches append without triggering Add overlay or importing', () => {
  const {MediaStudio}=load({document:{createElement:()=>mediaControlNode()}});
  const root=mediaControlNode(), calls=[];
  const studio=new MediaStudio(root,mediaControlNode(),{project:()=>appendProject(),busy:()=>false});
  studio.append=id=>calls.push(['append',id]);studio.add=id=>calls.push(['add',id]);studio.upload=()=>calls.push(['upload']);
  root.listeners.get('click')({target:{closest:()=>({dataset:{append:'video'},hasAttribute:()=>false})}});
  assert.deepEqual(calls,[['append','video']]);
});

test('selected video exposes saved audio state, mute recovery and absent-stream state without changing choices', () => {
  for (const state of ['on','off','muted','group-muted','no-stream']) {
    const {studio,activate} = studioHarness(async()=>null,{document:{createElement:()=>mediaControlNode()}});
    const clip={id:'overlay',asset_id:'video',start:1,end:3,source_start:0,speed:2,role:'voice',audio_enabled:state!=='off',muted:state==='muted',volume_db:-6};
    const project=appendProject({manual:{media_clips:[clip],audio_mixer:{voice_muted:state==='group-muted'}}});
    project.assets.video.has_audio=state!=='no-stream';
    const inputs=['audio_enabled','muted','volume_db','role','source_start'].map(key=>({dataset:{media:key},type:['audio_enabled','muted'].includes(key)?'checkbox':'number'}));
    activate(project);studio.projectId=project.id;studio.selected='overlay';studio.root=mediaControlNode();studio.library=mediaControlNode();
    studio.root.querySelectorAll=selector=>selector==='[data-media]'?inputs:[];
    const before=JSON.stringify(project);Object.getPrototypeOf(studio).render.call(studio);
    const status=studio.root.querySelector('.media-audio-status').textContent;
    assert.match(status,state==='no-stream'?/no audio stream/:state==='off'?/sound is off/:state==='muted'?/clip is muted/:state==='group-muted'?/group is muted/:/sound is on.*-6 dB/);
    assert.equal(inputs[0].checked,clip.audio_enabled);assert.equal(inputs[0].disabled,state==='no-stream');
    assert.equal(inputs[1].checked,clip.muted);assert.equal(inputs[1].disabled,['off','no-stream'].includes(state));
    assert.equal(inputs.at(-1).disabled,undefined,'audio availability never disables Source in');
    assert.equal(JSON.stringify(project),before,'opening the inspector preserves saved silent overlays');
    if(state==='on') { studio.mixerOverride={voice_muted:true};studio.renderClipAudio();assert.match(studio.root.querySelector('.media-audio-status').textContent,/group is muted/); }
  }
});

test('enabling a previously silent overlay persists only that explicit choice and preserves trim, mute and speed', async () => {
  let saved=appendProject({manual:{media_clips:[{id:'overlay',asset_id:'video',start:2,end:4,source_start:.5,video_source_start:1,speed:2,audio_enabled:false,muted:true,volume_db:-9,role:'voice'}]}});
  saved.assets.video.has_audio=true;
  const calls=[],{studio,activate}=studioHarness(async(action,payload)=>{calls.push([action,payload]);saved={...saved,manual:{...saved.manual,media_clips:saved.manual.media_clips.map(clip=>clip.id===payload.clip_id?{...clip,...payload}:clip)}};activate(saved);return saved;});
  activate(saved);studio.selected='overlay';
  studio.change({dataset:{media:'audio_enabled'},type:'checkbox',checked:true,value:'on',hasAttribute:()=>false,checkValidity:()=>true});
  await studio.flush();
  assert.equal(calls.length,1);assert.equal(calls[0][0],'media_update');assert.equal(calls[0][1].audio_enabled,true);
  const clip=saved.manual.media_clips[0];assert.equal(clip.muted,true);assert.equal(clip.source_start,.5);assert.equal(clip.video_source_start,1);assert.equal(clip.speed,2);assert.equal(clip.volume_db,-9);
  assert.equal(studio.clips()[0].audio_enabled,true,'reopened saved state retains explicit inclusion');
});

test('library video presence follows independent repeated occurrences and half-open timeline bounds', () => {
  const {libraryVideoAt}=load();
  const first={id:'first',asset_id:'video',start:4,end:7}, repeated={id:'repeat',asset_id:'video',start:6,end:9};
  const project=appendProject({manual:{media_clips:[first,repeated]}});
  assert.equal(libraryVideoAt(project),repeated);
  assert.equal(libraryVideoAt(project,0),null);
  assert.equal(libraryVideoAt(project,4),first);
  assert.equal(libraryVideoAt(project,6),repeated,'later rendered occurrences win while they overlap');
  assert.equal(libraryVideoAt(project,7),repeated);
  assert.equal(libraryVideoAt(project,9),null,'an ended occurrence must not hide the base gap');
  assert.equal(libraryVideoAt(project,-1),null);
  assert.equal(libraryVideoAt(project,NaN),null);
  assert.equal(libraryVideoAt(project,Infinity),null);
  const {studio,activate}=studioHarness(async()=>null);activate(project);
  assert.equal(studio.videoAt(),repeated);assert.equal(studio.videoAt(4),first);assert.equal(studio.videoAt(9),null);
});

test('library video presence excludes missing or unfinished assets, images, and malformed clip timing', () => {
  const {libraryVideoAt}=load();
  for (const reason of ['missing','cancelled','preparing','failed','image','negative','empty','reversed','nan','infinite']) {
    const clip={id:'bad',asset_id:'video',start:0,end:3}, project=appendProject({manual:{media_clips:[clip]}});
    if(reason==='missing')project.assets={};
    if(['cancelled','preparing','failed'].includes(reason))project.assets.video.status=reason;
    if(reason==='image')project.assets.video.kind='image';
    if(reason==='negative')clip.start=-1;
    if(reason==='empty')clip.end=0;
    if(reason==='reversed')clip.end=-1;
    if(reason==='nan')clip.start=NaN;
    if(reason==='infinite')clip.end=Infinity;
    assert.equal(libraryVideoAt(project),null,reason);
    assert.equal(libraryVideoAt(project,1),null,reason);
  }
  assert.equal(libraryVideoAt(null),null);
  assert.equal(libraryVideoAt({manual:{media_clips:{}}}),null);
});

test('media envelopes honor clip edges, fades, mute and bus gain', () => {
  const {clipEnvelope, mediaGain} = load();
  const clip = {start:2, end:8, fade_in:2, fade_out:2, volume_db:6, role:'music'};
  for (const time of [0, 2, 8, 9]) assert.equal(clipEnvelope(clip,time), 0);
  assert.equal(clipEnvelope(clip,3), .5);
  assert.equal(clipEnvelope(clip,5), 1);
  assert.equal(clipEnvelope(clip,7), .5);
  assert.equal(clipEnvelope({...clip,muted:true},5), 0);
  assert.equal(mediaGain(clip,{music_db:-6},5), 1);
  assert.equal(mediaGain(clip,{music_muted:true},5), 0);
  assert.equal(mediaGain(clip,{music_db:-6},3), .5);
});

test('pausing clears a measured live output instead of leaving a stale active meter', () => {
  const {studio} = studioHarness(async()=>({id:'one'}));
  const controls = new Map();
  studio.root = {querySelector(selector) { if (!controls.has(selector)) controls.set(selector,{}); return controls.get(selector); },querySelectorAll(){return [];}};
  studio.analyser = {fftSize:4,getFloatTimeDomainData(samples){samples.fill(.8);}};
  studio.sync(0,true);
  assert.ok(controls.get('.mixer-meter').value > .7);
  studio.pause();
  assert.equal(controls.get('.mixer-meter').value,0,'paused playback must never report a live signal');
  assert.match(controls.get('.mixer-level-text').textContent,/paused|play to monitor/i);
});

test('solo isolates only browser preview while saved mute remains authoritative', () => {
  const {studio,activate} = studioHarness(async()=>({id:'one'}));
  const clips = ['music','voice','effects'].map(role=>({id:role,asset_id:role,start:0,end:8,role,volume_db:0}));
  activate({id:'one',assets:Object.fromEntries(clips.map(clip=>[clip.asset_id,{kind:'audio',duration:8,status:'ready',url:`/${clip.id}`} ])),
    manual:{media_clips:clips,audio_mixer:{source_db:-6,music_db:-12,voice_db:-3,master_db:-4}}});
  const gains = new Map(); studio.master = {gain:{value:1}};
  studio.player = function(key) {const item={key,element:{},token:0};this.players.set(key,item);return item;};
  studio.syncPlayer = (item,time,rate,playing,gain)=>gains.set(item.key,gain);
  const source={url:'/source',point:{sourceTime:3},hasAudio:true};
  studio.sync(3,true,source);
  assert.ok(Math.abs(gains.get('source')-10**(-6/20))<1e-9);
  assert.ok(Math.abs(gains.get('a:music')-10**(-12/20))<1e-9);
  assert.ok(Math.abs(studio.master.gain.value-10**(-4/20))<1e-9);
  studio.toggleSolo('music'); studio.sync(3,true,source);
  assert.ok(gains.get('a:music')>0);
  for(const key of ['source','a:voice','a:effects'])assert.equal(gains.get(key),0);
  assert.equal(studio.pending.size,0,'Solo never enters the persisted export edit queue');
  studio.mixerOverride={music_muted:true}; studio.sync(3,true,source);
  assert.equal(gains.get('a:music'),0,'Solo must not unmute a saved channel');
  studio.toggleSolo('music'); studio.sync(3,true,source);
  assert.ok(gains.get('source')>0); assert.equal(gains.get('a:music'),0);
});

test('channel meters use real grouped samples and distinguish silence, clipping and pause', () => {
  const {studio}=studioHarness(async()=>({id:'one'}));
  const makeMeter=()=>({row:{states:new Map(),classList:{toggle(name,value){this.states?.set(name,value);}}},meter:{setAttribute(){}},level:{}});
  studio.channelMeters = new Map(['source','music','voice','effects','master'].map(role=>{
    const item=makeMeter(); item.row.classList.toggle=(name,value)=>item.row.states.set(name,value); return [role,item];
  }));
  const analyser=peak=>({fftSize:4,getFloatTimeDomainData(samples){samples.fill(peak);}});
  studio.analyser=analyser(.5);
  studio.audioBuses=new Map([['source',{analyser:analyser(.25)}],['music',{analyser:analyser(1.1)}],['voice',{analyser:analyser(0)}]]);
  for(const role of ['source','music','voice'])studio.players.set(role,{role,wanted:true,element:{paused:false},gain:{gain:{value:1}}});
  studio.updateMeters(true);
  assert.equal(studio.channelMeters.get('source').level.textContent,'-12.0 dBFS');
  assert.equal(studio.channelMeters.get('master').level.textContent,'-6.0 dBFS');
  assert.equal(studio.channelMeters.get('music').row.states.get('is-clipping'),true);
  for(const role of ['voice','effects'])assert.equal(studio.channelMeters.get(role).meter.value,0);
  studio.updateMeters(false);
  for(const {row,meter,level} of studio.channelMeters.values()){
    assert.equal(meter.value,0); assert.equal(level.textContent,'-inf dBFS'); assert.equal(row.states.get('is-clipping'),false);
  }
});

test('mixer gain and mute save together and are restored from a reopened project', async () => {
  let saved={id:'one',manual:{media_clips:[],audio_mixer:{source_db:-6}}};
  const calls=[];
  const {studio,activate}=studioHarness(async(action,patch)=>{
    calls.push({action,patch}); saved={...saved,manual:{...saved.manual,audio_mixer:{...saved.manual.audio_mixer,...patch}}}; activate(saved);return saved;
  });
  activate(saved); studio.queueMixer({music_db:-14});studio.queueMixer({music_muted:true});
  assert.equal(await studio.flush(),true);
  assert.equal(calls.length,1);assert.equal(calls[0].action,'set_audio_mixer');
  const reopened=studioHarness(async()=>saved);reopened.activate(saved);
  assert.equal(reopened.studio.mixer().music_db,-14);assert.equal(reopened.studio.mixer().music_muted,true);assert.equal(reopened.studio.mixer().source_db,-6);
  assert.equal(reopened.studio.solo,undefined,'preview Solo is not stored in the project');
});

test('slider updates coalesce and a change arriving during save is persisted next', async () => {
  const first = deferred(), calls = [];
  const {studio} = studioHarness(async (action, payload) => {
    calls.push({action,payload});
    return calls.length === 1 ? first.promise : {id:'one'};
  });
  studio.queueClip('clip1',{volume_db:-4});
  studio.queueClip('clip1',{volume_db:-8,fade_in:1});
  const saving = studio.flush();
  await Promise.resolve(); await Promise.resolve();
  assert.equal(calls.length,1);
  assert.equal(calls[0].payload.volume_db,-8);
  assert.equal(calls[0].payload.fade_in,1);
  studio.queueClip('clip1',{volume_db:-12});
  first.resolve({id:'one'});
  assert.equal(await saving,true);
  assert.equal(calls.length,2);
  assert.equal(calls[1].payload.volume_db,-12);
  assert.equal(studio.pending.size,0);
  assert.equal(studio.overrides.size,0);
});

test('failed save rolls preview back and reports the failure', async () => {
  const {studio} = studioHarness(async () => {throw new Error('revision conflict');});
  studio.queueClip('clip1',{volume_db:12});
  assert.equal(await studio.flush(),false);
  assert.equal(studio.overrides.size,0);
  assert.equal(studio.pending.size,0);
  assert.match(studio.status.textContent,/Not saved: revision conflict/);
});

test('a save failure from an old project cannot discard the new project edits', async () => {
  const old = deferred();
  const {studio,activate} = studioHarness(() => old.promise);
  studio.queueClip('old-clip',{volume_db:2});
  const saving = studio.flush();
  await Promise.resolve(); await Promise.resolve();
  // Match render's project-switch reset, then queue a change in the new project.
  activate({id:'two',manual:{media_clips:[]}});
  studio.pending.clear(); studio.overrides.clear();
  studio.queueClip('new-clip',{volume_db:-12});
  old.reject(new Error('old project changed'));
  await saving;
  assert.equal(studio.pending.get('new-clip')?.volume_db,-12);
  assert.equal(studio.overrides.get('new-clip')?.volume_db,-12);
  assert.doesNotMatch(studio.status.textContent,/old project changed/);
});

test('picture speed and held-tail seeks never change attached or source audio rate', () => {
  const calls=[];
  const {studio,activate} = studioHarness(async()=>({id:'one'}));
  activate({id:'one',assets:{asset1:{kind:'video',duration:10,has_audio:true,status:'ready',url:'/asset'}},manual:{
    media_clips:[{id:'clip1',asset_id:'asset1',start:2,end:8,source_start:1,video_source_start:3,speed:2,audio_enabled:true,role:'effects',x:0,y:0,w:1,h:1}],
  }});
  studio.player = function(key) {
    const item = {key,frame:{style:{}},element:{style:{}},token:0};
    this.players.set(key,item); return item;
  };
  studio.syncPlayer = (item,time,speed,playing,gain) => calls.push({key:item.key,time,speed,playing,gain});
  studio.sync(5,true,{url:'/main',point:{sourceTime:12},hasAudio:true});
  assert.equal(calls.find(row=>row.key==='v:clip1').time,9);
  assert.equal(calls.find(row=>row.key==='v:clip1').speed,2);
  assert.equal(calls.find(row=>row.key==='a:clip1').time,4);
  assert.equal(calls.find(row=>row.key==='a:clip1').speed,1);
  assert.equal(calls.find(row=>row.key==='source').time,12);
  assert.equal(calls.find(row=>row.key==='source').speed,1);
  calls.length=0;
  studio.sync(7,true,{url:'/main',point:{sourceTime:14},hasAudio:true});
  assert.equal(calls.find(row=>row.key==='v:clip1').playing,false);
  assert.ok(calls.find(row=>row.key==='v:clip1').time<10);
  assert.equal(calls.find(row=>row.key==='a:clip1').playing,true);
  assert.equal(calls.find(row=>row.key==='a:clip1').speed,1);
});

test('upload completion and failure both release busy controls', async () => {
  for (const fails of [false,true]) {
    const {studio,activate} = studioHarness(async()=>({id:'one'}));
    activate({id:'one',draft:{},manual:{media_clips:[]}});
    const states=[];
    Object.assign(studio.options, {
      flushSettings:async()=>{}, uploadFile:async()=>({asset_id:'new'}),
      acceptUpload:async()=>{if(fails)throw new Error('Cancelled');},
      busyChanged:()=>states.push(studio.uploading),
    });
    await studio.upload({name:'test.wav'});
    assert.deepEqual(states,[true,false]);
    assert.equal(studio.uploading,false);
    assert.match(studio.status.textContent,fails ? /Cancelled/ : /Ready/);
  }
});

test('media import reports sending and checking before preparation can become Ready', async () => {
  const {studio,activate}=studioHarness(async()=>({id:'one'}));
  activate({id:'one',draft:{},manual:{media_clips:[]}});
  const imported=deferred(), prepared=deferred(), sending=deferred(), storage={};
  studio.root={querySelector:()=>storage};
  Object.assign(studio.options,{
    flushSettings:async()=>{},
    uploadFile:async(_file,projectId,status)=>{
      assert.equal(projectId,'one');
      status('Sending 100%','Project data (D:): 26 GB free.');
      assert.match(studio.status.textContent,/Sending 100%/);
      status('Checking / importing','Project data (D:): 26 GB free.');
      sending.resolve();
      return imported.promise;
    },
    acceptUpload:async()=>prepared.promise,
  });
  const operation=studio.upload({name:'test.wav'});
  await sending.promise;
  assert.match(studio.status.textContent,/Checking \/ importing/);
  assert.doesNotMatch(studio.status.textContent,/Ready/);
  assert.match(storage.textContent,/D:.*26 GB free/);
  imported.resolve({asset_id:'new'});
  for(let index=0;index<10;index++)await Promise.resolve();
  assert.match(studio.status.textContent,/Preparing preview/);
  assert.equal(studio.uploading,true);
  prepared.resolve();await operation;
  assert.match(studio.status.textContent,/Ready/);
  assert.equal(studio.uploading,false);
});

test('inactive media releases decoder and audio graph resources', () => {
  const {studio}=studioHarness(async()=>({id:'one'}));
  const calls=[];
  const item={token:0,wanted:true,element:{pause(){calls.push('pause');},removeAttribute(name){calls.push(name);},load(){calls.push('unload');},remove(){calls.push('remove');}},node:{disconnect(){calls.push('disconnect');}}};
  studio.players.set('old',item);
  studio.sync(10,false);
  assert.equal(studio.players.size,0);
  assert.equal(item.wanted,false);
  assert.deepEqual(calls,['pause','disconnect','src','unload','remove']);
});

test('a successful old-project save cannot clear same-id edits in a new project', async () => {
  const old=deferred();
  const {studio,activate}=studioHarness(()=>old.promise);
  studio.queueClip('clip1',{volume_db:2});
  const saving=studio.flush();
  await Promise.resolve(); await Promise.resolve();
  activate({id:'two',manual:{media_clips:[]}});
  studio.pending.clear(); studio.overrides.clear(); studio.queueClip('clip1',{volume_db:-12});
  old.resolve({id:'one'}); await saving;
  assert.equal(studio.overrides.get('clip1').volume_db,-12);
  assert.equal(studio.pending.get('clip1').volume_db,-12);
});

function audioGraphHarness({alwaysReject = false, failConnect = false} = {}) {
  const associated = new WeakSet(), attempts = [], nodes = [], controls = new Map();
  const node = () => {
    const result = {gain:{value:1},connections:[],connect(target) {if(failConnect)throw new Error('Graph failed');this.connections.push(target);return target;},disconnect(){this.disconnected=true;this.connections=[];},getFloatTimeDomainData() {}};
    nodes.push(result); return result;
  };
  const document = {createElement(kind) {return {
    tagName:kind.toUpperCase(),currentTime:0,paused:true,volume:1,
    pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();},
    removeAttribute(){},load(){},remove(){this.removed=true;},
  };}};
  const {studio} = studioHarness(async()=>({id:'one'}), {document, console:{warn(){}}});
  studio.root = {append(){},querySelector(selector) {if(!controls.has(selector))controls.set(selector,{});return controls.get(selector);}};
  studio.context = {createGain:node,createAnalyser:node,createMediaElementSource(element) {
    attempts.push(element);
    if(alwaysReject || associated.has(element))throw Object.assign(new Error('HTMLMediaElement already connected'),{name:'InvalidStateError'});
    associated.add(element); return node();
  }};
  studio.master = node();
  return {studio,associated,attempts,nodes};
}

test('repeated sync, pause and resume reuse one Web Audio connection per element', async () => {
  const {studio,attempts} = audioGraphHarness();
  const source={url:'/main',point:{sourceTime:2},hasAudio:true};
  studio.sync(2,true,source); await Promise.resolve();
  const first=studio.players.get('source');
  for(let i=0;i<5;i++) {studio.pause();studio.sync(2,false,source);studio.sync(2,true,source);}
  assert.equal(attempts.length,1);
  assert.equal(studio.players.get('source'),first);
  studio.pause(); assert.equal(first.element.paused,true);
  studio.clearPlayers(); studio.sync(2,false,source);
  assert.equal(attempts.length,2);
  assert.notEqual(attempts[0],attempts[1]);
  assert.equal(first.element.removed,true);
});

test('already-associated audio recovers on a fresh element and pause never throws', () => {
  const {studio,associated,attempts,nodes}=audioGraphHarness();
  const old=studio.createPlayer('source','audio','/main'); old.element.currentTime=7; old.element.paused=false;
  associated.add(old.element); // Exact browser condition in the reported InvalidStateError.
  const source={url:'/main',point:{sourceTime:7},hasAudio:true};
  assert.doesNotThrow(()=>{studio.pause();studio.sync(7,false,source);});
  const fresh=studio.players.get('source');
  assert.notEqual(fresh.element,old.element);
  assert.equal(fresh.element.src,'/main'); assert.equal(fresh.element.currentTime,7);
  assert.equal(fresh.element.paused,true); assert.equal(old.element.removed,true);
  assert.equal(old.element.paused,true); assert.ok(fresh.node);
  studio.sync(7,false,source);
  assert.equal(attempts.length,2,'never retries the already-associated element');
  assert.ok(nodes.slice(1,3).every(n=>n.disconnected),'failed partial graph is released');
});

test('persistent graph errors use bounded basic playback with volume and mute intact', async () => {
  for(const options of [{alwaysReject:true},{failConnect:true}]) {
    const {studio,attempts}=audioGraphHarness(options);
    studio.mixerOverride={source_db:-6,master_db:-6};
    const source={url:'/main',point:{sourceTime:3},hasAudio:true};
    studio.sync(3,true,source); await Promise.resolve();
    const item=studio.players.get('source');
    assert.equal(item.basicAudio,true); assert.equal(item.element.paused,false);
    assert.ok(Math.abs(item.element.volume-10**(-12/20))<1e-9);
    assert.match(studio.status.textContent,/Basic audio preview/);
    studio.mixerOverride={source_muted:true}; studio.sync(3,true,source);
    assert.equal(item.element.volume,0);
    studio.pause(); studio.sync(3,false,source);
    assert.equal(item.element.paused,true); assert.equal(attempts.length,2);
    assert.equal(studio.players.size,1,'failed players do not accumulate');
    studio.clearPlayers(); studio.sync(3,false,{...source,url:'/next-project'});
    assert.equal(studio.players.get('source').basicAudio,true);
    assert.equal(attempts.length,2,'basic mode persists until reload, without retry loops');
  }
});

test('upgrading basic audio after first gesture removes duplicate attenuation', () => {
  const {studio,attempts}=audioGraphHarness();
  const context=studio.context; studio.context=null;
  const item=studio.player('source','audio','/main');
  studio.syncPlayer(item,0,1,false,.25); assert.equal(item.element.volume,.25);
  studio.context=context;
  assert.equal(studio.player('source','audio','/main'),item);
  studio.syncPlayer(item,0,1,false,.25);
  assert.equal(item.element.volume,1); assert.equal(item.gain.gain.value,.25);
  assert.equal(attempts.length,1);
});

test('moving a clip between audio groups reroutes its signal without reconnecting its media element', () => {
  const {studio,attempts}=audioGraphHarness();
  const item=studio.player('a:clip','audio','/music','music');
  const second=studio.player('a:other','audio','/other','music');
  assert.equal(item.analyser.connections[0],studio.audioBuses.get('music').gain);
  assert.equal(second.analyser.connections[0],studio.audioBuses.get('music').gain,'multiple clips are measured as one actual music bus');
  assert.equal(studio.player('a:clip','audio','/music','voice'),item);
  assert.equal(item.analyser.connections[0],studio.audioBuses.get('voice').gain);
  assert.equal(second.analyser.connections[0],studio.audioBuses.get('music').gain);
  assert.equal(attempts.length,2,'one media source connection for each of the two players');
});

function loadMixer(globals = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../web/media-studio.js'), 'utf8').replace(/^export /gm, '');
  const context = vm.createContext({window: {}, document: {}, FormData: class {append() {}}, performance: {now: () => 1000}, setTimeout: () => 1, clearTimeout() {}, ...globals});
  vm.runInContext(source + '\nglobalThis.api = {MediaStudio, previewNormalizationGain, mixerNormalization, PREVIEW_LOUDNESS_WINDOW_MS};', context);
  return context.api;
}

test('preview normalization follows the export: target minus measured loudness, held in silence', () => {
  const {previewNormalizationGain, mixerNormalization} = loadMixer();
  assert.equal(mixerNormalization({draft:{}}), null);
  assert.equal(mixerNormalization({draft:{audio_policy:{normalize:true,target_lufs:-14}}}).target, -14);
  assert.equal(mixerNormalization({draft:{audio_policy:{normalize:true,target_lufs:-40}}}).target, -24, 'targets stay in the export range');
  assert.equal(mixerNormalization({draft:{audio_policy:{normalize:true}}}).target, -16);
  // A long, steady signal converges to exactly the gain the export applies.
  let gain = 0;
  for (let step = 0; step < 100; step++) gain = previewNormalizationGain(gain, -28, -16, .1);
  assert.ok(Math.abs(gain - 12) < .01);
  // Lowering a fader by 12 dB on the only track: the measured level drops by
  // 12 dB and the normalizer gives it back, so the result does not change.
  let lowered = gain;
  for (let step = 0; step < 100; step++) lowered = previewNormalizationGain(lowered, -40, -16, .1);
  assert.ok(Math.abs((lowered - 40) - (gain - 28)) < .01);
  assert.equal(previewNormalizationGain(5, -Infinity, -16, 1), 5, 'silence holds the gain');
  assert.equal(previewNormalizationGain(5, -80, -16, 1), 5);
  assert.equal(previewNormalizationGain(0, 10, -16, 100) <= -26, true, 'gain is bounded');
});

test('mixer rows offer a typed value, a 0 dB mark and reset, and explain normalization', () => {
  const {MediaStudio} = loadMixer();
  const studio = Object.create(MediaStudio.prototype);
  let project = {id:'one', sources:{A:{has_audio:true}}, manual:{media_clips:[], audio_mixer:{source_db:-3.5}}, draft:{audio_policy:{normalize:true,target_lufs:-16}}, assets:{}};
  const note = {textContent:''};
  const rows = new Map();
  for (const role of ['source','music','voice','effects','master']) rows.set(role, {row:{classList:{toggle() {}}, dataset:{}}, meter:{}, level:{}});
  const typed = {dataset:{mixNumber:'source_db'}, value:''}, reset = {dataset:{mixReset:'source_db'}, disabled:false};
  const masterReset = {dataset:{mixReset:'master_db'}, disabled:false};
  Object.assign(studio, {
    options: {project: () => project, audioSlot: () => 'A', busy: () => false, preview() {}},
    overrides:new Map(), pending:new Map(), channelMeters: rows, mixerOverride:null, solo:null,
    audioRoot: {querySelector(selector) { return selector === '.mixer-normalization' ? note : selector === '[data-ducking]' ? {} : null; },
      querySelectorAll(selector) { return selector === '[data-mix-number]' ? [typed] : selector === '[data-mix-reset]' ? [reset, masterReset] : []; }},
  });
  studio.renderMixer();
  assert.equal(typed.value, '-3.5');
  assert.equal(reset.disabled, false); assert.equal(masterReset.disabled, true, 'reset is only offered away from 0 dB');
  assert.match(note.textContent, /normalization is on \(-16 LUFS\).*balance.*Master/i);
  assert.match(note.textContent, /Original is the only role group playing/, 'a lone track explains why its fader does not change the export');
  assert.equal(rows.get('source').row.dataset.normalizedAlone, 'true');
  project = {...project, draft:{}};
  studio.renderMixer();
  assert.match(note.textContent, /normalization is off/i);
  assert.equal(rows.get('source').row.dataset.normalizedAlone, 'false');
  // Typed values are clamped and kept to 0.1 dB; an empty field changes nothing.
  const queued = [];
  studio.queueMixer = patch => queued.push(patch);
  studio.change({dataset:{mixNumber:'music_db'}, value:'-7.26', hasAttribute: () => false});
  studio.change({dataset:{mixNumber:'music_db'}, value:'40', hasAttribute: () => false});
  studio.change({dataset:{mixNumber:'music_db'}, value:'', hasAttribute: () => false});
  assert.deepEqual(JSON.parse(JSON.stringify(queued)), [{music_db:-7.3}, {music_db:12}]);
});

test('successful media import rerenders ready review and append controls after uploading clears', async () => {
  const {studio,activate}=studioHarness(async()=>null);activate(appendProject());
  const paints=[];studio.render=()=>paints.push(studio.uploading);
  studio.flush=async()=>true;studio.options.flushSettings=async()=>{};
  studio.options.uploadFile=async()=>({});studio.options.acceptUpload=async()=>{};
  await studio.upload({name:'Synthetic.mp4'});
  assert.equal(studio.uploading,false);assert.equal(paints.at(-1),false);
  assert.ok(paints.includes(true),'the acceptance render is followed by an unlocked render');
  assert.equal(studio.status.textContent,'Ready. Add the file at the playhead.');
});
test('media import failure refreshes controls but preserves its actionable error', async () => {
  const {studio,activate}=studioHarness(async()=>null);activate(appendProject());
  const paints=[];studio.render=()=>paints.push(studio.uploading);studio.flush=async()=>true;
  studio.options.flushSettings=async()=>{};studio.options.uploadFile=async()=>{throw Error('Import failed. Retry this file.');};
  await studio.upload({name:'Synthetic.mp4'});
  assert.equal(studio.uploading,false);assert.equal(paints.at(-1),false);assert.equal(studio.status.textContent,'Import failed. Retry this file.');
});
test('late import completion does not rerender a different project library', async () => {
  const {studio,activate}=studioHarness(async()=>null);activate(appendProject());
  let paints=0;studio.render=()=>paints++;studio.flush=async()=>true;studio.options.flushSettings=async()=>{};
  studio.options.uploadFile=async()=>{activate({...appendProject(),id:'another'});return {};};studio.options.acceptUpload=async()=>{};
  await studio.upload({name:'Synthetic.mp4'});
  assert.equal(studio.uploading,false);assert.equal(paints,0);
});


test('compact media actions retain file-specific accessible names and source metadata', () => {
  const document = {createElement(tag) {
    const node = mediaControlNode(); node.tag = tag; node.attributes = {};
    node.setAttribute = (name,value) => { node.attributes[name] = value; };
    node.querySelectorAll = selector => selector === 'button' ? node.children.filter(item=>item.tag==='button') : [];
    return node;
  }};
  for (const state of ['ready','failed']) {
    const {studio,activate}=studioHarness(async()=>null,{document});
    const project=appendProject();project.assets.video.name='Interview 01.mp4';project.assets.video.status=state;
    activate(project);studio.projectId=project.id;studio.root=mediaControlNode();studio.library=mediaControlNode();studio.options.busy=()=>false;
    Object.getPrototypeOf(studio).render.call(studio);
    const card=studio.library.children[0], buttons=card.querySelectorAll('button');
    assert.equal(card.children[1].textContent,'Interview 01.mp4');
    assert.equal(card.children[2].textContent,'Video · 00:03');
    assert.equal(buttons.find(b=>b.dataset.reviewShot).textContent,'In / Out');
    assert.match(buttons.find(b=>b.dataset.reviewShot).title,/Review shot/);
    for(const button of buttons)assert.equal(button.attributes['aria-label'],`${button.textContent}: Interview 01.mp4`);
    if(state==='failed')assert.equal(buttons.find(b=>b.dataset.retry).attributes['aria-label'],'Retry: Interview 01.mp4');
  }
});


test('empty manual media import consumes first footage without duplicate asset upload', async () => {
  const {studio,activate}=studioHarness(async()=>null);
  activate({id:'one',settings:{workflow:'manual'},draft:null});
  let prepared=0,uploaded=0;
  studio.options.prepareEmptyImport=async file=>{prepared++;assert.equal(file.name,'first.mp4');activate({id:'one',draft:{engine:'manual'}});return true;};
  studio.options.uploadFile=async()=>{uploaded++;};
  await studio.upload({name:'first.mp4'});
  assert.equal(prepared,1);assert.equal(uploaded,0);assert.match(studio.status.textContent,/Recording ready in the timeline/);
});

test('empty media import reports errors and ignores results from a different project', async () => {
  for(const outcome of ['error','switched','not-ready']) {
    const {studio,activate}=studioHarness(async()=>null);
    activate({id:'one',settings:{workflow:'manual'},draft:null});
    studio.status.textContent='Original status';let uploaded=0;
    studio.options.prepareEmptyImport=async()=>{
      if(outcome==='error')throw new Error('Start with a video recording.');
      if(outcome==='switched')activate({id:'two',draft:{}});
      return false;
    };
    studio.options.uploadFile=async()=>{uploaded++;};
    await studio.upload({name:'file.mp4'});
    assert.equal(uploaded,0);
    assert.equal(studio.status.textContent,outcome==='error'?'Start with a video recording.':'Original status');
  }
});

test('legacy manual source starts its timeline then imports additional media once', async () => {
  const {studio,activate}=studioHarness(async()=>null);
  activate({id:'one',settings:{workflow:'manual'},sources:{A:{}},draft:null});
  let uploaded=0,accepted=0;
  studio.options.prepareEmptyImport=async()=>{activate({id:'one',draft:{}});return false;};
  studio.flush=async()=>true;studio.options.flushSettings=async()=>{};
  studio.options.uploadFile=async()=>{uploaded++;return {};};studio.options.acceptUpload=async()=>{accepted++;};
  await studio.upload({name:'more.mp4'});
  assert.equal(uploaded,1);assert.equal(accepted,1);assert.equal(studio.uploading,false);
});


function rangeDragHost() {
  const entries=new Map(),storage={getItem:k=>entries.get(k)??null,setItem:(k,v)=>entries.set(k,v)};
  const {MediaStudio}=load({localStorage:storage}),studio=Object.create(MediaStudio.prototype),calls=[];
  let p={id:'drag-project',revision:4,draft:{output_duration:8},editor_sequence:{duration:8},manual:{sequence:{duration:8},media_clips:[]},
    assets:{v:{id:'v',name:'Same.mp4',kind:'video',status:'ready',duration:10,width:160,height:90,url:'/v'},b:{id:'b',name:'Same.mp4',kind:'video',status:'ready',duration:10,width:160,height:90,url:'/b'},a:{id:'a',kind:'audio',status:'ready',duration:10,url:'/a'}}};
  const audioScope=vm.createContext({});vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/audio-source.js'),'utf8').replace(/^import .*\r?\n/gm,'').replace(/^export /gm,'')+'\nglobalThis.api={audioSourceRange,readAudioSourceMarks,saveAudioSourceMarks};',audioScope);
  const {audioSourceRange,readAudioSourceMarks,saveAudioSourceMarks}=audioScope.api;
  Object.assign(studio,{status:{textContent:''},pending:new Map(),flush:async()=>true,updateImportAvailability(){},syncSourceMonitor(){},render(){},options:{project:()=>p,busy:()=>false,pause(){},flushSettings:async()=>{},
    audioSource:{range:audioSourceRange,readMarks:(p,id)=>readAudioSourceMarks(p,id,storage)},
    placementPreview:(id,time,o)=>({issue:'',start:o.append?p.editor_sequence.duration:time,end:(o.append?p.editor_sequence.duration:time)+(o.sourceEnd??p.assets[id].duration)-(o.sourceStart??0)}),
    edit:async(action,payload,guard)=>{assert.equal(guard?.isCurrent?.(),true);calls.push({action,payload:JSON.parse(JSON.stringify(payload)),guard});p={...p,revision:p.revision+1};return p;}}});
  studio.insertionIssue=(_id,_time,o)=>{assert.equal(o.sourceEnd-o.sourceStart,2);return '';};
  return{studio,calls,entries,storage,audio:{saveAudioSourceMarks},get p(){return p},set p(x){p=x}};
}
for(const kind of ['v','a'])test('marked '+kind+' Overlay payload uses exact source_start and bounded timeline end',async()=>{
 const h=rangeDragHost();await h.studio.place(kind,7,{sourceStart:3,sourceEnd:5},{isCurrent:()=>true});
 assert.equal(h.calls.length,1);assert.equal(h.calls[0].action,'media_add');assert.deepEqual(h.calls[0].payload,{asset_id:kind,start:7,source_start:3,end:8});assert.equal(h.calls[0].guard.strictRevision,true);
});
for(const mode of ['append','insert'])test('marked video '+mode+' uses both exact source endpoints and the same readiness interval',async()=>{
 const h=rangeDragHost();await h.studio.place('v',2,{[mode]:true,sourceStart:3,sourceEnd:5},{isCurrent:()=>true});
 assert.equal(h.calls.length,1);assert.deepEqual(h.calls[0].payload,{asset_id:'v',...(mode==='append'?{}:{start:2}),source_start:3,source_end:5});
});
test('drag snapshot is rechecked after both flushes and no stale request is sent',async()=>{
 for(const step of ['flush','settings'])for(const mutation of ['selection','asset','revision','project']){
  const h=rangeDragHost();let current=true;const mutate=()=>{if(mutation==='selection')current=false;else if(mutation==='asset')h.p.assets.v.duration=11;else if(mutation==='revision')h.p.revision++;else h.p.id='changed';return true;};
  if(step==='flush')h.studio.flush=async()=>mutate();else h.studio.options.flushSettings=async()=>mutate();
  const result=await h.studio.place('v',2,{sourceStart:3,sourceEnd:5},{isCurrent:()=>current});assert.equal(result,null);assert.deepEqual(h.calls,[]);assert.equal(h.studio.placing,false);
 }
});
test('exact-asset video and audio saved marks stay separate and never bleed from active other-source marks',()=>{
 const h=rangeDragHost(),videoKey=id=>'cutroom.library-source-marks.v1:'+JSON.stringify([h.p.id,id]);
 h.storage.setItem(videoKey('v'),JSON.stringify({identity:JSON.stringify([1,h.p.id,'v',10,160,90,'video']),source_start:3,source_end:5}));
 h.audio.saveAudioSourceMarks(h.p,'a',{source_start:1.25,source_end:2.75},h.storage);
 h.studio.shotReview={sourceSelection:id=>id==='b'?{source_start:6,source_end:8}:null};
 assert.deepEqual(JSON.parse(JSON.stringify(h.studio.dragSelection('v'))),{sourceStart:3,sourceEnd:5});
 assert.deepEqual(JSON.parse(JSON.stringify(h.studio.dragSelection('a'))),{sourceStart:1.25,sourceEnd:2.75});
 assert.deepEqual(JSON.parse(JSON.stringify(h.studio.dragSelection('b'))),{sourceStart:6,sourceEnd:8});
 h.studio.shotReview=null;assert.equal(h.studio.dragSelection('b'),null);
 h.p.assets.v.duration=11;assert.equal(h.studio.dragSelection('v'),null);h.p.id='new-project';assert.equal(h.studio.dragSelection('a'),null);
});
