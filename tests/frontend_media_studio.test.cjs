const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function load() {
  const source = fs.readFileSync(path.join(__dirname, '../web/media-studio.js'), 'utf8').replace(/^export /gm, '');
  const context = vm.createContext({window: {}, document: {}, FormData: class {append() {}}, performance: {now: () => 1000}, setTimeout: () => 1, clearTimeout() {}});
  vm.runInContext(source + '\nglobalThis.api = {MediaStudio, clipEnvelope, mediaGain};', context);
  return context.api;
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
}

function studioHarness(edit) {
  const {MediaStudio} = load();
  let project = {id:'one', manual:{media_clips:[]}};
  const studio = Object.create(MediaStudio.prototype);
  Object.assign(studio, {
    options: {project: () => project, edit, preview() {}, pause() {}, busy: () => false},
    selected:null, pending:new Map(), overrides:new Map(), players:new Map(), saving:null,
    status:{textContent:''}, render() {}, renderMixer() {},
  });
  return {studio, activate(next) {project = next;}};
}

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
      flushSettings:async()=>{}, api:async()=>({asset_id:'new'}),
      acceptUpload:async()=>{if(fails)throw new Error('Cancelled');},
      busyChanged:()=>states.push(studio.uploading),
    });
    await studio.upload({name:'test.wav'});
    assert.deepEqual(states,[true,false]);
    assert.equal(studio.uploading,false);
    assert.match(studio.status.textContent,fails ? /Cancelled/ : /Ready/);
  }
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
