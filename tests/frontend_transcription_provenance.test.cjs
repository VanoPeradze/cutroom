const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'),vm=require('node:vm');
const app=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
const scope=vm.createContext({});
vm.runInContext(app.slice(app.indexOf('function transcriptionProvenance('),app.indexOf('function renderTranscript()')),scope);
const describe=scope.transcriptionProvenance;
test('fallback cloud history remains visible from saved transcript after reload/cache reuse',()=>{
 const saved={model:'ivrit-ai/whisper-large-v3-turbo-ct2',device:'cpu',execution:{actual_transcription_engine:'local',transcription_fallback:'cloudflare_to_cached_local',cloud_attempt:{provider:'cloudflare',uploaded_parts:3}}};
 const message=describe(saved);assert.match(message,/Cloudflare was attempted \(3 upload attempts\)/);assert.match(message,/completed with cached local/);assert.match(message,/charges were not undone/);assert.match(message,/device: cpu/);
 assert.equal(describe(JSON.parse(JSON.stringify(saved))),message);
 assert.match(app,/provenance.textContent = transcriptionProvenance\(transcript\)/);
});
test('successful cloud shows upload count, local-only never invents cloud history',()=>{
 assert.match(describe({execution:{provider:'cloudflare',uploaded_parts:1}}),/1 upload attempt\)/);
 const local=describe({model:'small',device:'cpu',execution:{actual_transcription_engine:'local'}});
 assert.doesNotMatch(local,/Cloudflare|uploaded audio/i);assert.match(local,/Local speech model: small/);
});
test('resource fallbacks are persistent without echoing raw errors or secrets',()=>{
 const message=describe({model:'ivrit',device:'cpu',execution:{requested_model:'turbo',actual_model:'ivrit',fallback_reason:'large_model_cuda_headroom',resource_warnings:['cpu_memory_unverified','large_model_cpu_may_be_slow'],prior_attempt_errors:['DO-NOT-EXPOSE'],fallback_detail:'DO-NOT-EXPOSE'}});
 assert.match(message,/headroom/);assert.match(message,/Requested model: turbo/);assert.match(message,/could not be verified/);assert.doesNotMatch(message,/DO-NOT-EXPOSE/);
});
test('legacy/missing data has no invented assurance or invalid counts',()=>{
 assert.equal(describe(null),'');assert.equal(describe({}), '');
 assert.doesNotMatch(describe({execution:{provider:'cloudflare',uploaded_parts:-1}}),/-1/);
 assert.doesNotMatch(describe({execution:{provider:'cloudflare',uploaded_parts:Infinity}}),/Infinity/);
});
