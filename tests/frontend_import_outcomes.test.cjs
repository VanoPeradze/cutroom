const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');

function node() {
  const children = new Map();
  const classes = new Set();
  return {
    value: '', textContent: '', dataset: {}, style: {}, hidden: false, attributes: {}, children: [],
    classList: {
      add(...names) { names.forEach(name => classes.add(name)); },
      remove(...names) { names.forEach(name => classes.delete(name)); },
      toggle(name, value) { if (value) classes.add(name); else classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    querySelector(selector) { if (!children.has(selector)) children.set(selector, node()); return children.get(selector); },
    querySelectorAll() { return []; },
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
    append(...items) { this.children.push(...items); },
    appendChild(item) { return this.insertBefore(item, null); },
    insertBefore(item, before) {
      if (item.parentElement) item.parentElement.children=item.parentElement.children.filter(child=>child!==item);
      const index=before?this.children.indexOf(before):0;
      this.children.splice(index,0,item); item.parentElement=this; return item;
    },
    replaceChildren(...items) { this.children = items; },
    load() {}, focus() {},
  };
}

function app() {
  const nodes = new Map();
  const checks = [.10, .58, .70, .86].map(threshold => Object.assign(node(), {dataset:{threshold:String(threshold)}}));
  const document = {
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); },
    createElement: node,
    querySelectorAll(selector) { return selector === '.analysis-checks li' ? checks : []; },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
  };
  const context = vm.createContext({document, console, setTimeout, clearTimeout, FormData: class {},
    window:{}, dictionaries:{en:{fileTooLarge:'File {file}; limit {limit}',notEnoughDisk:'File {file}; free {free}',uploadCancelled:'Upload cancelled',localUploadInterrupted:'Local transfer interrupted'}}});
  const run = code => vm.runInContext(code, context);
  run(source);
  run(`cacheElements(); state.project={id:'p',revision:1,sources:{A:{duration:100}},settings:{},draft:{title:'Existing edit',keep_ranges:[{start:0,end:12}]},manual:{sequence:[{id:'mine'}]}};
    state.system={limits:{disk_free_bytes:1,max_upload_bytes:40*1024**3}};
    globalThis.messages=[]; toast=(message,type)=>messages.push({message,type});
    renderReadiness=()=>{}; pauseAllMedia=()=>{}; rememberProjectRevision=()=>{};
    renderActiveJobBar=()=>{}; loadProjects=loadSystem=async()=>{};
  `);
  return {context, run, nodes, checks};
}

function fakeFile(size = 10) {
  return {name:'original.mp4', size, slice(start, end) { return {size:end-start}; }};
}

function session(token = 'attempt-1234567890') {
  return {upload_token:token,chunk_size_bytes:4,upload_url:'/chunks/attempt',cancel_url:'/cancel/attempt',
    storage_plan:{file_bytes:10,filesystems:[{roles:['data'],filesystem:'D:',disk_free_bytes:26*1024**3,
      reserved_bytes:2*1024**3,required_bytes:15*1024**3,available_bytes:23*1024**3},
    {roles:['temporary'],filesystem:'C:',disk_free_bytes:8*1024**3,reserved_bytes:0,required_bytes:4,available_bytes:7*1024**3}]}};
}

function xhrHarness(context, handler) {
  const requests = [];
  context.XMLHttpRequest = class {
    constructor() {
      this.listeners = {}; this.upload = {listeners:{}, addEventListener(type, callback) { this.listeners[type] = callback; }};
      this.headers = {}; requests.push(this);
    }
    open(method, url) { this.method=method; this.url=url; }
    setRequestHeader(name, value) { this.headers[name]=value; }
    addEventListener(type, callback) { this.listeners[type]=callback; }
    send(body) { this.body=body; handler(this, requests.length-1); }
    abort() { this.aborted=true; this.listeners.abort?.(); }
    complete(status=200, response={received_bytes:Number(this.headers['X-Cutroom-Upload-Offset'])+this.body.size}) {
      this.status=status; this.response=response; this.listeners.load();
    }
  };
  return requests;
}

async function drain() { for (let index=0; index<20; index++) await Promise.resolve(); }

