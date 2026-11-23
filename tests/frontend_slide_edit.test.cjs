const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const src=n=>fs.readFileSync(path.join(__dirname,'../web',n),'utf8').replace(/^import .*?;\r?\n/gm,'').replace(/^export /gm,'');
const {layerTrackState}=vm.runInNewContext(src('layer-tracks.js')+'\n;({layerTrackState})');
const {rollPair,rollFrame,planRoll,verifyRoll,initRollingEdit}=vm.runInNewContext(src('rolling-edit.js')+'\n;({rollPair,rollFrame,planRoll,verifyRoll,initRollingEdit})',{layerTrackState});
const [L,M,R,U]=['1','4','2','3'].map(c=>'media_'+c.repeat(32)),T='track_'+'a'.repeat(32),X='track_'+'b'.repeat(32),round=x=>Math.round(x*1e9)/1e9;
function data(fps=30,kind='video'){
 const row={track_id:T,source_start:1.,speed:kind==='video'?1.5:1,fade_in:0,fade_out:0,motion:'none',role:'voice',volume_db:-2,enabled:true,audio_enabled:kind!=='image'};
 const assets={};for(const [id,k] of [['a',kind],['m',kind],['b',kind],['u','image']])assets[id]={kind:k,name:id.toUpperCase(),duration:k==='image'?0:20,status:'ready'};
 return {id:'p1',revision:5,assets,settings:{fps},draft:{output_duration:12},manual:{sequence:{duration:12},history:{undo_count:2,redo_count:1},text_clips:[],layer_tracks:{version:2,tracks:[{id:T,name:'Story',kind:kind==='audio'?'audio':'visual',locked:false},{id:X,name:'Other',kind:'visual',locked:true}]},media_clips:[
 {...row,id:R,asset_id:'b',start:6.5,end:8.5,source_start:2,video_source_start:3,speed:kind==='video'?.5:1,fade_out:.3},
 {...row,id:U,asset_id:'u',start:4,end:7,source_start:0,track_id:X,speed:1},
 {...row,id:M,asset_id:'m',start:5,end:6.5,source_start:1.75,video_source_start:2.25,speed:kind==='video'?2:1,fade_in:.12,fade_out:.18,motion:kind==='audio'?'none':'pan'},
 {...row,id:L,asset_id:'a',start:3,end:5,video_source_start:2,fade_in:.25}
 ]}};
}
const save=(p,plan)=>{const q=structuredClone(p);q.revision++;q.manual.history={undo_count:3,redo_count:0};const [r,u,m,l]=q.manual.media_clips;l.end=m.start=plan.cut;m.end=plan.trailing;Object.assign(r,plan.incoming);return q;};
for(const rate of [24,25,30,50,60])for(const kind of ['video','audio','image'])for(const dir of [-1,1])test(rate+' '+kind+' '+dir+': entire center content remains intact; one receipt covers both seams',()=>{
 const p=data(rate,kind),raw=structuredClone(p),trio=rollPair(p,M,'slide'),frame=5*rate+dir*7,q=planRoll(trio,frame);assert.equal(trio.issue,'');assert.equal(q.issue,'');
 assert.equal(rollFrame(trio,dir>0?'later':'earlier'),5*rate+dir);assert.equal(rollFrame(trio,'playhead',frame/rate),frame);assert.equal(q.detail.left_id,L);assert.equal(q.detail.clip_id,M);assert.equal(q.detail.right_id,R);
 const delta=q.trailing-6.5;assert(Math.abs((q.trailing-q.cut)-1.5)<1.1e-9);if(kind!=='image')assert.equal(q.incoming.source_start,round(2+delta));if(kind==='video')assert.equal(q.incoming.video_source_start,round(3+delta*.5));
 const after=save(p,q);assert.equal(verifyRoll(p,after,q.detail),'');const middle=after.manual.media_clips[2];for(const [k,v] of Object.entries(raw.manual.media_clips[2]))if(k!=='start'&&k!=='end')assert.equal(middle[k],v);
 assert.deepEqual(p,raw);});
