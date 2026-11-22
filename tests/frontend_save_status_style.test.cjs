const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..'),css=fs.readFileSync(path.join(root,'web/studio-workbench.css'),'utf8'),finish=fs.readFileSync(path.join(root,'web/studio-finish.css'),'utf8');
const section=css.slice(css.indexOf('/* One existing save indicator'),css.indexOf('/* Temporary multi-selection'));
const block=selector=>{const escaped=selector.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');const m=section.match(new RegExp(escaped+'\\s*\\{([^}]+)\\}'));assert.ok(m,selector);return m[1]};
const luminance=hex=>hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
const ratio=(a,b)=>{const l=[luminance(a),luminance(b)].sort((a,b)=>a-b);return(l[1]+.05)/(l[0]+.05)};
test('existing save status remains compact visible text rather than a new toolbar or blinking indicator',()=>{
 const b=block('.topbar #saveState');assert.match(b,/font:500 11px\/1\.4 var\(--font\)/);assert.match(b,/min-height:28px/);assert.match(b,/flex:0 0 auto/);assert.match(b,/white-space:nowrap/);
 assert.doesNotMatch(section,/animation:|@keyframes|font-size:0|opacity:0|display:none|position:fixed|pointer-events:none/);
 assert.doesNotMatch(section,/#previewStage|#timelineCanvas|--workspace-timeline-height|--workspace-inspector-width/);
});
test('save phases use readable theme tokens without dimming inactive status',()=>{
 assert.match(block('.topbar #saveState:disabled'),/opacity:1/);assert.match(block('.topbar #saveState[data-save-state=saving]'),/var\(--cyan-text\)/);assert.match(block('.topbar #saveState[data-save-state=unsaved]'),/var\(--warning-text\)/);assert.match(block('.topbar #saveState[data-save-state=error]'),/var\(--danger\)/);
 for(const marker of [':root','html[data-theme=light]']){const start=finish.indexOf(marker),s=finish.slice(start,finish.indexOf('}',start)),tokens=Object.fromEntries([...s.matchAll(/--([\w-]+):(#[\da-f]{6})/g)].map(m=>[m[1],m[2]]));for(const fg of ['muted','cyan-text','warning-text','danger'])for(const bg of ['surface-chrome','surface-raised'])assert.ok(ratio(tokens[fg],tokens[bg])>=4.5,`${marker} ${fg}/${bg}`)}
});
test('only actionable status has a recovery cue, with keyboard and forced-colors focus',()=>{
 assert.match(block('.topbar #saveState:not(:disabled)'),/cursor:pointer/);assert.match(block('.topbar #saveState:disabled'),/cursor:default/);assert.match(block('.topbar #saveState:not(:disabled)::after'),/content:''/);assert.match(section,/\[dir=rtl\] \.topbar #saveState:not\(:disabled\)::after/);assert.match(block('.topbar #saveState:focus-visible'),/outline:2px solid var\(--focus-ring\)/);assert.match(section,/@media \(forced-colors:active\)/);
});
test('local Chroma draft discard is separate, wraps safely and has a touch target',()=>{
 const b=block('#studioInspector .chroma-actions [data-chroma-discard]');assert.match(b,/flex:1 1 100%/);assert.match(b,/min-height:32px/);assert.match(section,/@media \(max-width:899px\),\(max-height:539px\)/);assert.match(section,/\[data-chroma-discard\] \{ min-height:42px; \}/);assert.match(block('#studioInspector [data-chroma-status]'),/overflow-wrap:anywhere/);assert.doesNotMatch(section,/data-chroma-reset[^}]*display:none/);
});

test('compact shell keeps the same project and save controls available without cloning or hiding status',()=>{
 assert.match(section,/@media \(max-width:900px\)/);assert.match(block('body .app-chrome .topbar .project-head:not([hidden])'),/display:flex!important/);assert.match(block('body.studio-open .app-chrome .topbar .project-head:not([hidden])'),/grid-row:3/);assert.match(block('body.studio-open .app-chrome .topbar .project-name'),/min-width:0/);assert.match(section,/grid-template-rows:44px 44px 36px/);
});

test('medium-width desktop header reserves a status row before actions can overlap it',()=>{
 const medium=section.slice(section.indexOf('@media (min-width:900px) and (max-width:1099px)'));
 assert.match(medium,/display:grid; grid-template-columns:auto minmax\(0,1fr\); grid-template-rows:44px 36px/);
 assert.match(medium,/\.project-head:not\(\[hidden\]\) \{ grid-column:1\/-1; grid-row:2/);
 assert.match(medium,/\.top-actions \{ grid-column:2; grid-row:1; min-width:0; overflow-x:auto/);
});

test('compact RTL header keeps Export opposite the original home brand',()=>{
 assert.match(block('[dir=rtl] body.studio-open .app-chrome .topbar .top-actions #renderButton'),/left:12px; right:auto/);
});
