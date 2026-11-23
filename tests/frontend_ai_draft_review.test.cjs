const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/ai-draft-review.js'),'utf8').replace(/^export /gm,'');
const plain=value=>JSON.parse(JSON.stringify(value));
const tick=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve()};

class Element {
  constructor(doc,tag){this.ownerDocument=doc;this.tagName=tag.toUpperCase();this.children=[];this.listeners=new Map();this.attrs={};this.style={};this.paused=true;this.readyState=0;this.duration=8;this.videoWidth=960;this.videoHeight=540;this.seeking=false;this._time=0;this.frames=new Map();this.frameId=0;this.textContent='';this.disabled=false;this.hidden=false;this.isConnected=false;}
  connect(value){this.isConnected=value;this.children.forEach(n=>n.connect(value))}
  append(...nodes){nodes.forEach(n=>{n.parentElement=this;this.children.push(n);n.connect(this.isConnected)})}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);this.connect(false)}
  setAttribute(key,value){this.attrs[key]=String(value)}
  getAttribute(key){return this.attrs[key]??null}
  removeAttribute(key){delete this.attrs[key];if(key==='src')delete this.src}
  addEventListener(type,fn){const a=this.listeners.get(type)||[];a.push(fn);this.listeners.set(type,a)}
  emit(type,props={}){const e={target:this,preventDefault(){this.prevented=true},...props};for(const f of this.listeners.get(type)||[])f(e);return e}
  showModal(){this.open=true}
  close(){this.open=false;this.emit('close')}
  focus(){this.ownerDocument.activeElement=this;this.focuses=(this.focuses||0)+1}
  getClientRects(){return this.isConnected&&!this.hidden?[{}]:[]}
  get currentTime(){return this._time}
  set currentTime(value){if(this.throwSeek)throw Error('Synthetic seek failure');this._time=value;this.seeks=(this.seeks||0)+1}
  pause(){this.paused=true;this.emit('pause')}
  load(){this.loads=(this.loads||0)+1}
  play(){this.plays=(this.plays||0)+1;if(this.playError)return Promise.reject(this.playError);if(this.playPromise)return this.playPromise;this.paused=false;this.emit('play');if(!this.paused&&this.readyState>=2&&!this.seeking)this.emit('playing');return Promise.resolve()}
  requestVideoFrameCallback(fn){const id=++this.frameId;this.frames.set(id,fn);return id}
  cancelVideoFrameCallback(id){this.frames.delete(id)}
  frame(){const entries=[...this.frames];this.frames.clear();entries.forEach(([id,fn])=>fn(0,{}))}
}

function fixture(overrides={}){
  const doc={createElement:tag=>new Element(doc,tag)};doc.body=new Element(doc,'body');doc.body.connect(true);const origin=new Element(doc,'button');doc.body.append(origin);origin.focus();
  const context=vm.createContext({document:doc,AbortController});vm.runInContext(source+'\nglobalThis.api={AiDraftReview,aiReviewProposalIssue,formatAiReviewTime};',context);
  const proposal={proposal_id:'proposal-1',origin_id:'origin-1',project_id:'p',revision:7,apply_allowed:true,apply_issue:'',current:{duration:24,source_clip_counts:{A:2,B:0},media_count:9,text_count:3},proposed:{title:'Synthetic saved draft',summary:'Selected source material.',engine:'synthetic_review_fixture',output_duration:3,ranges:[{start:.5,end:2},{start:3,end:4.5}],source_slot:'A',source_duration:8},impact:{duration:20,source_clip_counts:{A:3,B:1},media_preserved:true,text_preserved:true},warnings:['Inspect transcript before applying.'],request:{instruction:'Keep the important action.',style:'story',duration_mode:'target',target_duration:3}};
  const calls=[],applies=[];let current=true,closes=0;
  const options={projectId:'p',revision:7,originId:'origin-1',sourceUrl:'/api/projects/p/media/A?generation=1',api:async(url,request)=>{calls.push({url,request});return{proposal}},isCurrent:()=>current,apply:async p=>{applies.push(p);return{id:'p',revision:8}},onClose:()=>closes++,...overrides};
  const review=new context.api.AiDraftReview(options);
  const metadata=()=>{review.video.readyState=2;review.video.emit('loadedmetadata')};
  const play=async()=>{metadata();await review.playRange()};
  const all=(node=doc.body)=>[node,...node.children.flatMap(n=>all(n))];
  return{...context.api,doc,origin,options,review,proposal,calls,applies,metadata,play,all,setCurrent:value=>current=value,get closes(){return closes}};
}

