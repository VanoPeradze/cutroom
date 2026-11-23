const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context=vm.createContext({});vm.runInContext(fs.readFileSync('web/layer-tracks.js','utf8').replace(/^export /gm,''),context);
const api=vm.runInContext('({layerTrackState,layerTrackRanks,layerTrackUpdateIssue,planLayerTrackMove,planLibraryTrackPlacement,createLibraryPlacementPlanner,layerMutationIssue,layerAssetMutationIssue,createLayerMutationPlanner})',context);
const id=(type,n)=>`${type}_${String(n).padStart(32,'0')}`;
function project(){return {id:'project_tracks',revision:4,draft:{output_duration:8},editor_sequence:{duration:8},assets:{v:{kind:'video',status:'ready'},a:{kind:'audio',status:'ready'},i:{kind:'image',status:'ready'}},manual:{layer_tracks:{version:1,tracks:[
 {id:id('track',1),kind:'visual',name:'Background'}, {id:id('track',2),kind:'audio',name:'Sound'},
 {id:id('track',3),kind:'visual',name:'Foreground'}, {id:id('track',4),kind:'text',name:'Titles'},
 {id:id('track',5),kind:'visual',name:'Empty'}, {id:id('track',6),kind:'text',name:'Top text'}]},
 media_clips:[{id:id('media',1),asset_id:'v',track_id:id('track',3),start:1,end:3,source_start:.5,video_source_start:1,speed:.5},
 {id:id('media',2),asset_id:'a',track_id:id('track',2),start:1,end:3,enabled:false},
 {id:id('media',3),asset_id:'i',track_id:id('track',1),start:2,end:5}],
 text_clips:[{id:id('text',1),track_id:id('track',6),start:.25,end:2,kind:'title'},
 {id:id('text',2),track_id:id('track',4),start:.5,end:3,kind:'caption'}]}};}


function locked(){const p=project();p.manual.layer_tracks.version=2;for(const t of p.manual.layer_tracks.tracks)t.locked=[2,3,6].includes(Number(t.id.slice(6)));p.assets.v.duration=8;return p;}
const issue=(p,a,d)=>api.layerMutationIssue(p,a,d);
test('v1 stays valid unchanged and v2 explicit booleans validate without mutation',()=>{assert.equal(api.layerTrackState(project()).issue,'');const p=locked(),before=JSON.stringify(p);assert.equal(api.layerTrackState(p).issue,'');assert.equal(JSON.stringify(p),before);});
for(const value of [undefined,null,0,1,'true'])test('v2 rejects nonboolean lock '+value,()=>{const p=locked();p.manual.layer_tracks.tracks[0].locked=value;assert.ok(api.layerTrackState(p).issue);});
test('v1 rejects lock field, future rejects model',()=>{const p=project();p.manual.layer_tracks.tracks[0].locked=false;assert.ok(api.layerTrackState(p).issue);p.manual.layer_tracks.version=3;assert.ok(api.layerTrackState(p).issue);});
test('locked ranks identical to unlocked ranks',()=>{const p=locked(),a=api.layerTrackRanks(p);for(const t of p.manual.layer_tracks.tracks)t.locked=false;const b=api.layerTrackRanks(p);assert.deepEqual([...a.visual],[...b.visual]);assert.deepEqual([...a.text],[...b.text]);});
for(const a of ['media_remove','media_split','media_trim','media_slip','media_move','media_set_enabled','media_transform'])test(a+' rejects protected selected occurrence',()=>assert.match(issue(locked(),a,{clip_id:id('media',1)}),/locked/));
for(const a of ['text_remove','text_split','text_trim','text_move','text_set_enabled'])test(a+' rejects protected text',()=>assert.match(issue(locked(),a,{clip_id:id('text',1)}),/locked/));
test('all update fields protected including content/gain; exact no-op allowed',()=>{const p=locked();assert.ok(issue(p,'media_update',{clip_id:id('media',1),volume_db:-4}));assert.ok(issue(p,'text_update',{clip_id:id('text',1),text:'new'}));assert.equal(issue(p,'media_update',{clip_id:id('media',1),start:1}),'');});
test('staged patch validator blocks movement into and out of locked tracks',()=>{const p=locked();assert.ok(api.layerTrackUpdateIssue(p,[{clip_id:id('media',1),start:4,end:6}]));assert.ok(api.layerTrackUpdateIssue(p,[{clip_id:id('media',3),track_id:id('track',3),start:4,end:7}]));});
test('move planner inherits exact protected patch admission',()=>assert.ok(api.planLayerTrackMove(locked(),id('media',1),4,id('track',5)).issue));
test('group mutation blocks any protected member including disabled audio',()=>{const p=locked();for(const a of ['layers_move','layers_remove'])assert.ok(issue(p,a,{clip_ids:[id('media',3),id('media',2)],delta:1}));assert.equal(issue(p,'layers_move',{clip_ids:[id('media',2)],delta:0}),'');});
test('duplicates are reads of protected originals',()=>{const p=locked();assert.equal(issue(p,'media_duplicate',{clip_id:id('media',1),start:4}),'');assert.equal(issue(p,'text_duplicate',{clip_id:id('text',1),start:4}),'');});
test('shared asset key changes protect every referenced locked occurrence',()=>{const p=locked();assert.ok(api.layerAssetMutationIssue(p,'v'));assert.ok(api.layerAssetMutationIssue(p,'a'));assert.equal(api.layerAssetMutationIssue(p,'i'),'');assert.ok(issue(p,'reset_chroma_key',{slot:'v'}));assert.equal(issue(p,'set_chroma_key',{slot:'A'}),'');});
test('rename/unlock/select/source audition/export remain allowed',()=>{const p=locked();for(const a of ['layer_track_rename','layer_track_lock','select','source_review','export','set_audio_mixer'])assert.equal(issue(p,a,{track_id:id('track',3)}),'');});
test('reordering cannot cross protected tracks even when moved lane is unlocked',()=>{const p=locked();assert.ok(issue(p,'layer_track_reorder',{track_id:id('track',1),position:'front'}));assert.equal(issue(p,'layer_track_reorder',{track_id:id('track',1),position:'back'}),'');assert.ok(issue(p,'layer_track_remove',{track_id:id('track',3)}));});
test('explicit creation rejects protected destination while automatic remains automatic',()=>{const p=locked();assert.ok(api.planLibraryTrackPlacement(p,'v',4,{trackId:id('track',3)}).issue);assert.equal(api.planLibraryTrackPlacement(p,'v',4,{}).issue,'');assert.ok(issue(p,'media_append',{track_id:id('track',3)}));});
test('all-layer insert blocks shifting/splitting protected content but permits later/tail',()=>{const p=locked();for(const a of ['sequence_insert_all','media_insert']){assert.ok(issue(p,a,{start:2}));assert.equal(issue(p,a,{start:4}),'');}assert.ok(api.planLibraryTrackPlacement(p,'v',2,{insert:true}).issue);assert.equal(api.planLibraryTrackPlacement(p,'v',8,{append:true}).issue,'');});
test('ripple removal protects later contents, source-only remains separate',()=>{const p=locked();assert.ok(issue(p,'sequence_ripple_delete',{start:.1,end:.5}));assert.equal(issue(p,'sequence_ripple_delete',{start:4,end:5}),'');assert.equal(issue(p,'track_remove_range',{slot:'A',start:0,end:1}),'');});
test('replace custom caption import blocks only protected custom captions',()=>{const p=locked();assert.equal(issue(p,'text_import',{replace:true}),'');p.manual.text_clips[0].kind='caption';assert.ok(issue(p,'text_import',{replace:true}));assert.equal(issue(p,'text_import',{replace:false}),'');});
test('close gaps blocks protected rows shifted by real gaps, not covered gaps',()=>{const p=locked();assert.ok(issue(p,'sequence_close_gaps',{}));p.manual.source_tracks={A:[{start:0,end:8}],B:[]};assert.equal(issue(p,'sequence_close_gaps',{}),'');assert.equal(issue(p,'sequence_close_gaps',{slot:'A'}),'');});
test('batch placement still evaluates exact time-dependent protection',()=>{const p=locked(),plan=api.createLibraryPlacementPlanner(p);assert.ok(plan('v',2,{insert:true}).issue);assert.equal(plan('v',4,{insert:true}).issue,'');});

