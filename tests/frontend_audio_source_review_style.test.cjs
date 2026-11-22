const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname,'..');
const css = fs.readFileSync(path.join(root,'web/studio-workbench.css'),'utf8');
const section = css.slice(css.indexOf('/* Audio Source audition:'),css.indexOf('/* End Audio Source audition. */'));
test('audio review styles are bounded to the existing source region',()=>{
  assert.ok(section.length>500);
  for(const line of section.split('\n').filter(line=>line.includes('{')&&!line.startsWith('@')))
    assert.match(line,/#studioInspector .*audio-source-review/);
  assert.doesNotMatch(section,/\.timeline-scroll|\.previewStage|position:\s*fixed|!important/);
});
test('native audio and exact input layout remain width constrained',()=>{
  assert.match(section,/audio \{[^}]*width:100%;[^}]*min-width:0/);
  assert.match(section,/grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(section,/overflow-wrap:anywhere/);
});
test('mobile audio controls have scoped 44px targets',()=>{
  assert.match(section,/@media \(max-width:620px\)[\s\S]*\.library-source-monitor\.audio-source-review :is\(button,input,select,summary\)[^}]*min-height:44px/);
});
test('hidden controls stay hidden and forced colors retain a visible focus ring',()=>{
  assert.match(section,/\.library-source-monitor\.audio-source-review \[hidden\] \{ display:none;/);
  assert.match(section,/@media \(forced-colors:active\)[\s\S]*outline-color:Highlight/);
});
test('all audio review surface tokens are already defined in the shipped styles',()=>{
  const styles=fs.readdirSync(path.join(root,'web')).filter(f=>f.endsWith('.css')).map(f=>fs.readFileSync(path.join(root,'web',f),'utf8')).join('\n');
  for(const token of new Set([...section.matchAll(/var\((--[\w-]+)\)/g)].map(m=>m[1])))
    assert.match(styles,new RegExp(`${token}\\s*:`),token);
});
test('source and style files contain no accidental replacement or control characters',()=>{
  const source=fs.readFileSync(path.join(root,'web/audio-source-review.js'),'utf8');
  assert.doesNotMatch(source+'\n'+section,/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffd]/);
});

test('mobile target rule outranks the existing compact inspector input rule',()=>{
  assert.match(section,/#advancedPanel #studioInspector \.library-source-monitor\.audio-source-review :is\(button,input,select,summary\)[^}]*min-height:44px/);
});
