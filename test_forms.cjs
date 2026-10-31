// Exercise the real submit listener in isolation with a named control that shadows form.id.
// This catches DOM named-property collisions missed by API-only tests.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const file=fs.readFileSync('static/app.js','utf8');
const code=file.slice(0,file.lastIndexOf('if(location.hash){'));
async function submitScenario(source,formName,entries,reject=false){
 const listeners={},calls=[],error={textContent:'',focus(){}},submit={disabled:false};
 const ctx=vm.createContext({console,URLSearchParams,Intl,encodeURIComponent,setTimeout,clearTimeout,
  document:{addEventListener(name,fn){listeners[name]=fn},querySelector(){return null}},
  window:{addEventListener(){}},location:{hash:'',search:''},history:{replaceState(){}},
  FormData:class{constructor(form){return form.entries}},
 });
 vm.runInContext(source,ctx);
 ctx.capture=async(path,data)=>{calls.push({path,data});if(reject)throw Error('Server rejected this transition');return {}};
 vm.runInContext("api=capture;me={role:'customer'};render=async()=>{};notice=()=>{};",ctx);
 const form={
  id:{value:entries.find(([k])=>k==='id')?.[1]}, // Browser exposes the input, not a string.
  entries,getAttribute(name){return name==='id'?formName:null},dataset:{dirty:'true'},
  querySelector(selector){return selector==='button[type=submit]'?submit:selector==='.form-error'?error:null},
  querySelectorAll(){return []},
 };
 await listeners.submit({preventDefault(){},target:form});
 return {calls,error:error.textContent,disabled:submit.disabled};
}
(async()=>{
 const broken=code.replace("formId=f.getAttribute('id')||''","formId=f.id");
 let r=await submitScenario(broken,'transition',[['id','10052'],['state','Quotation']]);
 assert.match(r.error,/startsWith is not a function/);assert.equal(r.calls.length,0);
 const cases=[
  ['transition',[['id','10052'],['state','Quotation']],'transition'],
  ['transition',[['id','10052'],['state','Confirmed']],'transition'],
  ['transition',[['id','10052'],['state','Active']],'transition'],
  ['invoice-action',[['id','42'],['action','confirm']],'invoice'],
  ['invoice-action',[['id','42'],['action','send']],'invoice'],
  ['invoice-action',[['id','42'],['action','cancel']],'invoice'],
  ['bill',[['id','10052'],['revision','7']],'bill'],
  ['bill',[['id',''],['revision','7']],'bill'],
  ['payment',[['invoice_id','42'],['amount','100.25']],'payment'],
  ['allocate',[['bank_id','9'],['invoice_id','42'],['amount','100.25']],'allocate'],
 ];
 for(const [name,entries,path] of cases){
  r=await submitScenario(code,name,entries);assert.equal(r.error,'',name);assert.equal(r.calls[0].path,path);assert.equal(r.disabled,false);
  if(['payment','allocate'].includes(name))assert.equal(r.calls[0].data.amount,10025);
  if(name==='bill'&&entries[0][1]==='')assert.equal('id' in r.calls[0].data,false);
 }
 r=await submitScenario(code,'transition',[['id','10052'],['state','Quotation']],true);
 assert.equal(r.error,'Server rejected this transition');assert.equal(r.disabled,false);
 console.log('12 form regression checks passed, including reproduction of the original bug.');
})().catch(e=>{console.error(e);process.exitCode=1});
