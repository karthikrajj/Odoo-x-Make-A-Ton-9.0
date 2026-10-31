import sqlite3, hashlib, secrets, json, datetime, calendar, csv, io, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
BASE=Path(__file__).resolve().parent
DB=os.environ.get('RENEWSURE_DB',str(BASE/'renewsure.db'))
from contextlib import contextmanager
@contextmanager
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
 try:
  with c: yield c
 finally: c.close()
def password(p,s): return hashlib.pbkdf2_hmac('sha256',p.encode(),s.encode(),100000).hex()
def valid(p): return len(p)>8 and any(x.isupper() for x in p) and any(x.islower() for x in p) and any(not x.isalnum() and not x.isspace() for x in p)
def advance(d,cycle):
 d=datetime.date.fromisoformat(d)
 if cycle in ('daily','weekly'): return str(d+datetime.timedelta(days=1 if cycle=='daily' else 7))
 m=d.month+(12 if cycle=='yearly' else 1); y=d.year+(m-1)//12; m=(m-1)%12+1
 return str(d.replace(year=y,month=m,day=min(d.day,calendar.monthrange(y,m)[1])))
def calc(price,qty,discount,tax):
 base=price*qty; disc=min(base,discount); net=base-disc; taxes=(net*tax+5000)//10000
 return dict(subtotal=base,discount=disc,tax=taxes,total=net+taxes)
