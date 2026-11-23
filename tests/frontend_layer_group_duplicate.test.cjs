const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const ctx=vm.createContext({});vm.runInContext(fs.readFileSync('web/layer-selection.js','utf8').replace(/^export /gm,''),ctx);
const plan=(...args)=>ctx.planLayerGroupDuplicate(...args),verify=(...args)=>ctx.verifyLayerGroupDuplicate(...args);
const clone=x=>JSON.parse(JSON.stringify(x));
const id=(prefix,n)=>prefix+'_'+n.toString(16).padStart(32,'0');
function fixture(tracked=false){
 const p={id:'p',revision:3,name:'Test',draft:{output_duration:20},editor_sequence:{duration:20},settings:{fps:30},assets:{v:{kind:'video',status:'ready'},a:{kind:'audio',status:'ready'}},manual:{media_clips:[{id:id('media',1),asset_id:'v',start:1,end:3,source_start:.25,video_source_start:.125,speed:.5,enabled:false,fade_in:.2},{id:id('media',2),asset_id:'a',start:2,end:4,source_start:.5}],text_clips:[{id:id('text',3),start:1.5,end:2.5,text:'Title',style:'chapter'}],source_mixer:{audio_slot:'B'}}};
 if(tracked){p.manual.layer_tracks={version:2,tracks:['visual','audio','text'].map((kind,i)=>({id:id('track',i+1),kind,name:kind,locked:true}))};[...p.manual.media_clips,...p.manual.text_clips].forEach((row,i)=>row.track_id=id('track',i+1));}
 return p;
}
const ids=p=>[...p.manual.media_clips,...p.manual.text_clips].map(row=>row.id);
function response(p,start=8){
 const c=ctx.duplicateGroupContext(p,ids(p),start);assert.equal(c.issue,'');const after=clone(p);after.revision++;
 const created=c.copies.map((copy,i)=>({source_id:copy.source_id,clip_id:id(copy.source_id.split('_')[0],100+i)}));
 if(c.state.enabled){after.manual.layer_tracks.tracks=c.tracks.map((t,i)=>t.id.startsWith('new:')?{id:id('track',100+i),kind:t.kind,name:'New '+i,locked:false}:clone(t));}
 c.copies.forEach((copy,i)=>{const row={...clone(c.originals[i]),id:created[i].clip_id,start:copy.start,end:copy.end};delete row.track_id;if(c.state.enabled){const lane=c.lanes[i];row.track_id=lane.startsWith('new:')?after.manual.layer_tracks.tracks[Number(lane.slice(4))].id:lane;}after.manual[copy.source_id.startsWith('text_')?'text_clips':'media_clips'].push(row);});
 after.manual.history={undo_count:1,redo_count:0};return {after,created};
}
for(const tracked of [false,true])test('mixed group plans and verifies '+tracked,()=>{const p=fixture(tracked),before=clone(p),{after,created}=response(p);const result=plan(p,ids(p).reverse(),8);assert.equal(result.issue,'');assert.equal(result.delta,7);assert.deepEqual(Array.from(result.copies,row=>row.start),[8,9,8.5]);const receipt=verify(p,after,ids(p).reverse(),8,created);assert.equal(receipt.issue,'');assert.deepEqual(Array.from(receipt.clip_ids),Array.from(created,row=>row.clip_id).reverse());assert.deepEqual(p,before);});
test('zero translation is a real raw-exact copy',()=>{const p=fixture();p.manual.media_clips[0].start=1.123456789123;const {after,created}=response(p,p.manual.media_clips[0].start);assert.equal(verify(p,after,ids(p),p.manual.media_clips[0].start,created).issue,'');assert.equal(after.manual.media_clips[2].start,p.manual.media_clips[0].start);});
test('round each type endpoints, preserve offsets',()=>{const p=fixture();const out=plan(p,ids(p),1/30);assert.equal(out.copies[0].start,.033333333);assert.equal(out.copies[2].start,.533333);});
for(const [label,edit] of Object.entries({single:(p,x)=>x.pop()&&x.pop(),duplicates:(p,x)=>x[1]=x[0],foreign:(p,x)=>x[0]=id('media',999),source:(p,x)=>x[0]='A',offline:p=>p.assets.v.status='failed',unknown:p=>p.assets.v.kind='mystery',badTiming:p=>p.manual.media_clips[0].end=1.01,orphan:p=>p.manual.media_clips[0].track_id=id('track',9)}))test('plan refuses '+label,()=>{const p=fixture(),x=ids(p);edit(p,x);assert.ok(plan(p,x,8).issue);});
for(const start of [-1,NaN,Infinity,'8',true,19,21])test('plan refuses destination '+String(start),()=>{const p=fixture();assert.ok(plan(p,ids(p),start).issue);});
test('capacity is aggregate',()=>{const p=fixture();for(let n=3;n<=200;n++)p.manual.media_clips.push({...p.manual.media_clips[0],id:id('media',n)});assert.ok(plan(p,[id('media',1),id('media',2)],8).issue);});
test('all new text considered together including disabled',()=>{const p=fixture();p.manual.text_clips=Array.from({length:9},(_,i)=>({id:id('text',i+1),start:1,end:3,enabled:false,text:'x'}));assert.ok(plan(p,p.manual.text_clips.map(r=>r.id),1).issue);});
test('future model fails closed',()=>{const p=fixture(true);p.manual.layer_tracks.version=3;assert.ok(plan(p,ids(p),8).issue);});
test('full locked model cannot allocate new lanes',()=>{const p=fixture(true);while(p.manual.layer_tracks.tracks.length<4096)p.manual.layer_tracks.tracks.push({id:id('track',p.manual.layer_tracks.tracks.length+1),kind:'visual',name:'Locked',locked:true});assert.ok(plan(p,ids(p),8).issue);});
test('available unlocked lanes at capacity work without migration',()=>{const p=fixture(true);p.manual.layer_tracks.tracks.forEach(t=>t.locked=false);while(p.manual.layer_tracks.tracks.length<4096)p.manual.layer_tracks.tracks.push({id:id('track',p.manual.layer_tracks.tracks.length+1),kind:'visual',name:'Locked',locked:true});assert.equal(plan(p,ids(p),8).issue,'');});
test('visual allocation sorted by track, persisted raw order and audio retained',()=>{const p=fixture(true);const lower={...p.manual.media_clips[0],id:id('media',4),track_id:id('track',4)};p.manual.layer_tracks.tracks.unshift({id:lower.track_id,kind:'visual',name:'Lower',locked:false});p.manual.media_clips.push(lower);const c=ctx.duplicateGroupContext(p,ids(p).reverse(),1);assert.equal(c.issue,'');assert.deepEqual(Array.from(c.copies,r=>r.source_id),ids(p));const upperIndex=c.tracks.findIndex(t=>t.id===c.lanes[0]),lowerIndex=c.tracks.findIndex(t=>t.id===c.lanes[2]);assert.ok(upperIndex>lowerIndex);const {after,created}=response(p,1);assert.equal(verify(p,after,ids(p),1,created).issue,'');});
const tamper={
 project:(a,c)=>a.id='other',revision:a=>a.revision=3,fractionalRevision:a=>a.revision=4.5,
 missingMapping:(a,c)=>c.pop(),repeatedMapping:(a,c)=>c[1]={...c[0]},wrongKind:(a,c)=>c[0].clip_id=id('text',100),oldId:(a,c)=>c[0].clip_id=id('media',1),extraKey:(a,c)=>c[0].extra=true,
 original:a=>a.manual.media_clips[0].source_start=9,extraCopy:a=>a.manual.media_clips.push({...a.manual.media_clips[2],id:id('media',900)}),missingCopy:a=>a.manual.text_clips.pop(),wrongClock:a=>a.manual.media_clips[2].source_start=3,wrongEnabled:a=>a.manual.media_clips[2].enabled=true,wrongLength:a=>a.manual.media_clips[2].end-=.1,wrongStyle:a=>a.manual.text_clips[1].style='plain',settings:a=>a.settings.fps=60,sources:a=>a.sources={A:{}},duration:a=>a.editor_sequence.duration=30,mixer:a=>a.manual.source_mixer.audio_slot='A',asset:a=>a.assets.v.status='failed',draft:a=>a.draft.output_duration=30,
 originalTrack:a=>a.manual.layer_tracks.tracks[0].locked=false,newLocked:a=>a.manual.layer_tracks.tracks[3].locked=true,wrongTrack:a=>a.manual.media_clips[2].track_id=a.manual.layer_tracks.tracks[0].id,extraTrack:a=>a.manual.layer_tracks.tracks.push({id:id('track',999),kind:'visual',name:'x',locked:false}),future:a=>a.manual.layer_tracks.version=3
};
for(const [name,change] of Object.entries(tamper))test('receipt fails closed: '+name,()=>{const p=fixture(true),{after,created}=response(p);change(after,created);const r=verify(p,after,ids(p),8,created);assert.ok(r.issue);assert.equal(r.clip_ids,null);assert.equal(r.mapping,null);});
test('mapping order is not identity, identical copies never guessed',()=>{const p=fixture();p.manual.media_clips[1]={...p.manual.media_clips[0],id:id('media',2)};const {after,created}=response(p);assert.equal(verify(p,after,ids(p),8,created.reverse()).issue,'');});
const extraCases={nullModel:p=>p.manual.layer_tracks=null,orphanModel:p=>delete p.manual.layer_tracks,nonBooleanLock:p=>p.manual.layer_tracks.tracks[0].locked='true',overlap:p=>{p.manual.media_clips.push({...p.manual.media_clips[0],id:id('media',77)});},duplicateTrack:p=>p.manual.layer_tracks.tracks.push({...p.manual.layer_tracks.tracks[0]})};
for(const [name,change] of Object.entries(extraCases))test('track admission refuses '+name,()=>{const p=fixture(true);change(p);assert.ok(plan(p,ids(p).slice(0,2),8).issue);});
test('text-only copy does not require unrelated media ready',()=>{const p=fixture(true);p.manual.text_clips.push({...p.manual.text_clips[0],id:id('text',9),start:5,end:6});p.assets.v.status='failed';const selected=p.manual.text_clips.map(row=>row.id);assert.equal(plan(p,selected,8).issue,'');});
test('receipt accepts omitted empty unselected collection',()=>{const p=fixture();delete p.manual.text_clips;const x=p.manual.media_clips.map(row=>row.id);const c=plan(p,x,8),after=clone(p);after.revision++;const created=x.map((source_id,i)=>({source_id,clip_id:id('media',100+i)}));after.manual.media_clips.push(...c.copies.map((copy,i)=>({...p.manual.media_clips[i],id:created[i].clip_id,start:copy.start,end:copy.end})));assert.equal(verify(p,after,x,8,created).issue,'');});
test('declared failure always leaves input and nested source content unchanged',()=>{const p=fixture(true),saved=clone(p);plan(p,ids(p),19);const {after,created}=response(p);after.manual.text_clips[1].text='wrong';verify(p,after,ids(p),8,created);assert.deepEqual(p,saved);});

test('receipt permits only known structural draft audit changes',()=>{const p=fixture(),{after,created}=response(p);after.draft.edited_at='2026-11-16T00:00:00Z';after.draft.status='ready';assert.equal(verify(p,after,ids(p),8,created).issue,'');after.draft.status='failed';assert.ok(verify(p,after,ids(p),8,created).issue);});

for(const draft of [[],'ready',true,false])test('duplicate rejects malformed raw draft '+JSON.stringify(draft),()=>{const p=fixture();p.draft=draft;assert.ok(plan(p,ids(p),8).issue);});
