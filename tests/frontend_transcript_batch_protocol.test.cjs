"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const dataUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
(async () => {
const lifecycleUrl = dataUrl(fs.readFileSync("web/transcript-batch.js", "utf8"));
const { frozenBatchBinding, createBatchProtocol, captureTranscriptBuffers, matchingCapturedBuffers, retainedDraftViews, pythonStrip } = await import(lifecycleUrl);
const item = (id = "0", text = "corrected") => ({ segment_id: id, base_text: "source", start: 1, end: 2, text });
const binding = () => frozenBatchBinding("project_0123456789ab", 12, [item()]);
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; };
const error = status => Object.assign(new Error(`status ${status}`), { status });
function harness(extra = {}) {
  const posts = [], reads = [], accepted = [], changed = [];
  const protocol = createBatchProtocol({ binding: binding(),
    post: async (id, body) => { posts.push({id,body}); return { kind: "changed", project: {id, revision: 13} }; },
    read: async id => { reads.push(id); return { kind: "saved-now", project: {id, revision: 13} }; },
    verify: (_binding, value) => value?.kind === "changed" || value?.kind === "unchanged" ? {outcome:value.kind} : null,
    classify: (_binding, value) => ({outcome:value?.kind}), admit: () => true, unchanged: () => true,
    accepted: (...args) => accepted.push(args), changed: value => changed.push(value), ...extra });
  return { protocol, posts, reads, accepted, changed };
}

test("binding owns a detached deep-frozen exact request", () => {
  const source = [item()]; const saved = frozenBatchBinding("project_0123456789ab",12,source);
  source[0].text = "newer"; source.push(item("1"));
  assert.equal(JSON.parse(saved.body).items.length,1); assert.equal(saved.items[0].text,"corrected");
  assert.throws(()=>{saved.items[0].text="mutated";},TypeError);
  assert.equal(JSON.parse(saved.body).expected_revision,12);
});

for (const [name, mutate] of [
  ["duplicate IDs", rows=>rows.push(item())], ["extra key", rows=>rows[0].extra=true],
  ["missing base", rows=>delete rows[0].base_text], ["empty ID", rows=>rows[0].segment_id=""],
  ["numeric ID", rows=>rows[0].segment_id=0], ["too long ID", rows=>rows[0].segment_id="x".repeat(129)],
  ["NaN time", rows=>rows[0].start=NaN], ["Infinity time", rows=>rows[0].end=Infinity],
  ["string time", rows=>rows[0].start="1"], ["zero span", rows=>rows[0].end=1],
  ["blank text", rows=>rows[0].text=" \u001c\u0085 "], ["overlong text", rows=>rows[0].text="x".repeat(4001)],
  ["lone surrogate", rows=>rows[0].text="\ud800"], ["lone base surrogate", rows=>rows[0].base_text="\udfff"],
  ["overlong base", rows=>rows[0].base_text="x".repeat(20001)]
]) test(`invalid binding refuses ${name}`,()=>{const rows=[item()];mutate(rows);assert.throws(()=>frozenBatchBinding("p",1,rows));});

test("signed source clocks, 4,000 astral code points and exact base spaces are retained",()=>{
  const value={...item(),start:-2,end:-1,base_text:"  source  ",text:"\u0085"+"😀".repeat(4000)+"\u001c"};
  const result=frozenBatchBinding("p",1,[value]); assert.deepEqual(result.items[0],value);
  assert.equal(Array.from(pythonStrip(value.text)).length,4000);
  assert.equal(pythonStrip("\ufeffvalue\ufeff"),"\ufeffvalue\ufeff");
});
test("request body tampering is refused before any transport",()=>{
  assert.throws(()=>harness({binding:{...binding(),body:binding().body.replace('12','13')}}));
});
test("one direct save produces one request and one accepted callback",async()=>{
  const h=harness();assert.equal(await h.protocol.submit(),true);assert.equal(h.posts.length,1);
  assert.equal(h.accepted.length,1);assert.equal(h.accepted[0][1],"changed");assert.equal(h.protocol.snapshot().attempts,1);
  assert.equal(await h.protocol.submit(),false);assert.equal(await h.protocol.retrySame(),false);
});
test("held POST synchronously reserves and rejects duplicate sends or reads",async()=>{
  const hold=deferred();let count=0;
  const h=harness({post:()=>{count++;return hold.promise;}});const pending=h.protocol.submit();
  assert.equal(h.protocol.snapshot().pending,true);assert.equal(await h.protocol.submit(),false);
  assert.equal(await h.protocol.check(),false);assert.equal(await h.protocol.retrySame(),false);assert.equal(count,1);
  hold.resolve({kind:"changed"});assert.equal(await pending,true);
});
test("reentrant render invalidation refuses before the first POST",async()=>{
  let allowed=true;const h=harness({changed:s=>{if(s.status==="submitting")allowed=false;},admit:()=>allowed});
  assert.equal(await h.protocol.submit(),false);assert.equal(h.posts.length,0);assert.equal(h.protocol.snapshot().status,"refused");
});
test("changed callback throws do not release the reservation or replay",async()=>{
  const h=harness({changed:()=>{throw Error("consumer");}});assert.equal(await h.protocol.submit(),true);assert.equal(h.posts.length,1);
});
test("synchronous transport throw is unknown and counts one attempted call",async()=>{
  const h=harness({post:()=>{throw Error("connection");}});assert.equal(await h.protocol.submit(),false);
  assert.equal(h.protocol.snapshot().status,"unknown");assert.equal(h.protocol.snapshot().attempts,1);
  assert.equal(h.protocol.snapshot().canRetry,false);
});
for(const status of [400,403,404,413,422])test(`confirmed HTTP ${status} rejects without automatic reads or retry`,async()=>{
  const h=harness({post:async()=>{throw error(status);}});await h.protocol.submit();
  assert.equal(h.protocol.snapshot().status,"rejected");assert.equal(h.reads.length,0);assert.equal(h.protocol.snapshot().canRetry,false);
});
for(const status of [0,408,499,500,502,504])test(`uncertain HTTP ${status} retains a checkable fence`,async()=>{
  const h=harness({post:async()=>{throw error(status);}});await h.protocol.submit();
  assert.equal(h.protocol.snapshot().status,"unknown");assert.equal(h.protocol.snapshot().canCheck,true);assert.equal(h.reads.length,0);
});
test("409 never retries automatically and retains one batch conflict",async()=>{
  const h=harness({post:async()=>{throw error(409);}});await h.protocol.submit();
  assert.equal(h.protocol.snapshot().status,"conflict");assert.equal(h.protocol.snapshot().canCheck,true);assert.equal(h.protocol.snapshot().canRetry,false);
});
test("malformed or thrown direct verifier keeps unknown, never accepts",async()=>{
  for(const verify of [()=>null,()=>{throw Error("bad");}]){
    const h=harness({verify});await h.protocol.submit();assert.equal(h.accepted.length,0);assert.equal(h.protocol.snapshot().status,"unknown");
  }
});
test("consumer adoption failure never makes a confirmed save retryable",async()=>{
  const h=harness({accepted:()=>{throw Error("new view");}});assert.equal(await h.protocol.submit(),true);
  assert.equal(h.protocol.snapshot().status,"saved");assert.equal(h.protocol.snapshot().canRetry,false);
});
test("terminal notification cannot force adoption into a newer view",async()=>{
  let view=1, installed=0;
  const h=harness({changed:s=>{if(s.status==="saved")view=2;},accepted:()=>{if(view===1)installed++;}});
  assert.equal(await h.protocol.submit(),true);assert.equal(installed,0);assert.equal(h.protocol.snapshot().status,"saved");
});
test("final admission is the last consumer call before a retry POST",async()=>{
  const trace=[];let n=0;
  const h=harness({post:async()=>{trace.push("post");if(!n++)throw Error("lost");return {kind:"changed"};},
    read:async()=>({kind:"baseline"}),unchanged:()=>{trace.push("unchanged");return true;},admit:()=>{trace.push("admit");return true;}});
  await h.protocol.submit();await h.protocol.check();trace.length=0;await h.protocol.retrySame();
  const posted=trace.indexOf("post");assert.equal(trace[posted-1],"admit");
});
test("GET-only check resolves current saved text without claiming request provenance",async()=>{
  const h=harness({post:async()=>{throw Error("lost");}});await h.protocol.submit();assert.equal(await h.protocol.check(),true);
  assert.equal(h.reads.length,1);assert.equal(h.accepted[0][1],"saved-now");assert.equal(h.protocol.snapshot().attempts,1);
});
test("baseline-equal GET is not success and unlocks only an explicit same-body retry",async()=>{
  let calls=0;const bodies=[];const h=harness({post:async(id,body)=>{bodies.push(body);if(!calls++)throw Error("lost");return {kind:"changed"};},read:async()=>({kind:"baseline"})});
  await h.protocol.submit();assert.equal(await h.protocol.retrySame(),false);await h.protocol.check();
  assert.equal(h.protocol.snapshot().status,"unknown");assert.equal(h.accepted.length,0);assert.equal(calls,1);
  assert.equal(await h.protocol.retrySame(),true);assert.equal(bodies[0],bodies[1]);assert.equal(JSON.parse(bodies[1]).expected_revision,12);
});
test("a changed captured buffer revokes retry, including after the Check completed",async()=>{
  let same=true;const h=harness({post:async()=>{throw Error("lost");},read:async()=>({kind:"baseline"}),unchanged:()=>same});
  await h.protocol.submit();await h.protocol.check();assert.equal(h.protocol.snapshot().canRetry,true);same=false;
  assert.equal(h.protocol.snapshot().canRetry,false);assert.equal(await h.protocol.retrySame(),false);assert.equal(h.protocol.snapshot().attempts,1);
});
test("reentrant change before retry admission cannot submit the stale draft",async()=>{
  let same=true;const h=harness({post:async()=>{throw Error("lost");},read:async()=>({kind:"baseline"}),unchanged:()=>same,
    changed:s=>{if(s.status==="submitting"&&s.attempts===1)same=false;}});
  await h.protocol.submit();await h.protocol.check();assert.equal(await h.protocol.retrySame(),false);assert.equal(h.protocol.snapshot().attempts,1);
});
test("same-body retry that loses CAS becomes conflict, not a new-revision request",async()=>{
  let n=0;const bodies=[];const h=harness({post:async(id,body)=>{bodies.push(body);throw error(++n===1?0:409);},read:async()=>({kind:"baseline"})});
  await h.protocol.submit();await h.protocol.check();await h.protocol.retrySame();assert.equal(h.protocol.snapshot().status,"conflict");
  assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);assert.equal(h.protocol.snapshot().canRetry,false);
});
for(const status of [400,403,404,413,422])test(`retry HTTP ${status} cannot erase the original request uncertainty`,async()=>{
  let n=0, readKind="baseline"; const h=harness({post:async()=>{throw error(++n===1?0:status);},read:async()=>({kind:readKind})});
  await h.protocol.submit();await h.protocol.check();await h.protocol.retrySame();
  assert.equal(h.protocol.snapshot().status,"unknown");assert.equal(h.protocol.snapshot().canCheck,true);
  assert.equal(h.protocol.snapshot().canRetry,false);assert.equal(h.accepted.length,0);
  readKind="saved-now";assert.equal(await h.protocol.check(),true);assert.equal(h.accepted[0][1],"saved-now");
  assert.equal(h.protocol.snapshot().attempts,2);
});
test("failed check removes stale retry eligibility and leaves the full batch retained",async()=>{
  let n=0;const h=harness({post:async()=>{throw Error("lost");},read:async()=>{if(n++)throw Error("offline");return {kind:"baseline"};}});
  await h.protocol.submit();await h.protocol.check();assert.equal(h.protocol.snapshot().canRetry,true);await h.protocol.check();
  assert.equal(h.protocol.snapshot().canRetry,false);assert.equal(h.accepted.length,0);
});
test("mixed latest result retains the whole batch without accepting a subset",async()=>{
  const h=harness({post:async()=>{throw Error("lost");},read:async()=>({kind:"mixed"})});await h.protocol.submit();await h.protocol.check();
  assert.equal(h.accepted.length,0);assert.equal(h.protocol.snapshot().status,"conflict");assert.equal(h.protocol.snapshot().canRetry,false);
});
test("held check cannot dispatch duplicate GET or POST",async()=>{
  const hold=deferred();let reads=0;const h=harness({post:async()=>{throw Error("lost");},read:()=>{reads++;return hold.promise;}});
  await h.protocol.submit();const checking=h.protocol.check();assert.equal(await h.protocol.check(),false);assert.equal(await h.protocol.retrySame(),false);
  hold.resolve({kind:"saved-now"});await checking;assert.equal(reads,1);assert.equal(h.protocol.snapshot().attempts,1);
});
test("semantic all-no-op response remains distinct from a changed save",async()=>{
  const h=harness({post:async()=>({kind:"unchanged"})});await h.protocol.submit();assert.equal(h.protocol.snapshot().status,"unchanged");assert.equal(h.accepted[0][1],"unchanged");
});
test("buffer cleanup preserves newer text, other projects, IDs and bases",()=>{
  const row={projectId:"p",id:"0",base:"source",text:"corrected",start:1,end:2};
  const captured=captureTranscriptBuffers([row]);
  for(const patch of [{text:"newer"},{projectId:"q"},{base:"new saved"},{start:1.1},{id:0}]){
    assert.deepEqual(matchingCapturedBuffers(captured,new Map([["p:0",{...row,...patch}]])),[]);
  }
  assert.deepEqual(matchingCapturedBuffers(captured,new Map([["p:0",row],["p:1",{...row,id:"1"}]])),["p:0"]);
  assert.deepEqual(matchingCapturedBuffers(captured,new Map([["p:0",{...row}]])),[],"equal text in a newer buffer object is still newer intent");
  row.text="mutated in place";assert.deepEqual(matchingCapturedBuffers(captured,new Map([["p:0",row]])),[]);
});

