const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const read=n=>fs.readFileSync(path.join(__dirname,'../web',n),'utf8');
const plain=x=>JSON.parse(JSON.stringify(x)),tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};
function documentFixture(){
 const timers=new Map(),images=[];let nextTimer=0;
 const doc={defaultView:{setTimeout(fn){timers.set(++nextTimer,fn);return nextTimer;},clearTimeout(id){timers.delete(id);}},createElement:node};
 function node(tag='div'){
  const n={tag,tagName:tag.toUpperCase(),ownerDocument:doc,children:[],dataset:{},listeners:{},value:'',disabled:false,hidden:false,currentTime:0,duration:10,paused:true,playbackRate:1,
   append(...xs){for(const x of xs){x.remove();x.parentElement=this;this.children.push(x);}},prepend(...xs){for(const x of xs)x.parentElement=this;this.children.unshift(...xs);},
   after(...xs){const p=this.parentElement,i=p.children.indexOf(this);for(const x of xs)x.parentElement=p;p.children.splice(i+1,0,...xs);},
   replaceWith(x){const p=this.parentElement,i=p.children.indexOf(this);assert(i>=0);x.parentElement=p;p.children[i]=x;this.parentElement=null;},
   setAttribute(k,v){this[k]=String(v);},removeAttribute(k){delete this[k];},getAttribute(k){return this[k]??null;},
   addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);},removeEventListener(k,fn){this.listeners[k]=(this.listeners[k]||[]).filter(f=>f!==fn);},
   async fire(k,extra={}){const e={target:this,defaultPrevented:false,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;},...extra};for(const fn of [...this.listeners[k]||[]])await fn(e);return e;},
   closest(selector){for(let x=this;x;x=x.parentElement)if(['input','textarea','select'].includes(x.tag)||x.isContentEditable||['textbox','combobox'].includes(x.role)||['video','audio'].includes(x.tag)&&x.controls&&selector.includes('controls'))return x;return null;},
   pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();},load(){},remove(){if(this.parentElement){this.parentElement.children=this.parentElement.children.filter(x=>x!==this);this.parentElement=null;}},reportValidity(){return true;},focus(){},scrollIntoView(){},contains(x){for(;x;x=x.parentElement)if(x===this)return true;return false;}};
  if(tag==='img'){images.push(n);n.decode=()=>{n.wasDecoded=true;return doc.nextDecode?.()||Promise.resolve();};}
  return n;
 }
 doc.body=node('body');return{doc,node,timers,images};
}
const all=n=>[n,...n.children.flatMap(all)],by=(d,key)=>all(d).find(n=>n.dataset[key]);
const pts=[0,.033333333,.166666667,.266666667,.433333333,.566666667];
function value(index=1,extra={}){return{project_id:'p',asset_id:'a',token:'a'.repeat(64),index,count:6,time:pts[index],end:pts[index+1]??null,duration:10,image:'data:image/png;base64,aGVsbG8=',...extra};}
function setup(){
 const d=documentFixture(),root=d.node('section'),video=d.node('video');video.controls=true;root.append(video);
 const context=vm.createContext({console,AbortController});vm.runInContext(read('source-frame.js').replace(/^export /gm,''),context);
 const h={...d,root,video,requests:[],changes:0,pauses:0,state:{key:'p:4:a',projectId:'p',assetId:'a',time:0,duration:10,available:true}};
 h.loader=request=>value(request.index==null?1:Math.max(0,Math.min(5,Number(request.index)+(request.direction==='next'?1:-1))));
 h.controller=context.initSourceFrameReview(root,video,{snapshot:()=>h.state,pause:()=>{h.pauses++;video.pause();},changed:()=>h.changes++,load:async(req,options)=>{h.requests.push({req,options});return h.loader(req);}});
 h.grid=context.projectFrameStep;return h;
}

