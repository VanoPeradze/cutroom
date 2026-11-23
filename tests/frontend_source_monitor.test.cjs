const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'');
const plain=x=>JSON.parse(JSON.stringify(x));
function node(tag){return {tag,tagName:tag.toUpperCase(),children:[],dataset:{},listeners:{},value:'',disabled:false,currentTime:0,duration:10,paused:true,playbackRate:1,
 append(...xs){for(const x of xs){if(x.parentElement)x.parentElement.children=x.parentElement.children.filter(n=>n!==x);x.parentElement=this;this.children.push(x);}},prepend(...xs){for(const x of xs)x.parentElement=this;this.children.unshift(...xs);},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},
 addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);},removeEventListener(k,fn){this.listeners[k]=(this.listeners[k]||[]).filter(f=>f!==fn);},
 async fire(k,extra={}){const e={target:this,defaultPrevented:false,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;},...extra};for(const fn of [...this.listeners[k]||[]])await fn(e);return e;},
 closest(){for(let n=this;n;n=n.parentElement)if(['input','textarea','select'].includes(n.tag))return n;return null;},
 pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();},load(){this.released=true;},remove(){this.removed=true;if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(x=>x!==this);},reportValidity(){return true;},focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;},showModal(){throw Error('Source monitor must not open a modal');}};}
function setup(){
 let p={id:'p',revision:4,draft:{output_duration:8},editor_sequence:{duration:8},manual:{media_clips:[],text_clips:[]},assets:{a:{id:'a',kind:'video',status:'ready',duration:10,width:160,height:120,url:'/original/a',name:'Original.mp4'}}};
 const root=node('section'),body=node('body'),entries=new Map(),timers=new Map();let nextTimer=0;
 const context=vm.createContext({console,document:{createElement:node,body},localStorage:{getItem:k=>entries.get(k)??null,setItem:(k,v)=>entries.set(k,v),removeItem:k=>entries.delete(k)},setTimeout:fn=>{timers.set(++nextTimer,fn);return nextTimer;},clearTimeout:k=>timers.delete(k)});
 vm.runInContext(source,context);
 const h={root,body,context,entries,timers,time:2,view:1,visible:true,issue:'',busy:false,programPauses:[],placements:[],requests:[],renders:0,opens:0,get:()=>p,set:v=>p=v};
 const studio=vm.runInContext('Object.create(MediaStudio.prototype)',context);h.studio=studio;studio.root=root;studio.status=node('p');studio.pending=new Map();studio.flush=async()=>true;studio.render=()=>{h.renders++;studio.syncSourceMonitor();};
 studio.options={project:()=>p,time:()=>h.time,busy:()=>h.busy,pause(){},sourceMonitor:{open:()=>{h.opens++;return true;},token:()=>h.view,visible:()=>h.visible,issue:()=>h.issue,pauseProgram:v=>h.programPauses.push(v),placed:(clip,result)=>{h.placements.push({clip:plain(clip),revision:result.revision});h.time=clip.end;}},edit:async(action,payload,guard)=>{
   assert.equal(guard.strictRevision,true);assert.equal(guard.isCurrent(),true);assert.equal(guard.admissionCurrent(),true);h.requests.push({action,payload:plain(payload),guard});
   const start=action==='media_insert'?payload.start:p.editor_sequence.duration,len=payload.source_end-payload.source_start;
   const clip={id:'media_'+h.requests.length,asset_id:payload.asset_id,start,end:start+len,source_start:payload.source_start};
   p={...p,revision:p.revision+1,editor_sequence:{duration:p.editor_sequence.duration+len},manual:{...p.manual,media_clips:[...p.manual.media_clips,clip]}};
   // The real host renders and publishes temporary cursor 0 inside its save.
   const previous=h.time;h.time=0;studio.syncSourceMonitor();h.time=previous;studio.syncSourceMonitor();return p;
 }};
 return h;
}
const all=n=>[n,...n.children.flatMap(all)],by=(d,key)=>all(d).find(n=>n.dataset[key]),video=d=>all(d).find(n=>n.tag==='video'),form=d=>all(d).find(n=>n.tag==='form'),points=d=>all(d).filter(n=>n.dataset.shotPoint);
async function ready(h){assert.equal(await h.studio.reviewShot('a'),true);const d=h.studio.shotReview;await video(d).fire('loadedmetadata');return d;}
async function marks(d,a,b){points(d)[0].value=String(a);points(d)[1].value=String(b);await points(d)[0].fire('input');}
async function submit(d,kind='Append'){await form(d).fire('submit',{submitter:by(d,'shot'+kind)});}
const status=d=>all(d).find(n=>n.className==='library-shot-status').textContent;

