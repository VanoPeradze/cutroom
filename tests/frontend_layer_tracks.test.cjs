const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/layer-tracks.js'),'utf8');
const context=vm.createContext({});
vm.runInContext(source.replace(/^export /gm,''),context);
const api=vm.runInContext('({layerTrackState,layerTrackKind,layerTrackRanks,layerTrackUpdateIssue,planLayerTrackMove})',context);
const id=(type,n)=>`${type}_${String(n).padStart(32,'0')}`;
const copy=value=>JSON.parse(JSON.stringify(value));
function project(){return {id:'project_tracks',revision:4,draft:{output_duration:8},editor_sequence:{duration:8},assets:{v:{kind:'video',status:'ready'},a:{kind:'audio',status:'ready'},i:{kind:'image',status:'ready'}},manual:{layer_tracks:{version:1,tracks:[
 {id:id('track',1),kind:'visual',name:'Background'}, {id:id('track',2),kind:'audio',name:'Sound'},
 {id:id('track',3),kind:'visual',name:'Foreground'}, {id:id('track',4),kind:'text',name:'Titles'},
 {id:id('track',5),kind:'visual',name:'Empty'}, {id:id('track',6),kind:'text',name:'Top text'}]},
 media_clips:[{id:id('media',1),asset_id:'v',track_id:id('track',3),start:1,end:3,source_start:.5,video_source_start:1,speed:.5},
 {id:id('media',2),asset_id:'a',track_id:id('track',2),start:1,end:3,enabled:false},
 {id:id('media',3),asset_id:'i',track_id:id('track',1),start:2,end:5}],
 text_clips:[{id:id('text',1),track_id:id('track',6),start:.25,end:2,kind:'title'},
 {id:id('text',2),track_id:id('track',4),start:.5,end:3,kind:'caption'}]}};}

