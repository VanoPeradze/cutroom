const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'');
function node(tag){return{tag,tagName:tag.toUpperCase(),children:[],dataset:{},listeners:{},value:'',disabled:false,currentTime:0,duration:10,paused:true,playCalls:0,pauseCalls:0,
  append(...xs){for(const child of xs){child.parentElement=this;this.children.push(child);}},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},
  addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);},removeEventListener(k,fn){this.listeners[k]=(this.listeners[k]||[]).filter(f=>f!==fn);},
  async fire(k,extra={}){const event={target:this,defaultPrevented:false,propagationStopped:false,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.propagationStopped=true;},...extra};for(const fn of [...this.listeners[k]||[]])await fn(event);return event;},
  closest(){for(let target=this;target;target=target.parentElement){if(['input','textarea','select'].includes(target.tag)||target.contenteditable!==undefined&&target.contenteditable!=='false'||['textbox','combobox'].includes(target.role))return target;}return null;},
  showModal(){this.open=true;},close(){this.open=false;this.fire('close');},pause(){this.paused=true;this.pauseCalls++;},play(){this.paused=false;this.playCalls++;return Promise.resolve();},load(){this.released=true;},remove(){this.removed=true;},reportValidity(){return true;}};}
function setup(storage){
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
test('pure source ranges reject nonready, reversed, tiny or out-of-bounds choices',()=>{const h=setup();for(const range of [[5,4],[-1,3],[0,11],[0,.01],[NaN,5]]){h.context.args=range;assert.throws(()=>vm.runInContext('libraryShotRange(options.project().assets.a,...args)',h.context));}});
test('opening and keeping review never submits an edit and releases preview',async()=>{const h=setup();await h.studio.reviewShot('a');const d=h.studio.shotReview;assert.equal(d.open,true);await by(d,'shotKeep').fire('click');assert.equal(h.requests.length,0);assert.equal(d.removed,true);assert.equal(all(d).find(n=>n.tag==='video').released,true);});
test('metadata gates source preview; selected In/Out goes to existing append with stale guard',async()=>{const h=setup();await h.studio.reviewShot('a');const d=h.studio.shotReview,v=all(d).find(n=>n.tag==='video'),f=all(d).find(n=>n.tag==='form');assert.equal(by(d,'shotAppend').disabled,true);await v.fire('loadedmetadata');const points=all(d).filter(n=>n.dataset.shotPoint);points[0].value='2.125';points[1].value='6.5';await points[0].fire('input');assert.equal(by(d,'shotAppend').disabled,false);await f.fire('submit');assert.equal(h.requests.length,1);assert.deepEqual(plain(h.requests[0]),{action:'media_append',payload:{asset_id:'a',source_start:2.125,source_end:6.5}});assert.equal(d.open,false);});
test('stale edit cannot append a previously reviewed range',async()=>{const h=setup();await h.studio.reviewShot('a');const d=h.studio.shotReview;await all(d).find(n=>n.tag==='video').fire('loadedmetadata');h.set({...h.get(),revision:99});await all(d).find(n=>n.tag==='form').fire('submit');assert.equal(h.requests.length,0);assert.match(all(d).find(n=>n.className==='library-shot-status').textContent,/changed/);});
test('source replacement and preview metadata mismatch fail safely',async()=>{const h=setup();await h.studio.reviewShot('a');const d=h.studio.shotReview,v=all(d).find(n=>n.tag==='video');v.duration=12;await v.fire('loadedmetadata');assert.equal(by(d,'shotAppend').disabled,true);assert.match(all(d).find(n=>n.className==='library-shot-status').textContent,/does not match/);});
test('play marked source range stops at Out without editing',async()=>{const h=setup();await h.studio.reviewShot('a');const d=h.studio.shotReview,v=all(d).find(n=>n.tag==='video');await v.fire('loadedmetadata');const points=all(d).filter(n=>n.dataset.shotPoint);points[0].value='1';points[1].value='4';await by(d,'shotPreview').fire('click');assert.equal(v.currentTime,1);v.currentTime=4;await v.fire('timeupdate');assert.equal(v.paused,true);assert.equal(h.requests.length,0);});
test('repeat clicks cannot submit the same successful review twice',async()=>{const h=setup();await h.studio.reviewShot('a');const d=h.studio.shotReview;await all(d).find(n=>n.tag==='video').fire('loadedmetadata');const f=all(d).find(n=>n.tag==='form');await f.fire('submit');await f.fire('submit');assert.equal(h.requests.length,1);});

test('reviewed range inserts at edited playhead with the same stale guard',async()=>{const h=setup();h.set({...h.get(),draft:{output_duration:10}});h.studio.options.time=()=>3;await h.studio.reviewShot('a');const d=h.studio.shotReview;await all(d).find(n=>n.tag==='video').fire('loadedmetadata');const points=all(d).filter(n=>n.dataset.shotPoint);points[0].value='1';points[1].value='2.5';await points[0].fire('input');const insert=by(d,'shotInsert');assert.equal(insert.disabled,false);await all(d).find(n=>n.tag==='form').fire('submit',{submitter:insert});assert.deepEqual(plain(h.requests[0]),{action:'media_insert',payload:{asset_id:'a',source_start:1,source_end:2.5,start:3}});});

test('insertion readiness blocks crossing layers and active alternatives while preserving end append',()=>{const h=setup();h.context.p={draft:{output_duration:10},manual:{media_clips:[{start:2,end:5}]}};assert.match(vm.runInContext('libraryInsertReadiness(p,3)',h.context),/crosses/);h.context.p={draft:{output_duration:10},caption_alternative_status:{active_id:'saved'}};assert.match(vm.runInContext('libraryInsertReadiness(p,3)',h.context),/alternative/);assert.equal(vm.runInContext('libraryInsertReadiness(p,10)',h.context),'');h.context.p={draft:{output_duration:10,audio_plan:[{}]}};assert.match(vm.runInContext('libraryInsertReadiness(p,3)',h.context),/audio plan/);});

function storageFixture() {
  const entries=new Map();return {entries,getItem:key=>entries.has(key)?entries.get(key):null,
    setItem:(key,value)=>entries.set(key,value),removeItem:key=>entries.delete(key)};
}
const points=dialog=>all(dialog).filter(n=>n.dataset.shotPoint);
async function ready(h) {await h.studio.reviewShot('a');const d=h.studio.shotReview;await all(d).find(n=>n.tag==='video').fire('loadedmetadata');return d;}
async function choose(d,start,end){const inputs=points(d);inputs[0].value=String(start);inputs[1].value=String(end);await inputs[0].fire('input');}

test('explicit saved marks survive review close and a fresh browser context without editing',async()=>{
  const storage=storageFixture(),h=setup(storage),before=JSON.stringify(h.get());
  const d=await ready(h);await choose(d,2.125,6.5);await by(d,'shotSaveMarks').fire('click');
  assert.match(by(d,'shotMarksStatus').textContent,/Source marks saved/);
  await by(d,'shotKeep').fire('click');assert.equal(JSON.stringify(h.get()),before);assert.equal(h.requests.length,0);
  const reopened=setup(storage),next=await ready(reopened);
  assert.deepEqual(points(next).map(n=>n.value),['2.125','6.5']);
  assert.match(by(next,'shotMarksStatus').textContent,/restored/);
  await all(next).find(n=>n.tag==='form').fire('submit');
  assert.deepEqual(plain(reopened.requests[0].payload),{asset_id:'a',source_start:2.125,source_end:6.5});
});

test('unsaved marks are not silently persisted on cancel or append',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h);
  await choose(d,1,4);await by(d,'shotKeep').fire('click');assert.equal(storage.entries.size,0);
  const next=await ready(h);assert.deepEqual(points(next).map(n=>n.value),['0','10']);
  await choose(next,2,5);await all(next).find(n=>n.tag==='form').fire('submit');assert.equal(storage.entries.size,0);
});

