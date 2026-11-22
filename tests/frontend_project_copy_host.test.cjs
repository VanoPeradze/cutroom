const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');
const plain = value => JSON.parse(JSON.stringify(value));

function app() {
  const nodes = new Map();
  const document = { activeElement: null, documentElement: {classList:{contains(){return false;}}}, addEventListener() {}, querySelectorAll() { return []; }, querySelector() { return null; } };
  function node(tag = 'div', id = '') {
    const result = {
      tag, id, value: '', textContent: '', dataset: {}, attrs: {}, listeners: {}, children: [], hidden: false, open: false,
      style: { setProperty() {} }, classList: { toggle() {}, add() {}, remove() {} },
      addEventListener(name, fn) { this.listeners[name] = fn; },
      setAttribute(name, value) { this.attrs[name] = value; }, removeAttribute(name) { delete this.attrs[name]; },
      append(...children) { for (const child of children) { child.parentElement = this; this.children.push(child); } },
      querySelector(selector) {
        const action = selector.match(/^\[data-project-action="(.*)"\]$/)?.[1];
        for (const child of this.children) {
          if (action ? child.dataset.projectAction === action : child.tag === selector) return child;
          const found = child.querySelector(selector); if (found) return found;
        }
        return null;
      },
      closest(selector) {
        if (selector === '[data-project-id]' && this.dataset.projectId) return this;
        if (selector === '#dialogProjects' && this.id === 'dialogProjects') return this;
        return this.parentElement?.closest(selector) || null;
      },
      focus() { document.activeElement = this; }, select() { this.selected = true; },
      showModal() { this.open = true; },
      close() { this.open = false; this.listeners.close?.(); },
    };
    Object.defineProperty(result, 'innerHTML', {
      set(markup) {
        this.children = [];
        if (markup) {
          const span = node('span'); span.append(node('strong'), node('small'));
          const label = node('b'); label.textContent = 'Open editor';
          this.append(span, label);
        }
      },
    });
    return result;
  }
  document.getElementById = id => { if (!nodes.has(id)) nodes.set(id, node('div', id)); return nodes.get(id); };
  document.createElement = tag => node(tag);
  const context = vm.createContext({ document, console, dictionaries: { en: { saved: 'Saved' } }, setTimeout, clearTimeout,
    localStorage: { getItem(){return null;}, setItem(){}, removeItem() {} }, FormData: class FormData {}, fetch: async()=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>({ok:true})}), window: { setTimeout: callback => callback(), addEventListener() {} } });
  const run = code => vm.runInContext(code, context);
  run(source);
  run(`cacheElements(); initProjectLibrary();
    globalThis.calls = []; globalThis.messages = []; globalThis.opened = []; globalThis.originalApi=api;
    state.projects = [
      {id:'a', name:'Alpha', updated_at:'2026-09-26', created_at:'2026-08-01', has_draft:true},
      {id:'b', name:'Beta', updated_at:'2026-09-28', created_at:'2026-09-01', has_draft:false}
    ];
    state.project = {id:'a', name:'Alpha', revision:4, settings:{aspect:'1:1'}, draft:{}, manual:{}};
    toast = (message, type) => messages.push({message,type});
    runUiAction = fn => Promise.resolve().then(fn);
    flushCurrentProjectSaves = async () => { calls.push('flushCurrent'); return true; };
    flushProjectSaves = async id => { calls.push('flush:' + id); };
    releaseMediaHandles = () => calls.push('release');
    renderDraft = () => calls.push('restoreMedia');
    clearRememberedProject = id => calls.push('forget:' + id);
    showWelcome = () => { calls.push('welcome'); elements.welcomeView.hidden = false; elements.workspaceView.hidden = true; };
    renderReadiness = () => calls.push('readiness');
    workspaceResizeIssue = () => '';
    explicitPendingDraft = () => null; pendingTranscriptBuffers = () => [];
    revealPendingSave = value => calls.push({reveal:value.target});
    renderProjectSaveState = () => calls.push('saveState');
    elements.welcomeView.hidden=true; elements.workspaceView.hidden=false;
    globalThis.entries=new Map();
    state.projectCopies={get:token=>entries.get(token)||null, forSource:id=>[...entries.values()].reverse().find(e=>e.source_project_id===id)||null, active:()=>[...entries.values()].filter(copyOperationActive), observe:e=>{entries.set(e.operation_token,e);return e;}};
    globalThis.op=(overrides={})=>({operation_token:'copy_token_12345678',source_project_id:'a',source_revision:5,name:'Alpha copy',status:'running',progress:.25,copied_bytes:5,total_bytes:20,job_id:'job1',copy_project_id:null,error:null,cancel_requested:false,known:true,pending:false,canCancel:true,canRetry:false,...overrides});
    globalThis.install=e=>{entries.set(e.operation_token,e);return e;};
    api = async (url, options = {}) => {
      calls.push({url, ...options});
      if (url.endsWith('/jobs/active')) return {jobs:[]};
      if (options.method === 'DELETE') return {ok:true};
      if (options.method === 'PATCH') return {project:{...state.project, id:url.split('/').at(-1), name:JSON.parse(options.body).name, revision:6, updated_at:'2026-09-29'}};
      return {project:{...state.project, id:url.split('/').at(-1), revision:5}};
    };
  `);
  return { run, nodes, document };
}