function recoveryHarness(extra = {}) {
  return harness({ post: async () => { throw Error("lost"); },
    read: async id => ({ project: { id, revision: 14 } }),
    classify: (_binding, value) => ({ outcome: "conflict", reviewable: true, revision: value.project.revision }),
    ...extra });
}

test("strictly newer mixed Check offers explicit load but never a retry or partial success", async () => {
  const h = recoveryHarness();
  await h.protocol.submit();
  assert.equal(h.protocol.snapshot().canLoadNewer, false);
  await h.protocol.check();
  const snapshot = h.protocol.snapshot();
  assert.equal(snapshot.canLoadNewer, true);
  assert.equal(snapshot.canRetry, false);
  assert.equal(snapshot.canCheck, true);
  assert.equal(snapshot.reviewRevision, 14);
  assert.equal(h.accepted.length, 0);
  assert.equal(snapshot.attempts, 1);
});

for (const assessment of [
  { outcome: "baseline" }, { outcome: "conflict" },
  { outcome: "conflict", reviewable: true, revision: 12 },
  { outcome: "conflict", reviewable: true, revision: 11 },
  { outcome: "conflict", reviewable: true, revision: "14" },
  { outcome: "conflict", reviewable: false, revision: 14 },
]) test(`non-authoritative newer-load assessment refuses ${JSON.stringify(assessment)}`, async () => {
  const h = recoveryHarness({ classify: () => assessment });
  await h.protocol.submit(); await h.protocol.check();
  assert.equal(h.protocol.snapshot().canLoadNewer, false);
  assert.equal(h.protocol.acceptNewerLoad({ id: binding().projectId, revision: 14 }), false);
  assert.equal(h.accepted.length, 0);
});

