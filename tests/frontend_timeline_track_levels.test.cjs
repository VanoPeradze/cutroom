const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/timeline.js','utf8');const scope=vm.createContext({});vm.runInContext(source.replace(/^export /gm,'')+'\nglobalThis.api={timelineLayerTrackState,TimelineView};',scope);
const {timelineLayerTrackState:state,TimelineView}=scope.api;
const track=(kind,i)=>({id:'track_'+String(i).padStart(32,'0'),kind,name:kind,locked:false,...(kind==='text'?{}:{audio:{gain_db:0,muted:false}})});
const model=()=>({version:3,protection_version:1,tracks:[track('visual',1),track('audio',2),track('text',3)]});
const read=m=>state({manual:{layer_tracks:m}});
test('valid v3 keeps exact saved tracks and does not mutate model',()=>{const m=model(),before=JSON.stringify(m),r=read(m);assert.equal(r.valid,true);assert.equal(r.enabled,true);assert.equal(r.tracks,m.tracks);assert.equal(JSON.stringify(m),before);});
for(const gain of [-60,-3.125,0,12])test('valid exact gain '+gain,()=>{const m=model();m.tracks[0].audio.gain_db=gain;m.tracks[1].audio.muted=true;assert.equal(read(m).valid,true);});
test('v3 protection2 retains locked rows',()=>{const m=model();m.protection_version=2;m.tracks[0].locked=true;assert.equal(read(m).valid,true);});
const badCases={
 missingProtection:m=>delete m.protection_version,invalidProtection:m=>m.protection_version=3,stringProtection:m=>m.protection_version='1',unknownVersion:m=>m.version=4,unknownModel:m=>m.other=true,
 missingAudio:m=>delete m.tracks[0].audio,textAudio:m=>m.tracks[2].audio={gain_db:0,muted:false},arrayAudio:m=>m.tracks[0].audio=[],nullAudio:m=>m.tracks[0].audio=null,extraAudio:m=>m.tracks[0].audio.other=true,
 missingGain:m=>delete m.tracks[0].audio.gain_db,stringGain:m=>m.tracks[0].audio.gain_db='0',nanGain:m=>m.tracks[0].audio.gain_db=NaN,infiniteGain:m=>m.tracks[0].audio.gain_db=Infinity,lowGain:m=>m.tracks[0].audio.gain_db=-60.001,highGain:m=>m.tracks[0].audio.gain_db=12.001,
 missingMute:m=>delete m.tracks[0].audio.muted,invalidMute:m=>m.tracks[0].audio.muted=0,missingLock:m=>delete m.tracks[0].locked,invalidLock:m=>m.tracks[0].locked='false',protectedV1:m=>m.tracks[0].locked=true,extraTrack:m=>m.tracks[0].other=true,duplicateTrack:m=>m.tracks[1].id=m.tracks[0].id,unknownKind:m=>m.tracks[0].kind='voice',nullTrack:m=>m.tracks[0]=null
};
for(const [name,mutate]of Object.entries(badCases))test('malformed v3 fails closed '+name,()=>{const m=model();mutate(m);const r=read(m);assert.equal(r.enabled,true);assert.equal(r.valid,false);assert.equal(r.tracks.length,0);});
for(const version of [1,2])test('legacy exact schema preserved '+version,()=>{const m={version,tracks:[{id:track('audio',1).id,kind:'audio',name:'Sound',...(version===2?{locked:true}:{})}]};assert.equal(read(m).valid,true);m.tracks[0].audio={gain_db:0,muted:false};assert.equal(read(m).valid,false);delete m.tracks[0].audio;m.protection_version=version;assert.equal(read(m).valid,false);});
test('absent model remains legacy while orphan memberships fail closed',()=>{assert.equal(state({manual:{}}).enabled,false);assert.equal(state({manual:{media_clips:[{track_id:track('audio',1).id}]}}).valid,false);});
test('v3 missing split planner cannot fall through legacy mutation',()=>{const t=Object.create(TimelineView.prototype);t.project={manual:{layer_tracks:model()}};t.mediaProtectionIssue=()=>'';assert.match(t.mediaSplitReadiness('media_x',1),/protection is unavailable/);});
test('both edge interaction guards cover v3 and future protected versions',()=>{assert.equal((source.match(/layer_tracks\?\.version >= 2 && !this\.nativeMediaTrim\(\)/g)||[]).length,2);assert.equal(source.includes('layer_tracks?.version === 2'),false);});
test('timeline drop and track manager import matching canonical cache',()=>{assert.match(fs.readFileSync('web/timeline-media-drop.js','utf8'),/timeline\.js\?v=20261117-editing-context1/);assert.match(fs.readFileSync('web/layer-track-manager.js','utf8'),/layer-tracks\.js\?v=20261116-track-levels2/);});