for(const [start,end,target,expected] of [[5.033333333,5.366666667,152,5.4],[5,5.333333333,151,5.366666667],[5.01234567891,6.12567891237,153,undefined]])test('frame-aligned or true subframe duration '+start,()=>{
 const p=data(),[r,u,m,l]=p.manual.media_clips;l.end=m.start=start;m.end=r.start=end;const t=planRoll(rollPair(p,M,'slide'),target);assert.equal(t.issue,'');
 if(expected!==undefined)assert.equal(t.trailing,expected);else {assert.equal(t.cut,start+2/30);assert.equal(t.trailing,end+2/30);assert.equal(rollFrame(rollPair(p,M,'slide'),'earlier'),150);assert.equal(rollFrame(rollPair(p,M,'slide'),'later'),152);}});
for(const [what,edit,n,wanted] of [
 ['no prior',p=>p.manual.media_clips[3].end-=1e-10,158,/both sides/],['no next',p=>p.manual.media_clips[0].start+=.07,158,/both sides/],
 ['locked',p=>p.manual.layer_tracks.tracks[0].locked=true,159,/Unlock/],['middle gone',p=>{delete p.assets.m},157,/known asset/],
 ['middle offline',p=>p.assets.m.status='waiting',157,/three/],['left motion',p=>p.manual.media_clips[3].motion='pan',159,/neighbor/],
 ['right motion',p=>p.manual.media_clips[0].motion='zoom_in',143,/neighbor/],['left fade',p=>p.manual.media_clips[3].fade_out=.05,153,/fades/],
 ['right fade',p=>p.manual.media_clips[0].fade_in=.05,147,/fades/],['out extent',p=>p.manual.media_clips[3].source_start=18,160,/outgoing source/],
 ['in extent',p=>p.manual.media_clips[0].source_start=.02,140,/incoming source/],['empty handle',p=>p.manual.media_clips[0].video_source_start=21,140,/held/],
 ['short left',p=>0,91,/0.08/],['short right',p=>0,208,/0.08/],['noop',p=>0,150,/already/]
])test('refusal leaves all saved rows alone: '+what,()=>{const p=data();edit(p);const before=structuredClone(p);assert.match(planRoll(rollPair(p,M,'slide'),n).issue,wanted);assert.deepEqual(p,before);});
for(const [label,damage] of [['middle source',p=>p.manual.media_clips[2].source_start++],['middle fade',p=>p.manual.media_clips[2].fade_out=0],['middle speed',p=>p.manual.media_clips[2].speed=1],
 ['trailing edge',p=>p.manual.media_clips[0].start+=1e-5],['left edge',p=>p.manual.media_clips[3].end-=1e-5],['other clip',p=>p.manual.media_clips[1].start=.5],['extra undo',p=>p.manual.history.undo_count++],
 ['lost selected',p=>p.manual.media_clips.splice(2,1)],['wrong project',p=>p.id='p2']])test('reject a mismatched slide receipt: '+label,()=>{
 const p=data(),q=planRoll(rollPair(p,M,'slide'),161),res=save(p,q);damage(res);assert(verifyRoll(p,res,q.detail));});
function dom(){const node=o=>Object.assign({textContent:'',disabled:false,ls:{},addEventListener(k,f){this.ls[k]=f;}},o),root=node({open:true}),title=node(),status=node(),buttons=['earlier','later','playhead'].map(slide=>node({dataset:{slide}}));
 root.querySelector=q=>q.includes('pair')?title:status;root.querySelectorAll=()=>buttons;return {root,title,status,buttons};}
test('changing playhead before applying is read-only; clicking twice still saves one captured three-ID slide',async()=>{
 let s={project:data(),selected:M,view:2,time:5.3,issue:''};const d=dom(),writes=[];let resolve;const c=initRollingEdit(d.root,{snapshot:()=>s,commit:(o,x)=>{writes.push([o,x]);return new Promise(r=>resolve=r);}},true);c.refresh();
 assert.match(d.title.textContent,/Story.*A.*M.*B.*00:00:05:00 to 00:00:06:15 \(45 frames\)/);assert.match(d.status.textContent,/At playhead: 00:00:05:09 to 00:00:06:24/);s.time=5.4;await d.buttons[2].ls.click();assert.equal(writes.length,0);
 c.refresh();const pending=d.buttons[2].ls.click();await d.buttons[2].ls.click();assert.equal(writes.length,1);assert.deepEqual(JSON.parse(JSON.stringify(writes[0][1])),{left_id:L,clip_id:M,right_id:R,frame:162});assert(d.buttons.every(b=>b.disabled));
 s={...s,selected:U};resolve(true);await pending;assert.doesNotMatch(d.status.textContent,/Clip slid/);assert.equal(writes.length,1);});