test('marks are isolated by project and imported asset IDs, never by equal filenames',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h);await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
  for(const variant of ['project','asset']){
    const other=setup(storage),p=other.get();
    if(variant==='project')p.id='another-project';else{p.assets.b={...p.assets.a,id:'b'};delete p.assets.a;}
    other.context.p=p;other.context.assetId=variant==='project'?'a':'b';
    assert.equal(vm.runInContext('readLibraryShotMarks(p,assetId).state',other.context),'empty');
  }
});

test('reimported equal-name equal-metadata footage never inherits another import selection',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h);await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
  const oldAsset=h.get().assets.a;
  h.get().assets.b={...oldAsset,id:'b',url:'/original/b'};
  await h.studio.reviewShot('b');const imported=h.studio.shotReview;
  await all(imported).find(n=>n.tag==='video').fire('loadedmetadata');
  assert.deepEqual(points(imported).map(n=>n.value),['0','10']);
  await choose(imported,5,8);await by(imported,'shotSaveMarks').fire('click');
  const original=await ready(h);assert.deepEqual(points(original).map(n=>n.value),['1','4']);
  assert.equal(storage.entries.size,2);assert.equal(h.requests.length,0);
});

test('fractional source timings remain valid HTML number inputs after save and restore',async()=>{
  const storage=storageFixture(),h=setup(storage);h.get().assets.a.duration=10.123456;
  const d=await ready(h);assert.ok(points(d).every(n=>n.step==='any'));
  await choose(d,1.2345,4.5678);await by(d,'shotSaveMarks').fire('click');
  const next=await ready(h);assert.deepEqual(points(next).map(n=>n.value),['1.2345','4.5678']);
  assert.ok(points(next).every(n=>n.step==='any'));
  await all(next).find(n=>n.tag==='form').fire('submit');
  assert.deepEqual(plain(h.requests[0].payload),{asset_id:'a',source_start:1.2345,source_end:4.5678});
});