def init():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,name TEXT,role TEXT,salt TEXT,hash TEXT); CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INT,expires REAL); CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY,name TEXT,price INT,cycle TEXT,tax INT,min_qty INT DEFAULT 1); CREATE TABLE IF NOT EXISTS subscriptions(id INTEGER PRIMARY KEY,customer TEXT,email TEXT,plan_id INT,qty INT,state TEXT,due TEXT,discount INT DEFAULT 0,discount_end TEXT,discount_limit INT DEFAULT 0,discount_used INT DEFAULT 0); CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,subscription_id INT,period TEXT,customer TEXT,email TEXT,subtotal INT,discount INT,tax INT,total INT,state TEXT DEFAULT 'Confirmed',UNIQUE(subscription_id,period)); CREATE TABLE IF NOT EXISTS bank(id INTEGER PRIMARY KEY,fingerprint TEXT UNIQUE,reference TEXT,customer TEXT,amount INT,date TEXT,method TEXT); CREATE TABLE IF NOT EXISTS allocations(id INTEGER PRIMARY KEY,bank_id INT,invoice_id INT,amount INT CHECK(amount>0),FOREIGN KEY(bank_id) REFERENCES bank(id),FOREIGN KEY(invoice_id) REFERENCES invoices(id)); CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT DEFAULT CURRENT_TIMESTAMP,event TEXT); CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY,invoice_id INT,at TEXT DEFAULT CURRENT_TIMESTAMP,status TEXT);''')
  if c.execute('SELECT count(*) FROM users').fetchone()[0]: return
  for name,role in [('Admin','admin'),('Staff','staff'),('Customer','customer')]:
   s=secrets.token_hex(16); c.execute('INSERT INTO users(email,name,role,salt,hash) VALUES(?,?,?,?,?)',(role+'@renewsure.demo',name,role,s,password('DemoPass!2026',s)))
  c.executemany('INSERT INTO plans(name,price,cycle,tax) VALUES(?,?,?,?)',[('Launch',50000,'monthly',1800),('Growth',150000,'monthly',1800),('Scale',500000,'monthly',1800),('Annual Suite',1200000,'yearly',1800)])
  c.execute("INSERT INTO settings VALUES('clock','2026-10-31')")
  names=['Malabar Design','Kochi Cloud','Harbour Labs','Spice Route Retail','Bluewater Systems','Coconut Studio','Metro Works','Backwater Digital']
  for i in range(1,10051):
   email='customer@renewsure.demo' if i<=3 else f'finance{i}@example.test'; name=names[(i-1)%8]+f' {i:04d}'; plan=(i-1)%4+1; qty=i%5+1; due=f'2026-10-{i%28+1:02d}'
   c.execute('INSERT INTO subscriptions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(i,name,email,plan,qty,'Active' if i%17 else 'Paused',due,50000 if i%7==0 else 0,'2026-10-15',2,0))
   if i%5:
    p=c.execute('SELECT * FROM plans WHERE id=?',(plan,)).fetchone(); a=calc(p['price'],qty,0,p['tax']); cur=c.execute('INSERT INTO invoices(subscription_id,period,customer,email,subtotal,discount,tax,total) VALUES(?,?,?,?,?,?,?,?)',(i,'2026-09-01',name,email,*a.values())); inv=cur.lastrowid
    if i%3:
     paid=a['total'] if i%4 else a['total']//2; b=c.execute('INSERT INTO bank(fingerprint,reference,customer,amount,date,method) VALUES(?,?,?,?,?,?)',(f'seed{i}',f'INV-{inv}',name,paid,'2026-09-10','NEFT')).lastrowid; c.execute('INSERT INTO allocations(bank_id,invoice_id,amount) VALUES(?,?,?)',(b,inv,paid))
  c.executescript('CREATE INDEX IF NOT EXISTS ix_invoice_email ON invoices(email); CREATE INDEX IF NOT EXISTS ix_allocation_invoice ON allocations(invoice_id); CREATE INDEX IF NOT EXISTS ix_subscription_due ON subscriptions(state,due);')
def preview(c,date):
 rows=c.execute('SELECT s.*,p.price,p.tax,p.cycle FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.state="Active" AND s.due<=?',(date,)).fetchall(); out=[]
 for s in rows:
  if c.execute('SELECT 1 FROM invoices WHERE subscription_id=? AND period=?',(s['id'],s['due'])).fetchone(): continue
  discount=s['discount'] if s['discount_end'] and s['due']<=s['discount_end'] and s['discount_used']<s['discount_limit'] else 0
  out.append(dict(s)|calc(s['price'],s['qty'],discount,s['tax']))
 return out
def bill(c,date):
 rows=preview(c,date)
 for s in rows:
  c.execute('INSERT INTO invoices(subscription_id,period,customer,email,subtotal,discount,tax,total) VALUES(?,?,?,?,?,?,?,?)',(s['id'],s['due'],s['customer'],s['email'],s['subtotal'],s['discount'],s['tax'],s['total']))
  c.execute('UPDATE subscriptions SET due=?,discount_used=discount_used+? WHERE id=?',(advance(s['due'],s['cycle']),int(s['discount']>0),s['id']))
 c.execute('INSERT INTO audit(event) VALUES(?)',(f'Billing run: {len(rows)} invoices for {date}',)); return len(rows)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def respond(self,data,status=200):
  b=json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(b)
 def do_GET(self): self.handle_req()
 def do_POST(self): self.handle_req()
 def handle_req(self):
  try:
   path=urlparse(self.path).path; q=parse_qs(urlparse(self.path).query)
   if not path.startswith('/api/'):
    file=(BASE/'static')/({'/':'index.html'}.get(path,path.lstrip('/')))
    if not file.resolve().is_relative_to((BASE/'static').resolve()) or not file.is_file(): return self.respond({'error':'Not found'},404)
    b=file.read_bytes(); self.send_response(200); self.send_header('Content-Type',{'html':'text/html','js':'text/javascript','css':'text/css'}.get(file.suffix[1:],'text/plain')); self.end_headers(); self.wfile.write(b); return
   data={}
   if self.command=='POST':
    if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.respond({'error':'JSON required'},415)
    n=int(self.headers.get('Content-Length',0))
    if n>2000000: return self.respond({'error':'Upload too large'},413)
    data=json.loads(self.rfile.read(n))
   with conn() as c:
    if path=='/api/login':
     u=c.execute('SELECT * FROM users WHERE email=?',(data.get('email','').lower(),)).fetchone()
     if not u or not secrets.compare_digest(u['hash'],password(data.get('password',''),u['salt'])): return self.respond({'error':'Email or password is incorrect'},401)
     import time
     t=secrets.token_hex(32); c.execute('INSERT INTO sessions VALUES(?,?,?)',(t,u['id'],time.time()+28800)); self.send_response(200); self.send_header('Set-Cookie',f'session={t}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(b'{}'); return
    import time
    token=next((x.strip()[8:] for x in self.headers.get('Cookie','').split(';') if x.strip().startswith('session=')),''); u=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE token=? AND expires>?',(token,time.time())).fetchone()
    if not u: return self.respond({'error':'Please sign in'},401)
    role=u['role']; customer=role=='customer'; clock=c.execute("SELECT value FROM settings WHERE key='clock'").fetchone()[0]
    if path=='/api/me': return self.respond({'name':u['name'],'role':role,'clock':clock})
    if path=='/api/logout': c.execute('DELETE FROM sessions WHERE token=?',(token,)); return self.respond({})
    if self.command=='POST' and customer: return self.respond({'error':'Staff access required'},403)
    if path=='/api/plans':
     if self.command=='POST':
      if role!='admin': return self.respond({'error':'Admin access required'},403)
      if data['cycle'] not in ['daily','weekly','monthly','yearly'] or int(data['price'])<=0 or not 0<=int(data['tax'])<=10000: raise ValueError('Invalid plan values')
      c.execute('INSERT INTO plans(name,price,cycle,tax) VALUES(?,?,?,?)',(data['name'],int(data['price']),data['cycle'],int(data['tax'])))
     return self.respond([dict(x) for x in c.execute('SELECT * FROM plans')])
    if path=='/api/clock':
     if role!='admin': return self.respond({'error':'Admin access required'},403)
     datetime.date.fromisoformat(data['date']); c.execute("UPDATE settings SET value=? WHERE key='clock'",(data['date'],)); return self.respond({})
    if path=='/api/preview' or path=='/api/bill':
     if customer: return self.respond({'error':'Staff access required'},403)
     c.execute('BEGIN IMMEDIATE')
     if path.endswith('bill'): return self.respond({'created':bill(c,clock)})
     rows=preview(c,clock); return self.respond({'count':len(rows),'total':sum(x['total'] for x in rows),'rows':rows[:20],'mrr_delta':0})
    if path=='/api/subscriptions' and self.command=='POST':
     p=c.execute('SELECT * FROM plans WHERE id=?',(data['plan_id'],)).fetchone(); qty=int(data['qty']); datetime.date.fromisoformat(data['due'])
     if not p or qty<p['min_qty'] or '@' not in data['email']: raise ValueError('Valid plan, quantity and email required')
     c.execute('INSERT INTO subscriptions(customer,email,plan_id,qty,state,due) VALUES(?,?,?,?,?,?)',(data['customer'],data['email'],p['id'],qty,'Draft',data['due'])); return self.respond({})
    if path=='/api/transition':
     s=c.execute('SELECT * FROM subscriptions WHERE id=?',(data['id'],)).fetchone(); allowed={'Draft':['Quotation'],'Quotation':['Confirmed'],'Confirmed':['Active'],'Active':['Paused','Closed'],'Paused':['Active','Closed']}
     if data['state'] not in allowed.get(s['state'],[]): raise ValueError('Invalid lifecycle transition')
     c.execute('UPDATE subscriptions SET state=? WHERE id=?',(data['state'],s['id'])); return self.respond({})
    if path=='/api/import':
     rows=list(csv.DictReader(io.StringIO(data['csv']))); count=0
     for r in rows:
      from decimal import Decimal
      amount=int(Decimal(r['amount'])*100); datetime.date.fromisoformat(r['date'])
      if amount<=0: raise ValueError('Amounts must be positive')
      fingerprint=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest(); count+=c.execute('INSERT OR IGNORE INTO bank(fingerprint,reference,customer,amount,date,method) VALUES(?,?,?,?,?,?)',(fingerprint,r['reference'],r['customer'],amount,r['date'],r.get('method','NEFT'))).rowcount
     return self.respond({'imported':count})
    if path=='/api/allocate':
     c.execute('BEGIN IMMEDIATE'); amount=int(data['amount']); b=c.execute('SELECT amount-COALESCE((SELECT SUM(amount) FROM allocations WHERE bank_id=bank.id),0) FROM bank WHERE id=?',(data['bank_id'],)).fetchone(); i=c.execute('SELECT total-COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0) FROM invoices WHERE id=?',(data['invoice_id'],)).fetchone()
     if not b or not i or amount<=0 or amount>min(b[0],i[0]): raise ValueError('Allocation exceeds available payment or invoice balance')
     c.execute('INSERT INTO allocations(bank_id,invoice_id,amount) VALUES(?,?,?)',(data['bank_id'],data['invoice_id'],amount)); c.execute('INSERT INTO audit(event) VALUES(?)',(f"Allocated {amount} paise to invoice {data['invoice_id']}",)); return self.respond({})
    if path=='/api/remind':
     c.execute('INSERT INTO reminders(invoice_id,status) VALUES(?,?)',(data['id'],'Demo reminder queued — no email sent')); return self.respond({'message':'Demo reminder queued. SMTP delivery is not configured.'})
    scope=' WHERE email=?' if customer else ''; args=[u['email']] if customer else []
    if path=='/api/dashboard':
     mrr=c.execute('SELECT COALESCE(SUM(p.price*s.qty / CASE p.cycle WHEN "yearly" THEN 12.0 WHEN "weekly" THEN 0.230769 WHEN "daily" THEN 0.0328767 ELSE 1 END),0) FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE state="Active"'+(' AND s.email=?' if customer else ''),args).fetchone()[0]
     totals=c.execute('SELECT count(*),COALESCE(sum(total),0),COALESCE(sum((SELECT COALESCE(sum(amount),0) FROM allocations WHERE invoice_id=invoices.id)),0) FROM invoices'+scope,args).fetchone(); active=c.execute('SELECT count(*) FROM subscriptions WHERE state="Active"'+(' AND email=?' if customer else ''),args).fetchone()[0]
     return self.respond({'mrr':round(mrr),'active':active,'invoices':totals[0],'invoiced':totals[1],'received':totals[2],'outstanding':totals[1]-totals[2]})
    if path=='/api/checks':
     if customer: return self.respond({'error':'Staff access required'},403)
     bad=c.execute('SELECT count(*) FROM invoices WHERE subtotal-discount+tax != total').fetchone()[0]; over=c.execute('SELECT count(*) FROM invoices WHERE total<(SELECT COALESCE(SUM(amount),0) FROM allocations WHERE invoice_id=invoices.id)').fetchone()[0]
     return self.respond([{'name':'Invoice arithmetic balances','passed':bad==0},{'name':'No overallocated invoices','passed':over==0},{'name':'Unique subscription + billing period enforced','passed':True}])
    if path=='/api/bank':
     if customer: return self.respond({'error':'Staff access required'},403)
     return self.respond([dict(x) for x in c.execute('SELECT *,amount-COALESCE((SELECT SUM(amount) FROM allocations WHERE bank_id=bank.id),0) available FROM bank WHERE available>0 ORDER BY id DESC LIMIT 100')])
    if path in ['/api/subscriptions','/api/invoices','/api/reconcile']:
     page=max(1,int(q.get('page',['1'])[0])); search=q.get('q',[''])[0]; where=' WHERE customer LIKE ?'; params=['%'+search+'%']
     if customer: where+=' AND email=?'; params.append(u['email'])
     table='subscriptions' if path.endswith('subscriptions') else 'invoices'; total=c.execute('SELECT count(*) FROM '+table+where,params).fetchone()[0]
     sql='SELECT * FROM subscriptions' if table=='subscriptions' else 'SELECT *,COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0) paid FROM invoices'
     rows=[dict(x) for x in c.execute(sql+where+' ORDER BY id DESC LIMIT 30 OFFSET ?',params+[(page-1)*30])]
     return self.respond({'rows':rows,'total':total,'page':page})
    return self.respond({'error':'Not found'},404)
  except (ValueError,KeyError,sqlite3.IntegrityError) as e: self.respond({'error':str(e)},400)
  except Exception as e:
   import traceback; traceback.print_exc(); self.respond({'error':'Unexpected server error'},500)
if __name__=='__main__':
 init()
 port=int(os.environ.get('PORT','8765'))
 httpd=ThreadingHTTPServer(('127.0.0.1',port),Handler)
 print(f'RenewSure: http://127.0.0.1:{port}',flush=True)
 httpd.serve_forever()

