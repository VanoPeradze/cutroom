const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

function harness(overrides = {}) {
  class Node {
    constructor(tag) { this.tag = tag; this.style = {}; this.children = []; this.listeners = {}; this.paused = true; }
    append(...nodes) { this.children.push(...nodes); }
    setAttribute(key, value) { this[key] = value; }
    removeAttribute(key) { delete this[key]; }
    addEventListener(type, fn) { this.listeners[type] = fn; }
    emit(type) { this.listeners[type]?.({preventDefault() {}}); }
    showModal() { this.open = true; }
    close() { this.open = false; this.emit('close'); }
    remove() { this.removed = true; }
    pause() { this.paused = true; }
    load() { this.loads = (this.loads || 0) + 1; }
    focus() { this.focused = true; }
  }
  const context = vm.createContext({AbortController, document: {body: new Node('body'), createElement: tag => new Node(tag)}});
  const source = fs.readFileSync(require('node:path').join(__dirname, '../web/reel-proposals.js'), 'utf8').replace(/^export /gm, '');
  vm.runInContext(source + '\nglobalThis.exports = {ReelProposalReview, supportsReelReview, formatReelReviewTime};', context);
  const calls = [];
  const proposal = {project_id:'p', revision:3, candidate_id:'alt', proposal_id:'digest', ranges:[{start:5,end:7},{start:8,end:15}], output_duration:9};
  const options = {
    project:{id:'p',revision:3}, candidateId:'alt', copy: (_he,en) => en, formatTime: String,
    sourceUrl:'/api/projects/p/media/A?generation=source-v1', isCurrent: () => true,
    api: async(url, request) => {calls.push({url,request});return {proposal};},
    apply: async value => {calls.push({applied:value});return {id:'p',revision:4};}, ...overrides,
  };
  return {review:new context.exports.ReelProposalReview(options), calls, options, proposal, ...context.exports};
}

test('review shows code-owned ranges, requires playback and applies exactly once', async () => {
  const {review,calls,proposal} = harness();
  await review.open();
  assert.equal(calls.length,1);
  assert.deepEqual(JSON.parse(calls[0].request.body), {candidate_id:'alt',expected_revision:3});
  assert.equal(review.applyButton.disabled,true);
  assert.match(review.ranges.textContent,/00:05\.000–00:07\.000.*00:08\.000–00:15\.000.*00:09\.000/);
  assert.match(review.message.textContent,/still needs review/);
  await review.apply();assert.equal(calls.length,1);
  review.video.emit('loadedmetadata');assert.equal(review.video.currentTime,5);
  review.video.emit('playing');assert.equal(review.applyButton.disabled,false);
  await Promise.all([review.apply(),review.apply()]);
  assert.equal(calls.length,2);assert.equal(calls[1].applied,proposal);
  assert.equal(review.closed,true);assert.equal(review.video.src,undefined);
});

test('keep current and Escape cancel do not submit an edit and dispose media', async () => {
  for (const type of ['keep','cancel']) {
    const {review,calls} = harness();await review.open();
    if (type === 'keep') review.keepButton.emit('click');else review.dialog.emit('cancel');
    assert.equal(review.closed,true);assert.equal(calls.length,1);
    assert.equal(review.abort.signal.aborted,true);assert.equal(review.video.paused,true);
    assert.equal(review.dialog.removed,true);
  }
});

test('late response after cancel cannot populate preview or apply', async () => {
  let resolve;
  const gate = new Promise(done => {resolve=done;});
  const {review,calls,proposal} = harness({api:() => gate});
  const opening = review.open();review.close();resolve({proposal});await opening;
  assert.equal(review.proposal,undefined);assert.equal(review.video.src,undefined);
  await review.apply();assert.equal(calls.length,0);
});

test('changed project is rejected both before preview and before accept', async () => {
  for (const stage of ['load','accept']) {
    let current = stage !== 'load';
    const {review,calls} = harness({isCurrent:()=>current});await review.open();
    current=false;review.video.emit('playing');await review.apply();
    assert.equal(calls.length,1);assert.match(review.message.textContent,/project changed/);
    assert.equal(review.applyButton.disabled,true);review.close();
  }
});