test('blocked storage reads report unavailable while range selection remains usable',async()=>{
  const h=setup({getItem(){throw Error('SecurityError');}}),d=await ready(h);
  assert.match(by(d,'shotMarksStatus').textContent,/storage is unavailable/);
  assert.deepEqual(points(d).map(n=>n.value),['0','10']);assert.equal(by(d,'shotAppend').disabled,false);
});

test('metadata mismatch after a ready event blocks saving and editing',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h),video=all(d).find(n=>n.tag==='video');
  video.duration=12;await video.fire('loadedmetadata');
  for(const key of ['shotSaveMarks','shotAppend','shotInsert','shotPreview'])assert.equal(by(d,key).disabled,true);
  await by(d,'shotSaveMarks').fire('click');assert.equal(storage.entries.size,0);assert.equal(h.requests.length,0);
});

test('save uses the same native form validity gate as insert and append',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h);
  all(d).find(n=>n.tag==='form').reportValidity=()=>false;
  await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
  assert.equal(storage.entries.size,0);assert.doesNotMatch(by(d,'shotMarksStatus').textContent,/Source marks saved/);
});

test('revision changes and renames retain marks but duration or dimensions changes invalidate them',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h);await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
  for(const field of ['duration','width','height']){
    const next=setup(storage);next.get().assets.a[field]+=1;next.context.p=next.get();
    assert.equal(vm.runInContext('readLibraryShotMarks(p,"a").state',next.context),'stale');
  }
  const next=setup(storage);next.get().revision=100;next.get().assets.a.name='Renamed original.mp4';next.get().assets.a.url='/regenerated-preview';
  const reopened=await ready(next);assert.deepEqual(points(reopened).map(n=>n.value),['1','4']);
});

test('clear saved marks restores the full source without a timeline edit',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h);await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
  await by(d,'shotResetMarks').fire('click');assert.equal(storage.entries.size,0);assert.deepEqual(points(d).map(n=>n.value),['0','10']);
  assert.match(by(d,'shotMarksStatus').textContent,/cleared/);assert.equal(h.requests.length,0);
});

test('blocked or full browser storage never loses the current selection or claims a save',async()=>{
  for(const storage of [undefined,{getItem(){return null;},setItem(){throw Error('QuotaExceededError');},removeItem(){throw Error('SecurityError');}}]){
    const h=setup(storage),d=await ready(h);await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
    assert.match(by(d,'shotMarksStatus').textContent,/cannot save|could not be saved/);
    assert.deepEqual(points(d).map(n=>n.value),['1','4']);assert.equal(by(d,'shotAppend').disabled,false);
    await by(d,'shotResetMarks').fire('click');assert.deepEqual(points(d).map(n=>n.value),['1','4']);
    assert.match(by(d,'shotMarksStatus').textContent,/cannot clear|could not be cleared/);
  }
});

test('malformed, oversized, wrong-version and out-of-bounds stored marks are ignored without deletion',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h);await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
  const [key,valid]=[...storage.entries][0];
  for(const bad of ['{broken','x'.repeat(2049),JSON.stringify({...JSON.parse(valid),identity:'v99'}),JSON.stringify({...JSON.parse(valid),source_end:999}),JSON.stringify({...JSON.parse(valid),source_start:'1'})]){
    storage.entries.set(key,bad);const next=setup(storage),dialog=await ready(next);
    assert.deepEqual(points(dialog).map(n=>n.value),['0','10']);assert.equal(storage.entries.get(key),bad);
    assert.match(by(dialog,'shotMarksStatus').textContent,/unreadable/);
  }
});

