"""RenewSure domain services. Money is integer paise; tax/percentage rates are basis points."""
import datetime as dt, calendar, hashlib, json, secrets, re, time, csv, io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import legacy as db

class Error(ValueError): pass

def today(c):
 mode=c.execute("SELECT value FROM settings WHERE key='clock_mode'").fetchone()
 if mode and mode[0]=='live':return str(dt.datetime.now(dt.timezone(dt.timedelta(hours=5,minutes=30))).date())
 return c.execute("SELECT value FROM settings WHERE key='clock'").fetchone()[0]
def rows(c,sql,args=()): return [dict(r) for r in c.execute(sql,args)]
def one(c,sql,args=()):
 r=c.execute(sql,args).fetchone()
 if r is None: raise Error('Record not found')
 return dict(r)
def date(s):
 try: return str(dt.date.fromisoformat(str(s)))
 except ValueError: raise Error('Use a valid date in YYYY-MM-DD format')
def integer(v,low=0,high=100000000000):
 try:
  n=int(str(v))
  if not low<=n<=high: raise ValueError()
  return n
 except (ValueError,TypeError): raise Error(f'Enter a whole number between {low} and {high}')
def text(v,limit=250):
 s=str(v or '').strip()
 if not s or len(s)>limit: raise Error(f'Text is required and must be at most {limit} characters')
 return s
def email(v):
 s=text(v).lower()
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',s): raise Error('Enter a valid email address')
 return s
def money(v):
 try:
  d=Decimal(str(v))
  if not d.is_finite() or d<0 or d>Decimal('1000000000') or d*100!=(d*100).to_integral_value(): raise ValueError()
  return int(d*100)
 except (ValueError,InvalidOperation): raise Error('Amount must be positive with at most two decimal places')