test('playback follows source gaps; failed decode prevents apply', async () => {
  const {review,calls} = harness();await review.open();
  review.video.paused=false;review.video.currentTime=7;review.video.emit('timeupdate');
  assert.equal(review.rangeIndex,1);assert.equal(review.video.currentTime,8);
  review.video.currentTime=15;review.video.emit('timeupdate');assert.equal(review.video.paused,true);
  review.video.emit('playing');review.video.emit('error');await review.apply();
  assert.equal(review.applyButton.disabled,true);assert.equal(calls.length,1);review.close();
});

test('server rejection is not retried and a fresh review is required', async () => {
  let attempts=0;
  const {review} = harness({apply:async()=>{attempts++;throw new Error('stale source');}});
  await review.open();review.video.emit('playing');await review.apply();
  assert.equal(attempts,1);assert.equal(review.applyButton.disabled,true);
  assert.equal(review.keepButton.disabled,false);assert.match(review.message.textContent,/stale source/);
  review.video.emit('playing');await review.apply();assert.equal(attempts,1);review.close();
});

test('only supported single-source projects enter the new review path', () => {
  const {supportsReelReview} = harness();
  assert.equal(supportsReelReview({sources:{A:{}}}),true);
  for (const project of [{sources:{}},{sources:{A:{},B:{}}},{sources:{A:{}},manual:{sequence:{}}},{sources:{A:{}},manual:{source_tracks:{}}}]) {
    assert.equal(supportsReelReview(project),false);
  }
});

test('source ranges retain milliseconds, hour offsets and rounding carry', () => {
  const {formatReelReviewTime:format} = harness();
  for (const [value,expected] of [[0,'00:00.000'],[1.5,'00:01.500'],[1.75,'00:01.750'],[3.75,'00:03.750'],[59.9996,'01:00.000'],[3601.25,'01:00:01.250']]) assert.equal(format(value),expected);
  for (const value of [-1,NaN,Infinity,null,'1.5',true,Number.MAX_SAFE_INTEGER]) assert.equal(format(value),'—');
});