test('stale project or replaced source cannot save or clear marks from an open dialog',async()=>{
  for(const variant of ['project','source','revision']){
    const storage=storageFixture(),h=setup(storage),d=await ready(h);await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
    const before=JSON.stringify([...storage.entries]);
    if(variant==='source')h.get().assets.a={...h.get().assets.a,duration:11};
    else if(variant==='project')h.set({...h.get(),id:'other'});else h.get().revision+=1;
    await by(d,'shotSaveMarks').fire('click');await by(d,'shotResetMarks').fire('click');
    assert.match(by(d,'shotMarksStatus').textContent,/changed.*saved marks are unchanged/);
    assert.equal(by(d,'shotSaveMarks').disabled,true);assert.equal(by(d,'shotResetMarks').disabled,true);
    assert.equal(JSON.stringify([...storage.entries]),before);assert.equal(h.requests.length,0);
  }
});

test('mark buttons label unsaved changes and blank inputs cannot overwrite saved marks',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h);await choose(d,1,4);await by(d,'shotSaveMarks').fire('click');
  const before=JSON.stringify([...storage.entries]),video=all(d).find(n=>n.tag==='video');video.currentTime=2;
  await by(d,'shotMark').fire('click');assert.match(by(d,'shotMarksStatus').textContent,/Selection changed/);
  await choose(d,'',5);assert.equal(by(d,'shotSaveMarks').disabled,true);await by(d,'shotSaveMarks').fire('click');
  assert.equal(JSON.stringify([...storage.entries]),before);
});

test('saved marks remain usable by insert and unchanged after timeline Undo or repeated reuse',async()=>{
  const storage=storageFixture(),h=setup(storage);h.set({...h.get(),draft:{output_duration:10}});h.studio.options.time=()=>3;
  const d=await ready(h);await choose(d,1,2.5);await by(d,'shotSaveMarks').fire('click');
  const saved=JSON.stringify([...storage.entries]);await all(d).find(n=>n.tag==='form').fire('submit',{submitter:by(d,'shotInsert')});
  assert.deepEqual(plain(h.requests[0]),{action:'media_insert',payload:{asset_id:'a',source_start:1,source_end:2.5,start:3}});
  h.set({...h.get(),revision:20,manual:{media_clips:[]}});
  const reopened=await ready(h);assert.deepEqual(points(reopened).map(n=>n.value),['1','2.5']);assert.equal(JSON.stringify([...storage.entries]),saved);
});

const videoOf=d=>all(d).find(n=>n.tag==='video');
const action=(d,key,value)=>all(d).find(n=>n.dataset[key]===value);
const reviewStatus=d=>all(d).find(n=>n.className==='library-shot-status').textContent;
const deferred=()=>{let resolve,reject;const promise=new Promise((ok,fail)=>{resolve=ok;reject=fail;});return{promise,resolve,reject};};
const sourceControls=d=>all(d).filter(n=>n.dataset.shotMark||n.dataset.shotJump||n.dataset.shotPoint||n.dataset.shotPreview||n.dataset.shotSaveMarks||n.dataset.shotAppend||n.dataset.shotInsert);

test('source controls and I/O require valid metadata and never autoplay when it arrives',async()=>{
  const h=setup();await h.studio.reviewShot('a');const d=h.studio.shotReview,v=videoOf(d);
  assert.ok(sourceControls(d).every(n=>n.disabled));v.currentTime=3;
  for(const key of ['in','out']){await action(d,'shotMark',key).fire('click');await action(d,'shotJump',key).fire('click');}
  const event=await d.fire('keydown',{key:'i'});await by(d,'shotPreview').fire('click');
  assert.equal(event.defaultPrevented,false);assert.deepEqual(points(d).map(n=>n.value),['0','10']);assert.equal(v.currentTime,3);assert.equal(v.playCalls,0);
  await v.fire('loadedmetadata');assert.equal(v.playCalls,0);assert.equal(v.paused,true);assert.equal(by(d,'shotPreview').textContent,'Play selected shot');
  assert.equal(action(d,'shotJump','in').disabled,false);assert.equal(h.requests.length,0);
});

test('I/O mark the source playhead only in the review dialog, pause preview and do not save or edit',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h),v=videoOf(d);
  assert.equal(h.body.listeners.keydown,undefined);
  assert.equal(action(d,'shotMark','in')['aria-keyshortcuts'],'I');assert.equal(action(d,'shotMark','out')['aria-keyshortcuts'],'O');
  await v.play();v.currentTime=2.34567;
  const input=await d.fire('keydown',{key:'i',target:v});
  assert.equal(input.defaultPrevented,true);assert.equal(input.propagationStopped,true);assert.equal(v.paused,true);
  v.currentTime=6.789;const output=await d.fire('keydown',{key:'O',target:by(d,'shotPreview')});
  assert.equal(output.defaultPrevented,true);assert.deepEqual(points(d).map(n=>n.value),['2.346','6.789']);
  assert.match(by(d,'shotMarksStatus').textContent,/Selection changed/);assert.equal(storage.entries.size,0);assert.equal(h.requests.length,0);
});