test('Source confirms the same decoded IMG before exact PTS marks; never seeks the proxy or Program',async()=>{
 const h=setup(),gate=deferred();h.doc.nextDecode=()=>gate.promise;
 const pending=h.controller.step('next');await tick();assert(h.controller.pending);assert(h.controller.mark('in').issue);assert.equal(h.video.hidden,false);assert.equal(h.video.currentTime,0);
 assert(by(h.root,'sourceFrameStep').disabled);assert.match(all(h.root).find(n=>n.role==='status').textContent,/wait for the picture/);
 const decoded=h.images.at(-1);gate.resolve();assert.equal(await pending,true);assert.equal(h.images.filter(n=>n.parentElement).length,1);
 assert.equal(h.root.children.find(n=>n.tag==='img'),decoded);assert(decoded.wasDecoded);assert.equal(decoded.hidden,false);assert.equal(h.video.hidden,true);
 assert.deepEqual(plain(h.controller.mark('in')),{value:.033333333});assert.deepEqual(plain(h.controller.mark('out')),{value:.166666667});assert.equal(h.video.currentTime,0);
 await h.controller.step('next');assert.equal(h.requests[1].req.time,.033333333);assert.equal(h.requests[1].req.index,1);assert.equal(h.requests[1].req.token,'a'.repeat(64));
 assert.equal(h.controller.mark('in').value,.166666667);assert.equal(h.requests[0].req.fps,undefined);assert.equal(h.pauses,2);assert.equal(h.timers.size,0);
});

test('Rapid requests and held keys never calculate a next frame from stale video.currentTime',async()=>{
 const h=setup(),gate=deferred();h.loader=()=>gate.promise;const pending=h.controller.step('next');
 assert.equal(await h.controller.step('next'),false);const e=await h.root.fire('keydown',{key:'ArrowRight',repeat:true});assert(e.defaultPrevented&&e.stopped);assert.equal(h.requests.length,1);
 gate.resolve(value());assert(await pending);await h.root.fire('keydown',{key:'ArrowRight'});await tick();assert.equal(h.requests.length,2);assert.equal(h.requests[1].req.index,1);
});
for(const reason of ['project','asset','revision','view','close','play','seeking','emptied','error','loadedmetadata','return'])test(`Pending original frame cannot survive ${reason}`,async()=>{
 const h=setup(),gate=deferred();h.loader=()=>gate.promise;const pending=h.controller.step('next');
 if(['project','asset','revision','view'].includes(reason)){h.state.key=reason+':new';h.controller.sync();}
 else if(reason==='close')h.controller.destroy();else if(reason==='return')await by(h.root,'sourceFramePlayback').fire('click');else await h.video.fire(reason);
 gate.resolve(value());assert.equal(await pending,false);assert.equal(h.controller.active,false);assert.equal(h.video.hidden,false);assert.equal(h.video.currentTime,0);assert.equal(h.controller.pending,false);assert(h.requests[0].options.signal.aborted);
});
test('Already requested image decode is revoked before source swap, not just before the network response',async()=>{
 const h=setup(),gate=deferred();h.doc.nextDecode=()=>gate.promise;const p=h.controller.step('next');await tick();h.state.key='other';h.controller.sync();assert.equal(await p,false);gate.resolve();await tick();assert.equal(h.controller.active,false);assert.equal(h.timers.size,0);
});
test('IMG decoding timeout preserves the last confirmed picture and exact mark, never a new false confirmation',async()=>{
 const h=setup();await h.controller.step('next');const original=h.root.children.find(n=>n.tag==='img'),gate=deferred();h.doc.nextDecode=()=>gate.promise;const p=h.controller.step('next');await tick();[...h.timers.values()][0]();assert.equal(await p,false);
 assert.equal(h.root.children.find(n=>n.tag==='img'),original);assert.equal(h.controller.mark('in').value,.033333333);assert.match(all(h.root).find(n=>n.role==='status').textContent,/timed out.*Still showing original frame 2/);assert.equal(h.timers.size,0);gate.resolve();
});
for(const mutation of [{asset_id:'b'},{project_id:'other'},{time:NaN},{end:.01},{token:'bad'},{index:50},{duration:11},{image:'https://example.com/image'}])test('Invalid or foreign response cannot authorize Source marks '+JSON.stringify(mutation),async()=>{
 const h=setup();h.loader=()=>value(1,mutation);assert.equal(await h.controller.step('next'),false);assert.equal(h.controller.active,false);assert.equal(h.video.hidden,false);assert.equal(h.controller.mark('in'),null);
});
test('Second response must remain on the same source index token and adjacent frame',async()=>{
 const h=setup();await h.controller.step('next');h.loader=()=>value(4);assert.equal(await h.controller.step('next'),false);assert.equal(h.controller.mark('in'),null);assert.equal(h.video.hidden,false);
 h.loader=()=>value(1);await h.controller.step('next');h.loader=()=>value(2,{token:'b'.repeat(64)});assert.equal(await h.controller.step('next'),false);assert.equal(h.controller.mark('in'),null);assert.equal(h.controller.active,false);
});
test('First/last endpoints are explicit and unavailable last Out is not guessed from 10 s audio tail',async()=>{
 const h=setup();h.loader=()=>value(0);await h.controller.step('previous');assert.equal(h.controller.mark('in').value,0);assert(by(h.root,'sourceFrameStep').disabled);assert.equal(await h.controller.step('previous'),false);
 h.controller.clear();h.loader=()=>value(5);await h.controller.step('next');assert.equal(h.controller.canMarkOut,false);assert(h.controller.mark('out').issue);assert.equal(await h.controller.step('next'),false);
 assert.equal(h.requests.length,2);await by(h.root,'sourceFramePlayback').fire('click');assert.equal(h.video.currentTime,.566666667);assert.equal(h.video.hidden,false);assert.equal(h.controller.active,false);
});
for(const [name,extra,tag] of [['input',{},'input'],['textarea',{},'textarea'],['select',{},'select'],['contenteditable',{},'editable'],['native video',{},'video'],['native audio',{},'audio'],['IME',{isComposing:true}],['IME key229',{keyCode:229}],['Ctrl',{ctrlKey:true}],['Alt',{altKey:true}],['Shift',{shiftKey:true}],['Meta',{metaKey:true}],['AltGraph',{getModifierState:()=>true}],['handled',{defaultPrevented:true}]])test('Source arrow leaves '+name+' alone',async()=>{
 const h=setup(),target=tag?h.node(tag):h.root;if(tag==='editable')target.isContentEditable=true;if(['video','audio'].includes(tag))target.controls=true;
 const e=await h.root.fire('keydown',{key:'ArrowRight',target,...extra});assert.equal(h.requests.length,0);assert.equal(e.stopped,undefined);
});
test('Arrow buttons share exact step path, busy owner cannot load, destroy removes all listeners',async()=>{
 const h=setup();await by(h.root,'sourceFrameStep').fire('click');await tick();assert.equal(h.requests[0].req.direction,'previous');
 h.state.available=false;h.controller.sync();assert.equal(await h.controller.step('next'),false);assert(h.controller.mark('in').issue);
 h.controller.destroy();assert.equal(h.root.children.length,1);assert.equal(h.video.hidden,false);assert(Object.values(h.root.listeners).every(x=>x.length===0));assert(Object.values(h.video.listeners).every(x=>x.length===0));
});
for(const fps of [24,25,30,50,60])for(const n of [1,2,7,29,101])test(`Timeline ${fps} FPS steps across engine-rounded edge ${n} in both directions`,()=>{
 const h=setup(),at=Number((n/fps).toFixed(9));assert.equal(h.grid(at,1,fps,20),(n+1)/fps);assert.equal(h.grid(at,-1,fps,20),(n-1)/fps);
 assert.equal(h.grid(n/fps+1e-9,-1,fps,20),n/fps);assert.equal(h.grid(n/fps-1e-9,1,fps,20),n/fps);
});
test('Timeline bounds and subframe choices do not use Source rate or alter source clock',()=>{
 const h=setup();assert.equal(h.grid(.021,1,60,5),2/60);assert.equal(h.grid(.021,-1,60,5),1/60);assert.equal(h.grid(0,-1,24,5),0);assert.equal(h.grid(5,1,24,5),5);assert.equal(h.grid(NaN,1,60,5),null);assert.equal(h.grid(0,0,60,5),null);assert.equal(h.video.currentTime,0);
});