test('Copy is a real separate card action with safe source naming and a native reviewed dialog', () => {
  const {run,nodes}=app();
  run(`state.projects[0].name='<img onerror=evil>'; renderRecentProjects();renderProjectDialog();`);
  for(const id of ['recentList','dialogProjects']){
    const row=nodes.get(id).children.find(n=>n.dataset.projectId==='a');
    const copy=row.querySelector('[data-project-action="copy"]');
    assert.ok(copy);assert.equal(copy.type,'button');assert.notEqual(copy.parentElement,row.querySelector('[data-project-action="open"]'));
    copy.focus();copy.listeners.click();
    assert.equal(nodes.get('projectCopyDialog').open,true);
    assert.equal(nodes.get('projectCopyName').value,'<img onerror=evil> copy');
    assert.equal(nodes.get('projectCopySource').textContent,'Source: <img onerror=evil>');
    assert.deepEqual(plain(run('calls')),[]);
    nodes.get('cancelProjectCopy').listeners.click();
  }
});

test('current source flushes accepted autosaves before reading its saved revision and never sends project content', async()=>{
  const {run}=app();
  run(`state.saveQueues.set('a',{pending:{caption_scale:103},revision:4});
    flushCurrentProjectSaves=async()=>{calls.push('flushCurrent');state.saveQueues.set('a',{revision:5});return true;};`);
  const result=await run(`prepareSavedProjectCopy('a')`);
  assert.deepEqual(plain(result),{revision:5});
  const calls=plain(run('calls'));assert.equal(calls[0],'flushCurrent');
  assert.deepEqual(calls.filter(c=>c.url),[{url:'/api/projects/a'}]);
  assert.equal(run('state.project.revision'),4);
});

test('current mixer queue is flushed instead of rejected as a processing job',async()=>{
  const {run}=app();
  run(`state.sourceMixerSavePending=true;state.sourceMixerDesired={projectId:'a'};
    flushCurrentProjectSaves=async()=>{calls.push('flushMixer');state.sourceMixerSavePending=false;return true;};`);
  assert.equal((await run(`prepareSavedProjectCopy('a')`)).revision,5);
  assert.equal(plain(run('calls'))[0],'flushMixer');
});

test('inactive source never flushes or changes current project, buffers, selection or clock',async()=>{
  const {run}=app();
  run(`globalThis.before=state.project;state.captionDirty=true;state.manualSelection={start:1,end:2};state.preview.current=3;`);
  assert.equal((await run(`prepareSavedProjectCopy('b')`)).revision,5);
  assert.deepEqual(plain(run('calls')),[{url:'/api/projects/b'}]);
  assert.equal(run('state.project===before'),true);assert.equal(run('state.captionDirty'),true);
  assert.deepEqual(plain(run('state.manualSelection')),{start:1,end:2});assert.equal(run('state.preview.current'),3);
});