test("a failed later Check revokes prior load authority and preserves the unknown batch", async () => {
  let n = 0;
  const h = recoveryHarness({ read: async id => {
    if (n++) throw Error("offline");
    return { project: { id, revision: 14 } };
  } });
  await h.protocol.submit(); await h.protocol.check();
  assert.equal(h.protocol.snapshot().canLoadNewer, true);
  await h.protocol.check();
  assert.equal(h.protocol.snapshot().canLoadNewer, false);
  assert.equal(h.protocol.snapshot().canCheck, true);
  assert.equal(h.protocol.snapshot().attempts, 1);
  assert.equal(h.accepted.length, 0);
});

test("host-confirmed explicit newer load is review-only and never clears or saves buffers", async () => {
  const h = recoveryHarness();
  await h.protocol.submit(); await h.protocol.check();
  for (const project of [{ id: "other", revision: 14 }, { id: binding().projectId, revision: 13 },
    { id: binding().projectId, revision: "14" }]) {
    assert.equal(h.protocol.acceptNewerLoad(project), false);
  }
  assert.equal(h.protocol.acceptNewerLoad({ id: binding().projectId, revision: 14 }), true);
  assert.equal(h.protocol.snapshot().status, "review");
  assert.equal(h.protocol.snapshot().outcome, "review");
  assert.equal(h.accepted.length, 0);
  assert.equal(await h.protocol.submit(), false);
  assert.equal(await h.protocol.retrySame(), false);
  assert.equal(await h.protocol.check(), false);
  assert.equal(h.protocol.acceptNewerLoad({ id: binding().projectId, revision: 15 }), false);
  assert.equal(h.protocol.snapshot().attempts, 1);
});

