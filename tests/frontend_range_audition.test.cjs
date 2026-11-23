const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const moduleText = fs.readFileSync(path.join(__dirname, '../web/range-audition.js'), 'utf8');
const init = vm.runInNewContext(moduleText.replace(/^export /gm, '') + '\ninitRangeAudition');

function node() {
  const events = new Map(), attr = new Map();
  return { events, addEventListener(k, fn) { events.set(k, fn); }, removeEventListener(k, fn) {
    if (events.get(k) === fn) events.delete(k); }, emit(k) { events.get(k)?.(); },
    setAttribute(k, v) { attr.set(k, v); }, getAttribute(k) { return attr.get(k); }, remove() { this.removed = true; } };
}
function harness(patch = {}, overrides = {}) {
  const s = { editor: true, id:'fixture', view:1, revision:12, duration:6, editMode:true,
    start:2, end:3, busy:false, dirtyRange:false, occurrence:false, ...patch };
  const doc = node(), button = node(), anchor = {}, bar = { ownerDocument: doc, querySelector: () => anchor,
    insertBefore(b, at) { assert.equal(b, button); assert.equal(at, anchor); } };
  doc.createElement = tag => { assert.equal(tag, 'button'); return button; };
  const calls = []; let playing = false, reads = 0;
  const api = init(bar, { ...(overrides.ready ? { ready: overrides.ready, now: overrides.now || (()=>0), notice:m=>calls.push(['notice',m]) } : {}), snapshot() { reads++; return {...s}; }, format: v => v.toFixed(2),
    seek(t) { calls.push(['seek', t]); overrides.onSeek?.(s); },
    play() { calls.push(['play']); playing = true; return overrides.onPlay?.(); },
    pause() { calls.push(['pause']); playing = false; }, isPlaying: () => overrides.isPlaying?.() ?? playing });
  return { s, api, button, doc, calls, reads: () => reads, click: () => button.emit('click'),
    active: () => button.getAttribute('aria-pressed') === 'true' };
}

test('mounts one native transport in the edit navigation only; not in an absent source-monitor bar', () => {
  assert.equal(init(null, {}), null); assert.equal(init({ownerDocument:node(),querySelector:()=>null}, {}), null);
  const h = harness(); assert.equal(h.button.type, 'button'); assert.equal(h.button.id, 'timelineLoopRange');
  assert.equal(h.button.getAttribute('aria-label'),'Loop range'); assert.equal(h.active(),false);
  assert.match(h.button.title,/2.00 to 3.00/); assert.deepEqual(h.calls,[]);
});

for (const [reason, change, message] of [
  ['closed studio',{editor:false},/saved timeline/], ['missing sequence',{duration:0},/saved timeline/],
  ['missing revision',{revision:undefined},/saved timeline/], ['source mode',{editMode:false},/Edited video/],
  ['foreground work',{busy:true},/operation/], ['unapplied time entries',{dirtyRange:true},/time entry/],
  ['an occurrence selected over a stale range',{occurrence:true},/Mark a range/],
  ['no range',{start:null,end:null},/Mark a range/], ['negative In',{start:-1},/Mark a range/],
  ['beyond duration',{end:6.001},/Mark a range/], ['reversed selection',{start:3,end:2},/Mark a range/],
  ['non-finite endpoint',{start:NaN},/Mark a range/], ['too-short range',{start:2.8,end:3},/quarter second/]
]) test('blocks '+reason+' without seeking, saving or starting playback', () => {
  const h = harness(change); assert.equal(h.button.disabled,true); assert.match(h.button.title,message);
  h.click(); assert.deepEqual(h.calls,[]); assert.equal(h.api.next(3),null);
});

test('rewinds exactly at the exclusive Out, including timeline zero, tail and delayed callbacks', () => {
  const h = harness({start:0,end:.25,duration:.25}); h.click();
  assert.deepEqual(h.calls,[['seek',0],['play']]); assert.equal(h.active(),true);
  assert.equal(h.api.next(.249),null); assert.equal(h.api.next(.25),0); assert.equal(h.api.next(140),0);
  h.click(); assert.deepEqual(h.calls,[['seek',0],['play'],['pause']]); assert.equal(h.active(),false);
  const reads=h.reads(); for(let i=0;i<120;i++) assert.equal(h.api.next(i),null);
  assert.equal(h.reads(),reads,'ordinary playback does not rescan readiness');
});

for (const [label, change] of Object.entries({ project:{id:'other'}, revision:{revision:13}, view:{view:2},
  duration:{duration:7}, sameLengthMovedRange:{start:3,end:4}, cleared:{start:null}, occurrence:{occurrence:true},
  mode:{editMode:false}, busy:{busy:true}, editedTime:{dirtyRange:true}, leave:{editor:false} })) {
  test('refuses to loop stale '+label+' before presenting a frame', () => {
    const h=harness(); h.click(); Object.assign(h.s,change);
    assert.equal(h.api.next(3),false); assert.equal(h.active(),false); assert.equal(h.api.next(3),null);
    assert.deepEqual(h.calls,[['seek',2],['play']]);
  });
}