test('known inactive queued edits refuse without flushing either project',async()=>{
  const {run}=app();run(`state.saveQueues.set('b',{pending:{fps:24}});`);
  await assert.rejects(run(`prepareSavedProjectCopy('b')`),/unresolved saved changes/);
  assert.deepEqual(plain(run('calls')),[]);
});

for(const target of ['caption','chroma','transcript'])test(`explicit ${target} draft is retained/revealed and never silently copied`,async()=>{
  const {run,nodes}=app();
  run(`openProjectCopy(state.projects[0]);
    ${target==='transcript' ? "pendingTranscriptBuffers=()=>[{text:'unsaved'}];" : `explicitPendingDraft=()=>({target:'${target}',detail:'Keep this unsaved draft'});`}`);
  await assert.rejects(run(`prepareSavedProjectCopy('a')`),/unsaved|transcript/);
  assert.equal(nodes.get('projectCopyDialog').open,false);
  assert.ok(plain(run('calls')).some(c=>c.reveal===target));
  assert.ok(!plain(run('calls')).some(c=>c.url||c==='flushCurrent'));
});

test('failed save does not read/copy an older snapshot',async()=>{
  const {run}=app();run(`flushCurrentProjectSaves=async()=>false;`);
  await assert.rejects(run(`prepareSavedProjectCopy('a')`),/not saved/);
  assert.deepEqual(plain(run('calls')),[]);
});

test('navigation while current flush is pending aborts before source GET',async()=>{
  const {run}=app();run(`flushCurrentProjectSaves=()=>new Promise(resolve=>globalThis.release=resolve);`);
  const pending=run(`prepareSavedProjectCopy('a')`);
  run(`state.projectViewToken++;release(true);`);
  await assert.rejects(pending,/not saved/);assert.deepEqual(plain(run('calls')),[]);
});

test('navigation or cancellation during source GET prevents admission receipt',async()=>{
  for(const mode of ['view','cancel']){
    const {run}=app();run(`globalThis.cancelled=false;api=()=>new Promise(resolve=>globalThis.release=resolve);`);
    const pending=run(`prepareSavedProjectCopy('a',{cancelled:()=>cancelled})`);
    await new Promise(setImmediate);
    run(`${mode==='view'?'state.projectViewToken++':'cancelled=true'};release({project:{id:'a',revision:8}});`);
    await assert.rejects(pending,/view changed/);
  }
});

for(const setup of [
  'state.timeline={gesture:{}}','state.timeline={scrubbing:true}','state.timeline={libraryDragActive:true}',
  'state.sourceReview={timeline:{gesture:{}}}','state.sourceReview={timeline:{scrubbing:true}}',
  'state.mediaStudio={frameEditorState:{dragging:true}}','state.embeddedEditor={dragging:true}',
  'document.documentElement.classList.contains=()=>true'
])test(`copy refuses an uncommitted live gesture: ${setup}`,async()=>{
  const {run}=app();run(setup);await assert.rejects(run(`prepareSavedProjectCopy('a')`),/current drag/);
  assert.deepEqual(plain(run('calls')),[]);
});

for(const setup of [
  "state.activeJobMeta={projectId:'a'}", "state.jobStartLocks.add('render:a')", "state.retainedResumePending={projectId:'a'}",
  'state.mediaStudio={uploading:true}', 'state.stabilizationStudio={uploading:true}'
])test(`copy refuses processing before save/read: ${setup}`,async()=>{
  const {run}=app();run(setup);await assert.rejects(run(`prepareSavedProjectCopy('a')`),/processing/);
  assert.deepEqual(plain(run('calls')),[]);
});