test('source keys leave typing, composition, modifiers, repeats and prevented events untouched',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d);v.currentTime=3;
  const editable=node('div');editable.setAttribute('contenteditable','true');const child=node('span');editable.append(child);
  const textbox=node('div');textbox.setAttribute('role','textbox');const textChild=node('span');textbox.append(textChild);
  const combobox=node('div');combobox.setAttribute('role','combobox');const comboChild=node('span');combobox.append(comboChild);
  const events=[...points(d),node('textarea'),node('select'),editable,child,textChild,comboChild,{isContentEditable:true}].map(target=>({target}));
  events.push(...['altKey','ctrlKey','metaKey','shiftKey','repeat','isComposing','defaultPrevented'].map(k=>({[k]:true})),{keyCode:229},{key:'x'},
    {getModifierState:key=>key==='AltGraph'},
    {target:v,composedPath:()=>[points(d)[0],v,d]});
  for(const extra of events){const e=await d.fire('keydown',{key:'i',...extra});assert.equal(e.defaultPrevented,!!extra.defaultPrevented);assert.equal(e.propagationStopped,false);}
  assert.deepEqual(points(d).map(n=>n.value),['0','10']);assert.equal(v.playCalls,0);assert.equal(h.requests.length,0);
});

test('Jump to In/Out pauses and seeks without changing saved marks or starting playback',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h),v=videoOf(d);await choose(d,2.125,6.5);await by(d,'shotSaveMarks').fire('click');
  const saved=JSON.stringify([...storage.entries]);await by(d,'shotPreview').fire('click');v.currentTime=3;
  await action(d,'shotJump','out').fire('click');assert.equal(v.currentTime,6.5);assert.equal(v.paused,true);assert.equal(v.playCalls,1);
  await action(d,'shotJump','in').fire('click');assert.equal(v.currentTime,2.125);assert.equal(v.paused,true);assert.equal(v.playCalls,1);
  assert.equal(by(d,'shotPreview').textContent,'Play selected shot');assert.deepEqual(points(d).map(n=>n.value),['2.125','6.5']);
  assert.equal(JSON.stringify([...storage.entries]),saved);assert.equal(h.requests.length,0);
});

test('invalid ranges block jumps and playback but leave mark controls available for correction',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d);await choose(d,8,4);v.currentTime=9;
  for(const key of ['in','out']){assert.equal(action(d,'shotJump',key).disabled,true);await action(d,'shotJump',key).fire('click');}
  assert.equal(v.currentTime,9);assert.equal(by(d,'shotPreview').disabled,true);await by(d,'shotPreview').fire('click');assert.equal(v.playCalls,0);
  assert.equal(action(d,'shotMark','out').disabled,false);await d.fire('keydown',{key:'o'});
  assert.deepEqual(points(d).map(n=>n.value),['8','9']);assert.equal(by(d,'shotPreview').disabled,false);assert.equal(h.requests.length,0);
});

test('selected playback toggles pause/resume, stops at Out and releases its old native boundary',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d),preview=by(d,'shotPreview');await choose(d,1,4);v.currentTime=7;
  await preview.fire('click');assert.equal(v.currentTime,1);assert.equal(preview.textContent,'Pause selected shot');
  v.currentTime=2;await preview.fire('click');assert.equal(v.paused,true);assert.equal(v.currentTime,2);assert.equal(preview.textContent,'Resume selected shot');
  await preview.fire('click');assert.equal(v.currentTime,2);assert.equal(v.paused,false);
  v.pause();await v.fire('pause');assert.equal(preview.textContent,'Resume selected shot');await preview.fire('click');
  v.currentTime=4.2;await v.fire('timeupdate');assert.equal(v.paused,true);assert.equal(v.currentTime,4);assert.equal(preview.textContent,'Play selected shot');
  await v.play();await v.fire('play');v.currentTime=5;await v.fire('timeupdate');
  assert.equal(v.paused,false);assert.equal(v.currentTime,5);assert.equal(preview.textContent,'Pause source preview');
  await preview.fire('click');assert.equal(v.paused,true);assert.equal(preview.textContent,'Play selected shot');
  await preview.fire('click');assert.equal(v.currentTime,1);assert.equal(h.requests.length,0);
});

