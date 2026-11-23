"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const dataUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
(async () => {
const lifecycleUrl = dataUrl(fs.readFileSync("web/transcript-batch.js", "utf8"));
const receiptSource = fs.readFileSync("web/transcript-batch-receipt.js", "utf8").replace("./transcript-batch.js?v=20261117-transcript-batch1", lifecycleUrl);
const { planPublicBatch, verifyPublicBatch, classifySavedBatch } = await import(dataUrl(receiptSource));
const { captionPreviewIssue } = await import(dataUrl(fs.readFileSync("web/caption-preview.js", "utf8")));
const options = { captionPreviewIssue };
const corpus = JSON.parse(fs.readFileSync("tests/fixtures/transcript-batch-api.json", "utf8")).cases;
const accepted=corpus.filter(row=>row.outcome.httpStatus===200);
for(const entry of corpus)test(`actual API receipt: ${entry.name}`,()=>{
  if(entry.outcome.httpStatus!==200){assert.throws(()=>planPublicBatch(entry.beforePublic,entry.request.items));return;}
  const plan=planPublicBatch(entry.beforePublic,entry.request.items);
  assert.equal(plan.binding.body,JSON.stringify({action:"transcript_text_batch",items:entry.request.items,expected_revision:entry.request.expected_revision}));
  const result=verifyPublicBatch(entry.beforePublic,plan,{project:entry.afterPublic},options);
  assert.equal(result.outcome,entry.outcome.changed?"changed":"unchanged",result.issue);
});
const base=corpus.find(row=>row.name==="existing-edit");
const changes=[
  ["wrong project",p=>p.id="project_ffffffffffff"], ["skipped revision",p=>p.revision++],
  ["changed settings",p=>p.settings.caption_scale=125], ["added manual key",p=>p.manual.unreviewed=true],
  ["wrong correction",p=>p.manual.caption_corrections[base.request.items[0].segment_id].text="wrong"],
  ["missing corrections",p=>delete p.manual.caption_corrections],
  ["wrong history",p=>p.manual.history.undo_count=19], ["uncleared redo",p=>p.manual.history.redo_count=1],
  ["target start",p=>p.analysis.transcript.segments[0].start+=0.1],
  ["target end",p=>p.analysis.transcript.segments[0].end+=0.1],
  ["target ID",p=>p.analysis.transcript.segments[0].id="not-reviewed"],
  ["target normalized",p=>p.analysis.transcript.segments[0].normalized="unrelated"],
  ["target word token",p=>p.analysis.transcript.segments[0].words[0].word="unrelated"],
  ["unrelated transcript text",p=>p.analysis.transcript.segments[1].text="unreviewed"],
  ["aggregate transcript text",p=>p.analysis.transcript.text="unrelated"],
  ["story cache retained",p=>p.analysis.story_hierarchy={old:true}],
  ["unrelated analysis",p=>p.analysis.opaque={new:true}],
  ["source clock",p=>p.sources.A.duration+=1], ["assets added",p=>p.assets.asset_bad={}],
  ["caption preview project",p=>p.caption_preview.project_id="wrong"],
  ["caption preview revision",p=>p.caption_preview.revision--],
  ["caption preview clock",p=>p.caption_preview.clock="source"],
  ["caption preview invalid event",p=>p.caption_preview.events[0].end=-1],
  ["caption preview settings",p=>p.caption_preview.settings.caption_scale=125],
  ["editor caption malformed",p=>p.editor_captions[0].hidden="false"],
  ["binding revision",p=>p.timeline_bindings.revision--],
  ["binding content",p=>p.timeline_bindings.selection_scope="changed"],
  ["stale correction added",p=>p.caption_corrections_stale=["unrelated"]],
];
for(const [name,mutate] of changes)test(`reject receipt tampering: ${name}`,()=>{
  const project=structuredClone(base.afterPublic);mutate(project);
  const result=verifyPublicBatch(base.beforePublic,planPublicBatch(base.beforePublic,base.request.items),{project},options);
  assert.equal(result.outcome,"invalid",name);
});
test("all-no-op cannot consume a revision",()=>{
  const entry=corpus.find(row=>row.name==="empty-present-noop"),project=structuredClone(entry.afterPublic);project.revision++;
  assert.equal(verifyPublicBatch(entry.beforePublic,planPublicBatch(entry.beforePublic,entry.request.items),{project},options).outcome,"invalid");
});
test("plan pins immutable baseline, correction map and reviewed request",()=>{
  const before=structuredClone(base.beforePublic),plan=planPublicBatch(before,base.request.items);
  before.name="newer local project";
  assert.notEqual(plan.before.name,before.name);
  assert.throws(()=>{plan.corrections.extra={original:"x",text:"y"};},TypeError);
  assert.equal(verifyPublicBatch(before,plan,{project:base.afterPublic},options).outcome,"invalid");
  assert.equal(verifyPublicBatch(plan.before,plan,{project:base.afterPublic},options).outcome,"changed");
});
test("strict direct receipt and saved-now reconciliation are separate",()=>{
  const plan=planPublicBatch(base.beforePublic,base.request.items),project=structuredClone(base.afterPublic);
  project.revision+=2;project.caption_preview.revision=project.revision;project.timeline_bindings.revision=project.revision;
  project.name="A later unrelated rename";project.display_name=project.name;
  assert.equal(verifyPublicBatch(base.beforePublic,plan,{project},options).outcome,"invalid");
  assert.equal(classifySavedBatch(base.beforePublic,plan,{project},options).outcome,"saved-now");
});
test("baseline GET stays unknown rather than asserting no original commit",()=>{
  const plan=planPublicBatch(base.beforePublic,base.request.items);
  assert.equal(classifySavedBatch(base.beforePublic,plan,{project:structuredClone(base.beforePublic)},options).outcome,"baseline");
});
test("stale saved snapshot never clears a newer view's drafts",()=>{
  const plan=planPublicBatch(base.beforePublic,base.request.items);
  assert.equal(classifySavedBatch(base.beforePublic,plan,{project:base.afterPublic},{...options,minimumRevision:base.afterPublic.revision+1}).outcome,"conflict");
});
test("later partial or source-replaced result cannot clear any batch subset",()=>{
  const entry=corpus.find(row=>row.name==="change21"),plan=planPublicBatch(entry.beforePublic,entry.request.items);
  for(const mutation of [p=>p.analysis.transcript.segments[15].text="changed elsewhere",p=>p.sources.A.duration++,p=>p.analysis.transcript.language="different",p=>p.caption_preview.revision--]){
    const project=structuredClone(entry.afterPublic);project.revision++;project.caption_preview.revision=project.revision;project.timeline_bindings.revision=project.revision;mutation(project);
    assert.equal(classifySavedBatch(entry.beforePublic,plan,{project},options).outcome,"conflict");
  }
});

function laterMixed() {
  const entry=corpus.find(row=>row.name==="change21"),project=structuredClone(entry.afterPublic);
  project.revision++;project.caption_preview.revision=project.revision;project.timeline_bindings.revision=project.revision;
  project.analysis.transcript.segments[15].text="changed elsewhere";
  return {entry,project,plan:planPublicBatch(entry.beforePublic,entry.request.items)};
}

test("a verified strictly newer mixed read authorizes only review loading, not saved-buffer cleanup",()=>{
  const {entry,project,plan}=laterMixed();
  const result=classifySavedBatch(entry.beforePublic,plan,{project},{...options,minimumRevision:project.revision});
  assert.equal(result.outcome,"conflict");assert.equal(result.reviewable,true);assert.equal(result.revision,project.revision);
});

for(const [name,mutation] of [
  ["new source",p=>p.sources.A.duration++],
  ["new transcript provenance",p=>p.analysis.transcript.generation="new"],
  ["removed transcript",p=>delete p.analysis.transcript],
  ["new original line IDs",p=>p.analysis.transcript.segments.forEach((row,index)=>row.id=`new-${index}`)],
])test(`newer ${name} is loadable for retained-draft review but cannot count as saved`,()=>{
  const {entry,project,plan}=laterMixed();mutation(project);
  const result=classifySavedBatch(entry.beforePublic,plan,{project},options);
  assert.equal(result.outcome,"conflict");assert.equal(result.reviewable,true);assert.equal(result.revision,project.revision);
});

for(const [name,mutation] of [
  ["wrong project",p=>p.id="wrong"],
  ["bad saved revision",p=>p.revision="100"],
  ["invalid source map",p=>p.sources=[]],
  ["invalid settings",p=>p.settings=null],
  ["invalid manual",p=>p.manual=[]],
  ["invalid analysis",p=>p.analysis=[]],
  ["malformed transcript",p=>p.analysis.transcript=[]],
  ["malformed segments",p=>p.analysis.transcript.segments={}],
  ["null transcript row",p=>p.analysis.transcript.segments=[null]],
  ["array transcript row",p=>p.analysis.transcript.segments=[[]]],
  ["non-string transcript text",p=>p.analysis.transcript.segments[0].text={}],
  ["invalid transcript start",p=>p.analysis.transcript.segments[0].start="1"],
  ["nonfinite transcript time",p=>p.analysis.transcript.segments[0].end=NaN],
  ["empty transcript interval",p=>p.analysis.transcript.segments[0].end=p.analysis.transcript.segments[0].start],
  ["invalid transcript identity",p=>p.analysis.transcript.segments[0].id={}],
  ["wrong preview project",p=>p.caption_preview.project_id="wrong"],
  ["old preview revision",p=>p.caption_preview.revision--],
  ["unsupported preview version",p=>p.caption_preview.version=9],
  ["wrong preview clock",p=>p.caption_preview.clock="source"],
  ["broken preview event",p=>p.caption_preview.events[0].end=-1],
  ["malformed editor caption",p=>p.editor_captions[0].hidden="false"],
  ["bad history counts",p=>p.manual.history.undo_count=-1],
  ["old timeline binding",p=>p.timeline_bindings.revision--],
])test(`malformed newer GET cannot authorize recovery loading: ${name}`,()=>{
  const {entry,project,plan}=laterMixed();mutation(project);
  const result=classifySavedBatch(entry.beforePublic,plan,{project},options);
  assert.equal(result.outcome,"conflict");assert.equal(result.reviewable,false);assert.equal(result.revision,null);
});

test("newer recovery loading refuses a GET below the current host revision",()=>{
  const {entry,project,plan}=laterMixed();
  const result=classifySavedBatch(entry.beforePublic,plan,{project},{...options,minimumRevision:project.revision+1});
  assert.equal(result.outcome,"conflict");assert.equal(result.reviewable,false);
});

for (const [name, mutate] of [
  ["null", p => p.analysis.transcript.segments[1] = null],
  ["string", p => p.analysis.transcript.segments[1] = "not a row"],
  ["array", p => p.analysis.transcript.segments[1] = []],
  ["object text", p => p.analysis.transcript.segments[1].text = {}],
  ["invalid clock", p => p.analysis.transcript.segments[1].start = Infinity],
]) test(`saved-now cannot bypass malformed unrelated ${name} row`, () => {
  const plan = planPublicBatch(base.beforePublic, base.request.items), project = structuredClone(base.afterPublic);
  project.revision += 2; project.caption_preview.revision = project.revision; project.timeline_bindings.revision = project.revision;
  mutate(project);
  const result = classifySavedBatch(base.beforePublic, plan, { project }, options);
  assert.equal(result.outcome, "conflict"); assert.equal(result.reviewable, false);
});

})().catch(error => { console.error(error); process.exitCode = 1; });
