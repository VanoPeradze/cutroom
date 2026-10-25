const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/caption-alternatives.js'),'utf8').replace(/^export /gm,'');
function setup(status='completed'){
 let project={id:'p',revision:3};const calls=[],messages=[];
 const context=vm.createContext({setTimeout:fn=>fn(),Promise,encodeURIComponent,console});vm.runInContext(source,context);
 const api=async(url,opts)=>{calls.push({url,body:opts?.body&&JSON.parse(opts.body)});if(url.endsWith('/caption-generation'))return{job:{id:'j',status:'queued'}};if(url==='/api/jobs/j')return{job:{id:'j',status,progress:1,message:status,error:status==='failed'?'Source changed':null}};if(url==='/api/projects/p')return{project:{id:'p',revision:4,caption_alternatives:[{id:'new'}]}};throw Error(url);};
 const options={getProject:()=>project,beforeReview:async()=>true,copy:(_he,en)=>en,api,acceptProject:p=>project=p};context.options=options;
 const ui=vm.runInContext('new CaptionAlternatives(options)',context);ui.render=()=>messages.push(ui.message);
 return{ui,calls,messages,getProject:()=>project,setProject:p=>project=p};
}
test('selected explicit language and revision go to local job; result only refreshes review registry',async()=>{
 const h=setup();h.ui.language='en';await h.ui.generate();assert.deepEqual(h.calls[0].body,{language:'en',expected_revision:3});assert.equal(h.getProject().revision,4);assert.ok(h.calls.every(c=>!c.url.includes('/manual/edit')));assert.match(h.ui.message,/Apply explicitly/);assert.equal(h.ui.busy,false);
});
test('failure leaves displayed project and original captions untouched',async()=>{
 const h=setup('failed');await h.ui.generate();assert.equal(h.getProject().revision,3);assert.match(h.ui.message,/Source changed/);assert.equal(h.ui.generationJob,null);
});
test('cancelled job is never reported saved or applied',async()=>{
 const h=setup('cancelled');await h.ui.generate();assert.equal(h.getProject().revision,3);assert.doesNotMatch(h.ui.message,/Alternative saved/);
});
test('pending text-save refusal prevents job request',async()=>{
 const h=setup();h.ui.options.beforeReview=async()=>false;await h.ui.generate();assert.equal(h.calls.length,0);
});
test('current manual revision cannot be overwritten by completed job refresh',async()=>{
 const h=setup();const original=h.ui.options.api;h.ui.options.api=async(url,opts)=>{const r=await original(url,opts);if(url==='/api/jobs/j')h.setProject({id:'p',revision:99});return r;};await h.ui.generate();assert.equal(h.getProject().revision,99);assert.match(h.ui.message,/edit changed/);
});
test('switching project cannot accept old generation result',async()=>{
 const h=setup();const original=h.ui.options.api;h.ui.options.api=async(url,opts)=>{const r=await original(url,opts);if(url==='/api/jobs/j')h.setProject({id:'other',revision:1});return r;};await h.ui.generate();assert.equal(h.getProject().id,'other');assert.ok(!h.calls.some(c=>c.url==='/api/projects/p'));
});

test('timeline selection is sent explicitly without changing requested language or revision',async()=>{
 const h=setup();h.ui.options.getSelection=()=>({start:2.5,end:8.75});await h.ui.generate();assert.deepEqual(h.calls[0].body,{language:'he',expected_revision:3,selection:{start:2.5,end:8.75}});
});