test('file size validation ignores stale disk snapshots and still enforces the file limit', () => {
  const {context,run}=app(); context.file=fakeFile(15*1024**3);
  assert.equal(run('validateUploadFile(file)'),null);
  context.file=fakeFile(41*1024**3);
  assert.match(run('validateUploadFile(file)'),/limit 40 GB/);
});

for (const route of ['/api/projects/p/sources/A','/api/projects/p/sources/B','/api/projects/p/assets']) {
  test(`${route} preflights before sending and remains importing after sent 100%`, async () => {
    const {context,run}=app(); context.file=fakeFile(); context.preflight=session();
    const trace=[]; let finalize;
    context.apiMock=async(url,options)=>{
      trace.push({url,options});
      if(url.endsWith('/preflight'))return context.preflight;
      if(url===route)return new Promise(resolve=>{finalize=resolve;});
      return {cancelled:true};
    };
    const slot=route.match(/sources\/([AB])$/)?.[1];
    context.uploadSlot=slot||null;
    run('api=apiMock; globalThis.states=[]; globalThis.upload={projectId:"p",slot:uploadSlot,purpose:uploadSlot?"source":"asset",uploadToken:"attempt-1234567890",cancelRequested:false};');
    const requests=xhrHarness(context,xhr=>queueMicrotask(()=>{xhr.upload.listeners.progress({lengthComputable:true,loaded:xhr.body.size,total:xhr.body.size});xhr.complete();}));
    const operation=run(`uploadWithProgress(${JSON.stringify(route)},file,upload.uploadToken,(value)=>states.push({phase:upload.phase,value,label:uploadStatusText(upload)}),null,upload)`);
    await drain();
    assert.equal(trace[0].url,'/api/projects/p/uploads/preflight');
    assert.equal(JSON.parse(trace[0].options.body).purpose,slot?'source':'asset');
    assert.equal(requests.length,3);
    assert.deepEqual(requests.map(xhr=>xhr.headers['X-Cutroom-Upload-Offset']),['0','4','8']);
    assert.deepEqual(requests.map(xhr=>xhr.body.size),[4,4,2]);
    for(const xhr of requests)assert.equal(xhr.headers['Content-Type'],'application/octet-stream');
    assert.equal(trace[1].options.headers['X-Cutroom-Upload-Transport'],'chunked-v1');
    assert.equal(trace[1].options.body,'{}');
    assert.equal(run('states.at(-1).label'),'Checking / importing');
    assert.equal(run('states.some(item=>item.label==="Sending 100%")'),true);
    assert.equal(run('states.some(item=>/Ready/.test(item.label))'),false);
    assert.match(run('elements.uploadStorageInfo.textContent'),/D:.*26 GB free/);
    assert.match(run('elements.uploadStorageInfo.textContent'),/C:.*8.0 GB free/);
    finalize({project:{id:'p'}});
    assert.equal((await operation).project.id,'p');
  });
}

test('a preflight 507 sends no bytes and reports the fresh filesystem details', async () => {
  const {context,run}=app(); context.file=fakeFile(15*1024**3); context.plan=session().storage_plan;
  const requests=xhrHarness(context,()=>assert.fail('bytes must not be sent after admission fails'));
  run(`api=async()=>{throw new ApiError('Storage changed',507,'insufficient_storage',{disk_free_bytes:3*1024**3,storage_plan:plan});};`);
  let failure;
  try {await run('uploadWithProgress("/api/projects/p/sources/A",file,"attempt-1234567890",()=>{})');}catch(error){failure=error;}
  assert.equal(requests.length,0);
  context.failure=failure;
  assert.match(run('uploadFailureMessage(failure,file)'),/free 3.0 GB/);
  assert.match(run('uploadFailureMessage(failure,file)'),/D:.*26 GB free/);
  assert.doesNotMatch(run('uploadFailureMessage(failure,file)'),/free 1 B/);
});

