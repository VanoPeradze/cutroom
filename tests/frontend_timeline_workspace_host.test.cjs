const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
const body=source.match(/function workspaceResizeIssue\(\) \{[\s\S]*?\n\}/)[0];
function app(extra=''){
 const context=vm.createContext({state:{},document:{documentElement:{classList:{contains:()=>false}}}});
 vm.runInContext(body,context);vm.runInContext(extra,context);
 return text=>vm.runInContext(text,context);
}
test('workspace layout is available before timeline initialization',()=>{const run=app();assert.equal(run('workspaceResizeIssue()'),'');});
for(const state of [
 'state.timeline={gesture:{type:"move"}}',
 'state.timeline={scrubbing:true}',
 'state.timeline={libraryDragActive:true}',
 'state.sourceReview={timeline:{gesture:{type:"range"}}}',
 'state.sourceReview={timeline:{scrubbing:true}}',
 'document.documentElement.classList.contains=name=>name==="numeric-scrubbing"',
])test(`live coordinate gesture refuses explicit resize without cancelling it: ${state}`,()=>{const run=app(state),before=run('JSON.stringify(state)');assert.match(run('workspaceResizeIssue()'),/Finish or cancel the current drag/);assert.equal(run('JSON.stringify(state)'),before);});
for(const state of ['state.mediaStudio={frameEditorState:{dragging:true}}','state.embeddedEditor={dragging:true}'])test(`viewer framing gesture owns workspace geometry: ${state}`,()=>{const run=app(state);assert.match(run('workspaceResizeIssue()'),/viewer frame adjustment/);});
for(const state of ['state.manualEditBusy=true','state.timeline={editPending:true}','state.sourceReview={busy:true}','state.mediaStudio={frameEditor:{pending:true}}','state.mediaStudio={frameEditorState:{pending:true}}'])test(`pending geometry save blocks layout until it resolves: ${state}`,()=>{const run=app(state);assert.match(run('workspaceResizeIssue()'),/Wait for the current edit/);run('state={}');assert.equal(run('workspaceResizeIssue()'),'');});
for(const field of ['mediaSelectionPending','mediaSourceOpening'])test(`${field} pending callback owns current navigation coordinates`,()=>{const run=app(`state.timeline={${field}:{id:'request'}}`);assert.match(run('workspaceResizeIssue()'),/selected clip or source preview/);});
for(const state of [
 'state.captionDirty=true;state.chromaStudio={drafts:new Map([["A",{}]])}',
 'state.activeJob="render-job";state.activeUploads=new Map([["id",{}]])',
 'state.jobStartLocks=new Set(["director"]);state.activeJob="director"',
 'state.mediaStudio={frameEditorState:{active:true,dragging:false,pending:false}}',
 'state.timeline={mediaSelection:"a",selectedMediaIds:()=>["a","b"]}',
])test(`presentation-only resize remains available for non-gesture state: ${state}`,()=>{const run=app(state);assert.equal(run('workspaceResizeIssue()'),'');});
test('coordinate guard has precedence over ordinary pending save message',()=>{const run=app('state.manualEditBusy=true;state.timeline={gesture:{}};');assert.match(run('workspaceResizeIssue()'),/current drag/);});
test('missing DOM class helper does not prevent initial workspace mount',()=>{const run=app('document.documentElement={};');assert.equal(run('workspaceResizeIssue()'),'');});
test('real host injects optional guard without changing ordinary redraw behavior',()=>{assert.match(source,/initWorkspace\(\{ document, window, resizeIssue: workspaceResizeIssue,/);assert.match(source,/onResize: \(\) => state\.timeline\?\.scheduleDraw\(\)/);assert.doesNotMatch(body,/cancelGesture|applyManualEdit|pauseAllMedia|setMediaSelection|localStorage|api\(/);});