test('source uses a contextual region in Media, not a modal or cloned control tree',async()=>{const h=setup(),before=JSON.stringify(h.get()),d=await ready(h);assert.equal(d.tag,'section');assert.equal(d.role,'region');assert.equal(d.dataset.editorShortcuts,'off');assert.equal(d.parentElement,h.root);assert.equal(h.root.dataset.sourceMonitorOpen,'true');assert.equal(h.body.children.length,0);assert.equal(h.opens,1);assert.equal(d.focused,true);assert.equal(JSON.stringify(h.get()),before);assert.equal(h.requests.length,0);assert.equal(by(d,'shotKeep').textContent,'Close source');});
test('source ranges remain exact and editable after own sequential Append and Insert saves',async()=>{const h=setup(),d=await ready(h),v=video(d);await marks(d,1.125,3.25);v.currentTime=2.1;await submit(d);assert.equal(h.studio.shotReview,d);assert.equal(d.open,true);assert.equal(video(d),v);assert.equal(v.currentTime,2.1);assert.deepEqual(points(d).map(x=>x.value),['1.125','3.25']);assert.equal(h.time,10.125);assert.equal(by(d,'shotRefresh').hidden,true);await marks(d,3.25,4.75);h.time=4;h.studio.syncSourceMonitor();await submit(d,'Insert');assert.equal(h.time,5.5);assert.equal(h.requests.length,2);assert.deepEqual(h.requests.map(x=>x.action),['media_append','media_insert']);assert.equal(h.requests[1].payload.start,4);assert.equal(h.studio.selected,'media_2');assert.equal(h.get().editor_sequence.duration,11.625);assert.equal(h.entries.size,0);});
test('ruler seeking refreshes destination/readiness without changing source time or marks',async()=>{const h=setup(),d=await ready(h),v=video(d);await marks(d,1,3);v.currentTime=1.75;h.time=6.123456;h.studio.syncSourceMonitor();assert.match(by(d,'shotDestination').textContent,/6\.123/);assert.equal(v.currentTime,1.75);await submit(d,'Insert');assert.equal(h.requests[0].payload.start,6.123456);assert.ok(Math.abs(h.time-8.123456)<1e-9);});
test('submit rechecks live destination even without a preceding paint',async()=>{const h=setup(),d=await ready(h);await marks(d,0,1);h.time=3.23456789;await submit(d,'Insert');assert.equal(h.requests[0].payload.start,3.23456789);});
test('unrelated revision never silently repins; refresh is explicit, paused and preserves marks',async()=>{const h=setup(),d=await ready(h),v=video(d);await marks(d,2.125,5.5);v.currentTime=3;v.paused=false;h.set({...h.get(),revision:9});h.time=5;h.studio.syncSourceMonitor();assert.equal(v.paused,true);assert.equal(by(d,'shotAppend').disabled,true);assert.equal(by(d,'shotRefresh').hidden,false);assert.match(status(d),/edit changed/);await submit(d);assert.equal(h.requests.length,0);await by(d,'shotRefresh').fire('click');assert.equal(by(d,'shotRefresh').hidden,true);assert.equal(by(d,'shotAppend').disabled,false);assert.equal(v.currentTime,3);assert.deepEqual(points(d).map(x=>x.value),['2.125','5.5']);await submit(d,'Insert');assert.equal(h.requests[0].payload.start,5);});
for(const change of ['project','view','asset','pane'])test(`${change} exit closes and releases the source without edits`,async()=>{const h=setup(),d=await ready(h),v=video(d);v.paused=false;if(change==='project')h.set({...h.get(),id:'other'});if(change==='view')h.view++;if(change==='asset')h.get().assets.a={...h.get().assets.a,url:'/replacement'};if(change==='pane')h.visible=false;h.studio.syncSourceMonitor();assert.equal(h.studio.shotReview,null);assert.equal(v.paused,true);assert.equal(v.released,true);assert.equal(d.removed,true);assert.equal(h.root.dataset.sourceMonitorOpen,undefined);assert.equal(h.requests.length,0);});
test('source refresh cannot bless a replaced asset before sync',async()=>{const h=setup(),d=await ready(h);h.get().assets.a={...h.get().assets.a,duration:11};await by(d,'shotRefresh').fire('click');assert.equal(h.studio.shotReview,null);assert.equal(h.requests.length,0);});
test('explicit occurrence selection exits source and reveals actual selection',async()=>{const h=setup(),d=await ready(h);h.studio.select('different');assert.equal(d.removed,true);assert.equal(h.studio.selected,'different');assert.equal(h.studio.shotReview,null);});
test('source preview claims only program transport, keeps normal rate, stops at Out',async()=>{const h=setup(),d=await ready(h),v=video(d);await marks(d,1,3);await by(d,'shotPreview').fire('click');assert.equal(h.programPauses.at(-1),v);assert.equal(v.paused,false);assert.equal(v.playbackRate,1);v.playbackRate=.5;await v.fire('ratechange');assert.equal(v.playbackRate,1);await v.fire('play');assert.equal(h.programPauses.at(-1),v);v.currentTime=3.1;await v.fire('timeupdate');assert.equal(v.paused,true);assert.equal(v.currentTime,3);assert.equal(h.requests.length,0);});
test('program-play pause invalidates a delayed source-play request and keeps the card',async()=>{const h=setup(),d=await ready(h),v=video(d);let resolve;v.play=()=>{v.paused=false;return new Promise(r=>resolve=r);};const playing=by(d,'shotPreview').fire('click');h.studio.pauseSourceMonitor();resolve();await playing;assert.equal(v.paused,true);assert.equal(d.open,true);assert.match(by(d,'shotPreview').textContent,/Play/);});
test('native Play while stale or busy is stopped instead of claiming program transport',async()=>{for(const stale of [false,true]){const h=setup(),d=await ready(h),v=video(d);if(stale)h.set({...h.get(),revision:22});else h.busy=true;v.paused=false;await v.fire('play');assert.equal(v.paused,true);assert.equal(h.programPauses.length,0);}});
test('busy is temporary while explicit draft reasons recover through sync',async()=>{const h=setup(),d=await ready(h);h.issue='Save or discard Chroma Key first.';h.studio.syncSourceMonitor();assert.equal(by(d,'shotAppend').disabled,true);assert.match(status(d),/Chroma/);h.issue='';h.busy=true;h.studio.syncSourceMonitor();assert.equal(by(d,'shotPreview').disabled,true);h.busy=false;h.studio.syncSourceMonitor();assert.equal(by(d,'shotAppend').disabled,false);assert.equal(d.open,true);});
test('selected duration and cursor recalculate both Insert and Append bounds',async()=>{const h=setup(),d=await ready(h);h.get().editor_sequence.duration=86399;await marks(d,1,3);h.studio.syncSourceMonitor();assert.equal(by(d,'shotAppend').disabled,true);assert.match(by(d,'shotAppend').title,/24 hours/);h.get().editor_sequence.duration=8;h.time=9;h.studio.syncSourceMonitor();assert.equal(by(d,'shotInsert').disabled,true);assert.equal(by(d,'shotAppend').disabled,false);});
test('own in-flight save freezes fields/Close/refresh, ignores repeats and opens, preserves source during transient render',async()=>{const h=setup(),d=await ready(h),v=video(d),real=h.studio.options.edit;let resolve;h.studio.options.edit=async(...args)=>{await new Promise(r=>resolve=r);return real(...args);};const saving=submit(d);assert.equal(d.pending,true);assert.equal(by(d,'shotKeep').disabled,true);assert.equal(points(d)[0].disabled,true);assert.equal(await h.studio.reviewShot('a'),undefined);await submit(d);await by(d,'shotKeep').fire('click');await d.fire('keydown',{key:'Escape'});assert.equal(d.open,true);resolve();await saving;assert.equal(h.requests.length,1);assert.equal(d.open,true);assert.equal(d.pending,false);assert.equal(video(d),v);assert.equal(by(d,'shotKeep').disabled,false);});
test('destination admission guard refuses changed cursor after preflush but does not discard an already accepted save',async()=>{const h=setup(),d=await ready(h);let guard;h.studio.options.edit=async(a,p,g)=>{guard=g;h.time=5;assert.equal(g.isCurrent(),true);assert.equal(g.admissionCurrent(),false);return null;};await submit(d,'Insert');assert.equal(h.requests.length,0);assert.equal(h.time,5);assert.equal(h.placements.length,0);assert.match(status(d),/not added/);});
test('late accepted save after newer seek keeps newer cursor instead of advancing it',async()=>{const h=setup(),d=await ready(h),real=h.studio.options.edit;h.studio.options.edit=async(...args)=>{const result=await real(...args);h.time=5;return result;};await submit(d);assert.equal(h.requests.length,1);assert.equal(h.placements.length,0);assert.equal(h.time,5);assert.equal(by(d,'shotRefresh').hidden,true);});
test('late result after forced context exit cannot resurrect source/selection or seek',async()=>{const h=setup(),d=await ready(h),real=h.studio.options.edit;h.studio.options.edit=async(...args)=>{const result=await real(...args);h.view++;h.studio.syncSourceMonitor();return result;};await submit(d);assert.equal(d.removed,true);assert.equal(h.studio.shotReview,null);assert.equal(h.placements.length,0);assert.equal(h.studio.selected,undefined);});
test('failed save retains video, currentTime and marks for a guarded retry',async()=>{const h=setup(),d=await ready(h),v=video(d),real=h.studio.options.edit;await marks(d,1.2,2.3);v.currentTime=1.7;h.studio.options.edit=async()=>{throw Error('Disk refused');};await submit(d);assert.match(status(d),/Disk refused/);assert.equal(video(d),v);assert.equal(v.currentTime,1.7);assert.deepEqual(points(d).map(x=>x.value),['1.2','2.3']);h.studio.options.edit=real;await submit(d);assert.equal(h.requests.length,1);});
test('Close and local Escape release once, leave edit and saved marks untouched',async()=>{for(const kind of ['close','escape']){const h=setup(),before=JSON.stringify(h.get()),d=await ready(h),v=video(d);await marks(d,1,2);if(kind==='close')await by(d,'shotKeep').fire('click');else{const event=await d.fire('keydown',{key:'Escape',target:points(d)[0]});assert.equal(event.defaultPrevented,true);assert.equal(event.stopped,true);}assert.equal(v.released,true);assert.equal(JSON.stringify(h.get()),before);assert.equal(h.entries.size,0);assert.equal(h.requests.length,0);h.studio.closeSourceMonitor();}});
test('explicit marks survive successful placement and a new source session only after Save marks',async()=>{const h=setup(),d=await ready(h);await marks(d,1.2345,4.5678);await by(d,'shotSaveMarks').fire('click');const saved=[...h.entries.values()];await submit(d);assert.deepEqual([...h.entries.values()],saved);h.studio.closeSourceMonitor();const next=await ready(h);assert.deepEqual(points(next).map(x=>x.value),['1.2345','4.5678']);});
test('match-origin source seek is one-time and survives own insertion invalidating the old occurrence',async()=>{const h=setup();h.get().manual.media_clips=[{id:'old',asset_id:'a',start:0,end:8,source_start:1,video_source_start:.5,speed:.5}];const plan=h.studio.sourceMatchPlan('old',2);await h.studio.reviewShot('a',{match:plan});const d=h.studio.shotReview,v=video(d);await v.fire('loadedmetadata');assert.equal(v.currentTime,1.5);await marks(d,2,3);await submit(d,'Insert');v.currentTime=2.25;await v.fire('durationchange');assert.equal(v.currentTime,2.25);assert.equal(by(d,'shotAppend').disabled,false);assert.match(by(d,'shotMatchOrigin').textContent,/Original source preview/);});
test('replacement requests racing a preflight cannot mount an older source',async()=>{const h=setup();let resolve;h.studio.flush=()=>new Promise(r=>resolve=r);const first=h.studio.reviewShot('a');h.studio.flush=async()=>true;await h.studio.reviewShot('a');const latest=h.studio.shotReview;resolve(true);await first;assert.equal(h.studio.shotReview,latest);assert.equal(h.opens,1);});
test('same-project reopen while preflighting never mounts the old monitor',async()=>{const h=setup();let resolve;h.studio.flush=()=>new Promise(r=>resolve=r);const opening=h.studio.reviewShot('a');h.view++;resolve(true);await opening;assert.equal(h.studio.shotReview,undefined);assert.equal(h.opens,0);});