test('storage changing during a chunk uses the race error payload and abandons the reservation', async () => {
  const {context,run}=app(); context.file=fakeFile(); context.preflight=session();
  const calls=[];context.apiMock=async(url)=>{calls.push(url);return url.endsWith('/preflight')?context.preflight:{cancelled:true};};
  run('api=apiMock;');
  xhrHarness(context,xhr=>queueMicrotask(()=>xhr.complete(507,{error:'insufficient_storage',message:'Disk filled',disk_free_bytes:0,storage_plan:{filesystems:[{roles:['data'],filesystem:'D:',disk_free_bytes:0,reserved_bytes:0,required_bytes:4,available_bytes:0}]}})));
  let failure;try{await run('uploadWithProgress("/api/projects/p/sources/A",file,"attempt-1234567890",()=>{})');}catch(error){failure=error;}
  context.failure=failure;
  assert.equal(failure.status,507);
  assert.match(run('uploadFailureMessage(failure,file)'),/free 0 B/);
  assert.match(run('elements.uploadStorageInfo.textContent'),/D:.*0 B free/);
  assert.equal(calls.at(-1),'/cancel/attempt');
});

for(const purpose of ['source','asset']) {
  test(`Stop during ${purpose} preflight uses this attempt token and prevents transfer`,async()=>{
    const {context,run}=app();context.file=fakeFile();context.preflight=session();
    let admit;const calls=[];
    context.apiMock=async(url)=>{
      calls.push(url);
      if(url.endsWith('/preflight'))return new Promise(resolve=>{admit=resolve;});
      return url==='/api/projects/p'?{project:run('state.project')}:{cancelled:true};
    };
    run(`api=apiMock; renderSources=hydrateSettings=()=>{};
      globalThis.upload={projectId:'p',slot:${purpose==='source'?"'A'":'null'},purpose:'${purpose}',uploadToken:'attempt-1234567890',cancelUrl:'/api/projects/p/uploads/attempt-1234567890/cancel',progress:0,cancelRequested:false};
      state.activeUploads.set('p:${purpose==='source'?'A':'asset:attempt-1234567890'}',upload);`);
    const requests=xhrHarness(context,()=>assert.fail('cancelled preflight sent a chunk'));
    const operation=run(`uploadWithProgress('/api/projects/p/${purpose==='source'?'sources/A':'assets'}',file,upload.uploadToken,()=>{},null,upload)`);
    run('cancelUpload();');
    const expected=purpose==='source'?'/api/projects/p/sources/A/uploads/attempt-1234567890/cancel':'/api/projects/p/uploads/attempt-1234567890/cancel';
    assert.ok(calls.includes(expected));
    admit(context.preflight);
    await assert.rejects(operation,error=>error.name==='AbortError');
    assert.equal(requests.length,0);
    assert.equal(calls.some(url=>url.endsWith('/sources/A')||url.endsWith('/assets')),false);
    assert.equal(run('messages.some(item=>/^Ready/.test(item.message))'),false);
  });
}

test('a stop after committed asset import reports that the file remains',async()=>{
  const {context,run}=app();context.file=fakeFile();context.preflight=session();let finalize;
  context.apiMock=async(url)=>url.endsWith('/preflight')?context.preflight:new Promise(resolve=>{finalize=resolve;});
  run(`api=apiMock; globalThis.upload={projectId:'p',purpose:'asset',uploadToken:'attempt-1234567890',cancelRequested:false};`);
  xhrHarness(context,xhr=>queueMicrotask(()=>xhr.complete()));
  const operation=run('uploadWithProgress("/api/projects/p/assets",file,upload.uploadToken,()=>{},null,upload)');
  await drain();run('upload.cancelRequested=true;');finalize({asset_id:'committed'});
  const result=await operation;
  assert.equal(result.asset_id,'committed');assert.equal(result.import_stop_too_late,true);
});

