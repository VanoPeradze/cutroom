const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const src=n=>fs.readFileSync(path.join(__dirname,'../web',n),'utf8').replace(/^import .*?;\r?\n/gm,'').replace(/^export /gm,'');
const {layerTrackState}=vm.runInNewContext(src('layer-tracks.js')+'\n;({layerTrackState})');
const {rollPair,rollFrame,planRoll,verifyRoll,initRollingEdit}=vm.runInNewContext(src('rolling-edit.js')+'\n;({rollPair,rollFrame,planRoll,verifyRoll,initRollingEdit})',{layerTrackState});
const L='media_'+'1'.repeat(32),R='media_'+'2'.repeat(32),T='track_'+'a'.repeat(32),V1='a',V2='b';
const data=(fps=30,cut=5)=>{
 const c={track_id:T,start:2,end:cut,source_start:1.5,video_source_start:2,speed:1.25,volume_db:0,muted:false,audio_enabled:true,role:'voice',motion:'none',fade_in:.25,fade_out:0};
 return {id:'project_a',revision:4,settings:{fps},sources:{A:{name:'test'}},draft:{output_duration:15,status:'ready'},assets:{[V1]:{kind:'video',name:'Left',duration:16,status:'ready'},[V2]:{kind:'video',name:'Right',duration:14,status:'ready'}},
 manual:{history:{undo_count:2,redo_count:1},sequence:{duration:15},layer_tracks:{version:2,tracks:[{id:T,name:'Story',kind:'visual',locked:false}]},media_clips:[{...c,id:R,asset_id:V2,start:cut,end:8,source_start:3,video_source_start:4,speed:.5,fade_in:0,fade_out:.3},{...c,id:L,asset_id:V1}]}};};
const {libraryVideoAt}=vm.runInNewContext(src('media-studio.js')+'\n;({libraryVideoAt})');
for(const fps of [24,25,30,50,60])test(fps+' FPS: the native rational seek at a saved cut picks only its incoming picture',()=>{
 const frame=5*fps+11,at=frame/fps,stored=Math.round(at*1e9)/1e9,p=data(fps,stored),order={enabled:true,visual:new Map([[L,0],[R,1]])};
 assert.equal(libraryVideoAt(p,(frame-1)/fps,order)?.id,L);
 assert.equal(libraryVideoAt(p,at,order)?.id,R);
 assert.equal(libraryVideoAt(p,(frame+1)/fps,order)?.id,R);
 // Genuine off-grid cut: do not round it early; genuine gap: do not fill it.
 p.manual.media_clips[0].start=p.manual.media_clips[1].end=at+.2/fps;
 assert.equal(libraryVideoAt(p,at,order)?.id,L);p.manual.media_clips[1].end=stored;
 assert.equal(libraryVideoAt(p,at,order),null);
});
const save=(p,plan)=>{const q=structuredClone(p);q.revision++;q.manual.history={undo_count:3,redo_count:0};const [r,l]=q.manual.media_clips;l.end=plan.cut;Object.assign(r,plan.incoming);return q;};
for(const fps of [24,25,30,50,60])for(const side of ['start','end'])test(fps+' FPS '+side+': ordered pair, one-frame moves, exact cut and retained incoming clocks',()=>{
 const p=data(fps),before=structuredClone(p),pair=rollPair(p,side==='start'?R:L,side);assert.equal(pair.issue,'');assert.equal(pair.left.id,L);assert.equal(pair.right.id,R);
 for(const [mode,f] of [['earlier',5*fps-1],['later',5*fps+1],['playhead',6*fps+1]]){
  const frame=rollFrame(pair,mode,6+1/fps);assert.equal(frame,f);const q=planRoll(pair,frame);assert.equal(q.issue,'');assert.equal(q.cut,Math.round(f/fps*1e9)/1e9);
  assert(Math.abs(q.incoming.source_start-(3+q.cut-5))<1.1e-9);assert(Math.abs(q.incoming.video_source_start-(4+(q.cut-5)*.5))<1.1e-9);
  assert.equal(verifyRoll(p,save(p,q),q.detail),'');}assert.deepEqual(p,before);
});
for(const fps of [24,25,30,50,60])test(fps+' FPS fractional and canonical boundary directions do not skip a frame',()=>{
 for(const t of [5+1/3/fps,Math.round((5+1/fps)*1e9)/1e9]){
  const p=data(fps,t),pair=rollPair(p,L,'end');assert.equal(rollFrame(pair,'earlier'),5*fps);
  assert.equal(rollFrame(pair,'later'),t===5+1/3/fps?5*fps+1:5*fps+2);
 }
});
for(const [what,adjust,wanted] of [
 ['locked',p=>p.manual.layer_tracks.tracks[0].locked=true,/Unlock/],
 ['legacy',p=>{delete p.manual.layer_tracks;for(const r of p.manual.media_clips)delete r.track_id;},/Enable editable/],
 ['gap',p=>p.manual.media_clips[0].start+=1e-10,/No touching/],['wrong edge',p=>{},/No touching/],
 ['missing',p=>delete p.assets.a,/known asset/],['not ready',p=>p.assets.a.status='failed',/Prepare/],
 ['motion',p=>p.manual.media_clips[1].motion='pan',/motion/],['inner fade',p=>p.manual.media_clips[0].fade_in=.01,/fades/],
 ['out source',p=>p.manual.media_clips[1].source_start=13,/outgoing source/],
 ['out picture',p=>p.manual.media_clips[1].video_source_start=12.25,/outgoing picture/],
 ['in source',p=>p.manual.media_clips[0].source_start=.001,/incoming source/],
 ['in picture',p=>p.manual.media_clips[0].video_source_start=.001,/incoming picture/],
 ['in hold',p=>p.manual.media_clips[0].video_source_start=15,/held frame/],
 ['outer fade',p=>p.manual.media_clips[1].fade_in=2.9,/outer/],['tiny',p=>{},/0.08/],
 ['same',p=>{},/already/],['fractional frame',p=>{},/integer|frame/],['bad FPS',p=>p.settings.fps=29.97,/unsupported/],
])test('read-only refusal: '+what,()=>{const p=data();adjust(p);const raw=structuredClone(p);
 const frame=what.startsWith('in ')||what==='outer fade'?140:what==='tiny'?61:what==='same'?150:what==='fractional frame'?149.5:160;
 const pair=rollPair(p,L,what==='wrong edge'?'start':'end');assert.match(planRoll(pair,frame).issue,wanted);assert.deepEqual(p,raw);});