test('explicit context exit while source is preflighting cancels the opening request',async()=>{const h=setup();let resolve;h.studio.flush=()=>new Promise(r=>resolve=r);const opening=h.studio.reviewShot('a');h.studio.closeSourceMonitor();resolve(true);await opening;assert.equal(h.studio.shotReview,undefined);assert.equal(h.opens,0);});

test('Close returns focus to connected opener only when source owned focus',async()=>{const h=setup(),opener=node('button');opener.isConnected=true;h.context.document.activeElement=opener;const d=await ready(h);d.contains=n=>n===d;h.context.document.activeElement=d;await by(d,'shotKeep').fire('click');assert.equal(opener.focused,true);});
test('Close after library redraw focuses replacement same-asset In/Out control',async()=>{const h=setup(),old=node('button'),replacement=node('button');old.isConnected=false;replacement.dataset.reviewShot='a';h.studio.library={querySelectorAll:()=>[replacement]};h.context.document.activeElement=old;const d=await ready(h);d.contains=n=>n===d;h.context.document.activeElement=d;await d.fire('keydown',{key:'Escape'});assert.equal(replacement.focused,true);assert.notEqual(old.focused,true);});
test('forced pane exit never steals focus back into the removed source context',async()=>{const h=setup(),opener=node('button');opener.isConnected=true;h.context.document.activeElement=opener;const d=await ready(h);d.contains=n=>n===d;h.context.document.activeElement=d;h.studio.closeSourceMonitor();assert.notEqual(opener.focused,true);});
test('insertion pauses edited transport before capturing its final displayed destination',async()=>{const h=setup(),d=await ready(h);let pauses=0;h.studio.options.pause=()=>{pauses++;h.time=3.125;};await marks(d,1,2);await submit(d,'Insert');assert.equal(pauses,1);assert.equal(h.requests[0].payload.start,3.125);assert.equal(h.time,4.125);});
test('programmatic submit cannot bypass a disabled source length limit',async()=>{const h=setup(),d=await ready(h);h.get().editor_sequence.duration=86399;await marks(d,1,3);await submit(d);assert.equal(h.requests.length,0);assert.equal(by(d,'shotAppend').disabled,true);});