test('an invalid selection still lets the transport pause native full-source playback',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d),preview=by(d,'shotPreview');await choose(d,8,4);
  assert.equal(preview.disabled,true);await v.play();await v.fire('play');
  assert.equal(preview.disabled,false);assert.equal(preview.textContent,'Pause source preview');
  await preview.fire('click');assert.equal(v.paused,true);assert.equal(preview.disabled,true);assert.equal(v.playCalls,1);
});

test('changing marks or clearing a saved range cancels the selected playback boundary',async()=>{
  const storage=storageFixture(),h=setup(storage),d=await ready(h),v=videoOf(d);await choose(d,1,4);
  await by(d,'shotPreview').fire('click');await choose(d,2,6);assert.equal(v.paused,true);assert.equal(by(d,'shotPreview').textContent,'Play selected shot');
  await v.play();v.currentTime=7;await v.fire('timeupdate');assert.equal(v.paused,false);
  await by(d,'shotResetMarks').fire('click');assert.equal(v.paused,true);assert.deepEqual(points(d).map(n=>n.value),['0','10']);
  assert.equal(v.playCalls,2);assert.equal(h.requests.length,0);
});

test('native scrubbing outside a selected range disarms it and pauses instead of restarting it',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d),preview=by(d,'shotPreview');await choose(d,2,6);await preview.fire('click');
  v.currentTime=3;await v.fire('seeking');assert.equal(v.paused,false);assert.equal(preview.textContent,'Pause selected shot');
  v.currentTime=1;await v.fire('seeking');assert.equal(v.paused,true);assert.equal(v.currentTime,1);assert.equal(preview.textContent,'Play selected shot');
  await v.play();v.currentTime=7;await v.fire('timeupdate');assert.equal(v.paused,false);assert.equal(v.playCalls,2);
});

test('native ended resets selected transport even when browser duration is slightly shorter than source metadata',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d);v.duration=9.9;await v.fire('durationchange');await choose(d,2,10);
  await by(d,'shotPreview').fire('click');v.currentTime=9.9;v.paused=true;await v.fire('ended');
  assert.equal(by(d,'shotPreview').textContent,'Play selected shot');assert.equal(v.playCalls,1);
  await by(d,'shotPreview').fire('click');assert.equal(v.currentTime,2);assert.equal(v.paused,false);
});

test('late rejected play after explicit pause is ignored and an active newer preview is preserved',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d),preview=by(d,'shotPreview'),pending=deferred();await choose(d,1,4);
  const play=v.play;v.play=function(){this.paused=false;this.playCalls++;return pending.promise;};
  const first=preview.fire('click');assert.equal(preview.textContent,'Pause selected shot');
  await preview.fire('click');assert.equal(v.paused,true);assert.equal(preview.textContent,'Resume selected shot');
  v.play=play;v.currentTime=2;await preview.fire('click');assert.equal(v.paused,false);
  pending.reject(Error('The play() request was interrupted by pause()'));await first;
  assert.equal(v.paused,false);assert.equal(preview.textContent,'Pause selected shot');assert.doesNotMatch(reviewStatus(d),/interrupted/);
});

test('play rejection reports the failure without starting a retry or changing the edit',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d);await choose(d,1,4);
  v.play=()=>Promise.reject(Error('NotAllowedError'));
  await by(d,'shotPreview').fire('click');assert.equal(v.paused,true);assert.equal(by(d,'shotPreview').textContent,'Play selected shot');
  assert.match(reviewStatus(d),/could not play.*NotAllowedError/);assert.equal(h.requests.length,0);
});

test('native pause during a pending play request preserves resume without reporting its expected interruption',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d),pending=deferred();await choose(d,1,4);
  v.play=function(){this.paused=false;this.playCalls++;return pending.promise;};
  const playback=by(d,'shotPreview').fire('click');v.currentTime=2;v.pause();await v.fire('pause');
  pending.reject(Error('The play() request was interrupted by pause()'));await playback;
  assert.equal(v.paused,true);assert.equal(v.currentTime,2);assert.equal(by(d,'shotPreview').textContent,'Resume selected shot');
  assert.doesNotMatch(reviewStatus(d),/interrupted|could not play/);assert.equal(v.playCalls,1);assert.equal(h.requests.length,0);
});