test('review time retains subsecond precision and handles invalid values',()=>{
  const f=fixture();assert.equal(f.formatAiReviewTime(61.234),'01:01.234');assert.equal(f.formatAiReviewTime(3600.004),'01:00:00.004');assert.equal(f.formatAiReviewTime(0),'00:00.000');for(const v of [-1,NaN,Infinity,'3',null])assert.equal(f.formatAiReviewTime(v),'Unavailable');
});
test('proposal validates exact project, revision, origin and proposal identity',()=>{
  const f=fixture();assert.equal(f.aiReviewProposalIssue(f.proposal,f.options),'');for(const key of ['project_id','revision','origin_id','proposal_id']){const p=plain(f.proposal);p[key]=key==='proposal_id'?'':key==='revision'?8:'other';assert.ok(f.aiReviewProposalIssue(p,f.options))}
});
test('malformed current or prospective counts/durations fail closed',()=>{
  const f=fixture();for(const edit of [p=>p.current.duration='24',p=>p.current.media_count=-1,p=>p.current.source_clip_counts.B=.2,p=>p.impact=null,p=>p.impact.media_preserved=9,p=>p.impact.text_preserved=null,p=>p.impact.duration=NaN]){const p=plain(f.proposal);edit(p);assert.ok(f.aiReviewProposalIssue(p,f.options))}
});
test('blocked stage may have no impact but must have a genuine reason',()=>{
  const f=fixture(),p=plain(f.proposal);p.apply_allowed=false;p.apply_issue='Retained media exceeds the shorter draft.';p.impact=null;assert.equal(f.aiReviewProposalIssue(p,f.options),'');p.apply_issue='';assert.ok(f.aiReviewProposalIssue(p,f.options));
});
test('invalid source passages, primary slot or metadata are never guessed',()=>{
  const f=fixture();for(const edit of [p=>p.proposed.source_slot='B',p=>p.proposed.source_duration=0,p=>p.proposed.ranges=[],p=>p.proposed.ranges=[null],p=>p.proposed.ranges[0].start=-1,p=>p.proposed.ranges[0].end=9,p=>p.proposed.ranges[0].start='0.5',p=>p.proposed.output_duration=Infinity]){const p=plain(f.proposal);edit(p);assert.ok(f.aiReviewProposalIssue(p,f.options))}
});
test('plain warnings and nullable request intent follow the exact payload contract',()=>{
  const f=fixture(),p=plain(f.proposal);p.request.duration_mode=null;p.request.target_duration=null;assert.equal(f.aiReviewProposalIssue(p,f.options),'');p.warnings=[{message:'not plain'}];assert.ok(f.aiReviewProposalIssue(p,f.options));p.warnings=[];p.request.instruction=null;assert.ok(f.aiReviewProposalIssue(p,f.options));
});
test('open sends exact read-only proposal request, never applies or autoplays',async()=>{
  const f=fixture(),before=plain(f.proposal);assert.equal(await f.review.open(),true);assert.equal(f.calls.length,1);assert.equal(f.calls[0].url,'/api/projects/p/ai-draft-proposal');assert.deepEqual(JSON.parse(f.calls[0].request.body),{expected_revision:7,origin_id:'origin-1'});assert.equal(f.calls[0].request.method,'POST');assert.equal(f.applies.length,0);assert.equal(f.review.video.plays,undefined);assert.equal(f.review.applyButton.disabled,true);assert.equal(f.doc.activeElement,f.review.keepButton);assert.deepEqual(plain(f.proposal),before);f.review.close();
});
test('current and staged impact durations stay distinct from candidate source selection',async()=>{
  const f=fixture();await f.review.open();const text=f.all().map(e=>e.textContent).join('\n');assert.match(text,/Current timeline/);assert.match(text,/00:24\.000/);assert.match(text,/After applying/);assert.match(text,/00:20\.000/);assert.match(text,/Selected source: 00:03\.000/);assert.match(text,/9 imported media and 3 custom text layers remain/);assert.match(text,/not the final composite/);assert.match(text,/Inspect transcript/);f.review.close();
});
test('proposal descriptions remain text rather than executable markup',async()=>{
  const f=fixture();f.proposal.proposed.title='<img src=x onerror=alert(1)>';f.proposal.warnings=['<script>bad()</script>'];await f.review.open();assert.ok(f.all().some(n=>n.textContent===f.proposal.proposed.title));assert.equal(f.all().some(n=>n.tagName==='IMG'||n.tagName==='SCRIPT'),false);f.review.close();
});
test('initial metadata seeks once while paused; later durationchange does not reset inspection',async()=>{
  const f=fixture();await f.review.open();f.metadata();assert.equal(f.review.video.currentTime,.5);assert.equal(f.review.video.paused,true);assert.equal(f.review.video.plays,undefined);f.review.video.currentTime=1.2;const seeks=f.review.video.seeks;f.review.video.emit('durationchange');assert.equal(f.review.video.currentTime,1.2);assert.equal(f.review.video.seeks,seeks);f.review.close();
});
test('passage selected during loading becomes the initial seek without autoplay',async()=>{
  const f=fixture();await f.review.open();assert.equal(f.review.selectRange(1),true);f.metadata();assert.equal(f.review.video.currentTime,3);assert.equal(f.review.rangeButtons[1].getAttribute('aria-pressed'),'true');assert.equal(f.review.rangeButtons[0].getAttribute('aria-pressed'),'false');assert.equal(f.review.video.plays,undefined);f.review.close();
});
test('Apply requires actual playable source activity, not play request or loaded metadata',async()=>{
  const f=fixture();await f.review.open();f.metadata();await f.review.apply();assert.equal(f.applies.length,0);f.review.video.emit('play');assert.equal(f.review.applyButton.disabled,true);f.review.video.readyState=1;f.review.video.emit('playing');assert.equal(f.review.applyButton.disabled,true);f.review.video.readyState=2;await f.review.playRange();assert.equal(f.review.previewed,true);assert.equal(f.review.applyButton.disabled,false);f.review.close();
});
test('a validated application blocker does not prevent read-only source inspection',async()=>{
  const f=fixture();f.proposal.apply_allowed=false;f.proposal.apply_issue='A is locked.';f.proposal.impact=null;await f.review.open();await f.play();assert.equal(f.review.previewed,true);assert.equal(f.review.applyButton.disabled,true);assert.match(f.review.applyButton.title,/locked/);assert.ok(f.all().some(e=>e.textContent==='A is locked.'));await f.review.apply();assert.equal(f.applies.length,0);f.review.close();
});
for(const mode of ['duration','dimensions','nonfinite','shorter'])test(`bad actual ${mode} metadata prevents source approval and application`,async()=>{
  const f=fixture();await f.review.open();if(mode==='duration')f.review.video.duration=9;if(mode==='dimensions')f.review.video.videoWidth=0;if(mode==='nonfinite')f.review.video.duration=Infinity;if(mode==='shorter')f.review.video.duration=4;f.metadata();assert.equal(f.review.metadataReady,false);assert.equal(f.review.playButton.disabled,true);assert.equal(f.review.applyButton.disabled,true);assert.match(f.review.sourceStatus.textContent,/metadata/);await f.review.apply();assert.equal(f.applies.length,0);f.review.close();
});
test('changed source metadata after playback invalidates prior preview eligibility',async()=>{
  const f=fixture();await f.review.open();await f.play();f.review.video.duration=20;f.review.video.emit('durationchange');assert.equal(f.review.previewed,false);assert.equal(f.review.video.paused,true);assert.equal(f.review.applyButton.disabled,true);f.review.close();
});
test('seek throw and decode error release playback eligibility without an edit',async()=>{
  for(const mode of ['seek','error']){const f=fixture();await f.review.open();if(mode==='seek'){f.review.video.throwSeek=true;f.metadata()}else{await f.play();f.review.video.emit('error')}assert.equal(f.review.applyButton.disabled,true);assert.equal(f.review.video.paused,true);assert.equal(f.review.video.controls,false);await f.review.apply();assert.equal(f.applies.length,0);f.review.close()}
});
test('rejected playback can be retried but never counts as inspected source',async()=>{
  const f=fixture();await f.review.open();f.metadata();f.review.video.playError=Error('Gesture required');assert.equal(await f.review.playRange(),false);assert.equal(f.review.previewed,false);assert.equal(f.review.applyButton.disabled,true);f.review.video.playError=null;await f.review.playRange();assert.equal(f.review.previewed,true);f.review.close();
});
test('late playback failure cannot overwrite a newly selected passage or closed viewer',async()=>{
  for(const mode of ['selection','close']){const f=fixture();await f.review.open();f.metadata();let reject;f.review.video.playPromise=new Promise((_,fail)=>reject=fail);const playing=f.review.playRange();if(mode==='selection')f.review.selectRange(1);else f.review.close();const text=f.review.sourceStatus.textContent;reject(Error('Old play failure'));await playing;assert.equal(f.review.sourceStatus.textContent,text);f.review.close()}
});
test('audition stops at the selected end and does not silently continue into another passage',async()=>{
  const f=fixture();await f.review.open();await f.play();assert.equal(f.review.video.frames.size,1);f.review.video.currentTime=2.01;f.review.video.frame();assert.equal(f.review.video.paused,true);assert.equal(f.review.rangeIndex,0);assert.equal(f.review.video.frames.size,0);f.review.selectRange(1);await f.review.playRange();assert.equal(f.review.video.currentTime,3);f.review.video.currentTime=1;f.review.video.emit('timeupdate');assert.equal(f.review.video.currentTime,3);f.review.close();assert.equal(f.review.video.frames.size,0);
});
for(const how of ['Keep','Escape','Close'])test(`${how} dismisses without application, aborts load, unloads media and restores focus once`,async()=>{
  const f=fixture();await f.review.open();await f.play();if(how==='Keep')f.review.keepButton.emit('click');else if(how==='Escape')assert.equal(f.review.dialog.emit('cancel').prevented,true);else f.review.closeButton.emit('click');assert.equal(f.applies.length,0);assert.equal(f.review.abort.signal.aborted,true);assert.equal(f.review.video.paused,true);assert.equal(f.review.video.src,undefined);assert.equal(f.review.dialog.isConnected,false);assert.equal(f.doc.activeElement,f.origin);assert.equal(f.closes,1);f.review.close();assert.equal(f.closes,1);
});
test('late load after dismissal cannot install a source or proposal',async()=>{
  let resolve;const f=fixture({api:()=>new Promise(done=>resolve=done)});const opening=f.review.open();f.review.close();resolve({proposal:f.proposal});assert.equal(await opening,false);assert.equal(f.review.video,undefined);assert.equal(f.review.proposal,undefined);assert.equal(f.applies.length,0);
});
test('API errors and invalid response identity keep a closable sheet without source playback',async()=>{
  for(const mode of ['error','identity']){const f=fixture();if(mode==='error')f.options.api=async()=>{throw Error('Review unavailable')};else f.proposal.project_id='other';assert.equal(await f.review.open(),false);assert.equal(f.review.applyButton.disabled,true);assert.equal(f.review.keepButton.disabled,false);assert.equal(f.review.video,undefined);f.review.close()}
});
test('stale context before or after load cannot issue or populate a proposal review',async()=>{
  const f=fixture();f.setCurrent(false);assert.equal(await f.review.open(),false);assert.equal(f.calls.length,0);assert.match(f.review.message.textContent,/project changed/);f.review.close();
  let resolve;const g=fixture({api:()=>new Promise(done=>resolve=done)});const opening=g.review.open();g.setCurrent(false);resolve({proposal:g.proposal});await opening;assert.equal(g.review.video,undefined);assert.equal(g.applies.length,0);g.review.close();
});
test('stale context while auditioning pauses the source and blocks Apply',async()=>{
  const f=fixture();await f.review.open();await f.play();f.setCurrent(false);f.review.video.frame();assert.equal(f.review.video.paused,true);assert.equal(f.review.applyButton.disabled,true);await f.review.apply();assert.equal(f.applies.length,0);f.review.close();
});
test('one pending Apply pins exact proposal and refuses repeat, cancel, range change or replacement modal',async()=>{
  let finish;const f=fixture({apply:p=>{f.applies.push(p);return new Promise(done=>finish=done)}});await f.review.open();await f.play();const applied=f.review.apply();assert.equal(f.review.applying,true);assert.equal(f.review.close(),false);assert.equal(f.review.keepButton.disabled,true);assert.equal(f.review.closeButton.disabled,true);assert.equal(f.review.selectRange(1),false);assert.equal(await f.review.apply(),false);const second=new f.AiDraftReview(f.options);assert.equal(await second.open(),false);assert.equal(second.dialog,undefined);assert.equal(f.applies.length,1);assert.equal(f.applies[0],f.proposal);finish({id:'p',revision:8});assert.equal(await applied,true);assert.equal(f.review.closed,true);assert.equal(f.closes,1);
});
for(const outcome of ['null','throw','wrong-project','old-revision'])test(`unconfirmed ${outcome} Apply requires a fresh review without automatic retry`,async()=>{
  const f=fixture({apply:async p=>{f.applies.push(p);if(outcome==='throw')throw Error('Saved proposal changed');return outcome==='null'?null:outcome==='wrong-project'?{id:'other',revision:8}:{id:'p',revision:7}}});await f.review.open();await f.play();assert.equal(await f.review.apply(),false);assert.equal(f.review.applyButton.disabled,true);assert.equal(f.review.keepButton.disabled,false);f.review.video.emit('playing');await f.review.apply();assert.equal(f.applies.length,1);f.review.close();
});
test('repeat open on same instance fetches once; new review closes and releases its predecessor',async()=>{
  const f=fixture();await f.review.open();assert.equal(await f.review.open(),true);assert.equal(f.calls.length,1);const next=new f.AiDraftReview(f.options);await next.open();assert.equal(f.review.closed,true);assert.equal(f.review.video.src,undefined);assert.equal(f.calls.length,2);next.close();assert.equal(await next.open(),false);
});
test('close callback failure and disconnected origin cannot trap or resurrect the modal',async()=>{
  const f=fixture({onClose:()=>{throw Error('Host close issue')}});await f.review.open();f.origin.remove();assert.doesNotThrow(()=>f.review.close());assert.equal(f.review.dialog.isConnected,false);assert.notEqual(f.doc.activeElement,f.origin);
});
test('comparison layout keeps controls outside scrollable body and supports narrow/RTL content',()=>{
  const css=fs.readFileSync(path.join(__dirname,'../web/studio-workbench.css'),'utf8');assert.match(css,/\.ai-review-content\s*\{[^}]*overflow:auto/);assert.match(css,/\.ai-review-footer\s*\{[^}]*flex:none/);assert.match(css,/\.ai-review-passage\s*\{[^}]*text-align:start[^}]*overflow-wrap:anywhere/);assert.match(css,/@media \(max-width:680px\)/);assert.match(css,/\.ai-review-actions button\s*\{[^}]*min-height:44px/);
});