def audit(c,event,actor='system'): c.execute('INSERT INTO audit(event) VALUES(?)',(actor+': '+event,))
def bump(c): c.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
def migrate():
 with db.conn() as c:
  additions={'plans':{'available_from':"TEXT DEFAULT '2020-01-01'",'available_to':'TEXT','allow_pause':'INTEGER DEFAULT 1','allow_close':'INTEGER DEFAULT 1','allow_renew':'INTEGER DEFAULT 1','auto_close':'INTEGER DEFAULT 1'},'subscriptions':{'start_date':'TEXT','expiry':'TEXT','terms_days':'INTEGER DEFAULT 15','quotation_until':'TEXT','discount_id':'INTEGER','anchor_day':'INTEGER'},'invoices':{'due_date':'TEXT','disputed':'INTEGER DEFAULT 0','lines':'TEXT','expected':'INTEGER','notes':"TEXT DEFAULT ''"},'bank':{'note':"TEXT DEFAULT ''"},'outbox':{'invoice_id':'INTEGER'}}
  for table,cols in additions.items():
   existing={r[1] for r in c.execute('PRAGMA table_info('+table+')')}
   if not existing:continue
   for k,v in cols.items():
    if k not in existing:c.execute(f'ALTER TABLE {table} ADD COLUMN {k} {v}')
  c.executescript('''
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT NOT NULL,type TEXT,sales_price INTEGER,cost_price INTEGER,notes TEXT,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS variants(id INTEGER PRIMARY KEY,product_id INTEGER REFERENCES products(id),name TEXT,extra INTEGER);
CREATE TABLE IF NOT EXISTS taxes(id INTEGER PRIMARY KEY,name TEXT,rate INTEGER,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS discount_rules(id INTEGER PRIMARY KEY,name TEXT,kind TEXT,value INTEGER,min_qty INTEGER,min_purchase INTEGER,start TEXT,end TEXT,limit_uses INTEGER,used INTEGER DEFAULT 0,product_id INTEGER,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS templates(id INTEGER PRIMARY KEY,name TEXT,plan_id INTEGER,valid_days INTEGER,lines TEXT);
CREATE TABLE IF NOT EXISTS subscription_lines(id INTEGER PRIMARY KEY,subscription_id INTEGER REFERENCES subscriptions(id),product_id INTEGER,variant_id INTEGER,description TEXT,qty INTEGER,unit_price INTEGER,tax_rate INTEGER);
CREATE TABLE IF NOT EXISTS discount_applications(id INTEGER PRIMARY KEY,discount_id INTEGER,invoice_id INTEGER UNIQUE,amount INTEGER);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,recipient TEXT,subject TEXT,body TEXT,kind TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP,status TEXT DEFAULT 'Local mailbox');
CREATE TABLE IF NOT EXISTS resets(token TEXT PRIMARY KEY,user_id INTEGER,expires REAL,used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS reminder_events(invoice_id INTEGER,stage INTEGER,mail_id INTEGER,PRIMARY KEY(invoice_id,stage));
CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,date TEXT,subscription_id INTEGER,email TEXT,kind TEXT,amount INTEGER);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,date TEXT,created INTEGER,skipped INTEGER,total INTEGER,revision INTEGER,at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS run_items(run_id INTEGER,subscription_id INTEGER,period TEXT,invoice_id INTEGER,reason TEXT);
CREATE INDEX IF NOT EXISTS ix_lines_sub ON subscription_lines(subscription_id);
CREATE INDEX IF NOT EXISTS ix_bank_alloc ON allocations(bank_id);
CREATE INDEX IF NOT EXISTS ix_invoice_due ON invoices(due_date,state);
CREATE INDEX IF NOT EXISTS ix_moves_date ON movements(date);
''')
  if 'invoice_id' not in {r[1] for r in c.execute('PRAGMA table_info(outbox)')}:c.execute('ALTER TABLE outbox ADD COLUMN invoice_id INTEGER')
  c.execute("INSERT OR IGNORE INTO settings VALUES('revision','1')")
  c.execute("INSERT OR IGNORE INTO settings VALUES('clock_mode','demo')")
  c.execute("INSERT OR IGNORE INTO settings VALUES('auto_billing','0')")
  c.execute('CREATE INDEX IF NOT EXISTS ix_bank_date ON bank(date)')
  c.execute('CREATE INDEX IF NOT EXISTS ix_sub_email ON subscriptions(email)')
  c.execute('CREATE INDEX IF NOT EXISTS ix_outbox_recipient ON outbox(recipient,id)')
  if not c.execute('SELECT 1 FROM products').fetchone():
   for p in rows(c,'SELECT * FROM plans'):
    c.execute('INSERT INTO products(id,name,type,sales_price,cost_price,notes) VALUES(?,?,?,?,?,?)',(p['id'],p['name']+' Software','Service',p['price'],p['price']//3,'Seeded subscription software'))
   c.execute("INSERT INTO variants(product_id,name,extra) VALUES(1,'Odoo brand',56000)")
   c.executemany('INSERT INTO taxes(name,rate) VALUES(?,?)',[('Standard 18%',1800),('Reduced 5%',500),('Zero rated',0)])
  c.execute('INSERT INTO subscription_lines(subscription_id,product_id,description,qty,unit_price,tax_rate) SELECT s.id,p.id,p.name,s.qty,p.price,p.tax FROM subscriptions s JOIN plans p ON s.plan_id=p.id WHERE NOT EXISTS(SELECT 1 FROM subscription_lines l WHERE l.subscription_id=s.id)')
  c.execute('UPDATE subscriptions SET start_date=COALESCE(start_date,due),anchor_day=COALESCE(anchor_day,CAST(substr(due,9,2) AS INT))')
  c.execute("UPDATE invoices SET due_date=date(period,'+15 days'),expected=total WHERE due_date IS NULL")
  c.execute("UPDATE invoices SET state='Paid' WHERE state='Confirmed' AND total<=COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0)")
  if not c.execute('SELECT 1 FROM movements').fetchone():
   for s in rows(c,"SELECT s.*,p.cycle FROM subscriptions s JOIN plans p ON s.plan_id=p.id WHERE state='Active'"):
    c.execute('INSERT INTO movements(date,subscription_id,email,kind,amount) VALUES(?,?,?,?,?)',('2026-09-01',s['id'],s['email'],'opening',mrr(c,s)))
  if not c.execute('SELECT 1 FROM templates').fetchone():
   c.execute('INSERT INTO templates(name,plan_id,valid_days,lines) VALUES(?,?,?,?)',('Launch · Odoo starter',1,14,json.dumps([{'product_id':1,'variant_id':1,'qty':1,'tax_id':1}])))

def mrr(c,s):
 total=c.execute('SELECT COALESCE(SUM(qty*unit_price),0) FROM subscription_lines WHERE subscription_id=?',(s['id'],)).fetchone()[0]
 cycle=s.get('cycle') or one(c,'SELECT cycle FROM plans WHERE id=?',(s['plan_id'],))['cycle']
 return int((Decimal(total)*{'daily':Decimal(365)/12,'weekly':Decimal(52)/12,'monthly':Decimal(1),'yearly':Decimal(1)/12}[cycle]).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def movement(c,s,kind,amount): c.execute('INSERT INTO movements(date,subscription_id,email,kind,amount) VALUES(?,?,?,?,?)',(today(c),s['id'],s['email'],kind,amount))
def next_period(s,period):
 d=dt.date.fromisoformat(period); cycle=s['cycle']
 if cycle in ['daily','weekly']: return str(d+dt.timedelta(days=1 if cycle=='daily' else 7))
 month=d.month+(12 if cycle=='yearly' else 1);year=d.year+(month-1)//12;month=(month-1)%12+1
 return str(dt.date(year,month,min(s.get('anchor_day') or d.day,calendar.monthrange(year,month)[1])))
def quote(c,s,period,used=None,legacy_used=None,line_cache=None,rule_cache=None):
 lines=line_cache.get(s['id'],[]) if line_cache is not None else rows(c,'SELECT * FROM subscription_lines WHERE subscription_id=? ORDER BY id',(s['id'],)); base=sum(l['qty']*l['unit_price'] for l in lines)
 rule=None; amount=0; eligible=lines
 if s.get('discount_id'):
  rule=rule_cache[s['discount_id']] if rule_cache is not None else one(c,'SELECT * FROM discount_rules WHERE id=?',(s['discount_id'],)); count=(used or {}).get(rule['id'],rule['used'])
  eligible=[l for l in lines if not rule['product_id'] or l['product_id']==rule['product_id']]; subtotal=sum(l['qty']*l['unit_price'] for l in eligible)
  if rule['active'] and rule['start']<=period<=rule['end'] and count<rule['limit_uses'] and sum(l['qty'] for l in eligible)>=rule['min_qty'] and subtotal>=rule['min_purchase']:
   amount=min(subtotal,rule['value'] if rule['kind']=='fixed' else (subtotal*rule['value']+5000)//10000)
 elif s.get('discount') and s.get('discount_end') and period<=s['discount_end'] and (s['discount_used'] if legacy_used is None else legacy_used)<s['discount_limit']: amount=min(base,s['discount'])
 eligible_total=sum(l['qty']*l['unit_price'] for l in eligible); remaining=amount; output=[]; last=eligible[-1]['id'] if eligible else None
 for l in lines:
  sub=l['qty']*l['unit_price']; disc=0
  if l in eligible and eligible_total: disc=remaining if l['id']==last else amount*sub//eligible_total;remaining-=disc
  tax=((sub-disc)*l['tax_rate']+5000)//10000
  output.append({**l,'subtotal':sub,'discount':disc,'tax':tax,'total':sub-disc+tax})
 return {'lines':output,'subtotal':base,'discount':amount,'tax':sum(l['tax'] for l in output),'total':sum(l['total'] for l in output),'discount_id':rule['id'] if rule and amount else None}

def rehearsal(c,on=None,only=None):
 on=on or today(c); conditions='WHERE (s.due<=? OR s.expiry<?)';params=[on,on]
 if only:conditions+=' AND s.id=?';params.append(only)
 subs=rows(c,'SELECT s.*,p.cycle,p.auto_close FROM subscriptions s JOIN plans p ON p.id=s.plan_id '+conditions+' ORDER BY s.due,s.id',params)
 line_cache={}
 for l in rows(c,'SELECT * FROM subscription_lines ORDER BY id'):line_cache.setdefault(l['subscription_id'],[]).append(l)
 rule_cache={r['id']:r for r in rows(c,'SELECT * FROM discount_rules')}
 exists={(r['subscription_id'],r['period']):r['id'] for r in c.execute('SELECT id,subscription_id,period FROM invoices')};used={};items=[];skips=[];expired=[]
 for s in subs:
  if s['state']=='Paused' and s['expiry'] and s['expiry']<on and s['auto_close']:
   expired.append(s['id']);skips.append({'id':s['id'],'customer':s['customer'],'reason':'Paused contract expired; automatic close'});continue
  if s['state']!='Active': skips.append({'id':s['id'],'customer':s['customer'],'reason':s['state']});continue
  if s['expiry'] and s['expiry']<on and s['due']>on and s['auto_close']:
   expired.append(s['id']);skips.append({'id':s['id'],'customer':s['customer'],'reason':'Contract expired; automatic close'});continue
  period=s['due']; legacy_count=s['discount_used']; count=0
  while period<=on:
   if s['expiry'] and period>s['expiry']:
    skips.append({'id':s['id'],'customer':s['customer'],'reason':'Contract expired'})
    if s['auto_close']:expired.append(s['id'])
    break
   if (s['id'],period) in exists:skips.append({'id':s['id'],'customer':s['customer'],'reason':'Already invoiced','period':period})
   else:
    a=quote(c,s,period,used,legacy_count,line_cache,rule_cache)
    if a['discount_id']:used[a['discount_id']]=used.get(a['discount_id'],rule_cache[a['discount_id']]['used'])+1
    if a['discount']:legacy_count+=1
    items.append({'id':s['id'],'customer':s['customer'],'email':s['email'],'period':period,'due_date':str(dt.date.fromisoformat(period)+dt.timedelta(days=s['terms_days'])),**a})
   period=next_period(s,period);count+=1
   if count>400: raise Error('More than 400 periods are overdue. Advance in smaller billing batches.')
 return {'items':items,'skips':skips,'expired':expired,'count':len(items),'total':sum(i['total'] for i in items),'revision':int(one(c,"SELECT value FROM settings WHERE key='revision'")['value']),'date':on}

def billing(c,revision=None,only=None):
 p=rehearsal(c,only=only)
 if revision is not None and integer(revision)!=p['revision']:raise Error('Data changed after preview. Refresh rehearsal before running billing.')
 run=c.execute('INSERT INTO runs(date,created,skipped,total,revision) VALUES(?,?,?,?,?)',(p['date'],p['count'],len(p['skips']),p['total'],p['revision'])).lastrowid
 for a in p['items']:
  cur=c.execute('INSERT INTO invoices(subscription_id,period,customer,email,subtotal,discount,tax,total,state,due_date,lines,expected) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(a['id'],a['period'],a['customer'],a['email'],a['subtotal'],a['discount'],a['tax'],a['total'],'Draft',a['due_date'],json.dumps(a['lines']),a['total']));iid=cur.lastrowid
  if a['discount_id']:
   c.execute('UPDATE discount_rules SET used=used+1 WHERE id=?',(a['discount_id'],));c.execute('INSERT INTO discount_applications(discount_id,invoice_id,amount) VALUES(?,?,?)',(a['discount_id'],iid,a['discount']))
  elif a['discount']: c.execute('UPDATE subscriptions SET discount_used=discount_used+1 WHERE id=?',(a['id'],))
  c.execute('INSERT INTO run_items VALUES(?,?,?,?,?)',(run,a['id'],a['period'],iid,'Created draft invoice'))
 for a in p['skips']:c.execute('INSERT INTO run_items VALUES(?,?,?,?,?)',(run,a['id'],a.get('period'),None,a['reason']))
 for s in rows(c,'SELECT s.*,p.cycle FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.state="Active" AND (s.due<=? OR s.expiry<?)',(p['date'],p['date'])):
  if only and s['id']!=only:continue
  period=s['due']
  while period<=p['date'] and (not s['expiry'] or period<=s['expiry']):period=next_period(s,period)
  c.execute('UPDATE subscriptions SET due=? WHERE id=?',(period,s['id']))
  if s['id'] in p['expired']:movement(c,s,'churn',-mrr(c,s));c.execute("UPDATE subscriptions SET state='Closed' WHERE id=?",(s['id'],))
 for sid in p['expired']:
  c.execute("UPDATE subscriptions SET state='Closed' WHERE id=? AND state='Paused'",(sid,))
 audit(c,f'Billing run {run}: {p["count"]} draft invoices; {len(p["skips"])} explained skips');bump(c)
 return {'created':p['count'],'run_id':run,'total':p['total']}

def new_user(c,d,role='customer'):
 e=email(d.get('email'));p=d.get('password','')
 if not db.valid(p):raise Error('Password must exceed 8 characters and include uppercase, lowercase and a special character')
 if c.execute('SELECT 1 FROM users WHERE email=?',(e,)).fetchone():raise Error('An account already exists for that email')
 salt=secrets.token_hex(16);uid=c.execute('INSERT INTO users(email,name,role,salt,hash) VALUES(?,?,?,?,?)',(e,text(d.get('name')),role,salt,db.password(p,salt))).lastrowid
 audit(c,'Created '+role+' account '+e);return uid

def mail(c,to,subject,body,kind='invoice',invoice_id=None):
 import delivery
 status='Suppressed demo recipient' if (to.rsplit('@',1)[-1].endswith(('.test','.demo','.invalid','.example')) or to.rsplit('@',1)[-1] in ['example.com','example.org','example.net']) else 'Queued' if delivery.configured() else 'Waiting for email setup'
 return c.execute('INSERT INTO outbox(recipient,subject,body,kind,status,invoice_id) VALUES(?,?,?,?,?,?)',(to,subject,body,kind,status,invoice_id)).lastrowid

def invoice(c,iid,user=None):
 i=one(c,'SELECT i.*,COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=i.id),0) paid FROM invoices i WHERE id=?',(iid,))
 if user and user['role']=='customer' and i['email']!=user['email']:raise PermissionError('You can only access your own invoice')
 i['lines']=json.loads(i['lines']) if i['lines'] else [{'description':'Historical subscription charge','qty':1,'unit_price':i['subtotal'],'subtotal':i['subtotal'],'discount':i['discount'],'tax':i['tax'],'total':i['total']}]
 i['balance']=i['total']-i['paid'];return i

def allocate(c,bid,iid,amount):
 b=one(c,'SELECT *,amount-COALESCE((SELECT SUM(amount) FROM allocations WHERE bank_id=bank.id),0) available FROM bank WHERE id=?',(bid,));i=invoice(c,iid);amount=integer(amount,1)
 if i['state'] not in ['Confirmed','Paid']:raise Error('Confirm the invoice before recording payment')
 if amount>min(b['available'],i['balance']):raise Error('Allocation exceeds transaction funds or invoice balance')
 c.execute('INSERT INTO allocations(bank_id,invoice_id,amount) VALUES(?,?,?)',(bid,iid,amount))
 if amount==i['balance']:c.execute("UPDATE invoices SET state='Paid' WHERE id=?",(iid,))
 audit(c,f'Allocated {amount} paise from bank {bid} to invoice {iid}');bump(c)

def candidates(c,b):
 invoices=rows(c,"SELECT i.id,i.customer,i.total-COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=i.id),0) balance FROM invoices i WHERE state='Confirmed' AND (lower(customer)=lower(?) OR id=?) LIMIT 20",(b['customer'],int(re.search(r'(?i)INV[- #]*(\d+)',b['reference']).group(1)) if re.search(r'(?i)INV[- #]*(\d+)',b['reference']) else -1))
 out=[]
 for i in invoices:
  if i['balance']<=0:continue
  ref=bool(re.search(r'(?i)\bINV[- #]*'+str(i['id'])+r'\b',b['reference'])); same=i['customer'].casefold()==b['customer'].casefold();exact=i['balance']==b['available']
  out.append({**i,'amount':min(i['balance'],b['available']),'confidence':'High' if ref and exact and same else 'Medium' if ref or same and exact else 'Low','reason':', '.join([s for s,ok in [('Invoice reference',ref),('Customer name',same),('Exact balance',exact)] if ok])})
 return sorted(out,key=lambda x: {'High':0,'Medium':1,'Low':2}[x['confidence']])[:3]

def chase(c,manual=None):
 result=[];on=today(c)
 for i in rows(c,"SELECT i.*,total-COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=i.id),0) balance FROM invoices i WHERE state='Confirmed' AND disputed=0 AND due_date<=?",(on,)):
  if manual and i['id']!=manual:continue
  if i['balance']<=0:continue
  days=(dt.date.fromisoformat(on)-dt.date.fromisoformat(i['due_date'])).days;stage=7 if days>=7 else 3 if days>=3 else 0
  if c.execute('SELECT 1 FROM reminder_events WHERE invoice_id=? AND stage=?',(i['id'],stage)).fetchone():continue
  mid=mail(c,i['email'],f'Payment reminder · INV-{i["id"]}',f'Hello {i["customer"]},\nInvoice INV-{i["id"]} has an outstanding balance of INR {i["balance"]/100:.2f}. Due date: {i["due_date"]}. Please contact Brightloop if you need help.','reminder')
  c.execute('INSERT INTO reminder_events VALUES(?,?,?)',(i['id'],stage,mid));result.append(mid)
 return result

def checks(c):
 tests=[('Invoice totals equal line calculations','SELECT COUNT(*) FROM invoices WHERE subtotal-discount+tax<>total'),('No duplicate subscription-period invoices','SELECT COUNT(*) FROM (SELECT 1 FROM invoices GROUP BY subscription_id,period HAVING COUNT(*)>1)'),('No invoice overallocated','SELECT COUNT(*) FROM invoices WHERE total<COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0)'),('No bank transaction overallocated','SELECT COUNT(*) FROM bank WHERE amount<COALESCE((SELECT SUM(amount) FROM allocations WHERE bank_id=bank.id),0)'),('Discount usage matches committed applications','SELECT COUNT(*) FROM discount_rules d WHERE used<>(SELECT COUNT(*) FROM discount_applications WHERE discount_id=d.id)'),('No discount exceeds its usage limit','SELECT COUNT(*) FROM discount_rules WHERE used>limit_uses'),('Invoice totals match expected snapshots','SELECT COUNT(*) FROM invoices WHERE total<>expected')]
 out=[{'name':n,'passed':(nerr:=c.execute(sql).fetchone()[0])==0,'failures':nerr} for n,sql in tests]
 line_errors=0
 for i in rows(c,'SELECT subtotal,discount,tax,total,lines FROM invoices WHERE lines IS NOT NULL'):
  ls=json.loads(i['lines'])
  if any(sum(l[k] for l in ls)!=i[k] for k in ['subtotal','discount','tax','total']):line_errors+=1
 out.append({'name':'Invoice line sums match stored totals','passed':line_errors==0,'failures':line_errors})
 last=c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
 if last:
  n=c.execute('SELECT COUNT(*) FROM run_items WHERE run_id=? AND invoice_id IS NULL AND COALESCE(reason,\'\')=\'\'',(last['id'],)).fetchone()[0]
  out.append({'name':'Latest run: every considered item has an invoice or skip reason','passed':n==0,'failures':n})
 return out