test('an invalid clock cancels rather than substituting a source or inventing a zero position', () => {
  for(const t of [NaN,1.99]) {const h=harness();h.click();assert.equal(h.api.next(t),false);assert.equal(h.active(),false);}
});
test('ordinary seek/pause clears a loop without seeking back or calling Play again', () => {
  const h=harness();h.click();h.api.clear();h.api.clear();assert.equal(h.active(),false);
  assert.deepEqual(h.calls,[['seek',2],['play']]);assert.equal(h.api.next(4),null);
});
test('readiness synchronizes disabled and active state and pauses just once for a changed selection', () => {
  const h=harness();h.click();h.s.end=4;h.api.sync();h.api.sync();assert.equal(h.active(),false);
  assert.match(h.button.title,/2.00 to 4.00/);assert.deepEqual(h.calls,[['seek',2],['play'],['pause']]);
});
test('project change during the initial seek never starts playback on the new timeline', () => {
  const h=harness({}, {onSeek(s){s.id='next';}});h.click();assert.deepEqual(h.calls,[['seek',2]]);assert.equal(h.active(),false);
});
test('backgrounding stops only an owned audition; destroy removes the button and its handlers', () => {
  const h=harness();h.doc.hidden=true;h.doc.emit('visibilitychange');assert.deepEqual(h.calls,[]);
  h.doc.hidden=false;h.click();h.doc.emit('visibilitychange');assert.equal(h.active(),true);
  h.doc.hidden=true;h.doc.emit('visibilitychange');h.doc.emit('visibilitychange');assert.deepEqual(h.calls,[['seek',2],['play'],['pause']]);
  h.api.destroy();assert.equal(h.button.removed,true);assert.equal(h.doc.events.size,0);assert.equal(h.button.events.size,0);
});
test('holds the edit clock at In until actual players are ready, then resumes once from the exact In', () => {
  let ready=false,lookups=0;const h=harness({}, {ready(){lookups++;return ready;}});
  h.click();assert.equal(h.api.preparing,true);for(let i=0;i<4;i++)assert.deepEqual({...h.api.next(2.1)},{at:2,hold:true});
  assert.deepEqual(h.calls,[['seek',2],['play']],'holding must not re-seek native decoders');
  ready=true;assert.deepEqual({...h.api.next(2.25)},{at:2,hold:false});assert.equal(h.api.preparing,false);
  h.api.next(2.3);h.api.next(2.5);assert.equal(lookups,5,'ordinary frames do not inspect browser decoders');
  assert.equal(h.api.next(3),2);assert.equal(h.api.preparing,true);
  h.api.clear();assert.equal(h.api.preparing,false);assert.equal(h.api.next(9),null);
});
test('timeout and a media error disarm an audition with an explanation, never silently play another source', () => {
  let time=100;for(const broken of [false,true]){
    const h=harness({}, {ready:()=>broken?null:false,now:()=>time});h.click();
    if(!broken){time+=4999;assert.deepEqual({...h.api.next(2)},{at:2,hold:true});time+=1;}
    assert.equal(h.api.next(2),false);assert.equal(h.api.preparing,false);assert.equal(h.active(),false);
    assert.match(h.calls.at(-1)[1],/not ready/);assert.equal(h.api.next(3),null);
  }
});
test('a navigation or revision change during buffering cancels instead of reviving the older playback', () => {
  const h=harness({}, {ready:()=>false});h.click();h.s.view++;assert.equal(h.api.next(2.2),false);
  assert.equal(h.api.preparing,false);assert.equal(h.active(),false);assert.deepEqual(h.calls,[['seek',2],['play']]);
});
test('rejected native playback can never leave an active loop on a previously running clock', async () => {
  for (const onPlay of [()=>{throw Error('device');},()=>Promise.reject(Error('device'))]) {
    const h=harness({}, {onPlay,isPlaying:()=>true});h.click();
    await new Promise(resolve=>setImmediate(resolve));assert.equal(h.active(),false);assert.deepEqual(h.calls,[['seek',2],['play'],['pause']]);
  }
});
test('declined native Play clears pressed state; late old completions cannot stop a second audition', async () => {
  let resolveFirst,resolveSecond;const pending=[];
  const h=harness({}, {onPlay(){return new Promise(r=>pending.push(r));},isPlaying:()=>false});
  h.click();resolveFirst=pending[0];h.click();h.click();resolveSecond=pending[1];
  resolveFirst();await Promise.resolve();await Promise.resolve();assert.equal(h.active(),true);
  resolveSecond();await Promise.resolve();await Promise.resolve();assert.equal(h.active(),false);
});