test('default source card exposes picture/range/placement while optional persistence/help is collapsed',async()=>{const h=setup(),d=await ready(h),help=all(d).find(n=>n.className==='library-source-help');assert.equal(help.tag,'details');assert.ok(!help.open);const inside=n=>{for(let x=n;x;x=x.parentElement)if(x===help)return true;return false;};for(const key of ['shotPreview','shotInsert','shotAppend','shotDestination','shotKeep'])assert.equal(inside(by(d,key)),false,key);for(const n of all(d).filter(n=>n.dataset.shotPoint||n.dataset.shotMark))assert.equal(inside(n),false);for(const n of all(d).filter(n=>n.dataset.shotJump||n.dataset.shotSaveMarks||n.dataset.shotResetMarks||n.dataset.shotMarksStatus))assert.equal(inside(n),true);assert.equal(all(d).filter(n=>n.dataset.shotJump).length,2);});


test('live source marks drive only their own asset, remain unsaved, and expose one native drag summary',async()=>{
 const h=setup(),d=await ready(h);await marks(d,1.25,4.5);
 assert.deepEqual(plain(h.studio.dragSelection('a')),{sourceStart:1.25,sourceEnd:4.5});assert.equal(h.studio.dragSelection('missing'),null);
 const summary=all(d).filter(n=>n.dataset.sourceDrag);assert.equal(summary.length,1);assert.equal(summary[0].draggable,true);
 assert.match(summary[0].textContent,/Drag selection.*3.250 s selected.*1.250–4.500/);assert.equal(h.entries.size,0);assert.equal(h.requests.length,0);
 await marks(d,5,2);assert.match(h.studio.dragSelection('a').issue,/In \/ Out/);assert.equal(summary[0].draggable,false);
});
test('invalid or stale active source never falls back to older saved marks',async()=>{
 const h=setup(),d=await ready(h);await marks(d,1,3);await by(d,'shotSaveMarks').fire('click');await marks(d,4,2);
 assert.ok(h.studio.dragSelection('a').issue);h.get().revision++;assert.match(h.studio.dragSelection('a').issue,/current source/);
 h.studio.closeSourceMonitor();assert.deepEqual(plain(h.studio.dragSelection('a')),{sourceStart:1,sourceEnd:3});
 h.get().assets.a.duration=11;assert.equal(h.studio.dragSelection('a'),null,'stale saved marks are not applied to changed source metadata');
});
test('same-name source B cannot inherit source A active or saved marks',async()=>{
 const h=setup();h.get().assets.b={...h.get().assets.a,id:'b',url:'/original/b'};const d=await ready(h);await marks(d,1,2);await by(d,'shotSaveMarks').fire('click');
 assert.equal(h.studio.dragSelection('b'),null);assert.deepEqual(plain(h.studio.dragSelection('a')),{sourceStart:1,sourceEnd:2});
 h.studio.closeSourceMonitor();h.get().id='another-project';assert.equal(h.studio.dragSelection('a'),null);
});