test('metadata changes, errors and emptied events stop playback and gate every source action until metadata returns',async()=>{
  for(const kind of ['durationchange','error','emptied']){
    const h=setup(),d=await ready(h),v=videoOf(d);await choose(d,1,4);await by(d,'shotPreview').fire('click');
    if(kind==='durationchange')v.duration=12;
    await v.fire(kind);assert.equal(v.paused,true);assert.ok(sourceControls(d).every(n=>n.disabled));assert.equal(v.controls,false);
    const before=points(d).map(n=>n.value);v.currentTime=3;await d.fire('keydown',{key:'i'});await action(d,'shotJump','out').fire('click');await by(d,'shotPreview').fire('click');
    assert.deepEqual(points(d).map(n=>n.value),before);assert.equal(v.currentTime,3);assert.equal(v.playCalls,1);
    v.duration=10;await v.fire('loadedmetadata');assert.equal(by(d,'shotPreview').disabled,false);assert.equal(v.controls,true);assert.equal(v.paused,true);assert.equal(v.playCalls,1);
  }
});

test('every source action rechecks live duration even before the durationchange event arrives',async()=>{
  for(const kind of ['mark','jump','preview','submit','save']){
    const storage=storageFixture(),h=setup(storage),d=await ready(h),v=videoOf(d);await choose(d,1,4);v.duration=12;v.currentTime=3;
    if(kind==='mark')await action(d,'shotMark','in').fire('click');
    if(kind==='jump')await action(d,'shotJump','out').fire('click');
    if(kind==='preview')await by(d,'shotPreview').fire('click');
    if(kind==='submit')await all(d).find(n=>n.tag==='form').fire('submit');
    if(kind==='save')await by(d,'shotSaveMarks').fire('click');
    assert.deepEqual(points(d).map(n=>n.value),['1','4']);assert.equal(v.currentTime,3);assert.equal(v.playCalls,0);assert.equal(h.requests.length,0);assert.equal(storage.entries.size,0);
    assert.ok(sourceControls(d).every(n=>n.disabled));assert.match(reviewStatus(d),/does not match/);
  }
});

test('stale project, source, revision and externally busy editor block monitor actions including native playback',async()=>{
  for(const variant of ['project','source','revision','busy','uploading']){
    const h=setup(),d=await ready(h),v=videoOf(d);await choose(d,1,4);
    if(variant==='project')h.set({...h.get(),id:'other'});
    else if(variant==='source')h.get().assets.a={...h.get().assets.a,url:'/replacement'};
    else if(variant==='revision')h.get().revision++;
    else if(variant==='busy')h.studio.options.busy=()=>true;
    else h.studio.uploading=true;
    v.currentTime=3;await action(d,'shotMark','in').fire('click');await action(d,'shotJump','out').fire('click');await by(d,'shotPreview').fire('click');
    const e=await d.fire('keydown',{key:'o'});assert.equal(e.defaultPrevented,false);
    assert.deepEqual(points(d).map(n=>n.value),['1','4']);assert.equal(v.currentTime,3);assert.equal(v.playCalls,0);assert.ok(sourceControls(d).every(n=>n.disabled));
    await v.play();await v.fire('play');assert.equal(v.paused,true);assert.equal(h.requests.length,0);
    if(variant==='busy'||variant==='uploading'){
      assert.equal(h.timers.size,1);await h.runTimers();assert.equal(h.timers.size,1);assert.equal(by(d,'shotPreview').disabled,true);
      h.studio.options.busy=()=>false;h.studio.uploading=false;await h.runTimers();
      assert.equal(by(d,'shotPreview').disabled,false);assert.equal(v.controls,true);assert.equal(v.paused,true);assert.equal(h.timers.size,0);
      assert.deepEqual(points(d).map(n=>n.value),['1','4']);assert.equal(v.playCalls,1);
    }else assert.equal(h.timers.size,0);
  }
});

test('pending append disables marks and transport, blocks close/cancel, and failure restores only valid controls',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d),pending=deferred();await choose(d,1,4);
  h.studio.options.edit=()=>pending.promise;
  const submission=all(d).find(n=>n.tag==='form').fire('submit');
  assert.ok(sourceControls(d).every(n=>n.disabled));assert.equal(by(d,'shotKeep').disabled,true);assert.equal(by(d,'shotResetMarks').disabled,true);
  await by(d,'shotKeep').fire('click');assert.equal(d.open,true);assert.equal((await d.fire('cancel')).defaultPrevented,true);
  v.currentTime=3;await d.fire('keydown',{key:'i'});await by(d,'shotPreview').fire('click');await action(d,'shotJump','out').fire('click');await by(d,'shotResetMarks').fire('click');
  assert.deepEqual(points(d).map(n=>n.value),['1','4']);assert.equal(v.playCalls,0);
  v.duration=12;await v.fire('durationchange');pending.reject(Error('Edit request failed'));await submission;
  assert.ok(sourceControls(d).every(n=>n.disabled));assert.equal(by(d,'shotKeep').disabled,false);assert.match(reviewStatus(d),/Edit request failed/);
  v.duration=10;await v.fire('loadedmetadata');assert.equal(by(d,'shotAppend').disabled,false);assert.equal(v.paused,true);
});