test("a separately verified still-newer explicit load can retire the original CAS owner", async () => {
  const h = recoveryHarness();
  await h.protocol.submit(); await h.protocol.check();
  assert.equal(h.protocol.acceptNewerLoad({ id: binding().projectId, revision: 16 }), true);
  assert.equal(h.protocol.snapshot().reviewRevision, 16);
  assert.equal(h.accepted.length, 0);
});

test("pending Check cannot be bypassed by an explicit load acknowledgment", async () => {
  const hold = deferred();
  const h = recoveryHarness({ read: () => hold.promise });
  await h.protocol.submit();
  const pending = h.protocol.check();
  assert.equal(h.protocol.acceptNewerLoad({ id: binding().projectId, revision: 14 }), false);
  hold.resolve({ project: { id: binding().projectId, revision: 14 } });
  await pending;
  assert.equal(h.protocol.snapshot().canLoadNewer, true);
});

const draftRow = () => ({ projectId: "p", id: "one", base: "saved", text: "retained", start: 1, end: 2 });
const savedProject = (rows = [{ id: "one", text: "saved", start: 1, end: 2 }]) =>
  ({ id: "p", revision: 14, analysis: { transcript: { segments: rows } } });

for (const provenanceVerified of [false, true]) test(`retained matching draft remains review-only with provenance ${provenanceVerified}`, () => {
  const draft = draftRow(), project = savedProject(), beforeDraft = structuredClone(draft), beforeProject = structuredClone(project);
  const views = retainedDraftViews([draft], project, { provenanceVerified });
  assert.equal(views.length, 1);
  const row = views[0];
  assert.equal(row.identity, draft);
  assert.equal(row.readOnly, true);
  for (const permission of ["canSeek", "canRemove", "canRestore", "canSave"]) assert.equal(row[permission], false);
  assert.equal(row.canCopy, true); assert.equal(row.canDiscard, true);
  assert.equal(row.kind, provenanceVerified ? "stale" : "orphan");
  assert.equal(row.current, provenanceVerified ? project.analysis.transcript.segments[0] : null);
  assert.deepEqual(draft, beforeDraft); assert.deepEqual(project, beforeProject);
  assert.throws(() => { row.canSave = true; }, TypeError);
  assert.throws(() => { views.push(row); }, TypeError);
  assert.equal(Object.isFrozen(draft), false);
});