test('source response crossing a pending cancellation cannot publish Ready or replace the restored edit',async()=>{
  const {context,run}=app();context.file=fakeFile();const calls=[];let transfer;let confirmCancel;
  context.apiMock=async(url)=>{
    calls.push(url);
    if(url.endsWith('/cancel'))return new Promise(resolve=>{confirmCancel=resolve;});
    return {project:run('originalProject')};
  };
  context.transferMock=(_url,_file,_token,_progress,_request,upload)=>{
    context.attempt=upload;return new Promise(resolve=>{transfer=resolve;});
  };
  run(`globalThis.originalProject=state.project;globalThis.originalEdit=JSON.stringify(state.project);
    api=apiMock;uploadWithProgress=transferMock;flushCurrentProjectSaves=async()=>true;
    renderSources=renderSourceMixer=hydrateSettings=()=>{};`);
  const operation=run('uploadSource("A",file)');await drain();
  run('cancelUpload("A");');
  assert.ok(calls.includes(`/api/projects/p/sources/A/uploads/${context.attempt.uploadToken}/cancel`));
  transfer({project:{id:'p',sources:{A:{name:'new'}},draft:null}});await drain();
  assert.equal(run('state.activeUploads.size'),1,'attempt stays active until rollback confirmation');
  assert.equal(run('messages.some(item=>/^Ready/.test(item.message))'),false);
  confirmCancel({cancelled:true,restored:true});await operation;
  assert.equal(run('JSON.stringify(state.project)===originalEdit'),true);
  assert.equal(run('state.activeUploads.size'),0);
  assert.equal(run('messages.some(item=>/^Ready/.test(item.message))'),false);
});

test('navigation during source settings flush cannot preflight the previous project',async()=>{
  const {context,run}=app();context.file=fakeFile();let finish;
  context.flushMock=()=>new Promise(resolve=>{finish=resolve;});
  run('flushCurrentProjectSaves=flushMock;uploadWithProgress=()=>{throw new Error("stale upload started");};');
  const operation=run('uploadSource("A",file)');await drain();
  run('state.project={id:"new-project",sources:{}};state.projectViewToken+=1;');finish(true);await operation;
  assert.equal(run('state.activeUploads.size'),0);
});

test('a source slot progress callback cannot update a newer attempt in the same slot',async()=>{
  const {context,run}=app();context.file=fakeFile();let complete;let oldProgress;
  context.transferMock=(_url,_file,_token,progress)=>{oldProgress=progress;return new Promise(resolve=>{complete=resolve;});};
  run(`flushCurrentProjectSaves=async()=>true;uploadWithProgress=transferMock;
    renderSources=renderSourceMixer=hydrateSettings=()=>{};api=async()=>({project:state.project});clearDraftRebuild=()=>{};`);
  const operation=run('uploadSource("A",file)');await drain();
  run(`globalThis.oldAttempt=activeUploadForSlot('A');oldAttempt.cancelRequested=true;oldAttempt.cancelPromise=Promise.resolve();
    globalThis.nextAttempt={projectId:'p',slot:'A',purpose:'source',uploadToken:'next-attempt-1234567890',progress:.25,phase:'sending'};
    state.activeUploads.set('p:A',nextAttempt);elements.sourceSlotA.querySelector('.source-upload').querySelector('b').textContent='Sending 25%';`);
  oldProgress(1);
  assert.equal(run('activeUploadForSlot("A").progress'),.25);
  assert.equal(run('elements.sourceSlotA.querySelector(".source-upload").querySelector("b").textContent'),'Sending 25%');
  complete({project:{id:'p',sources:{},draft:null}});await operation;
  assert.equal(run('activeUploadForSlot("A")===nextAttempt'),true);
});

test('terminal editorial rejection retains the observed stage and clears every active indicator',()=>{
  const {run,checks}=app();
  run(`updateJobUI({progress:.68,message:'Reviewing story',status:'running'});
    showAnalysisError({status:'failed',progress:.68,error:'No fit',failure:{outcome:'editorial_no_fit'}});`);
  assert.equal(run('elements.jobProgress.style.width'),'68%');
  assert.equal(run('elements.jobMessage.textContent'),'No suitable story found');
  assert.equal(run('elements.analysisPanel.dataset.outcome'),'editorial_no_fit');
  assert.equal(checks[0].classList.contains('done'),true);
  assert.equal(checks.some(item=>item.classList.contains('active')),false);
  assert.equal(run('elements.cancelJobButton.hidden'),true);
});