test('keyed background identity is protected even without own occurrence',()=>{const p=locked();p.manual.chroma_key={v:{enabled:true,background_asset_id:'background'}};assert.ok(api.layerAssetMutationIssue(p,'background'));p.manual.chroma_key.v.background_mode='transparent';assert.equal(api.layerAssetMutationIssue(p,'background'),'');});
test('already-saved enable/move/trim/slip are harmless reads',()=>{const p=locked(),clip_id=id('media',1);for(const [a,d]of [['media_move',{start:1}],['media_trim',{edge:'start',time:1}],['media_slip',{source_start:.5}],['media_set_enabled',{enabled:true}]])assert.equal(issue(p,a,{clip_id,...d}),'');});

test('mutation batch validates once for all same-pass manager and Chroma checks',()=>{
 const ctx=vm.createContext({});vm.runInContext(fs.readFileSync('web/layer-tracks.js','utf8').replace(/^export /gm,''),ctx);
 vm.runInContext('globalThis.calls=0;const original=layerTrackState;layerTrackState=p=>{calls++;return original(p)};',ctx);
 ctx.project=locked();vm.runInContext(`const plan=createLayerMutationPlanner(project);for(let i=0;i<100;i++){plan('layer_track_reorder',{track_id:project.manual.layer_tracks.tracks[0].id,position:'front'});plan('set_chroma_key',{slot:'v'});}globalThis.batchCalls=calls;layerMutationIssue(project,'media_remove',{clip_id:project.manual.media_clips[0].id});`,ctx);
 assert.equal(ctx.batchCalls,1);assert.equal(ctx.calls,2);
});
test('new readiness pass and direct admission see incoming saved locks',()=>{
 const before=project(),first=api.createLayerMutationPlanner(before),payload={clip_id:id('media',1)};
 assert.equal(first('media_remove',payload),'');
 const incoming=locked(),next=api.createLayerMutationPlanner(incoming);
 assert.ok(next('media_remove',payload));assert.ok(api.layerMutationIssue(incoming,'media_remove',payload));
 // The old closure describes only its old snapshot, so callers must create next each pass.
 assert.equal(first('media_remove',payload),'');
});
test('mutation batch fails closed for invalid model and permits omitted payload on safe actions',()=>{
 const p=locked();assert.equal(api.createLayerMutationPlanner(p)('layer_track_add'),'');
 p.manual.layer_tracks.version=999;assert.ok(api.createLayerMutationPlanner(p)('layer_track_add'));
});
