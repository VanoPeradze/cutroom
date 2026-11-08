const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const css=fs.readFileSync(path.join(root,'web/studio-finish.css'),'utf8');
const html=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
function luminance(hex){const c=hex.replace('#','').match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;}
function contrast(a,b){const l=[luminance(a),luminance(b)].sort((a,b)=>a-b);return (l[1]+.05)/(l[0]+.05);}
function tokens(block){return Object.fromEntries([...block.matchAll(/--([a-z-]+):(#[a-f0-9]{6})/g)].map(m=>[m[1],m[2]]));}
test('studio finish uses readable dark and light panel text and selected controls',()=>{
 for(const [name,block]of [['dark',css.match(/:root\s*\{([^}]+)\}/)[1]],['light',css.match(/html\[data-theme=light\]\s*\{([^}]+)\}/)[1]]]){
 const t=tokens(block);
 for(const fg of ['paper','paper-dim','muted'])for(const bg of ['surface-panel','surface-inset','surface-chrome'])assert.ok(contrast(t[fg],t[bg])>=4.5,`${name}: ${fg}/${bg}`);
 assert.ok(contrast(t['cyan-text'],t['surface-selected'])>=4.5,`${name}: selected text`);
 }
});
test('new skin loads after geometry repairs without redefining monitor ownership',()=>{
 assert.ok(html.indexOf('studio-finish.css')>html.indexOf('ui-polish.css'));
 assert.doesNotMatch(css,/#previewStage|preview-viewport|--workspace-inspector-width|--workspace-timeline-height/);
 assert.match(css,/prefers-reduced-motion:reduce/);assert.match(css,/forced-colors:active/);
 assert.doesNotMatch(css,/@import|url\(['"]?https?:/);
 for(const workflow of ['short','youtube','manual'])assert.match(html,new RegExp(`data-start-workflow="${workflow}"`));
});