test('same-source operation locks rename/delete, source writes and job starts but not unrelated saved edits',async()=>{
  const {run,nodes}=app();run(`install(op());openProjectRename(state.projects[0]);`);
  await run(`deleteProject(state.projects[0])`);
  assert.equal(nodes.get('projectRenameDialog').open,false);assert.equal(nodes.get('projectDeleteDialog').open,false);
  await assert.rejects(run(`originalApi('/api/projects/a',{method:'PATCH',body:'{}'})`),/copy/);
  assert.deepEqual(plain(await run(`originalApi('/api/projects/b',{method:'PATCH',body:'{}'})`)),{ok:true});
  assert.equal(run(`acquireJobStartLock('render','b')`),null);
  assert.deepEqual(plain(await run(`originalApi('/api/projects/a/copies',{method:'POST',body:'{}'})`)),{ok:true});
});

test('preparing copy reserves project-library action but permits its own queued saves',async()=>{
  const {run}=app();run(`install(op({status:'preparing',known:false}));`);
  assert.equal(run(`projectLibraryBusy('a')`),true);assert.equal(run('foregroundBusy()'),false);
  assert.deepEqual(plain(await run(`originalApi('/api/projects/a',{method:'PATCH',body:'{}'})`)),{ok:true});
});

for(const status of ['submitting','unknown','queued','running','publishing'])test(`${status} current copy is modal until explicit Back to Projects`,()=>{
  const {run,nodes,document}=app();run(`globalThis.entry=install(op({status:'${status}'}));openProjectCopyOperation(entry);`);
  assert.equal(nodes.get('closeProjectCopy').disabled,true);assert.equal(nodes.get('cancelProjectCopy').hidden,true);
  assert.equal(nodes.get('projectCopyBack').hidden,false);
  let prevented=false;nodes.get('projectCopyDialog').listeners.cancel({preventDefault(){prevented=true;}});assert.equal(prevented,true);
  run('closeProjectCopyDialog()');assert.equal(nodes.get('projectCopyDialog').open,true);
  nodes.get('projectCopyDialog').close();assert.equal(nodes.get('projectCopyDialog').open,true);
  run('renderRecentProjects();leaveCopyForProjects()');
  assert.equal(nodes.get('projectCopyDialog').open,false);assert.equal(nodes.get('welcomeView').hidden,false);
  assert.equal(run('state.project.id'),'a');assert.equal(run('entries.size'),1);
  assert.equal(document.activeElement.dataset.projectAction,'copy');
});

test('inactive copy dialog closes freely and opening its source does not flush or navigate current editor',async()=>{
  const {run,nodes}=app();run(`globalThis.entry=install(op({source_project_id:'b'}));openProjectCopyOperation(entry);`);
  assert.equal(nodes.get('closeProjectCopy').disabled,false);run('closeProjectCopyDialog()');
  assert.equal(nodes.get('projectCopyDialog').open,false);
  assert.equal(await run(`openProject('b')`),null);
  assert.deepEqual(plain(run('calls')),[]);assert.equal(run('state.project.id'),'a');
});

test('unknown outcome uses checking/retry language, never claims failed or cancelled',()=>{
  const {run,nodes}=app();run(`openProjectCopyOperation(install(op({status:'unknown',known:false,canCancel:false,canRetry:true})));`);
  assert.match(nodes.get('projectCopyStatus').textContent,/not confirmed/);
  assert.doesNotMatch(nodes.get('projectCopyStatus').textContent,/cancelled|failed/i);
  assert.equal(nodes.get('projectCopyCheck').hidden,false);assert.equal(nodes.get('projectCopyRetry').hidden,false);
  assert.equal(nodes.get('projectCopyCancel').disabled,true);
  assert.equal(run('projectSaveStatus().target'),'copy');
});

test('known terminal receipt releases stale raw operation without deleting or mutating project snapshot',()=>{
  const {run}=app();run(`state.project.project_copy=op();globalThis.before=state.project;install(op({status:'completed',copy_project_id:'c'}));`);
  assert.equal(run('projectCopySourceBusy()'),false);assert.equal(run('state.project===before'),true);
});