async function host(){
 const d=documentFixture(),root=d.node('section'),entries=new Map();let project={id:'p',revision:4,draft:{output_duration:8},editor_sequence:{duration:8},manual:{media_clips:[],text_clips:[]},assets:{a:{id:'a',kind:'video',status:'ready',duration:10,width:160,height:90,url:'/proxy/a',name:'Original.mp4'}}};
 const context=vm.createContext({console,document:d.doc,AbortController,URLSearchParams,localStorage:{getItem:k=>entries.get(k)??null,setItem:(k,v)=>entries.set(k,v),removeItem:k=>entries.delete(k)},...d.doc.defaultView});
 vm.runInContext(read('source-frame.js').replace(/^export /gm,''),context);vm.runInContext(read('media-studio.js').replace(/^export /gm,''),context);
 const studio=vm.runInContext('Object.create(MediaStudio.prototype)',context),h={...d,studio,entries,requests:[],programTime:2,get:()=>project,set:p=>project=p};
 studio.root=root;studio.status=d.node('p');studio.pending=new Map();studio.flush=async()=>true;studio.render=()=>studio.syncSourceMonitor();
 studio.options={project:()=>project,time:()=>h.programTime,busy:()=>false,pause(){},sourceFrames:(...args)=>(h.controller=context.initSourceFrameReview(...args)),sourceMonitor:{open:()=>true,token:()=>1,visible:()=>true,issue:()=>'',pauseProgram(){},placed(){}},api:async(url,context)=>{h.requests.push({url,context});return value();}};
 await studio.reviewShot('a');h.dialog=studio.shotReview;h.video=all(h.dialog).find(n=>n.tag==='video');await h.video.fire('loadedmetadata');return h;
}
test('Native Source controls use confirmed PTS, disable pending placement, save/reopen exact marks without changing the project',async()=>{
 const h=await host(),before=JSON.stringify(h.get()),gate=deferred();h.doc.nextDecode=()=>gate.promise;
 const p=h.controller.step('next');await tick();assert(by(h.dialog,'shotMark').disabled);assert(by(h.dialog,'shotAppend').disabled);assert.match(h.studio.dragSelection('a').issue,/current source/);
 gate.resolve();assert(await p);assert.equal(h.programTime,2);assert.equal(h.video.currentTime,0);assert.match(h.requests[0].url,/\/assets\/a\/frame-step\?time=0&direction=next/);
 const mark=key=>all(h.dialog).find(n=>n.dataset.shotMark===key),point=key=>all(h.dialog).find(n=>n.dataset.shotPoint===key);
 await mark('in').fire('click');await mark('out').fire('click');assert.equal(point('in').value,'0.033333333');assert.equal(point('out').value,'0.166666667');
 assert.deepEqual(plain(h.studio.dragSelection('a')),{sourceStart:.033333333,sourceEnd:.166666667});await by(h.dialog,'shotSaveMarks').fire('click');assert.equal(h.entries.size,1);assert.equal(JSON.stringify(h.get()),before);
 h.studio.closeSourceMonitor();await h.studio.reviewShot('a');h.dialog=h.studio.shotReview;assert.equal(point('in').value,'0.033333333');assert.equal(point('out').value,'0.166666667');assert.equal(JSON.stringify(h.get()),before);
});
test('Exact stepping does not weaken the existing 80 ms placement minimum or stale-revision guard',async()=>{
 const h=await host();h.studio.options.api=async()=>value(1,{end:.066666667});await h.controller.step('next');
 await all(h.dialog).find(n=>n.dataset.shotMark==='in').fire('click');await all(h.dialog).find(n=>n.dataset.shotMark==='out').fire('click');assert(by(h.dialog,'shotAppend').disabled);assert.match(h.studio.dragSelection('a').issue,/0.08/);
 h.set({...h.get(),revision:5});h.studio.syncSourceMonitor();assert.equal(h.controller.active,false);assert(by(h.dialog,'shotMark').disabled);assert.equal(h.programTime,2);
});

