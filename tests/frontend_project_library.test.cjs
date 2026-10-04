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
  const document = { activeElement: null, addEventListener() {}, querySelectorAll() { return []; }, querySelector() { return null; } };
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
    localStorage: { removeItem() {} }, window: { setTimeout: callback => callback(), addEventListener() {} } });
  const run = code => vm.runInContext(code, context);
  run(source);
  run(`cacheElements(); initProjectLibrary();
    globalThis.calls = []; globalThis.messages = []; globalThis.opened = [];
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
    showWelcome = () => { calls.push('welcome'); elements.welcomeView.hidden = false; };
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

test('lobby and Projects expose separate open, rename and delete controls with safe text', async () => {
  const { run, nodes } = app();
  run(`state.projects[0].name = '<img src=x onerror=alert(1)>'; renderRecentProjects(); renderProjectDialog();
    openProject = async id => { opened.push(id); return state.project; };`);
  assert.equal(nodes.get('recentCount').textContent, '2');
  for (const container of ['recentList', 'dialogProjects']) {
    const row = nodes.get(container).children.find(item => item.dataset.projectId === 'a');
    assert.equal(row.querySelector('strong').textContent, '<img src=x onerror=alert(1)>');
    const open = row.querySelector('[data-project-action="open"]');
    const rename = row.querySelector('[data-project-action="rename"]');
    const remove = row.querySelector('[data-project-action="delete"]');
    assert.notEqual(rename.parentElement, open);
    assert.notEqual(remove.parentElement, open);
    rename.focus(); rename.listeners.click();
    assert.equal(nodes.get('projectRenameDialog').open, true);
    assert.deepEqual(plain(run('opened')), []);
    nodes.get('cancelProjectRename').listeners.click();
    await remove.listeners.click();
    assert.equal(nodes.get('projectDeleteDialog').open, true);
    assert.equal(nodes.get('confirmProjectDelete').textContent, 'Delete project permanently');
    assert.deepEqual(plain(run('calls')), []);
    nodes.get('cancelProjectDelete').listeners.click();
  }
});

test('search and sort match names without changing stored order', () => {
  const { run, nodes } = app();
  assert.deepEqual(plain(run('projectLibraryRows().map(p => p.id)')), ['b', 'a']);
  assert.deepEqual(plain(run('projectLibraryRows(" ALP ", "name").map(p => p.id)')), ['a']);
  assert.deepEqual(plain(run('projectLibraryRows("", "oldest").map(p => p.id)')), ['a', 'b']);
  nodes.get('projectSearch').value = 'missing'; run('renderProjectDialog()');
  assert.equal(nodes.get('projectLibrarySummary').textContent, '0 of 2 projects');
  assert.match(nodes.get('dialogProjects').children[0].textContent, /No matching/);
  assert.deepEqual(plain(run('state.projects.map(p => p.id)')), ['a', 'b']);
});

test('renaming current project flushes saves, uses latest revision and preserves editor selection', async () => {
  const { run, nodes, document } = app();
  run('state.manualSelection = {start:2,end:4}; renderRecentProjects();');
  const row = nodes.get('recentList').children.find(item => item.dataset.projectId === 'a');
  row.querySelector('[data-project-action="rename"]').focus();
  run('openProjectRename(state.projects[0])');
  nodes.get('projectRenameInput').value = '  Clear name  ';
  await run('saveProjectName()');
  const calls = plain(run('calls'));
  assert.equal(calls[0], 'flushCurrent');
  assert.deepEqual(JSON.parse(calls.find(call => call.method === 'PATCH').body), {name:'Clear name', expected_revision:5});
  assert.equal(run('state.project.name'), 'Clear name');
  assert.equal(run('state.project.revision'), 6);
  assert.equal(run('state.saveQueues.get("a").revision'), 6);
  assert.equal(nodes.get('projectName').value, 'Clear name');
  assert.deepEqual(plain(run('state.manualSelection')), {start:2,end:4});
  assert.equal(nodes.get('projectRenameDialog').open, false);
  assert.equal(document.activeElement.dataset.projectAction, 'rename');
});

test('renaming an inactive project leaves current editor intact', async () => {
  const { run, nodes } = app();
  run('globalThis.originalProject = state.project; openProjectRename(state.projects[1])');
  nodes.get('projectRenameInput').value = 'Second edit'; await run('saveProjectName()');
  assert.equal(run('state.project === originalProject'), true);
  assert.equal(run('state.projects.find(p => p.id === "b").name'), 'Second edit');
  assert.ok(!plain(run('calls')).includes('flushCurrent'));
});

test('rename validates blank names and retains typed name on conflict', async () => {
  const { run, nodes } = app();
  run('openProjectRename(state.projects[1])');
  nodes.get('projectRenameInput').value = '   '; await run('saveProjectName()');
  assert.deepEqual(plain(run('calls')), []);
  assert.match(nodes.get('projectRenameError').textContent, /between 1 and 120/);
  nodes.get('projectRenameInput').value = 'My new name';
  run(`api = async (url, options = {}) => {
    if (options.method === 'PATCH') throw new ApiError('Conflict', 409, 'revision_conflict');
    return {project:{id:'b',revision:5}};
  }`);
  await run('saveProjectName()');
  assert.equal(nodes.get('projectRenameInput').value, 'My new name');
  assert.equal(nodes.get('projectRenameDialog').open, true);
  assert.match(nodes.get('projectRenameError').textContent, /changed while/);
  assert.equal(nodes.get('saveProjectRename').disabled, false);
  assert.equal(run('state.projects[1].name'), 'Beta');
});

test('busy project and media imports block actions before mutation', async () => {
  const { run, nodes } = app();
  run('state.mediaStudio = {uploading:true}; openProjectRename(state.projects[0])');
  await run('deleteProject(state.projects[0])');
  assert.equal(nodes.get('projectRenameDialog').open, false);
  assert.equal(nodes.get('projectDeleteDialog').open, false);
  assert.deepEqual(plain(run('calls')), []);
});

test('a failed edit save prevents rename and delete requests', async () => {
  const { run, nodes } = app();
  run('flushCurrentProjectSaves = async () => false; openProjectRename(state.projects[0]);');
  nodes.get('projectRenameInput').value = 'Unsaved edit'; await run('saveProjectName()');
  assert.match(nodes.get('projectRenameError').textContent, /could not be saved/);
  nodes.get('cancelProjectRename').listeners.click();
  await run('deleteProject(state.projects[0])'); await run('confirmProjectDeletion()');
  assert.match(nodes.get('projectDeleteError').textContent, /could not be saved/);
  assert.deepEqual(plain(run('calls')), []);
  assert.equal(run('state.project.name'), 'Alpha');
});

test('rename checks server jobs even when no job is known in this browser', async () => {
  const { run, nodes } = app();
  run(`globalThis.defaultApi = api;
    api = async (url, options = {}) => url.endsWith('/jobs/active') ? {jobs:[{id:'background-job'}]} : defaultApi(url, options);
    openProjectRename(state.projects[1]);`);
  nodes.get('projectRenameInput').value = 'Wait for job'; await run('saveProjectName()');
  assert.ok(!plain(run('calls')).some(call => call.method === 'PATCH'));
  assert.match(nodes.get('projectRenameError').textContent, /active work/);
  assert.equal(run('state.projects[1].name'), 'Beta');
});

test('delete requires explicit confirmation and rechecks busy work after opening', async () => {
  const { run, nodes, document } = app();
  await run('deleteProject(state.projects[0])');
  assert.equal(document.activeElement.id, 'cancelProjectDelete');
  assert.deepEqual(plain(run('calls')), []);
  run('state.activeJobMeta = {projectId:"a"};');
  await run('confirmProjectDeletion()');
  assert.deepEqual(plain(run('calls')), []);
  assert.match(nodes.get('projectDeleteError').textContent, /active job/);
  assert.equal(nodes.get('projectDeleteDialog').open, true);
});

test('delete preflight refuses background work without sending DELETE', async () => {
  const { run, nodes } = app();
  await run('deleteProject(state.projects[1])');
  run(`api = async (url, options) => { calls.push({url, ...options}); return {jobs:[{id:'active'}]}; }`);
  await run('confirmProjectDeletion()');
  assert.ok(!plain(run('calls')).some(call => call.method === 'DELETE'));
  assert.match(nodes.get('projectDeleteError').textContent, /active work/);
  assert.equal(run('state.projects.length'), 2);
});

test('failed delete preserves project and restores released media with recoverable error', async () => {
  const { run, nodes } = app();
  await run('deleteProject(state.projects[0])');
  run(`api = async (url, options = {}) => {
    calls.push({url,...options}); if (options.method === 'DELETE') throw new Error('Windows is closing a media file. Try again.');
    return {jobs:[]};
  };`);
  await run('confirmProjectDeletion()');
  assert.equal(run('state.project.id'), 'a');
  assert.equal(run('state.projects.length'), 2);
  assert.ok(plain(run('calls')).includes('restoreMedia'));
  assert.equal(nodes.get('projectDeleteDialog').open, true);
  assert.equal(nodes.get('confirmProjectDelete').disabled, false);
  assert.match(nodes.get('projectDeleteError').textContent, /Try again/);
});

test('successful current deletion releases media before request and returns home only after success', async () => {
  const { run, nodes } = app();
  run('state.saveQueues.set("a", {}); elements.projectsDialog.open = true;');
  await run('deleteProject(state.projects[0])'); await run('confirmProjectDeletion()');
  const calls = plain(run('calls'));
  const requestIndex = calls.findIndex(call => call.method === 'DELETE');
  assert.ok(calls.indexOf('release') < requestIndex);
  assert.ok(calls.indexOf('welcome') > requestIndex);
  assert.equal(run('state.project'), null);
  assert.equal(run('state.saveQueues.has("a")'), false);
  assert.deepEqual(plain(run('state.projects.map(p => p.id)')), ['b']);
  assert.equal(nodes.get('projectDeleteDialog').open, false);
  assert.equal(nodes.get('projectsDialog').open, false);
});

test('deleting an inactive project keeps the active editor and dialog open', async () => {
  const { run, nodes } = app();
  run('elements.projectsDialog.open = true;');
  await run('deleteProject(state.projects[1])'); await run('confirmProjectDeletion()');
  assert.equal(run('state.project.id'), 'a');
  assert.ok(!plain(run('calls')).includes('release'));
  assert.equal(nodes.get('projectsDialog').open, true);
  assert.equal(nodes.get('projectDeleteDialog').open, false);
});

test('delete disables repeated confirmation and Escape while the request is pending', async () => {
  const { run, nodes } = app();
  await run('deleteProject(state.projects[1])');
  run(`globalThis.finishDelete = null; globalThis.deleteRequests = 0;
    api = async (url, options = {}) => {
      if (options.method === 'DELETE') { deleteRequests++; return new Promise(resolve => { finishDelete = resolve; }); }
      return {jobs:[]};
    };
    globalThis.deleting = confirmProjectDeletion();`);
  // Drain the save and job-check awaits without depending on wall-clock timers.
  for (let i = 0; i < 6 && !run('finishDelete'); i++) await Promise.resolve();
  assert.equal(typeof run('finishDelete'), 'function');
  assert.equal(nodes.get('confirmProjectDelete').disabled, true);
  let prevented = false;
  nodes.get('projectDeleteDialog').listeners.cancel({preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  await run('confirmProjectDeletion()');
  assert.equal(run('deleteRequests'), 1);
  run('finishDelete({ok:true})'); await run('deleting');
  assert.equal(run('state.projects.length'), 1);
});

test('old list response cannot resurrect a project after a confirmed deletion', async () => {
  const { run } = app();
  run(`globalThis.oldApi = api; globalThis.resolveList = null;
    api = (url, options) => url === '/api/projects' ? new Promise(resolve => { resolveList = resolve; }) : oldApi(url, options);
    globalThis.pendingList = loadProjects();`);
  await run('deleteProject(state.projects[1])'); await run('confirmProjectDeletion()');
  run('resolveList({projects:[{id:"b",name:"Old response"}]});'); await run('pendingList');
  assert.deepEqual(plain(run('state.projects.map(p => p.id)')), ['a']);
});
