const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
function text(plan){
  const start=app.indexOf('function storagePlanText('),end=app.indexOf('function rememberUploadStorage',start);
  const c=vm.createContext({plan,formatBytes:n=>`${n} bytes`});vm.runInContext(app.slice(start,end),c);return vm.runInContext('storagePlanText(plan)',c);
}
test('actual data and TEMP paths, free capacity, work and safety reserve are visible',()=>{
  const value=text({reserve_bytes:100,filesystems:[{roles:['data','temporary'],filesystem:'private-volume-guid',locations:['D:\\CUTROOM projects','D:\\TEMP'],disk_free_bytes:500,reserved_bytes:10,required_bytes:200,available_bytes:390}]});
  for(const item of ['D:\\CUTROOM projects','D:\\TEMP','500 bytes free','200 bytes estimated work + 100 bytes safety reserve','10 bytes reserved'])assert.ok(value.includes(item),value);
  assert.equal(value.includes('private-volume-guid'),false);
});
test('render detail preserves separate export and project volumes',()=>{
  const value=text({filesystems:[{roles:['exports'],locations:['E:\\exports'],disk_free_bytes:900,required_bytes:500,reserve_bytes:100,available_bytes:800},
    {roles:['project scratch'],locations:['D:\\project'],disk_free_bytes:200,required_bytes:10,reserve_bytes:100,available_bytes:100}]});
  assert.match(value,/E:\\exports.*900 bytes free/);assert.match(value,/D:\\project.*200 bytes free/);
});
test('export detail supports long paths without changing overflow protections',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8'),css=fs.readFileSync(path.join(__dirname,'../web/styles.css'),'utf8');
  assert.match(html,/id="exportStorageInfo"[^>]*role="status"[^>]*dir="auto"/);
  assert.match(css,/\.export-storage-info,#exportDescription\s*\{[^}]*overflow-wrap:anywhere/);
  assert.match(app,/storage_estimate/);
});
