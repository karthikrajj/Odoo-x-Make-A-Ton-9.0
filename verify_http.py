"""Real HTTP integration tests against an isolated disposable database."""
import tempfile,threading,json,time,urllib.request,urllib.error,http.cookiejar,re,os
from pathlib import Path
import server,legacy as db

def run():
 old=db.DB
 with tempfile.TemporaryDirectory() as temp:
  db.DB=os.path.join(temp,'integration.db');server.initialize();httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{httpd.server_port}/api/';timings={};checks=[]
  def client():return urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
  admin=client();customer=client();staff=client();anon=client()
  def req(op,path,data=None,expected=200):
   r=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'} if data is not None else {})
   try:response=op.open(r,timeout=30)
   except urllib.error.HTTPError as e:response=e
   body=response.read();assert response.status==expected,(path,response.status,body[:300]);return body if path.startswith('invoice.pdf') else json.loads(body)
  def login(op,role):req(op,'login',{'email':role+'@renewsure.demo','password':'DemoPass!2026'})
  try:
   for op,role in [(admin,'admin'),(staff,'staff'),(customer,'customer')]:login(op,role)
   req(anon,'demo-mail?email=admin%40renewsure.demo',expected=404);req(anon,'dashboard',expected=401);req(customer,'checks',expected=403);req(staff,'staff',expected=403);req(customer,'invoice?id=4',expected=403);req(admin,'bill',expected=405);checks+=['authentication','roles','ownership','GET mutation rejected']
   req(admin,'staff',{'name':'API Staff','email':'api.staff@example.test','password':'ValidPass!2026'});req(staff,'staff',{'name':'Bad','email':'bad@example.test','password':'ValidPass!2026'},403)
   req(anon,'signup',{'name':'API Customer','email':'api.customer@example.test','password':'ValidPass!2026'});req(anon,'forgot',{'email':'api.customer@example.test'});
   with db.conn() as c:body=c.execute("SELECT body FROM outbox WHERE recipient='api.customer@example.test' AND kind='reset' ORDER BY id DESC LIMIT 1").fetchone()[0]
   token=re.search(r'reset=([^\s]+)',body).group(1);req(anon,'reset',{'token':token,'password':'ResetPass!2026'});req(anon,'reset',{'token':token,'password':'ResetPass!2026'},400);req(anon,'login',{'email':'api.customer@example.test','password':'ResetPass!2026'});checks+=['staff creation','signup','single-use password reset']
   for path in ['dashboard','subscriptions','invoices','payments','reconcile','preview','checks','bank','recovery','products','variants','taxes','plans','discounts','templates','mailbox-all']:
    start=time.perf_counter();req(admin,path);timings[path]=round((time.perf_counter()-start)*1000,2)
   for n in range(10):
    name=f'Rehearsal Shop {n+1}';sid=req(admin,'subscriptions',{'customer':name,'email':'customer@renewsure.demo','plan_id':1,'template_id':1,'start_date':'2026-10-31','terms_days':0})['id']
    for state in ['Quotation','Confirmed','Active']:req(admin,'transition',{'id':sid,'state':state})
    p=req(admin,'preview');assert req(admin,'bill',{'id':sid,'revision':p['revision']})['created']==1;assert req(admin,'bill',{'id':sid})['created']==0
    records=req(admin,'invoices?q='+urllib.parse.quote(name))['rows'];i=records[0];assert i['total']==125080;req(admin,'invoice',{'id':i['id'],'action':'confirm'})
    csv=f'reference,customer,amount,date,method\nINV-{i["id"]},{name},500.00,2026-10-31,UPI\n';assert req(admin,'import',{'csv':csv})['imported']==1;assert req(admin,'import',{'csv':csv})['duplicates']==1
    b=req(admin,'bank?q='+urllib.parse.quote(name))['rows'][0];assert b['suggestions'][0]['id']==i['id'];req(admin,'allocate',{'bank_id':b['id'],'invoice_id':i['id'],'amount':50000});assert req(admin,'invoice?id='+str(i['id']))['balance']==75080
    req(admin,'payment',{'invoice_id':i['id'],'amount':75080,'reference':f'FINAL-{n}','date':'2026-10-31','method':'NEFT'});assert req(customer,'invoice?id='+str(i['id']))['state']=='Paid';req(admin,'invoice',{'id':i['id'],'action':'send'});pdf=req(customer,'invoice.pdf?id='+str(i['id']));assert pdf.startswith(b'%PDF');assert all(x['passed'] for x in req(admin,'checks')['checks'])
   checks.append('10 complete API demo rehearsals: quote to invoice to split payment to PDF')
   from concurrent.futures import ThreadPoolExecutor
   # Test every read screen at four simultaneous users, using separate clients and shared session cookie.
   cookie='; '.join(c.name+'='+c.value for h in admin.handlers if isinstance(h,urllib.request.HTTPCookieProcessor) for c in h.cookiejar)
   paths=['dashboard','subscriptions','invoices','payments','reconcile','preview','checks','bank','recovery','products','variants','taxes','plans','discounts','templates','staff','mailbox-all']
   def timed(path):
    start=time.perf_counter();op=client();response=op.open(urllib.request.Request(base+path,headers={'Cookie':cookie}),timeout=30);payload=json.loads(response.read());assert response.status==200;return {'path':path,'ms':round((time.perf_counter()-start)*1000,2)}
   with ThreadPoolExecutor(max_workers=4) as pool:concurrent=list(pool.map(timed,paths*2))
   Path('performance.json').write_text(json.dumps({'users':4,'requests':len(concurrent),'max_ms':max(x['ms'] for x in concurrent),'all_under_2_seconds':all(x['ms']<2000 for x in concurrent),'requests_ms':concurrent},indent=2),encoding='utf-8')

   # Prove request transaction rollback after an injected mid-batch failure.
   with db.conn() as c:c.execute("UPDATE subscriptions SET state='Paused' WHERE state='Active'")
   ids=[]
   for name in ['Rollback A','Rollback B']:
    sid=req(admin,'subscriptions',{'customer':name,'email':'customer@renewsure.demo','plan_id':1,'template_id':1,'start_date':'2026-10-31','terms_days':0})['id'];ids.append(sid)
    for state in ['Quotation','Confirmed','Active']:req(admin,'transition',{'id':sid,'state':state})
   with db.conn() as c:c.execute(f"CREATE TRIGGER fail_batch BEFORE INSERT ON invoices WHEN NEW.subscription_id={ids[1]} BEGIN SELECT RAISE(ABORT,'Injected billing failure'); END")
   req(admin,'bill',{},400)
   with db.conn() as c:
    assert c.execute('SELECT COUNT(*) FROM invoices WHERE subscription_id IN (?,?)',ids).fetchone()[0]==0
    assert all(r[0]=='2026-10-31' for r in c.execute('SELECT due FROM subscriptions WHERE id IN (?,?)',ids))
    c.execute('DROP TRIGGER fail_batch')
   assert req(admin,'bill',{})['created']==2
   checks.append('Injected mid-batch failure rolled back all invoices and next dates; retry succeeded')
   report={'domain_tests':51,'api_checks':checks,'demo_rehearsals':10,'seed_subscriptions':10050,'http_timings_ms':timings,'all_under_2_seconds':all(v<2000 for v in timings.values())};Path('verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
  finally:httpd.shutdown();httpd.server_close();thread.join();db.DB=old
if __name__=='__main__':run()