for (const [name, rows, reason] of [
  ["missing", [], "missing_or_ambiguous_identity"],
  ["ambiguous", [{ id: "one", start: 1, end: 2 }, { id: "one", start: 1, end: 2 }], "missing_or_ambiguous_identity"],
  ["retimed", [{ id: "one", start: 1.25, end: 2 }], "changed_source_times"],
]) test(`retained ${name} line is an orphan, not a navigable saved row`, () => {
  const [row] = retainedDraftViews([draftRow()], savedProject(rows), { provenanceVerified: true });
  assert.equal(row.kind, "orphan"); assert.equal(row.current, null); assert.equal(row.reason, reason);
  assert.equal(row.readOnly, true); assert.equal(row.canSave, false); assert.equal(row.canSeek, false);
});

test("new analysis with identical IDs and times stays orphan-equivalent without provenance proof", () => {
  const project = savedProject(); project.analysis.transcript.generation = "new-analysis";
  const [row] = retainedDraftViews([draftRow()], project);
  assert.equal(row.kind, "orphan"); assert.equal(row.reason, "unverified_provenance"); assert.equal(row.current, null);
});

test("numeric/string/fallback duplicate saved identity cannot be labeled current", () => {
  const draft = { ...draftRow(), id: "0" };
  const [row] = retainedDraftViews([draft], savedProject([{ start: 1, end: 2 }, { id: 0, start: 1, end: 2 }]), { provenanceVerified: true });
  assert.equal(row.kind, "orphan"); assert.equal(row.reason, "missing_or_ambiguous_identity");
});

test("recovery views preserve other-project buffers and remain outside saved transcript counts", () => {
  const draft = draftRow(), other = { ...draft, projectId: "q" }, project = savedProject([]);
  const input = [draft, other];
  const views = retainedDraftViews(input, project);
  assert.equal(views.length, 1); assert.equal(input.length, 2); assert.equal(views[0].identity, draft);
  assert.equal(project.analysis.transcript.segments.length, 0);
  assert.equal(views[0].key, "p:one");
});

test("copy/discard then fresh editing does not inherit the old recovery or cleanup identity", () => {
  const draft = draftRow(), captured = captureTranscriptBuffers([draft]);
  const [retained] = retainedDraftViews([draft], savedProject());
  const current = new Map([["p:one", draft]]);
  const copied = retained.identity.text;
  current.delete(retained.key);
  const fresh = { ...draft, base: "new saved", text: copied };
  current.set("p:one", fresh);
  assert.deepEqual(matchingCapturedBuffers(captured, current), []);
  assert.equal(retained.identity, draft); assert.notEqual(retained.identity, fresh);
  assert.equal(Object.hasOwn(fresh, "readOnly"), false);
});

})().catch(error => { console.error(error); process.exitCode = 1; });