for(const [what,change] of [
 ['wrong project',q=>q.id='other'],['old revision',q=>q.revision--],['swapped ids',q=>q.manual.media_clips.reverse()],
 ['duration',q=>q.manual.sequence.duration++],['track',q=>q.manual.layer_tracks.tracks[0].name='Wrong'],
 ['sibling',q=>q.manual.media_clips[1].muted=true],['audio source',q=>q.manual.media_clips[0].source_start+=.01],
 ['picture source',q=>q.manual.media_clips[0].video_source_start+=.01],['settings',q=>q.settings.fps=24],['asset',q=>q.assets.a.name='changed'],
 ['undo count',q=>q.manual.history.undo_count=4],['redo',q=>q.manual.history.redo_count=1]])test('reject mistargeted receipt: '+what,()=>{
 const p=data(),plan=planRoll(rollPair(p,R,'start'),161),q=save(p,plan);change(q);assert(verifyRoll(p,q,plan.detail));
});
function dom(){const make=(m={})=>Object.assign({textContent:'',disabled:false,listeners:{},addEventListener(k,f){this.listeners[k]=f;}},m),root=make({open:true}),
 side=make(),title=make(),status=make(),bs=['earlier','later','playhead'].map(mode=>make({dataset:{roll:mode}}));root.querySelector=q=>q.includes('edge')?side:q.includes('pair')?title:status;root.querySelectorAll=()=>bs;
 return {root,side,title,status,bs};}
test('view-only open/switch never writes; default incoming edge; rapid double activation saves once',async()=>{
 const p=data(),d=dom(),s={project:p,view:2,selected:R,time:5.5,issue:''};let writes=[],resolve;const ctl=initRollingEdit(d.root,{snapshot:()=>s,commit:(owner,detail)=>{writes.push({owner,detail});return new Promise(ok=>resolve=ok);}});
 ctl.refresh();assert.equal(d.side.value,'start');assert.match(d.title.textContent,/Left → Right/);d.side.value='end';d.side.listeners.change();assert(d.bs.every(b=>b.disabled));assert.equal(writes.length,0);
 d.side.value='start';d.side.listeners.change();const wait=d.bs[1].listeners.click();await d.bs[1].listeners.click();assert.equal(writes.length,1);assert.equal(writes[0].detail.frame,151);assert(d.bs.every(b=>b.disabled));resolve(true);await wait;assert.match(d.status.textContent,/Cut saved/);
});
test('click refuses became-stale revision, changed playhead, selection, source mode and closed disclosure',async()=>{
 const p=data(),d=dom(),s={project:p,view:2,selected:L,time:5.2,issue:''};let n=0;const ctl=initRollingEdit(d.root,{snapshot:()=>s,commit:async()=>{n++;}});
 ctl.refresh();s.time=5.6;await d.bs[2].listeners.click();s.project={...p,revision:5};await d.bs[1].listeners.click();
 s.selected=R;await d.bs[1].listeners.click();s.issue='Choose Edited video';await d.bs[1].listeners.click();assert.equal(n,0);
 s.issue='';ctl.refresh();d.root.open=false;await d.bs[1].listeners.click();assert.equal(n,0);
});
