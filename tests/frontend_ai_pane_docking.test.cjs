const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/studio-workbench.js'),'utf8').replace(/^export /gm,'');
const scope=vm.createContext({});vm.runInContext(source+'\nglobalThis.initWorkbench=initWorkbench;',scope);
class Node {
 constructor(tag,doc){this.tagName=tag.toUpperCase();this.doc=doc;this.children=[];this.attributes=new Map();this.dataset={};this.listeners=new Map();this.hidden=false;this.disabled=false;this.inert=false;this.open=false;this.scrollTop=0;this.classes=new Set();this.classList={add:v=>this.classes.add(v),remove:v=>this.classes.delete(v),contains:v=>this.classes.has(v),toggle:(v,on)=>on?this.classes.add(v):this.classes.delete(v)};}
 set id(v){this._id=v;this.doc.ids.set(v,this)}get id(){return this._id||''}set className(v){this.classes=new Set(v.split(' '))}get className(){return[...this.classes].join(' ')}
 set textContent(v){this.text=v}get textContent(){return[this.text||'',...this.children.map(n=>n.textContent)].join('')}
 get parentNode(){return this.parentElement}get firstChild(){return this.children[0]||null}get nextSibling(){return this.parentElement?.children[this.parentElement.children.indexOf(this)+1]||null}
 append(...nodes){for(const n of nodes){n.remove();this.children.push(n);n.parentElement=this}}insertBefore(n,next){if(n===next)return;n.remove();const i=this.children.indexOf(next);if(i<0)this.append(n);else{this.children.splice(i,0,n);n.parentElement=this}}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);this.parentElement=null}
 setAttribute(k,v){this.attributes.set(k,String(v))}getAttribute(k){return this.attributes.get(k)??null}removeAttribute(k){this.attributes.delete(k)}
 addEventListener(type,fn){this.listeners.set(type,[...(this.listeners.get(type)||[]),fn])}removeEventListener(type,fn){this.listeners.set(type,(this.listeners.get(type)||[]).filter(f=>f!==fn))}
 dispatchEvent(e){e.target??=this;for(const f of this.listeners.get(e.type)||[])f(e);return true}click(){if(!this.disabled)this.dispatchEvent({type:'click',target:this})}focus(){this.doc.activeElement=this}
 descendants(){return this.children.flatMap(n=>[n,...n.descendants()])}contains(n){return n===this||this.descendants().includes(n)}
 matches(s){return s.startsWith('.')?this.classes.has(s.slice(1)):s.startsWith('#')?this.id===s.slice(1):s==='[data-tab]'?Boolean(this.dataset.tab):this.tagName===s.toUpperCase()}
 closest(s){return this.matches(s)?this:this.parentElement?.closest(s)||null}
 querySelector(s){return this.descendants().find(n=>n.matches(s))||null}querySelectorAll(s){return s===':scope > .tab-panel'?this.children.filter(n=>n.classes.has('tab-panel')):this.descendants().filter(n=>n.matches(s))}
}
function fixture({missing=null,analysis=true}={}){
 const doc={ids:new Map(),activeElement:null,createElement(tag){return new Node(tag,this)},createComment(text){const n=new Node('comment',this);n.text=text;return n},getElementById(id){return this.ids.get(id)||null}};
 const node=(id,tag='div',cls='')=>{const n=doc.createElement(tag);if(id)n.id=id;n.className=cls;return n};doc.body=node('body','body');
 const setup=node('setupPanel'),grid=node('briefGrid'),before=node('beforeBrief'),after=node('afterBrief'),instruction=node('instructionGroup','label','instruction-group'),input=node('directorInstruction','textarea'),counter=node('directorInstructionCounter','small'),duration=node('durationGroup','fieldset','duration-group'),durationInput=node('targetDuration','input'),fallback=node('fallbackLabel','label','burn-caption-choice'),checkbox=node('allowExtractiveRoughCut','input'),burn=node('burnCaptionsLabel','label'),goal=node('goalChoices'),style=node('editStyleChoices'),action=node('action','div','director-action'),ready=node('readiness'),generate=node('generateButton','button');
 input.value='Keep the qualification.';input.selectionStart=5;input.selectionEnd=9;checkbox.checked=true;durationInput.value='45';instruction.append(input,counter);duration.append(durationInput);fallback.append(checkbox);grid.append(before,instruction,duration,fallback,burn,after);action.append(ready,generate);setup.append(goal,style,grid,action);setup.hidden=true;
 const analysisNode=analysis?node('analysisPanel','section'):null;if(analysisNode){analysisNode.hidden=true;analysisNode.append(node('jobMessage','h2'),node('jobProgress','span'),node('cancelJobButton','button'));}
 const panel=node('advancedPanel'),header=node('header','header','studio-header'),inspector=node('studioInspector'),shelf=node('studioShelf'),tools=node('studioPanelTimeline','section','tab-panel'),media=node('studioPanelMedia','section','tab-panel'),suggestions=node('suggestions','details','editor-ai-suggestions'),dock=node('studioDirectorDock'),toolsToggle=node('workspaceToolsToggle','button'),nav=node('nav','nav','advanced-tabs'),edit=node('studioTabTimeline','button');edit.dataset.tab='timeline';header.append(toolsToggle);suggestions.append(dock);tools.append(suggestions);inspector.append(tools,media);nav.append(edit);panel.append(header,inspector,shelf,nav);
 const connection=node('aiConnectionButton','button'),transcription=node('transcriptionButton','button');doc.body.append(setup,...(analysisNode?[analysisNode]:[]),panel,connection,transcription);if(missing)doc.ids.delete(missing);
 const observers=[],events=[],writes=[];const win={localStorage:{getItem:()=>null,setItem:(...a)=>writes.push(a)},Event:class{constructor(type,options={}){this.type=type;this.bubbles=Boolean(options.bubbles)}},dispatchEvent:e=>events.push(e.type),MutationObserver:class{constructor(fn){this.callback=fn;observers.push(this)}observe(target,options){this.target=target;this.options=options}disconnect(){this.disconnected=true}}};
 const mutate=(target,attributeName)=>observers.filter(o=>o.target===target&&!o.disconnected).forEach(o=>o.callback([{attributeName}]));
 const contexts=[];panel.addEventListener('workbench-ai-context',event=>contexts.push({bubbles:event.bubbles,value:panel.dataset.aiRequestContext||null,visible:!doc.getElementById('workbenchAIPanel').hidden,parent:input.parentNode?.parentNode?.id}));
 const controller=scope.initWorkbench({document:doc,window:win});const originalOrder=grid.children.filter(n=>n.tagName!=='COMMENT');
 return{doc,win,panel,header,inspector,shelf,tools,media,suggestions,setup,grid,instruction,input,counter,duration,durationInput,fallback,checkbox,burn,goal,style,action,ready,generate,analysis:analysisNode,connection,transcription,nav,edit,observers,contexts,events,writes,controller,originalOrder,mutate,get:id=>doc.getElementById(id)};
}
test('opening the pane mounts complete original groups and one authoritative action',()=>{
 const h=fixture();assert.equal(h.instruction.parentNode,h.grid);assert.equal(h.contexts.length,0);h.controller.setPane('ai');
 assert.equal(h.instruction.parentNode,h.get('workbenchAIBrief'));assert.equal(h.duration.parentNode,h.get('workbenchAIRequestOptions'));assert.equal(h.fallback.parentNode,h.get('workbenchAIRequestOptions'));assert.equal(h.action.parentNode,h.get('workbenchAIBrief'));
 assert.equal(h.input.parentNode,h.instruction);assert.equal(h.counter.parentNode,h.instruction);assert.equal(h.generate.parentNode,h.action);assert.equal(h.ready.parentNode,h.action);assert.equal(h.goal.parentNode,h.setup);assert.equal(h.style.parentNode,h.setup);assert.equal(h.burn.parentNode,h.grid);assert.equal(h.panel.dataset.aiRequestContext,'editor');
 assert.deepEqual(h.contexts,[{bubbles:true,value:'editor',visible:true,parent:'workbenchAIBrief'}]);assert.equal(h.doc.body.descendants().filter(n=>n.id==='directorInstruction').length,1);
});
test('typing state, selection, checked values and the one original listener survive repeated switches',()=>{
 const h=fixture();let inputs=0;h.input.addEventListener('input',()=>inputs++);
 for(let i=0;i<3;i++){h.controller.setPane('ai');h.input.dispatchEvent({type:'input'});h.controller.setPane('inspector');}
 assert.equal(inputs,3);assert.equal(h.input.value,'Keep the qualification.');assert.equal(h.input.selectionStart,5);assert.equal(h.input.selectionEnd,9);assert.equal(h.checkbox.checked,true);assert.equal(h.durationInput.value,'45');assert.deepEqual(h.grid.children.filter(n=>n.tagName!=='COMMENT'),h.originalOrder);assert.deepEqual(h.writes,[]);
});
test('the relocation never starts generation, speech, setup actions or changes workflow',()=>{
 const h=fixture();const calls=[];for(const[id,node]of[['generate',h.generate],['connection',h.connection],['speech',h.transcription]])node.addEventListener('click',()=>calls.push(id));h.setup.dataset.workflow='manual';h.controller.setPane('ai');h.controller.setPane('inspector');h.controller.leaveEditor();assert.deepEqual(calls,[]);assert.equal(h.setup.dataset.workflow,'manual');assert.deepEqual(h.writes,[]);assert.doesNotMatch(source,/fetch\s*\(|\.value\s*=|\.checked\s*=|dataset\.workflow\s*=/);
});
test('same-pane refresh does not reparent or reset focused instruction/cursor or emit repeated context',()=>{
 const h=fixture();h.controller.setPane('ai');h.input.focus();h.inspector.scrollTop=72;const parent=h.input.parentNode;h.controller.setPane('ai');assert.equal(h.doc.activeElement,h.input);assert.equal(h.input.parentNode,parent);assert.equal(h.input.selectionStart,5);assert.equal(h.inspector.scrollTop,72);assert.equal(h.contexts.length,1);
});
test('leaving AI moves focus out before the original textarea returns to hidden Setup',()=>{
 const h=fixture();h.controller.setPane('ai');h.input.focus();h.controller.setPane('inspector');assert.equal(h.doc.activeElement,h.get('workbenchInspectorButton'));assert.equal(h.instruction.parentNode,h.grid);assert.equal(h.contexts.at(-1).value,null);assert.equal(h.contexts.at(-1).visible,false);
});
test('leaveEditor restores every control synchronously before a host Setup focus',()=>{
 const h=fixture();h.controller.setPane('ai');h.controller.leaveEditor();assert.equal(h.instruction.parentNode,h.grid);assert.equal(h.action.parentNode,h.setup);assert.equal(h.analysis.parentNode,h.doc.body);assert.equal(h.panel.hidden,false);assert.equal(h.get('workbenchAIPanel').hidden,true);h.durationInput.focus();h.panel.hidden=true;h.mutate(h.panel,'hidden');assert.equal(h.doc.activeElement,h.durationInput);assert.equal(h.panel.dataset.aiRequestContext,undefined);
});
test('workspace navigation and defensive hidden observer both restore original request groups',()=>{
 for(const mode of['tab','workspace','hidden']){const h=fixture();h.controller.setPane('ai');if(mode==='tab')h.nav.dispatchEvent({type:'click',target:h.edit});else{if(mode==='hidden')h.panel.hidden=true;h.mutate(h.panel,mode==='hidden'?'hidden':'data-workspace')}assert.equal(h.action.parentNode,h.setup,mode);assert.equal(h.instruction.parentNode,h.grid,mode);assert.equal(h.panel.dataset.aiRequestContext,undefined,mode);}
});
test('hidden host-owned duration remains hidden when docked and restored',()=>{
 const h=fixture();h.duration.hidden=true;h.controller.setPane('ai');assert.equal(h.duration.hidden,true);h.controller.leaveEditor();assert.equal(h.duration.hidden,true);
});
test('new project hydration updates the same controls instead of exposing cached prior values',()=>{
 const h=fixture();h.controller.setPane('ai');h.input.value='Second project request';h.checkbox.checked=false;h.controller.setPane('inspector');h.controller.setPane('ai');assert.equal(h.input.value,'Second project request');assert.equal(h.checkbox.checked,false);assert.equal(h.doc.getElementById('directorInstruction'),h.input);
});
test('providers are an ordinary disclosure after the request, with original dialog proxies',()=>{
 const h=fixture();h.controller.setPane('ai');const calls=[];h.connection.addEventListener('click',()=>calls.push('connection'));h.transcription.addEventListener('click',()=>calls.push('speech'));const panel=h.get('workbenchAIPanel'),providers=h.get('workbenchAIConnections');assert.ok(panel.children.indexOf(h.get('workbenchAIBrief'))<panel.children.indexOf(providers));assert.equal(providers.open,false);assert.equal(providers.tagName,'DETAILS');h.get('workbenchAIConnection').click();h.get('workbenchTranscription').click();assert.deepEqual(calls,['connection','speech']);
});
test('missing required original controls never cause a partial second form',()=>{
 for(const missing of['directorInstruction','durationGroup','allowExtractiveRoughCut','generateButton']){const h=fixture({missing});h.controller.setPane('ai');assert.equal(h.get('workbenchAIBrief').hidden,true);assert.equal(h.instruction.parentNode,h.grid);assert.equal(h.action.parentNode,h.setup);assert.equal(h.panel.dataset.aiRequestContext,undefined);assert.equal(h.contexts.length,0);}
});
test('absent analysis panel leaves brief docking functional without a fabricated progress display',()=>{
 const h=fixture({analysis:false});h.controller.setPane('ai');assert.equal(h.instruction.parentNode,h.get('workbenchAIBrief'));assert.equal(h.get('workbenchAIProgress').hidden,true);h.controller.leaveEditor();assert.equal(h.instruction.parentNode,h.grid);
});
test('actual progress/error controls retain node identity and host-owned hidden state',()=>{
 const h=fixture();const progress=h.get('workbenchAIProgress'),job=h.get('jobMessage');h.controller.setPane('ai');assert.equal(h.analysis.parentNode,progress);assert.equal(progress.hidden,true);assert.equal(h.analysis.hidden,true);h.analysis.hidden=false;h.mutate(h.analysis,'hidden');assert.equal(progress.hidden,false);assert.equal(progress.open,true);assert.equal(h.get('jobMessage'),job);assert.equal(h.get('cancelJobButton').parentNode,h.analysis);h.controller.leaveEditor();assert.equal(h.analysis.parentNode,h.doc.body);assert.equal(h.analysis.hidden,false);
});
test('manual progress collapse persists through repeated updates, but a new visible job opens it',()=>{
 const h=fixture();h.controller.setPane('ai');h.analysis.hidden=false;h.mutate(h.analysis,'hidden');const progress=h.get('workbenchAIProgress');progress.open=false;h.mutate(h.analysis,'hidden');assert.equal(progress.open,false);h.analysis.hidden=true;h.mutate(h.analysis,'hidden');assert.equal(progress.hidden,true);h.analysis.hidden=false;h.mutate(h.analysis,'hidden');assert.equal(progress.open,true);
});
test('destroy restores exact original order, removes placeholders and disconnects observers',()=>{
 const h=fixture();h.controller.setPane('ai');h.input.focus();h.controller.destroy();assert.deepEqual(h.grid.children,h.originalOrder);assert.equal(h.analysis.parentNode,h.doc.body);assert.equal(h.action.parentNode,h.setup);assert.equal(h.doc.body.descendants().filter(n=>n.tagName==='COMMENT').length,0);assert.equal(h.panel.dataset.aiRequestContext,undefined);assert.ok(h.observers.every(o=>o.disconnected));assert.equal(h.panel.workbenchController,undefined);
});
test('destroy/reinitialization does not strand originals or multiply event owners',()=>{
 const h=fixture();h.controller.setPane('ai');h.controller.destroy();const next=scope.initWorkbench({document:h.doc,window:h.win});next.setPane('ai');assert.equal(h.doc.body.descendants().filter(n=>n.id==='directorInstruction').length,1);assert.equal(h.doc.body.descendants().filter(n=>n.id==='generateButton').length,1);next.leaveEditor();assert.equal(h.instruction.parentNode,h.grid);
});
test('fallback restoration retains original controls if their nonvisual placeholder was removed',()=>{
 const h=fixture();h.controller.setPane('ai');h.grid.children.find(n=>n.tagName==='COMMENT'&&n.text.endsWith('instruction')).remove();h.controller.leaveEditor();assert.equal(h.instruction.parentNode,h.grid);assert.equal(h.doc.getElementById('directorInstruction'),h.input);
});
test('docking status is accessible and does not provide its own misleading saved/generation assertion',()=>{
 const h=fixture(),status=h.get('workbenchAIRequestStatus');assert.equal(status.getAttribute('role'),'status');assert.equal(status.getAttribute('aria-live'),'polite');assert.equal(status.getAttribute('aria-atomic'),'true');assert.equal(status.textContent,'');assert.equal(h.get('workbenchAIBrief').getAttribute('aria-label'),'Editing request');
});
const css=fs.readFileSync(path.join(__dirname,'../web/studio-workbench.css'),'utf8'),section=css.slice(css.indexOf('/* The AI pane docks'),css.indexOf('/* One existing save indicator'));
test('docked request uses compact theme controls and preserves host visibility and readable readiness on mobile',()=>{
 assert.match(section,/#workbenchAIBrief\[hidden\],#workbenchAIBrief \[hidden\] \{ display:none!important/);assert.match(section,/#workbenchAIBrief \.readiness \{ display:flex/);assert.match(section,/#workbenchAIBrief \.director-action \{ position:static/);assert.match(section,/textarea:focus-visible \{ outline:2px solid var\(--focus-ring\)/);assert.match(section,/@media \(max-width:899px\)/);assert.match(section,/textarea \{ font-size:16px/);assert.match(section,/min-height:44px/);assert.doesNotMatch(section,/position:fixed|animation:|#previewStage|#timelineCanvas/);
});
test('progress styling suppresses only decoration, not native message, error or Stop controls',()=>{
 assert.match(section,/#workbenchAIProgress #analysisPanel \.analysis-orbit/);assert.match(section,/#workbenchAIProgress #jobMessage/);assert.match(section,/#workbenchAIProgress \.analysis-error/);assert.match(section,/#workbenchAIProgress #analysisPanel #cancelJobButton/);assert.doesNotMatch(section,/#(?:jobMessage|jobProgress|analysisError|cancelJobButton)[^{]*\{[^}]*display:none/);
});

test('host context changes bubble from the authoritative advanced panel to document listeners',()=>{const h=fixture();h.controller.setPane('ai');h.controller.setPane('inspector');assert.equal(h.contexts.length,2);assert.ok(h.contexts.every(e=>e.bubbles===true));});

test('actual full-page progress checklist is reset to narrow-dock geometry without hiding statuses',()=>{
 assert.match(css,/#workbenchAIProgress #analysisPanel \.analysis-checks\s*\{[^}]*grid-template-columns:minmax\(0,1fr\)[^}]*width:100%/);
 assert.match(css,/#workbenchAIProgress #analysisPanel \.analysis-checks li\s*\{[^}]*grid-template-columns:14px minmax\(0,1fr\) auto/);
 assert.match(css,/#workbenchAIProgress #analysisPanel #cancelJobButton\s*\{[^}]*min-width:0/);
 assert.match(css,/#workbenchAIProgress #analysisPanel \.director-progress-head b\s*\{[^}]*overflow-wrap:anywhere/);
 assert.doesNotMatch(css,/#workbenchAIProgress[^{}]*\.analysis-checks li::after\s*\{[^}]*display:none/);
});