// Source -> Timeline handoff: presentation must use, not replace, native commands.
const placementHelp=(d,kind)=>all(d).find(n=>n.dataset.shotPlacementHelp===kind.toLowerCase());
const placementReceipt=d=>by(d,'shotPlacementReceipt');
test('selection summary precedes timeline placement; original form/player stay direct Source children',async()=>{
 const h=setup(),d=await ready(h),f=form(d),v=video(d),summary=by(d,'sourceDrag'),placement=all(d).find(n=>n.className==='library-source-placement');
 assert.equal(f.parentElement,d);assert.equal(v.parentElement,d);assert.equal(summary.parentElement,f);assert(f.children.indexOf(summary)<f.children.indexOf(placement));
 assert.equal(placement.parentElement,f);assert.equal(by(d,'shotDestination').parentElement,placement);assert.equal(by(d,'shotRefresh').parentElement,placement);
 assert.equal(all(d).filter(n=>n.dataset.sourceDrag).length,1);assert.equal(all(d).filter(n=>n.dataset.shotAppend).length,1);assert.equal(all(d).filter(n=>n.dataset.shotInsert).length,1);
 assert.deepEqual(all(f).filter(n=>n.type==='submit').map(n=>n.dataset.shotAppend?'append':'insert'),['append','insert']);
 for(const kind of ['Append','Insert'])assert.equal(by(d,'shot'+kind)['aria-describedby'],placementHelp(d,kind).id);
 assert(points(d).every(n=>n.dir==='ltr'));assert.equal(placementHelp(d,'Append')['aria-live'],'off');assert.equal(h.requests.length,0);
});
test('implicit form submit and Enter in a source field never add a shot; explicit native keyboard submit still does',async()=>{
 const h=setup(),d=await ready(h);await marks(d,1,2);
 const e=await points(d)[0].fire('keydown',{key:'Enter'});assert(e.defaultPrevented&&e.stopped);assert.equal(h.requests.length,0);
 await form(d).fire('submit');assert.equal(h.requests.length,0);
 await form(d).fire('submit',{submitter:by(d,'shotPreview')});assert.equal(h.requests.length,0);
 const ime=await points(d)[1].fire('keydown',{key:'Enter',isComposing:true});assert.equal(ime.defaultPrevented,false);
 const code229=await points(d)[1].fire('keydown',{key:'Enter',keyCode:229});assert.equal(code229.defaultPrevented,false);
 await submit(d,'Insert');assert.equal(h.requests.length,1);assert.equal(h.requests[0].action,'media_insert');
});
test('Append-only and Insert-only blockers are visible without hover and recover independently',async()=>{
 const h=setup(),d=await ready(h);await marks(d,1,3);h.get().editor_sequence.duration=86399;h.studio.syncSourceMonitor();
 assert.match(placementHelp(d,'Append').textContent,/Append unavailable:.*24 hours/);assert.equal(placementHelp(d,'Append').dataset.state,'blocked');
 h.get().editor_sequence.duration=8;h.time=9;h.studio.syncSourceMonitor();
 assert.match(placementHelp(d,'Insert').textContent,/Insert unavailable:/);assert.equal(placementHelp(d,'Append').dataset.state,'ready');assert.match(placementHelp(d,'Append').textContent,/existing clips stay put/);
 h.time=2;h.studio.syncSourceMonitor();assert.equal(placementHelp(d,'Insert').dataset.state,'ready');assert.match(placementHelp(d,'Insert').textContent,/later clips move/);
 assert.equal(h.requests.length,0);
});
for(const mode of ['stale','host','busy','invalid','metadata','frame'])test('both placement notes explain actual shared unavailability: '+mode,async()=>{
 const h=setup();let frame;
 if(mode==='frame')h.studio.options.sourceFrames=()=>frame={pending:false,sync(){},destroy(){},clear(){}};
 const d=await ready(h);let expected;
 if(mode==='stale'){h.set({...h.get(),revision:9});expected=/edit changed.*Use current edit/;}
 if(mode==='host'){h.issue='Save or discard Chroma Key first.';expected=/Chroma Key/;}
 if(mode==='busy'){h.busy=true;expected=/busy/;}
 if(mode==='invalid'){points(d)[1].value='';expected=/Enter both source/;}
 if(mode==='metadata'){video(d).duration=12;await video(d).fire('durationchange');expected=/does not match/;}
 if(mode==='frame'){frame.pending=true;expected=/original frame.*decoding/;}
 h.studio.syncSourceMonitor();for(const kind of ['Append','Insert']){const b=by(d,'shot'+kind),note=placementHelp(d,kind);assert(b.disabled);assert.equal(note.dataset.state,'blocked');assert.match(note.textContent,expected);assert.match(b.title,expected);}
 await submit(d);assert.equal(h.requests.length,0);
 if(mode==='stale'){assert.equal(by(d,'shotRefresh').hidden,false);await by(d,'shotRefresh').fire('click');assert.equal(placementHelp(d,'Append').dataset.state,'ready');}
});
test('unchanged sync writes the final draggable summary only once, never bare then prefixed text',async()=>{
 const h=setup(),d=await ready(h),summary=by(d,'sourceDrag');let value=summary.textContent,writes=0;
 Object.defineProperty(summary,'textContent',{get:()=>value,set:v=>{value=v;writes++;}});
 for(let n=0;n<6;n++){h.time=n/30;h.studio.syncSourceMonitor();}assert.equal(writes,0);
 await marks(d,1,3);assert.equal(writes,1);assert.match(value,/^Drag selection/);
});
test('confirmed placement receipt names actual saved interval, remains outside drag region and survives seek/mark changes',async()=>{
 const h=setup(),d=await ready(h);await marks(d,1.125,3.25);const receipt=placementReceipt(d);assert(receipt.hidden);
 await submit(d);assert.equal(receipt.hidden,false);assert.match(receipt.textContent,/Appended on timeline: 8\.000–10\.125 s/);assert.match(receipt.textContent,/Undo/);
 assert.equal(receipt.role,'status');assert.equal(receipt['aria-live'],'polite');assert.equal(receipt.dataset.sourceDrag,undefined);
 h.time=1;h.studio.syncSourceMonitor();await marks(d,2,3);assert.match(receipt.textContent,/8\.000–10\.125/);
 await submit(d,'Insert');assert.match(receipt.textContent,/Inserted on timeline: 1\.000–2\.000 s/);assert.equal(h.requests.length,2);
 h.set({...h.get(),revision:h.get().revision+1});h.studio.syncSourceMonitor();assert.equal(receipt.hidden,true);assert.equal(receipt.textContent,'');
});
test('receipt never uses a newer cursor or claims cursor moved after an accepted late save',async()=>{
 const h=setup(),d=await ready(h),real=h.studio.options.edit;await marks(d,1,2);
 h.studio.options.edit=async(...args)=>{const result=await real(...args);h.time=5;return result;};await submit(d);
 assert.equal(h.time,5);assert.equal(h.placements.length,0);assert.match(placementReceipt(d).textContent,/8\.000–9\.000/);assert.doesNotMatch(placementReceipt(d).textContent,/cursor|playhead/);
});
test('failed or context-obsolete placement cannot invent a success receipt',async()=>{
 for(const mode of ['failed','exit']){const h=setup(),d=await ready(h),real=h.studio.options.edit;
 h.studio.options.edit=mode==='failed'?async()=>{throw Error('Disk refused');}:async(...args)=>{const result=await real(...args);h.view++;h.studio.syncSourceMonitor();return result;};
 await submit(d);assert.equal(placementReceipt(d).hidden,true);if(mode==='failed')assert.match(status(d),/Disk refused/);}
});
test('new Source session cannot inherit an old placement receipt or unsaved marks',async()=>{
 const h=setup(),d=await ready(h);await marks(d,1,2);await submit(d);assert.equal(placementReceipt(d).hidden,false);
 h.studio.closeSourceMonitor();const next=await ready(h);assert.equal(placementReceipt(next).hidden,true);assert.deepEqual(points(next).map(n=>n.value),['0','10']);
});