test('copy status is visible in row metadata, including a late completed result',()=>{
  const {run,nodes}=app();run(`install(op());renderRecentProjects();renderProjectDialog();`);
  for(const id of ['recentList','dialogProjects'])assert.match(nodes.get(id).children.find(n=>n.dataset.projectId==='a').querySelector('small').textContent,/Copying saved project/);
  run(`globalThis.before=state.project;globalThis.selected=state.manualSelection;install(op({status:'completed',copy_project_id:'c'}));projectCopyChanged(op({status:'completed',copy_project_id:'c'}));`);
  assert.match(nodes.get('recentList').children.find(n=>n.dataset.projectId==='a').querySelector('small').textContent,/Copy ready: Alpha copy/);
  assert.equal(nodes.get('projectCopyDialog').open,false);assert.equal(run('state.project===before'),true);assert.equal(run('state.manualSelection===selected'),true);
  assert.deepEqual(plain(run('opened')),[]);
});

test('terminal details offer explicit Open or a fresh reviewed name form, never automatic resubmission',async()=>{
  const {run,nodes}=app();run(`install(op({status:'completed',copy_project_id:'c'}));openProjectCopy(state.projects[0]);`);
  assert.equal(nodes.get('projectCopyOpen').hidden,false);assert.equal(nodes.get('projectCopyCreate').textContent,'Save another copy');
  await run('createSavedProjectCopy()');
  assert.equal(nodes.get('projectCopyName').disabled,false);assert.equal(nodes.get('projectCopyCreate').textContent,'Create copy');
  assert.equal(run('projectLibrary.copy.started'),false);assert.deepEqual(plain(run('calls')),[]);
});

test('explicit Open copy runs normal navigation and closes covering dialog before draft guard',async()=>{
  const {run,nodes}=app();run(`install(op({status:'completed',copy_project_id:'c'}));openProjectCopy(state.projects[0]);
    openProject=async id=>{calls.push({opened:id,covered:elements.projectCopyDialog.open});return null;};`);
  await run('openSavedProjectCopy()');
  assert.deepEqual(plain(run('calls')),[{opened:'c',covered:false}]);assert.equal(run('state.project.id'),'a');
});

test('submit is single-owner across awaits and validates name before controller invocation',async()=>{
  const {run,nodes}=app();run(`openProjectCopy(state.projects[0]);state.projectCopies.start=()=>new Promise(resolve=>{calls.push('start');globalThis.release=resolve;});`);
  nodes.get('projectCopyName').value=' ';await run('createSavedProjectCopy()');assert.deepEqual(plain(run('calls')),[]);
  nodes.get('projectCopyName').value='A named branch';
  const first=run('createSavedProjectCopy()');await run('createSavedProjectCopy()');
  assert.deepEqual(plain(run('calls')),['start']);run('release()');await first;
});