test('close releases all review listeners and late media/play completions cannot mutate or reopen it',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d),pending=deferred();await choose(d,1,4);
  v.play=function(){this.paused=false;this.playCalls++;return pending.promise;};
  const playback=by(d,'shotPreview').fire('click');
  assert.equal((await d.fire('cancel')).defaultPrevented,false);d.close();
  assert.equal(v.paused,true);assert.equal(v.released,true);assert.equal(v.src,undefined);assert.equal(d.removed,true);assert.equal(h.studio.shotReview,null);
  for(const n of all(d))for(const handlers of Object.values(n.listeners))assert.equal(handlers.length,0);
  const status=reviewStatus(d);pending.resolve();await playback;
  v.currentTime=8;await v.fire('loadedmetadata');await v.fire('error');await v.fire('play');await d.fire('keydown',{key:'i'});await by(d,'shotPreview').fire('click');
  assert.equal(reviewStatus(d),status);assert.deepEqual(points(d).map(n=>n.value),['1','4']);assert.equal(h.studio.shotReview,null);assert.equal(v.playCalls,1);assert.equal(h.requests.length,0);
});

test('the busy refresh releases its timer on close and ignores an already queued callback',async()=>{
  const h=setup(),d=await ready(h),v=videoOf(d);await choose(d,1,4);assert.equal(h.timers.size,0);
  h.studio.options.busy=()=>true;await by(d,'shotPreview').fire('click');assert.equal(h.timers.size,1);
  const queued=[...h.timers.values()][0];assert.equal(queued.delay,250);d.close();assert.equal(h.timers.size,0);
  h.studio.options.busy=()=>false;const second=await ready(h);await choose(second,2,5);const status=reviewStatus(second);
  await queued.fn();assert.equal(h.timers.size,0);assert.equal(h.studio.shotReview,second);assert.equal(reviewStatus(second),status);
  assert.deepEqual(points(second).map(n=>n.value),['2','5']);assert.equal(v.playCalls,0);assert.equal(videoOf(second).playCalls,0);
});

test('a busy refresh that discovers a replaced source stays blocked and stops polling',async()=>{
  const h=setup(),d=await ready(h);await choose(d,1,4);h.studio.options.busy=()=>true;await by(d,'shotPreview').fire('click');
  assert.equal(h.timers.size,1);h.get().assets.a={...h.get().assets.a,url:'/replacement'};await h.runTimers();
  assert.ok(sourceControls(d).every(n=>n.disabled));assert.equal(h.timers.size,0);assert.match(reviewStatus(d),/changed/);
  assert.deepEqual(points(d).map(n=>n.value),['1','4']);assert.equal(videoOf(d).playCalls,0);
});

test('opening another review detaches the previous monitor and never carries playback into the new one',async()=>{
  const h=setup(),first=await ready(h),oldVideo=videoOf(first);await choose(first,1,4);await by(first,'shotPreview').fire('click');
  const second=await ready(h);assert.equal(first.removed,true);assert.equal(oldVideo.paused,true);assert.equal(oldVideo.released,true);
  assert.equal(videoOf(second).playCalls,0);assert.equal(videoOf(second).paused,true);assert.deepEqual(points(second).map(n=>n.value),['0','10']);
  await first.fire('keydown',{key:'i'});assert.deepEqual(points(second).map(n=>n.value),['0','10']);
});

test('review opening still flushes pending edits and rechecks project or busy state before mounting',async()=>{
  for(const variant of ['failed','project','busy','uploading']){
    const h=setup(),pending=deferred();h.studio.flush=()=>pending.promise;const opening=h.studio.reviewShot('a');
    assert.equal(h.studio.shotReview,undefined);
    if(variant==='project')h.set({...h.get(),id:'next'});
    if(variant==='busy')h.studio.options.busy=()=>true;
    if(variant==='uploading')h.studio.uploading=true;
    pending.resolve(variant!=='failed');await opening;
    assert.equal(h.studio.shotReview,undefined);assert.equal(h.body.children.length,0);assert.equal(h.requests.length,0);
  }
});
