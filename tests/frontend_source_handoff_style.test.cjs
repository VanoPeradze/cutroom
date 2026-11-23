const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const css=fs.readFileSync(path.join(__dirname,'../web/source-view.css'),'utf8'),html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
const section=css.slice(css.indexOf('/* Source selection stays above'));
test('narrow Source handoff uses one column by default, actual container width enables two',()=>{
 assert.match(section,/container:source-placement \/ inline-size/);assert.match(section,/min-inline-size:0/);
 assert.match(section,/\.library-source-placement-options \{ display:grid; grid-template-columns:minmax\(0,1fr\)/);
 assert.match(section,/@container source-placement \(min-width:300px\)/);assert.match(section,/grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
 assert.doesNotMatch(section,/@media[^{}]*max-width:[0-9]+px[^}]*grid-template-columns|position:\s*(fixed|absolute)|overflow:\s*(auto|scroll)/);
});
test('native handoff controls keep touch targets, wrapping and proportional tabular numbers without fixed heights',()=>{
 assert.match(section,/min-height:44px/);assert.match(section,/overflow-wrap:anywhere/);assert.match(section,/font-variant-numeric:tabular-nums/);
 assert.match(section,/font:11px\/1\.5 var\(--font\)/);assert.doesNotMatch(section,/monospace|var\(--mono\)|(?:^|[;{])\s*height\s*:|text-transform:uppercase|box-shadow/);
});
test('Source handoff uses existing themed surfaces and leaves timeline RTL geometry alone',()=>{
 for(const token of ['--line','--paper','--paper-dim','--muted'])assert(section.includes(`var(${token})`));
 assert.doesNotMatch(section,/#timeline|direction:rtl|order:|#[a-fA-F0-9]{3,8}\b|lucide/);
 assert.match(css,/:focus-visible \{ outline:2px solid var\(--focus-ring\)/);assert.match(css,/@media\(forced-colors:active\)/);
 assert.match(html,/source-view\.css\?v=20261120-handoff1/);
});

test('repair remains a full-width form action and a narrow focused pane stacks the real destination chooser',()=>{
 assert.match(section,/\.library-shot-range > \.library-preview-repair-link \{ grid-column:1\/-1; \}/);
 assert.match(section,/@container source-placement \(max-width:299px\) \{ #studioInspector \.library-source-placement \.media-destination-control \{ grid-template-columns:minmax\(0,1fr\)/);
});

test('revalidated entry HTML discovers new app import and Source stylesheet together',()=>{
 const app=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
 assert.match(html,/src="\/assets\/app\.js\?v=[^"]*-handoff1(?:-[a-z0-9]+)*"/);
 assert.match(app,/from "\.\/media-studio\.js\?v=[^"]*-handoff1"/);
 assert.match(html,/source-view\.css\?v=20261120-handoff1/);
});