test('an allowed response may not silently change retained media or custom text',()=>{
  const f=fixture();for(const key of ['media_preserved','text_preserved']){const p=plain(f.proposal);p.impact[key]=false;assert.match(f.aiReviewProposalIssue(p,f.options),/would change/);p.apply_allowed=false;p.apply_issue='Existing layers cannot be preserved.';assert.equal(f.aiReviewProposalIssue(p,f.options),'')}
});
test('review styling uses the existing light and dark workbench tokens',()=>{
  const css=fs.readFileSync(path.join(__dirname,'../web/studio-workbench.css'),'utf8').split('/* Compare a saved AI source edit')[1];assert.ok(css);assert.match(css,/var\(--line\)/);assert.match(css,/var\(--paper\)/);assert.doesNotMatch(css,/var\(--(?:border|text)\)/);
});

test('late queued playing after a pause cannot unlock an unplayed review',async()=>{
  const f=fixture();await f.review.open();f.metadata();f.review.video.pause();f.review.video.emit('playing');assert.equal(f.review.previewed,false);assert.equal(f.review.applyButton.disabled,true);f.review.selectRange(1);f.review.video.emit('playing');assert.equal(f.review.applyButton.disabled,true);f.review.close();
});
test('native playback cannot restart while a real Apply is pending',async()=>{
  let finish;const f=fixture({apply:()=>new Promise(done=>finish=done)});await f.review.open();await f.play();const applied=f.review.apply();assert.equal(f.review.video.controls,false);await f.review.video.play();assert.equal(f.review.video.paused,true);finish(null);await applied;assert.equal(f.review.video.controls,false);f.review.close();
});
test('native rate changes cannot contradict normal-speed original-source audition',async()=>{
  const f=fixture();await f.review.open();await f.play();assert.equal(f.review.video.playbackRate,1);f.review.video.playbackRate=2;f.review.video.emit('ratechange');assert.equal(f.review.video.playbackRate,1);assert.equal(f.review.video.defaultPlaybackRate,1);f.review.close();
});
