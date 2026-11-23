const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'');
function node(tag){return{tag,tagName:tag.toUpperCase(),children:[],dataset:{},listeners:{},value:'',disabled:false,currentTime:0,duration:10,paused:true,playCalls:0,pauseCalls:0,
  append(...xs){for(const child of xs){child.parentElement=this;this.children.push(child);}},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},
  addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);},removeEventListener(k,fn){this.listeners[k]=(this.listeners[k]||[]).filter(f=>f!==fn);},
  async fire(k,extra={}){const event={target:this,defaultPrevented:false,propagationStopped:false,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.propagationStopped=true;},...extra};for(const fn of [...this.listeners[k]||[]])await fn(event);return event;},
  closest(){for(let target=this;target;target=target.parentElement){if(['input','textarea','select'].includes(target.tag)||target.contenteditable!==undefined&&target.contenteditable!=='false'||['textbox','combobox'].includes(target.role))return target;}return null;},
  showModal(){this.open=true;},close(){this.open=false;this.fire('close');},pause(){this.paused=true;this.pauseCalls++;},play(){this.paused=false;this.playCalls++;return Promise.resolve();},load(){this.released=true;},remove(){this.removed=true;},reportValidity(){return true;}};}
function legacySetup(storage){
  const body=node('body'),timers=new Map();let nextTimer=0;
  const context=vm.createContext({document:{createElement:node,body},localStorage:storage,console,
    setTimeout:(fn,delay)=>{const id=++nextTimer;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source,context);
  let p={id:'p',revision:4,draft:{},assets:{a:{id:'a',kind:'video',status:'ready',duration:10,width:160,height:120,url:'/original/a',name:'Event camera original.mp4'}}};
  const requests=[];
  context.options={project:()=>p,busy:()=>false,pause(){},edit:async(action,payload,guard)=>{assert.equal(guard.isCurrent(),true);requests.push({action,payload});p={...p,revision:p.revision+1,manual:{media_clips:[{id:'appended'}]}};return p;}};
  const studio=vm.runInContext('Object.create(MediaStudio.prototype)',context);studio.options=context.options;studio.flush=async()=>true;studio.render=()=>{};studio.status=node('p');
  return{studio,body,requests,get:()=>p,set:v=>p=v,context,timers,runTimers:async()=>{const pending=[...timers.values()];timers.clear();for(const {fn} of pending)await fn();}};
}
const all=root=>[root,...root.children.flatMap(all)];
const by=(dialog,k)=>all(dialog).find(n=>n.dataset[k]);
const plain=x=>JSON.parse(JSON.stringify(x));

function setup(storage) {
  const h=legacySetup(storage),p=h.get();
  p.draft.output_duration=24;p.editor_sequence={duration:24};
  p.manual={media_clips:[{id:'media_v',asset_id:'a',start:10.5,end:17,source_start:2,video_source_start:1.25,speed:.5,x:0,y:0,w:1,h:1}],text_clips:[{id:'text_title',start:0,end:24}]};
  const stats={pause:0,flush:0};h.studio.selected='media_v';h.studio.pending=new Map();
  h.studio.options.time=()=>12;h.studio.options.pause=()=>stats.pause++;
  h.studio.flush=async()=>{stats.flush++;throw Error('Source match must not flush edits');};
  return {...h,stats,clip:p.manual.media_clips[0],asset:p.assets.a};
}
const video=d=>all(d).find(n=>n.tag==='video');
const points=d=>all(d).filter(n=>n.dataset.shotPoint);
function match(h,time=12,id='media_v') {h.context.args=[h.get(),id,time];return plain(vm.runInContext('librarySourceMatch(...args)',h.context));}
const storageFixture=()=>{const entries=new Map();return {entries,getItem:k=>entries.has(k)?entries.get(k):null,setItem:(k,v)=>entries.set(k,v),removeItem:k=>entries.delete(k)};};
async function ready(h,time=12) {assert.equal(await h.studio.openSourceAt('media_v',time),true);const d=h.studio.shotReview;await video(d).fire('loadedmetadata');return d;}

test('picture matching maps independent slipped start and speed, never normal-speed audio',()=>{
  const h=setup(),before=JSON.stringify(h.get()),plan=match(h);assert.equal(plan.issue,'');assert.equal(plan.sourceTime,2);assert.equal(plan.editTime,12);assert.equal(plan.assetId,'a');assert.equal(JSON.stringify(h.get()),before);
});
for(const speed of [.25,.5,1,1.5,2,4])test(`picture matching preserves fractional source/edit positions at ${speed}x`,()=>{const h=setup();Object.assign(h.clip,{source_start:5.4321,video_source_start:.123456789,speed});const p=match(h,11.333333333);assert.equal(p.issue,'');assert.equal(p.sourceTime,.123456789+(11.333333333-10.5)*speed);});
test('legacy picture clock falls back to source in, including explicit zero',()=>{const h=setup();delete h.clip.video_source_start;assert.equal(match(h).sourceTime,2.75);h.clip.video_source_start=0;assert.equal(match(h).sourceTime,.75);delete h.clip.source_start;delete h.clip.video_source_start;delete h.clip.speed;assert.equal(match(h).sourceTime,1.5);});
test('covered and disabled videos remain inspectable without enabling, reordering or unmuting',()=>{const h=setup();h.clip.enabled=false;h.clip.muted=true;h.get().manual.media_clips.push({...h.clip,id:'cover'});assert.equal(match(h).sourceTime,2);assert.equal(h.clip.enabled,false);assert.equal(h.clip.muted,true);assert.equal(h.get().manual.media_clips.at(-1).id,'cover');});
test('half-open clip range permits exact head and rejects tail/outside/nonfinite clocks',()=>{const h=setup();assert.equal(match(h,10.5).sourceTime,1.25);for(const t of [10.49,17,17.1,NaN,Infinity,'12',null])assert.match(match(h,t).issue,/inside/);});
test('held last-frame positions fail explicitly rather than clamp or claim source progression',()=>{const h=setup();h.clip.speed=4;h.clip.video_source_start=4;assert.match(match(h,12).issue,/holding/);assert.equal(match(h,11.999).issue,'');});
test('invalid saved timing fails closed without coercion or fallback to A',()=>{for(const patch of [{start:'10.5'},{end:10},{start:-1},{source_start:NaN,video_source_start:NaN},{video_source_start:-1},{video_source_start:true},{speed:0},{speed:5},{speed:Infinity}]){const h=setup();Object.assign(h.clip,patch);assert.match(match(h).issue,/invalid/);}});
test('unknown, text, source, unavailable and nonvideo targets never fall back to another clip',()=>{for(const id of ['A','text_title','missing',null]){const h=setup();assert.match(match(h,12,id).issue,/Select/);}for(const patch of [{kind:'audio'},{kind:'image'},{status:'preparing'},{id:'different'},{url:''}]){const h=setup();Object.assign(h.asset,patch);assert.match(match(h).issue,/ready imported video/);}});
test('missing metadata or corrupt sequence fails explicitly',()=>{for(const patch of [{duration:0},{duration:.01},{duration:'10'},{width:0},{height:NaN}]){const h=setup();Object.assign(h.asset,patch);assert.match(match(h).issue,/metadata/);}const h=setup();h.get().editor_sequence.error='Broken sequence';assert.equal(match(h).issue,'Broken sequence');});
test('identity pins saved source clocks, revision and asset metadata without relying on filename',()=>{const h=setup(),p=match(h);h.asset.name='renamed';assert.equal(match(h).token,p.token);for(const change of [()=>h.get().revision++,()=>h.clip.video_source_start+=.01,()=>h.asset.url+='new',()=>h.asset.width++]){const before=match(h).token;change();assert.notEqual(match(h).token,before);}});
test('source match opens existing review, seeks only after metadata, never flushes or writes',async()=>{const h=setup(),before=JSON.stringify(h.get());assert.equal(await h.studio.openSourceAt('media_v',12),true);const d=h.studio.shotReview,v=video(d);assert.equal(v.currentTime,0);assert.equal(v.paused,true);await v.fire('loadedmetadata');assert.equal(v.currentTime,2);assert.equal(v.playCalls,0);assert.match(by(d,'shotMatchOrigin').textContent,/2.000 s.*12.000 s/);assert.match(by(d,'shotMatchOrigin').textContent,/normal speed.*not the edited mix/);await by(d,'shotKeep').fire('click');assert.equal(JSON.stringify(h.get()),before);assert.equal(h.stats.flush,0);assert.equal(h.stats.pause,1);assert.equal(h.requests.length,0);assert.equal(v.released,true);});
test('opening preserves remembered In/Out even when matched picture is outside those marks',async()=>{const storage=storageFixture(),h=setup(storage);h.context.p=h.get();vm.runInContext('saveLibraryShotMarks(p,"a",{source_start:5,source_end:7})',h.context);const saved=JSON.stringify([...storage.entries]);const d=await ready(h);assert.deepEqual(points(d).map(x=>x.value),['5','7']);assert.equal(video(d).currentTime,2);await by(d,'shotKeep').fire('click');assert.equal(JSON.stringify([...storage.entries]),saved);assert.equal(h.requests.length,0);});
test('source match seeks once, not on durationchange or native source playback/seek events',async()=>{const h=setup(),d=await ready(h),v=video(d);v.currentTime=6;await v.fire('durationchange');await v.fire('loadedmetadata');await v.fire('timeupdate');assert.equal(v.currentTime,6);assert.equal(h.requests.length,0);});
test('metadata mismatch cannot seek or save; valid later metadata seeks the pinned original picture once',async()=>{const h=setup();await h.studio.openSourceAt('media_v',12);const d=h.studio.shotReview,v=video(d);v.duration=12;await v.fire('loadedmetadata');assert.equal(v.currentTime,0);assert.equal(by(d,'shotSaveMarks').disabled,true);v.duration=10;await v.fire('durationchange');assert.equal(v.currentTime,2);});
test('a stale revision before metadata never seeks or enables submit',async()=>{const h=setup();await h.studio.openSourceAt('media_v',12);const d=h.studio.shotReview;h.get().revision++;await video(d).fire('loadedmetadata');assert.equal(video(d).currentTime,0);assert.equal(by(d,'shotAppend').disabled,true);assert.match(all(d).find(n=>n.className==='library-shot-status').textContent,/changed/);});
test('changed occurrence clock without revision is still rejected by the pinned mapping',async()=>{const h=setup(),d=await ready(h);h.clip.video_source_start=3;await all(d).find(n=>n.tag==='form').fire('submit');assert.equal(h.requests.length,0);assert.match(all(d).find(n=>n.className==='library-shot-status').textContent,/changed/);});
test('closing or replacing the dialog prevents a delayed old metadata seek',async()=>{const h=setup();await h.studio.openSourceAt('media_v',12);const old=h.studio.shotReview;await h.studio.openSourceAt('media_v',13);const next=h.studio.shotReview;assert.equal(old.open,false);await video(old).fire('loadedmetadata');assert.equal(video(old).currentTime,0);await video(next).fire('loadedmetadata');assert.equal(video(next).currentTime,2.5);});
test('seek failure is honest and does not fabricate a match or write',async()=>{const h=setup();await h.studio.openSourceAt('media_v',12);const d=h.studio.shotReview,v=video(d);Object.defineProperty(v,'currentTime',{get:()=>0,set(){throw Error('blocked seek');}});await v.fire('loadedmetadata');assert.match(by(d,'shotMatchOrigin').textContent,/could not seek/);assert.equal(h.requests.length,0);});
test('match beyond actual loaded duration reports unavailable seek rather than clamping',async()=>{const h=setup();h.clip.video_source_start=9.2;await h.studio.openSourceAt('media_v',12);const d=h.studio.shotReview,v=video(d);v.duration=9.9;await v.fire('loadedmetadata');assert.equal(v.currentTime,0);assert.match(by(d,'shotMatchOrigin').textContent,/could not seek/);});
test('explicit Save marks and Insert keep existing semantics; mere opening never persists them',async()=>{const storage=storageFixture(),h=setup(storage),d=await ready(h);points(d)[0].value='1';points(d)[1].value='2';await points(d)[0].fire('input');assert.equal(storage.entries.size,0);await by(d,'shotSaveMarks').fire('click');assert.equal(storage.entries.size,1);const f=all(d).find(n=>n.tag==='form');await f.fire('submit',{submitter:by(d,'shotInsert')});assert.deepEqual(plain(h.requests),[{action:'media_insert',payload:{asset_id:'a',source_start:1,source_end:2,start:12}}]);});
test('pending edits/import/frame gestures block without flushing, pausing or opening',async()=>{for(const setupBusy of [h=>h.studio.pending.set('media_v',{}),h=>h.studio.saving=Promise.resolve(),h=>h.studio.uploading=true,h=>h.studio.importQueue={running:true},h=>h.studio.frameEditor={pending:true},h=>h.studio.frameEditorState={dragging:true},h=>h.studio.options.busy=()=>true,h=>h.studio.options.sourceMatchBlocked=()=> 'Caption changes pending']){const h=setup();setupBusy(h);assert.equal(await h.studio.openSourceAt('media_v'),false);assert.equal(h.stats.pause,0);assert.equal(h.stats.flush,0);assert.equal(h.studio.shotReview,undefined);assert.equal(h.requests.length,0);}});
test('Full source mode is blocked while disabled and source-lock flags do not block original review',async()=>{const h=setup();h.studio.options.sourceMode=()=>true;assert.match(h.studio.sourceMatchPlan('media_v',12).issue,/Edited/);assert.equal(await h.studio.openSourceAt('media_v'),false);h.studio.options.sourceMode=()=>false;h.clip.enabled=false;h.get().manual.track_locks={A:true,B:true};assert.equal(await h.studio.openSourceAt('media_v'),true);});
test('readiness refresh preserves DOM and follows cursor, pending state and mapped source context',()=>{const h=setup(),b=node('button'),n=node('p');h.studio.root={querySelector:s=>s==='[data-match-source]'?b:n};h.studio.updateSourceMatchAvailability(12);assert.equal(b.disabled,false);assert.match(b.title,/2.000/);h.studio.updateSourceMatchAvailability(17);assert.equal(b.disabled,true);assert.match(n.textContent,/inside/);h.studio.pending.set('x',{});h.studio.updateSourceMatchAvailability(12);assert.equal(b.disabled,true);h.studio.pending.clear();h.studio.updateSourceMatchAvailability(12);assert.equal(b.disabled,false);});
test('post-pause recheck rejects project or clock changes rather than use a stale match',async()=>{for(const change of [h=>h.set({...h.get(),id:'other'}),h=>h.clip.video_source_start=3,h=>h.studio.pending.set('late',{})]){const h=setup();h.studio.options.pause=()=>change(h);assert.equal(await h.studio.openSourceAt('media_v',12),false);assert.equal(h.studio.shotReview,undefined);assert.equal(h.stats.flush,0);assert.equal(h.requests.length,0);}});
test('source opening closes frame-mode transient only after readiness and identity checks',async()=>{const h=setup();let closed=0;h.studio.frameEditor={pending:false,close(){closed++;}};await h.studio.openSourceAt('media_v',12);assert.equal(closed,1);assert.equal(h.requests.length,0);});
function appFunction(name) {const app=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),start=app.indexOf(`function ${name}(`);assert.ok(start>=0);let count=0,body=app.indexOf('{',start),end=body;for(;end<app.length;end++){if(app[end]==='{')count++;if(app[end]==='}'&&--count===0)break;}return app.slice(start,end+1);}
test('timeline bridge validates first, then pauses/seeks clicked edit point and opens source without edit',async()=>{const calls=[],studio={sourceMatchPlan:(id,t)=>{calls.push(['check',id,t]);return {issue:''};},openSourceAt:(id,t)=>{calls.push(['open',id,t]);return true;}};const c=vm.createContext({state:{mediaStudio:studio},pauseAllMedia:()=>calls.push(['pause']),seekSourcePreview:t=>calls.push(['seek',t]),setStatus:()=>{throw Error('unexpected error');}});vm.runInContext(appFunction('openTimelineSource'),c);assert.equal(await vm.runInContext('openTimelineSource("media_v",12.345)',c),true);assert.deepEqual(calls,[['check','media_v',12.345],['pause'],['seek',12.345],['open','media_v',12.345]]);});
test('blocked timeline source opening never changes cursor or dispatches edit',()=>{const calls=[],status={textContent:''};const c=vm.createContext({state:{mediaStudio:{status,sourceMatchPlan:()=>({issue:'Wait'}),openSourceAt:()=>calls.push('open')}},pauseAllMedia:()=>calls.push('pause'),seekSourcePreview:()=>calls.push('seek')});vm.runInContext(appFunction('openTimelineSource'),c);assert.equal(vm.runInContext('openTimelineSource("media_v",12)',c),false);assert.deepEqual(calls,[]);assert.equal(status.textContent,'Wait');});
test('native source bridge and inspector wiring share the same canonical helper',()=>{const app=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');assert.match(app,/mediaSourceIssue: \(id,time\) => state\.mediaStudio\?\.sourceMatchPlan\(id,time\)/);assert.match(app,/onMediaSourceOpen: openTimelineSource/);assert.match(source,/data-match-source aria-describedby="mediaMatchHelp"/);assert.match(source,/this\.updateSourceMatchAvailability\(editTime\)/);});

test('Match and the displayed video agree at every saved cut; exact incoming source In at every supported fps',()=>{
  const h=setup(), p=h.get();
  h.asset.duration=120;
  const left={...h.clip,id:'out',video_source_start:1,speed:.5}, right={...h.clip,id:'in',video_source_start:30.125,speed:2};
  p.manual.media_clips=[left,right];
  for(const fps of [24,25,30,50,60]){
    p.settings={fps};
    for(let frame=2*fps;frame<12*fps;frame++){
      const time=frame/fps,edge=Math.round(time*1e9)/1e9;
      Object.assign(left,{start:edge-2,end:edge});Object.assign(right,{start:edge,end:edge+2});
      h.context.args=[p,time];assert.equal(vm.runInContext('libraryVideoAt(...args).id',h.context),'in');
      assert.match(match(h,time,'out').issue,/inside/);
      assert.equal(match(h,time,'in').sourceTime,30.125);
    }
  }
});

test('Match does not snap genuine off-grid edits or scrub positions to a cut',()=>{
  const h=setup(), t=119/30;
  h.get().settings={fps:30};
  Object.assign(h.clip,{start:t+3e-9,end:t+1,video_source_start:1.25,speed:2});
  assert.match(match(h,t).issue,/inside/);
  h.clip.start=t-4e-9;
  assert.equal(match(h,t).sourceTime,1.25+(t-h.clip.start)*2);
  const offgrid=t+.00123456;assert.equal(match(h,offgrid).sourceTime,1.25+(offgrid-h.clip.start)*2);
  h.clip.end=offgrid;assert.match(match(h,offgrid).issue,/inside/);
});

test('actual Match handler at the decimal shared cut opens incoming picture, never the outgoing review or a write',async()=>{
  const storage=storageFixture(),h=setup(storage),p=h.get(),t=119/30,edge=3.966666667;
  p.settings={fps:30};h.context.p=p;
  vm.runInContext('saveLibraryShotMarks(p,"a",{source_start:5,source_end:6})',h.context);
  const beforeMarks=JSON.stringify([...storage.entries]);
  const out={...h.clip,id:'media_out',start:0,end:edge,video_source_start:3,speed:1};
  Object.assign(h.clip,{start:edge,end:8,video_source_start:1.25,speed:2});
  p.manual.media_clips=[out,h.clip];h.studio.options.time=()=>t;
  const saved=JSON.stringify(p);
  assert.equal(await h.studio.openSourceAt(out.id,t),false);
  assert.ok(!h.studio.shotReview);assert.equal(h.requests.length,0);
  assert.equal(await h.studio.openSourceAt(h.clip.id,t),true);
  const d=h.studio.shotReview;await video(d).fire('loadedmetadata');
  assert.equal(video(d).currentTime,1.25);assert.deepEqual(points(d).map(n=>n.value),['5','6']);
  await by(d,'shotKeep').fire('click');
  assert.equal(h.studio.options.time(),t);assert.equal(JSON.stringify(p),saved);
  assert.equal(JSON.stringify([...storage.entries]),beforeMarks);assert.equal(h.requests.length,0);assert.equal(h.stats.flush,0);
});
