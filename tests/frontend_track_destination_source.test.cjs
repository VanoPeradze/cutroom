const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'');
const plain=x=>JSON.parse(JSON.stringify(x));
function node(tag){return {tag,tagName:tag.toUpperCase(),children:[],dataset:{},listeners:{},value:'',disabled:false,currentTime:0,duration:10,paused:true,playbackRate:1,
 replaceChildren(){this.children=[];},querySelector(sel){return this.children.find(x=>x.tag===sel);},append(...xs){for(const x of xs){if(x.parentElement)x.parentElement.children=x.parentElement.children.filter(n=>n!==x);x.parentElement=this;this.children.push(x);}},prepend(...xs){for(const x of xs)x.parentElement=this;this.children.unshift(...xs);},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},
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


const tid=n=>'track_'+String(n).padStart(32,'0'),cid=n=>'media_'+String(n).padStart(32,'0');
function trackedSetup(){
 const h=setup(),p=h.get();p.manual.layer_tracks={version:1,tracks:[{id:tid(1),kind:'visual',name:'Footage'},{id:tid(2),kind:'audio',name:'Sound'},{id:tid(3),kind:'visual',name:'B-roll'}]};
 h.studio.destinationControls=new Set();h.studio.destinationTrackId='';
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/layer-tracks.js'),'utf8').replace(/^export /gm,''),h.context);
 const helpers=vm.runInContext('({layerTrackState,planLibraryTrackPlacement})',h.context);
 h.studio.options.trackState=helpers.layerTrackState;
 h.studio.options.placementPreview=(a,t,o)=>helpers.planLibraryTrackPlacement(h.get(),a,t,o);
 h.studio.updateImportAvailability=()=>h.studio.updateDestinationControls();
 h.studio.options.edit=async(action,payload,guard)=>{
  assert.equal(guard.strictRevision,true);assert.equal(guard.isCurrent(),true);assert.equal(guard.admissionCurrent(),true);
  h.requests.push({action,payload:plain(payload),guard});const p=h.get(),start=action==='media_insert'?payload.start:p.editor_sequence.duration,len=payload.source_end-payload.source_start;
  const row={id:cid(h.requests.length),asset_id:payload.asset_id,start,end:start+len,source_start:payload.source_start,track_id:payload.track_id||tid(1)};
  h.set({...p,revision:p.revision+1,editor_sequence:{duration:p.editor_sequence.duration+len},manual:{...p.manual,media_clips:[...p.manual.media_clips,row]}});return h.get();
 };
 return h;
}
const chooser=d=>all(d).find(n=>n.dataset.mediaDestination==='source');
test('native source chooser submits exact source marks and chosen lane in one Append',async()=>{const h=trackedSetup(),d=await ready(h),v=video(d);chooser(d).value=tid(3);await chooser(d).fire('change');await marks(d,.125,1.25);v.currentTime=.75;await submit(d);assert.equal(h.requests.length,1);assert.deepEqual(h.requests[0].payload,{asset_id:'a',source_start:.125,source_end:1.25,track_id:tid(3)});assert.equal(h.studio.shotReview,d);assert.equal(video(d),v);assert.equal(v.currentTime,.75);assert.equal(chooser(d).value,tid(3));assert.deepEqual(points(d).map(n=>n.value),['0.125','1.25']);});
test('source destination defaults Automatic and omits track_id',async()=>{const h=trackedSetup(),d=await ready(h);await marks(d,1,2);await submit(d);assert.equal(Object.hasOwn(h.requests[0].payload,'track_id'),false);});
test('pool/source destination choice is one local state, not a write',async()=>{const h=trackedSetup(),pool=h.studio.makeDestinationControl('pool'),d=await ready(h);pool.querySelector('select').value=tid(3);await pool.querySelector('select').fire('change');assert.equal(chooser(d).value,tid(3));assert.equal(h.requests.length,0);assert.equal(h.get().revision,4);});
test('stale chosen track remains visible after explicit Use current edit and blocks placement',async()=>{const h=trackedSetup(),d=await ready(h);chooser(d).value=tid(3);await chooser(d).fire('change');h.set({...h.get(),revision:5,manual:{...h.get().manual,layer_tracks:{version:1,tracks:h.get().manual.layer_tracks.tracks.filter(t=>t.id!==tid(3))}}});h.studio.syncSourceMonitor();assert.equal(by(d,'shotAppend').disabled,true);await by(d,'shotRefresh').fire('click');assert.equal(chooser(d).value,tid(3));assert.equal(by(d,'shotAppend').disabled,true);assert.match(by(d,'shotAppend').title,/no longer available/);await submit(d);assert.equal(h.requests.length,0);chooser(d).value='';await chooser(d).fire('change');assert.equal(by(d,'shotAppend').disabled,false);});
test('audio destination chosen from pool never silently becomes visual in Source',async()=>{const h=trackedSetup();h.studio.destinationTrackId=tid(2);const d=await ready(h);assert.equal(chooser(d).value,tid(2));assert.equal(by(d,'shotAppend').disabled,true);assert.equal(by(d,'shotInsert').disabled,true);await submit(d);assert.equal(h.requests.length,0);});
test('source Insert carries destination and exact edited cursor, retaining original node',async()=>{const h=trackedSetup(),d=await ready(h),v=video(d);chooser(d).value=tid(3);await chooser(d).fire('change');await marks(d,1.25,2.5);h.time=3.125;await submit(d,'Insert');assert.deepEqual(h.requests[0].payload,{asset_id:'a',source_start:1.25,source_end:2.5,start:3.125,track_id:tid(3)});assert.equal(video(d),v);assert.equal(h.time,4.375);});
test('pending source write disables shared chooser and duplicate actions',async()=>{const h=trackedSetup(),d=await ready(h);let done;const original=h.studio.options.edit;h.studio.options.edit=async(...args)=>{await new Promise(r=>done=r);return original(...args);};await marks(d,1,2);const first=submit(d);assert.equal(chooser(d).disabled,true);await submit(d);assert.equal(h.requests.length,0);done();await first;assert.equal(h.requests.length,1);assert.equal(chooser(d).disabled,false);});
test('closing contextual source unregisters only its chooser and keeps pool/local choice',async()=>{const h=trackedSetup(),pool=h.studio.makeDestinationControl('pool'),d=await ready(h);chooser(d).value=tid(3);await chooser(d).fire('change');assert.equal(h.studio.destinationControls.size,2);h.studio.closeSourceMonitor();assert.equal(h.studio.destinationControls.size,1);assert.equal(pool.querySelector('select').value,tid(3));assert.equal(h.requests.length,0);});

test('held pool placement prevents source submit and restores after release',async()=>{const h=trackedSetup(),d=await ready(h);h.studio.placing=true;h.studio.syncSourceMonitor();assert.equal(by(d,'shotAppend').disabled,true);assert.equal(chooser(d).disabled,true);await submit(d);assert.equal(h.requests.length,0);h.studio.placing=false;h.studio.syncSourceMonitor();assert.equal(by(d,'shotAppend').disabled,false);assert.equal(chooser(d).disabled,false);});


const placementHelp=(d,kind)=>all(d).find(n=>n.dataset.shotPlacementHelp===kind.toLowerCase());
test('each action shows its canonical saved-track destination span, not source or new playhead time',async()=>{
 const h=trackedSetup(),d=await ready(h);chooser(d).value=tid(3);await chooser(d).fire('change');await marks(d,1.125,3.25);h.time=3.125;h.studio.syncSourceMonitor();
 assert.match(placementHelp(d,'Insert').textContent,/Timeline 3\.125–5\.250 s on “B-roll”/);
 assert.match(placementHelp(d,'Append').textContent,/Timeline 8\.000–10\.125 s on “B-roll”/);
 assert.equal(h.requests.length,0);await submit(d,'Insert');assert.equal(h.requests[0].payload.start,3.125);assert.equal(h.requests[0].payload.source_start,1.125);
});
for(const mode of ['locked','audio','missing','capacity'])test('canonical '+mode+' refusal is visible beside both native actions',async()=>{
 const h=trackedSetup();
 if(mode==='locked'){h.get().manual.layer_tracks.version=2;for(const t of h.get().manual.layer_tracks.tracks)t.locked=t.id===tid(3);h.studio.destinationTrackId=tid(3);}
 if(mode==='audio')h.studio.destinationTrackId=tid(2);
 if(mode==='missing')h.studio.destinationTrackId=tid(9);
 if(mode==='capacity'){h.get().draft.output_duration=300;h.get().editor_sequence.duration=300;h.get().manual.media_clips=Array.from({length:200},(_,i)=>({id:cid(i+1),asset_id:'a',start:i,end:i+1,source_start:0,track_id:tid(1)}));}
 const d=await ready(h),pattern={locked:/locked/,audio:/visual track/,missing:/no longer available/,capacity:/200 media clip/}[mode];
 for(const kind of ['Append','Insert']){assert(by(d,'shot'+kind).disabled);assert.match(placementHelp(d,kind).textContent,pattern);}
 await submit(d);assert.equal(h.requests.length,0);
});
test('track names are plain text in placement feedback, including mixed Hebrew and markup',async()=>{
 const h=trackedSetup();h.get().manual.layer_tracks.tracks[2].name='צילום <img src=x> 2';h.studio.destinationTrackId=tid(3);
 const d=await ready(h),note=placementHelp(d,'Append');assert.match(note.textContent,/צילום <img src=x> 2/);assert.equal(note.children.length,0);assert.equal(note.dir,'auto');
});