test('each typed failure has a distinct title and a retry cannot inherit a terminal active stage',()=>{
  const {run}=app();
  const expected={technical_error:'The edit stopped before completion',invalid_model_output:'Story AI returned an unusable response',constraint_conflict:'The brief has conflicting requirements',editorial_no_fit:'No suitable story found'};
  for(const [outcome,title] of Object.entries(expected))assert.equal(run(`directorOutcomeDescription({failure:{outcome:${JSON.stringify(outcome)}},message:'Problem'}).title`),title);
});

test('failed job polling retains structured failure on the Error for the UI',async()=>{
  const {run}=app();
  run(`setActiveJob=()=>{}; clearActiveJob=()=>{}; api=async()=>({job:{id:'j',status:'failed',progress:.68,error:'No fit',failure:{outcome:'editorial_no_fit',reason:'no_fit'}}});`);
  await assert.rejects(run('pollJob("j",{projectId:"p",director:true})'),error=>error.job.progress===.68&&error.failure.outcome==='editorial_no_fit');
});

test('a failed rerun keeps the current edit and shows the outcome only for its project',async()=>{
  const {run}=app();
  run(`globalThis.before=JSON.stringify({draft:state.project.draft,manual:state.project.manual});
    api=async()=>({project:state.project}); hydrateProject=renderDirectorOutcomeNotice;`);
  await run('reconcileDirectorOutcome("p",{job:{project_id:"p",status:"failed",failure:{outcome:"editorial_no_fit"}}})');
  assert.equal(run('JSON.stringify({draft:state.project.draft,manual:state.project.manual})===before'),true);
  assert.match(run('elements.directorOutcomeNotice.textContent'),/existing edit was kept/);
  run('state.project={id:"different",draft:{},sources:{}};renderDirectorOutcomeNotice();');
  assert.equal(run('elements.directorOutcomeNotice.hidden'),true);
});

test('director instruction counter matches maxlength and preserves Hebrew and English input',()=>{
  const {run}=app();
  for(const locale of ['en','he']) {
    run(`state.locale='${locale}';elements.directorInstruction.value='שמור את ההסתייגות. Keep the qualification.';renderDirectorInstruction();`);
    assert.equal(run('elements.directorInstruction.maxLength'),8000);
    assert.equal(run('elements.directorInstruction.value'),'שמור את ההסתייגות. Keep the qualification.');
    assert.match(run('elements.directorInstructionCounter.textContent'),/^42 \/ 8,000/);
    assert.equal(run('elements.directorInstructionCounter.attributes.dir'),'auto');
    run('elements.directorInstruction.value="א".repeat(8000);renderDirectorInstruction();');
    assert.equal(run('elements.directorInstruction.attributes["aria-invalid"]'),'false');
    run('elements.directorInstruction.value+="x";renderDirectorInstruction();');
    assert.equal(run('elements.directorInstruction.attributes["aria-invalid"]'),'true');
  }
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
  assert.match(html,/id="directorInstruction"[^>]*dir="auto"[^>]*maxlength="8000"[^>]*aria-describedby="directorInstructionCounter"/);
  assert.doesNotMatch(html,/keep the pricing explanation and open with the result/);
});

test('instruction result summary renders only reported per-requirement verification',()=>{
  const {run}=app();
  run(`state.project.draft.instruction_contract={verification_scope:'proposed_director_draft',requirements:[
    {id:'1',text:'Keep the qualification',status:'fulfilled',reason:'Present in selected source range'},
    {id:'2',text:'Make it funny',status:'unverified',reason:'Requires editorial review'},
    {id:'3',text:'Add an effect',status:'unknown',reason:'No verified effect evidence'}]};renderInstructionResults();`);
  assert.equal(run('elements.instructionResults.hidden'),false);
  assert.equal(run('elements.instructionResultsList.children[0].children[0].textContent'),'Fulfilled');
  assert.equal(run('elements.instructionResultsList.children[1].children[0].textContent'),'Unverified');
  assert.equal(run('elements.instructionResultsList.children[2].children[0].textContent'),'Unverified');
  assert.equal(run('elements.instructionResultsList.children[1].children[1].textContent'),'Make it funny');
  assert.equal(run('elements.instructionResultsList.children[1].dir'),'auto');
  assert.match(run('elements.instructionResultsSummary.textContent'),/proposed Director draft/);
});