test('legacy absence remains an unmodified legacy state, not virtual saved tracks',()=>{const p=project();delete p.manual.layer_tracks;for(const row of [...p.manual.media_clips,...p.manual.text_clips])delete row.track_id;const before=JSON.stringify(p);assert.deepEqual(copy(api.layerTrackState(p)),{enabled:false,issue:'',tracks:[]});assert.equal(JSON.stringify(p),before);});
test('valid empty tracks remain in the canonical model',()=>{const p=project();const result=api.layerTrackState(p);assert.equal(result.issue,'');assert.equal(result.tracks.length,6);assert.strictEqual(result.tracks,p.manual.layer_tracks.tracks);});
test('visual ranks follow tracks without reordering source arrays or audio',()=>{const p=project(),before=JSON.stringify(p),r=api.layerTrackRanks(p);assert.equal(r.visual.get(id('media',3)),0);assert.equal(r.visual.get(id('media',1)),1);assert.equal(r.visual.has(id('media',2)),false);assert.equal(r.text.get(id('text',2)),0);assert.equal(r.text.get(id('text',1)),1);assert.equal(JSON.stringify(p),before);});
test('many empty tracks do not raise picture above the separate text plane',()=>{const p=project();for(let n=7;n<800;n++)p.manual.layer_tracks.tracks.push({id:id('track',n),kind:'visual',name:`Empty ${n}`});const ranks=api.layerTrackRanks(p);assert.equal(ranks.issue,'');assert.deepEqual([...ranks.visual.values()].sort(),[0,1]);});
for(const [name,mutate] of [
 ['future version',p=>p.manual.layer_tracks.version=2],
 ['null model',p=>p.manual.layer_tracks=null],
 ['unknown model key',p=>p.manual.layer_tracks.extra=true],
 ['tracks not array',p=>p.manual.layer_tracks.tracks={}],
 ['duplicate track',p=>p.manual.layer_tracks.tracks.push({...p.manual.layer_tracks.tracks[0]})],
 ['invalid kind',p=>p.manual.layer_tracks.tracks[0].kind='V1'],
 ['padded name',p=>p.manual.layer_tracks.tracks[0].name=' title '],
 ['empty name',p=>p.manual.layer_tracks.tracks[0].name=''],
 ['overlong name',p=>p.manual.layer_tracks.tracks[0].name='a'.repeat(81)],
 ['unknown track field',p=>p.manual.layer_tracks.tracks[0].muted=true],
 ['bad track identity',p=>p.manual.layer_tracks.tracks[0].id='A'],
 ['missing membership',p=>delete p.manual.media_clips[0].track_id],
 ['wrong kind',p=>p.manual.media_clips[0].track_id=id('track',2)],
 ['duplicate clip',p=>p.manual.media_clips.push({...p.manual.media_clips[0]})],
 ['null clip',p=>p.manual.media_clips.push(null)],
 ['invalid clip identity',p=>p.manual.media_clips[0].id='clip_A'],
 ['invalid timing',p=>p.manual.media_clips[0].start=NaN],
 ['boolean timing',p=>p.manual.media_clips[0].start=true],
 ['beyond duration',p=>p.manual.media_clips[0].end=9],
 ['asset kind missing',p=>delete p.assets.v.kind],
 ['same-track overlap',p=>p.manual.media_clips[2].track_id=id('track',3)],
 ['disabled overlap',p=>{p.manual.media_clips[2].track_id=id('track',3);p.manual.media_clips[2].enabled=false;}],
 ['orphan membership',p=>delete p.manual.layer_tracks],
 ['too many tracks',p=>{for(let n=7;n<=4097;n++)p.manual.layer_tracks.tracks.push({id:id('track',n),kind:'visual',name:'Track'});}],
])test(`invalid saved model fails closed: ${name}`,()=>{const p=project();mutate(p);assert.ok(api.layerTrackState(p).issue);assert.ok(api.planLayerTrackMove(p,id('media',1),1,id('track',5)).issue);assert.equal(api.layerTrackRanks(p).visual.size,0);});
test('Unicode name limit counts codepoints, not UTF-16 units',()=>{const p=project();p.manual.layer_tracks.tracks[0].name='🎞'.repeat(80);assert.equal(api.layerTrackState(p).issue,'');p.manual.layer_tracks.tracks[0].name+='🎞';assert.ok(api.layerTrackState(p).issue);});
test('disabled or failed media still owns its track interval',()=>{const p=project();p.assets.v.status='failed';p.manual.media_clips[0].enabled=false;assert.equal(api.layerTrackState(p).issue,'');assert.ok(api.planLayerTrackMove(p,id('media',3),2,id('track',3)).issue);});
test('pure vertical assignment preserves exact fractional timing even without ready preview',()=>{const p=project(),clip=p.manual.media_clips[0];clip.start=1.123456789123;clip.end=3.234567891234;p.assets.v.status='failed';const plan=api.planLayerTrackMove(p,clip.id,clip.start,id('track',5));assert.deepEqual(copy(plan.patch),{start:clip.start,end:clip.end,track_id:id('track',5)});assert.ok(api.planLayerTrackMove(p,clip.id,2,id('track',5)).issue);});
test('whole-clip track move is canonical without changing clocks, effects or source model',()=>{const p=project(),before=JSON.stringify(p);const plan=api.planLayerTrackMove(p,id('media',1),4.123456789,id('track',5));assert.equal(plan.issue,'');assert.deepEqual(copy(plan.patch),{start:4.123456789,end:6.123456789,track_id:id('track',5)});assert.equal(JSON.stringify(p),before);});
test('same exact membership/time is a no-op and uses no write-shaped patch',()=>{const p=project();assert.deepEqual(copy(api.planLayerTrackMove(p,id('media',1),1,id('track',3))),{issue:'',patch:{}});});
test('changed text timing uses existing microsecond endpoint precision',()=>{const p=project();const plan=api.planLayerTrackMove(p,id('text',1),4.1234567,id('track',4));assert.equal(plan.issue,'');assert.equal(plan.patch.end,5.873457);assert.equal(plan.patch.start,4.1234567);});
test('boundary contact is allowed and overlap tolerance is exactly 1e-8',()=>{const p=project();assert.equal(api.planLayerTrackMove(p,id('media',1),5,id('track',1)).issue,'');assert.equal(api.planLayerTrackMove(p,id('media',1),5-5e-9,id('track',1)).issue,'');assert.ok(api.planLayerTrackMove(p,id('media',1),5-2e-8,id('track',1)).issue);});
for(const destination of [id('track',2),id('track',4),'A','missing'])test(`wrong or fixed-band target rejects entire move: ${destination}`,()=>{const p=project();assert.ok(api.planLayerTrackMove(p,id('media',1),1,destination).issue);});
for(const start of [NaN,Infinity,-1,7,true,'1'])test(`invalid/too-late start is not individually clamped: ${start}`,()=>{assert.ok(api.planLayerTrackMove(project(),id('media',1),start,id('track',5)).issue);});
test('simultaneous same-track group shift validates final arrangement rather than intermediate collisions',()=>{const p=project();p.manual.media_clips[2].track_id=id('track',3);p.manual.media_clips[2].start=3;p.manual.media_clips[2].end=5;assert.equal(api.layerTrackUpdateIssue(p,[{clip_id:id('media',1),start:2,end:4},{clip_id:id('media',3),start:4,end:6}]),'');assert.ok(api.layerTrackUpdateIssue(p,[{clip_id:id('media',1),start:2,end:4}]));});
test('global custom-text overlap limit stays sixteen across different tracks',()=>{const p=project();p.manual.text_clips=[];for(let n=10;n<27;n++){p.manual.layer_tracks.tracks.push({id:id('track',n),kind:'text',name:'Caption'});p.manual.text_clips.push({id:id('text',n),track_id:id('track',n),start:0,end:2,enabled:false});}assert.match(api.layerTrackState(p).issue,/16/);});
for(const key of ['media_clips','text_clips'])test(`explicit null ${key} cannot become an empty tracked list`,()=>{const p=project();p.manual[key]=null;assert.match(api.layerTrackState(p).issue,/layer list/);});
test('tiny horizontal delta stays exact and is not silently turned into a vertical-only operation',()=>{const p=project(),clip=p.manual.media_clips[0],start=clip.start+5e-10;const plan=api.planLayerTrackMove(p,clip.id,start,clip.track_id);assert.equal(plan.issue,'');assert.equal(plan.patch.start,start);assert.notDeepEqual(copy(plan.patch),{});p.assets.v.status='failed';assert.match(api.planLayerTrackMove(p,clip.id,start,clip.track_id).issue,/Prepare/);});