for(const [status,message] of [[409,'The original source changed.'],[409,'Another original frame is decoding.'],[404,'Original no longer exists.'],[422,'Original is unavailable.']])test(`API ${status} ${message} revokes a confirmed still even when JS source metadata is unchanged`,async()=>{
 const h=setup();await h.controller.step('next');const key=h.state.key,old=h.root.children.find(n=>n.tag==='img'),before=h.changes;
 h.loader=()=>{throw Object.assign(Error(message),{status});};assert.equal(await h.controller.step('next'),false);
 assert.equal(h.state.key,key);assert.equal(h.controller.active,false);assert.equal(h.controller.pending,false);assert.equal(h.controller.mark('in'),null);assert.equal(h.controller.mark('out'),null);
 assert(old.hidden);assert.equal(old.src,undefined);assert.equal(h.video.hidden,false);assert.equal(h.video.currentTime,0);assert(h.changes>before);
 assert.equal(h.root.dataset.decodedFrame,undefined);assert(!all(h.root).find(n=>n.role==='status').textContent.includes('Still showing'));
 h.loader=()=>value(1,{token:'b'.repeat(64)});assert(await h.controller.step('next'));assert.equal(h.requests.at(-1).req.index,undefined);assert.equal(h.requests.at(-1).req.token,undefined);
 assert.equal(h.controller.mark('in').value,.033333333,'Only a newly confirmed original may supply an exact mark again');
});