test('copy status preserves bounded current editing flags rather than touching display-owned inert state',()=>{
  assert.doesNotMatch(source.slice(source.indexOf('// Independent copies use'),source.indexOf('function formatDate')),/\.inert\s*=|setAttribute\([^\n]*inert/);
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
  assert.match(html,/id="projectCopyDialog"/);assert.match(html,/fresh Undo history|Undo history starts fresh/i);
  assert.match(html,/Previous exports|existing exports|Exports are not/i);
});

test('save status refreshes on uncertainty even when active-copy boolean is unchanged',()=>{
  const {run}=app();run(`install(op());projectLibrary.lastCopyBusy=true;projectCopyChanged(op());`);
  assert.ok(plain(run('calls')).includes('saveState'));
});

test('foreign active receipt discovered during a refused local attempt retains modal source containment',()=>{
  const {run,nodes}=app();
  run(`globalThis.local=install(op({status:'failed'}));openProjectCopyOperation(local);
    globalThis.foreign=install(op({operation_token:'foreign_token_12345',status:'publishing'}));projectCopyChanged(local);`);
  assert.equal(nodes.get('projectCopyDialog').open,true);
  assert.equal(run('projectLibrary.copy.token'),'foreign_token_12345');
  assert.equal(nodes.get('closeProjectCopy').disabled,true);
});

test('copy blocks uploads before opening the request body even for another project',async()=>{
  const {run}=app();run(`install(op({source_project_id:'b'}));`);
  assert.equal(run(`uploadStartBlocked('a','A')`),true);
  await assert.rejects(run(`uploadWithProgress('/api/projects/a/assets',{},'token',()=>{})`),/active project copy/);
  assert.deepEqual(plain(run('calls')),[]);
});

test('source Rename/Delete truthfully disable while copied and recover without losing their row',()=>{
  const {run,nodes}=app();run(`install(op());renderRecentProjects();`);
  const row=nodes.get('recentList').children.find(n=>n.dataset.projectId==='a');
  for(const kind of ['rename','delete'])assert.equal(row.querySelector(`[data-project-action="${kind}"]`).disabled,true);
  run(`install(op({status:'cancelled'}));refreshProjectCopyRows();`);
  assert.equal(nodes.get('recentList').children.find(n=>n.dataset.projectId==='a'),row);
  for(const kind of ['rename','delete'])assert.equal(row.querySelector(`[data-project-action="${kind}"]`).disabled,false);
});

test('Create hands keyboard focus to persistent status rather than a hidden pending submit',async()=>{
  const {run,nodes,document}=app();run(`openProjectCopy(state.projects[0]);state.projectCopies.start=()=>new Promise(resolve=>globalThis.release=resolve);`);
  nodes.get('projectCopyCreate').focus();const p=run('createSavedProjectCopy()');
  assert.equal(document.activeElement,nodes.get('projectCopyStatus'));run('release()');await p;
});

function actualCopy(run,transport) {
  const controller=fs.readFileSync(path.join(__dirname,'../web/project-copy.js'),'utf8').replace('export function initProjectCopyController','function initProjectCopyController');
  run(`globalThis.actualCopyFactory=(()=>{${controller};return initProjectCopyController;})();
    globalThis.initProjectCopyController=options=>actualCopyFactory({...options,token:()=> 'copy_token_integrated_1',schedule:()=>1,clearSchedule:()=>{}});
    state.projectCopies=null;state.project.id='project_aaaaaaaaaaaa';state.projects[0].id=state.project.id;state.projects[1].id='project_bbbbbbbbbbbb';
    api=${transport};loadProjects=async()=>{calls.push('libraryRefresh');};initializeProjectCopies();`);
}

test('actual controller host integration flushes once, submits only immutable binding and keeps current view on completion',async()=>{
  const {run,nodes}=app();
  actualCopy(run,`async(url,options={})=>{calls.push({url,...options});if(!options.method)return {project:{...state.project,revision:5}};
    const b=JSON.parse(options.body);return {operation:{operation_token:b.operation_token,source_project_id:state.project.id,source_revision:b.expected_revision,name:b.name,status:'completed',progress:1,copied_bytes:20,total_bytes:20,job_id:'job_111111111111',copy_project_id:'project_cccccccccccc',error:null,cancel_requested:false}};}`);
  run(`globalThis.before=state.project;state.manualSelection={start:1,end:2};openProjectCopy(state.projects[0]);`);
  nodes.get('projectCopyName').value='Exact branch';await run('createSavedProjectCopy()');
  const calls=plain(run('calls')),post=calls.filter(c=>c.method==='POST');
  assert.ok(calls.indexOf('flushCurrent') < calls.findIndex(c=>c.url));assert.equal(post.length,1);
  assert.deepEqual(JSON.parse(post[0].body),{expected_revision:5,name:'Exact branch',operation_token:'copy_token_integrated_1'});
  assert.equal(run('state.project===before'),true);assert.deepEqual(plain(run('state.manualSelection')),{start:1,end:2});
  assert.equal(run('projectLibrary.listRequest'),1);assert.ok(calls.includes('libraryRefresh'));
  assert.equal(nodes.get('projectCopyOpen').hidden,false);assert.equal(nodes.get('projectCopyDialog').open,true);
  assert.equal(nodes.get('closeProjectCopy').disabled,false);assert.deepEqual(plain(run('opened')),[]);
});

test('actual lost-response integration keeps source modal, and explicit retry reuses exact body once',async()=>{
  const {run,nodes}=app();
  actualCopy(run,`async(url,options={})=>{calls.push({url,...options});
    if(url.startsWith('/api/project-copies/'))throw new ApiError('not found',404,'not_found');
    if(!options.method)return {project:{...state.project,revision:5}};throw new Error('response lost');}`);
  run(`openProjectCopy(state.projects[0]);`);await run('createSavedProjectCopy()');
  assert.equal(run('projectCopyEntry().status'),'unknown');assert.equal(nodes.get('closeProjectCopy').disabled,true);
  const first=plain(run('calls')).find(c=>c.method==='POST').body;
  await run(`projectCopyRequest('retry')`);
  const posts=plain(run('calls')).filter(c=>c.method==='POST');assert.equal(posts.length,2);assert.equal(posts[1].body,first);
  assert.equal(run('projectCopyEntry().status'),'unknown');assert.equal(run('foregroundBusy()'),true);
});

test('actual prepare cancellation prevents admission while retaining any accepted queued save',async()=>{
  const {run}=app();actualCopy(run,`async(url,options={})=>{calls.push({url,...options});return {project:{...state.project,revision:5}};}`);
  run(`flushCurrentProjectSaves=()=>new Promise(resolve=>globalThis.release=resolve);openProjectCopy(state.projects[0]);`);
  const pending=run('createSavedProjectCopy()');
  assert.equal(run('projectCopyEntry().status'),'preparing');await run(`projectCopyRequest('cancel')`);run('release(true)');await pending;
  assert.equal(run('projectCopyEntry().status'),'cancelled');assert.ok(!plain(run('calls')).some(c=>c.url));
});

test('unverifiable public copy state never hydrates or opens its source editor',async()=>{
  for(const invalid of [{status:'future'},[],0]){
    const {run}=app();run(`globalThis.before=state.project;
      pauseAllMedia=()=>{};discardUntouchedProject=async()=>{};setAdvanced=()=>{};
      state.projectCopies.observe=()=>null;
      api=async()=>({project:{id:'b',revision:5,project_copy:${JSON.stringify(invalid)}}});
      showWorkspace=()=>calls.push('openedWorkspace');hydrateProject=()=>calls.push('hydrate');`);
    await assert.rejects(run(`openProject('b')`),/copy state could not be verified/);
    assert.equal(run('state.project===before'),true);assert.ok(!plain(run('calls')).includes('hydrate'));
  }
});

test('foreign server-side copy refusal discovers durable status without replaying the rejected write',async()=>{
  const {run}=app();run(`fetch=async()=>{calls.push('fetch');return {ok:false,status:409,headers:{get:()=> 'application/json'},json:async()=>({error:'project_copy_active',message:'Source copying'})};};
    recoverProjectCopies=async()=>calls.push('discover');`);
  await assert.rejects(run(`originalApi('/api/projects/a',{method:'PATCH',body:'{}'})`),/Source copying/);
  assert.deepEqual(plain(run('calls')),['fetch','discover']);
});


test('terminal refusal directs the user to the real reviewed new-request control',()=>{
  const {run,nodes}=app();run(`openProjectCopyOperation(install(op({status:'failed',error:'Source changed'})));`);
  assert.match(nodes.get('projectCopyStatus').textContent,/Choose Save another copy to review a new request/);
  assert.equal(nodes.get('projectCopyCreate').hidden,false);assert.equal(nodes.get('projectCopyCreate').textContent,'Save another copy');
  assert.doesNotMatch(nodes.get('projectCopyStatus').textContent,/Close these details/);
});