test('normal app routes eligible alternatives through review and never auto-retries its token', () => {
  const source = fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
  assert.match(source,/new ReelProposalReview\(/);
  assert.match(source,/proposal_id: proposal\.proposal_id/);
  assert.match(source,/if \(detail\.proposal_id \|\|/);
});

test('normal app click flushes saved edits and passes the reviewed identity to manual apply', async () => {
  const source = fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8').replace(/\r\n/g,'\n');
  const start = source.indexOf('  elements.reelCandidateList.addEventListener("click"');
  const end = source.indexOf('\n\n  elements.previewPlay',start);
  assert.ok(start >= 0 && end > start);
  let click, options;const calls=[];
  const project={id:'p',revision:7,sources:{A:{url:'source'}}};
  const context=vm.createContext({
    state:{project,draftDirtyReasons:new Set()},elements:{reelCandidateList:{addEventListener:(_type,fn)=>{click=fn;}}},
    supportsReelReview:()=>true,flushCurrentProjectSaves:async()=>{calls.push('flush');return true;},
    foregroundBusy:()=>false,pauseAllMedia:()=>calls.push('pause'),api(){},uiCopy(){},formatTime(){},
    sourceMediaUrl:()=>'/source',ReelProposalReview:class {constructor(value){options=value;}async open(){calls.push('open');}},
    applyManualEdit:async(action,detail)=>{calls.push({action,detail});return project;},
  });
  vm.runInContext(source.slice(start,end),context);
  await click({target:{closest:()=>({disabled:false,dataset:{candidateId:'alt'}})}});
  assert.deepEqual(calls,['flush','pause','open']);
  assert.equal(options.isCurrent(),true);
  await options.apply({candidate_id:'alt',proposal_id:'bound-token'});
  assert.deepEqual(JSON.parse(JSON.stringify(calls[3])),{action:'apply_reel_candidate',detail:{candidate_id:'alt',proposal_id:'bound-token'}});
  await options.apply({kind:'unverified_source_candidate',candidate_id:'review-new',proposal_id:'source-token'});
  assert.deepEqual(JSON.parse(JSON.stringify(calls[4])),{action:'apply_review_candidate',detail:{candidate_id:'review-new',proposal_id:'source-token'}});
  project.revision++;assert.equal(options.isCurrent(),false);
});

test('unverified source proposal states uncertainty and still requires playback', async () => {
  const h=harness();h.proposal.kind='unverified_source_candidate';
  await h.review.open();
  assert.match(h.review.message.textContent,/AI did not verify/);
  assert.equal(h.review.applyButton.disabled,true);
  await h.review.apply();assert.equal(h.calls.length,1);
  h.review.video.emit('playing');await h.review.apply();
  assert.equal(h.calls.length,2);
});

test('source proposals appear without an approved draft; stale rows hide and Undo exposes Redo', async () => {
  const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
  const start=source.indexOf('function renderReelCandidates()');
  const end=source.indexOf('\nfunction renderDraftActions()',start);
  assert.ok(start>=0&&end>start);
  class Node {
    constructor(){this.children=[];this.dataset={};this.listeners={};this.hidden=false;}
    append(...nodes){for(const n of nodes){n.parentNode=this;this.children.push(n);}}
    insertBefore(n){this.append(n);}
    replaceChildren(){this.children=[];}
    addEventListener(t,f){this.listeners[t]=f;}
  }
  const elements={reelCandidates:new Node(),reelCandidateList:new Node(),reelCandidatesTitle:new Node(),
    resultPanel:new Node(),analysisPanel:new Node(),analysisError:new Node(),setupPanel:new Node()};
  elements.resultPanel.append(elements.reelCandidates);elements.analysisPanel.hidden=true;
  const state={project:{id:'p',revision:5,draft:null,analysis:{review_candidates:{revision:5,items:[{id:'review-a',kind:'unverified_source_candidate',output_duration:3}]}},manual:{}},manualEditBusy:false};
  const calls=[];
  const context=vm.createContext({state,elements,document:{createElement:()=>new Node()},
    uiCopy:(_h,en)=>en,formatTime:String,foregroundBusy:()=>false,supportsReelReview:()=>true,
    renderDraftActions(){},applyManualEdit:action=>calls.push(action)});
  vm.runInContext(source.slice(start,end)+'\nrenderReelCandidates();',context);
  assert.equal(elements.reelCandidates.hidden,false);
  assert.equal(elements.reelCandidates.parentNode,elements.setupPanel);
  assert.match(elements.reelCandidatesTitle.textContent,/review required/);
  assert.equal(elements.reelCandidateList.children.length,1);
  state.project.revision++;
  vm.runInContext('renderReelCandidates()',context);assert.equal(elements.reelCandidates.hidden,true);
  state.project.manual.history={redo_count:1};
  vm.runInContext('renderReelCandidates()',context);
  assert.equal(elements.reelCandidates.hidden,false);
  assert.equal(elements.reelCandidateList.children.length,1);
  elements.reelCandidateList.children[0].listeners.click();
  assert.deepEqual(calls,['redo']);
});

test('central readiness keeps fresh source review usable without a draft', () => {
  const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
  const start=source.indexOf('function renderDraftActions()');const end=source.indexOf('\nfunction canVaryDraft()',start);
  const sourceButton={dataset:{candidateId:'review-a'}},normalButton={dataset:{candidateId:'alternative'}};
  const state={project:{revision:4,draft:null,analysis:{review_candidates:{revision:4,items:[{id:'review-a'}]}}},draftDirtyReasons:new Set()};
  let busy=false;
  const context=vm.createContext({state,elements:{reelCandidateList:{}},document:{},foregroundBusy:()=>busy,
    $$:selector=>selector.startsWith('button[data-candidate-id]')?[sourceButton,normalButton]:[],t:()=>'',canVaryDraft:()=>false});
  vm.runInContext(source.slice(start,end)+'\nrenderDraftActions()',context);
  assert.equal(sourceButton.disabled,false);assert.equal(normalButton.disabled,true);
  busy=true;vm.runInContext('renderDraftActions()',context);assert.equal(sourceButton.disabled,true);
  busy=false;state.project.revision++;vm.runInContext('renderDraftActions()',context);assert.equal(sourceButton.disabled,true);
  // Both absent revisions compare equal; that must never dereference a missing shelf.
  state.project={draft:null,analysis:{}};
  assert.doesNotThrow(()=>vm.runInContext('renderDraftActions()',context));
  assert.equal(sourceButton.disabled,true);
  state.project=null;
  assert.doesNotThrow(()=>vm.runInContext('renderDraftActions()',context));
  assert.equal(sourceButton.disabled,true);
});
