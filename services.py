import json,datetime as dt,hashlib,csv,io
from decimal import Decimal, ROUND_HALF_UP
import domain as d
import legacy as db

def line_values(c,raw,plan=None):
 if not raw or len(raw)>30:raise d.Error('Add 1 to 30 product lines')
 out=[]
 for l in raw:
  p=d.one(c,'SELECT * FROM products WHERE id=? AND active=1',(d.integer(l['product_id'],1),));v=d.integer(l.get('variant_id') or 0);desc=p['name'];price=plan['price'] if plan and len(out)==0 else p['sales_price']
  if v:
   variant=d.one(c,'SELECT * FROM variants WHERE id=? AND product_id=?',(v,p['id']));desc+=' / '+variant['name'];price+=variant['extra']
  tax=d.one(c,'SELECT * FROM taxes WHERE id=? AND active=1',(d.integer(l['tax_id'],1),))
  out.append((p['id'],v or None,desc,d.integer(l['qty'],1,100000),price,tax['rate']))
 return out

def catalog(c,path,v,user):
 table={'discounts':'discount_rules','staff':'users'}.get(path,path)
 if v is None:return d.rows(c,"SELECT id,name,email,role FROM users WHERE role='staff'" if path=='staff' else 'SELECT * FROM '+table+' ORDER BY id DESC')
 if user['role']!='admin':raise PermissionError('Only an admin can change configuration')
 if path=='staff':return {'id':d.new_user(c,v,'staff')}
 identifier=d.integer(v.get('id') or 0)
 if path=='products':
  if v['type'] not in ['Service','Software','Physical']:raise d.Error('Invalid product type')
  values={'name':d.text(v['name']),'type':v['type'],'sales_price':d.integer(v['sales_price']),'cost_price':d.integer(v['cost_price']),'notes':str(v.get('notes',''))[:2000],'active':int(bool(v.get('active',True)))}
 elif path=='variants':
  pid=d.integer(v['product_id'],1);d.one(c,'SELECT id FROM products WHERE id=?',(pid,));values={'product_id':pid,'name':d.text(v['name']),'extra':d.integer(v['extra'])}
 elif path=='taxes':values={'name':d.text(v['name']),'rate':d.integer(v['rate'],0,10000),'active':int(bool(v.get('active',True)))}
 elif path=='plans':
  if v['cycle'] not in ['daily','weekly','monthly','yearly']:raise d.Error('Invalid billing cycle')
  start=d.date(v.get('available_from') or '2020-01-01');end=d.date(v['available_to']) if v.get('available_to') else None
  if end and end<start:raise d.Error('Availability end precedes start')
  values={'name':d.text(v['name']),'price':d.integer(v.get('price',0)),'cycle':v['cycle'],'tax':d.integer(v.get('tax',0),0,10000),'min_qty':d.integer(v.get('min_qty',1),1),'available_from':start,'available_to':end,**{k:int(bool(v.get(k))) for k in ['allow_pause','allow_close','allow_renew','auto_close']}}
 elif path=='discounts':
  if v['kind'] not in ['fixed','percent']:raise d.Error('Invalid discount type')
  start=d.date(v['start']);end=d.date(v['end']);pid=d.integer(v.get('product_id') or 0)
  if end<start:raise d.Error('Discount end precedes start')
  if pid:d.one(c,'SELECT id FROM products WHERE id=?',(pid,))
  used=d.one(c,'SELECT used FROM discount_rules WHERE id=?',(identifier,))['used'] if identifier else 0
  values={'name':d.text(v['name']),'kind':v['kind'],'value':d.integer(v['value'],0,10000 if v['kind']=='percent' else 100000000000),'min_qty':d.integer(v.get('min_qty',1),1),'min_purchase':d.integer(v.get('min_purchase',0)),'start':start,'end':end,'limit_uses':d.integer(v['limit_uses'],used),'product_id':pid or None,'active':int(bool(v.get('active',True)))}
 elif path=='templates':
  pid=d.integer(v['plan_id'],1);d.one(c,'SELECT id FROM plans WHERE id=?',(pid,));line_values(c,v['lines']);values={'name':d.text(v['name']),'plan_id':pid,'valid_days':d.integer(v['valid_days'],1,365),'lines':json.dumps(v['lines'])}
 else:raise d.Error('Unknown catalog')
 if identifier:
  d.one(c,'SELECT id FROM '+table+' WHERE id=?',(identifier,));c.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in values)+' WHERE id=?',list(values.values())+[identifier])
 else:identifier=c.execute('INSERT INTO '+table+'('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',list(values.values())).lastrowid
 d.audit(c,f'Saved {path} #{identifier}',user['email']);d.bump(c);return {'id':identifier}

def subscription_create(c,v,user):
 template=None
 if d.integer(v.get('template_id') or 0):
  template=d.one(c,'SELECT * FROM templates WHERE id=?',(d.integer(v['template_id'],1),));v={**v,'plan_id':template['plan_id'],'lines':json.loads(template['lines'])}
 p=d.one(c,'SELECT * FROM plans WHERE id=?',(d.integer(v['plan_id'],1),));start=d.date(v['start_date']);expiry=d.date(v['expiry']) if v.get('expiry') else None
 if start<p['available_from'] or p['available_to'] and start>p['available_to']:raise d.Error('Plan unavailable on start date')
 if expiry and expiry<start:raise d.Error('Expiry precedes start')
 lines=line_values(c,v['lines'],p);qty=sum(l[3] for l in lines)
 if qty<p['min_qty']:raise d.Error('Quantity is below plan minimum')
 did=d.integer(v.get('discount_id') or 0)
 if did:d.one(c,'SELECT id FROM discount_rules WHERE id=?',(did,))
 until=str(dt.date.fromisoformat(d.today(c))+dt.timedelta(days=template['valid_days'] if template else d.integer(v.get('valid_days',14),1,365)))
 sid=c.execute('INSERT INTO subscriptions(customer,email,plan_id,qty,state,due,start_date,expiry,terms_days,quotation_until,discount_id,anchor_day) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(d.text(v['customer']),d.email(v['email']),p['id'],qty,'Draft',start,start,expiry,d.integer(v.get('terms_days',15),0,365),until,did or None,int(start[-2:]))).lastrowid
 c.executemany('INSERT INTO subscription_lines(subscription_id,product_id,variant_id,description,qty,unit_price,tax_rate) VALUES(?,?,?,?,?,?,?)',[(sid,*l) for l in lines]);d.audit(c,f'Created SUB-{sid}',user['email']);d.bump(c);return {'id':sid}

def subscription_edit(c,v,user):
 s=d.one(c,'SELECT * FROM subscriptions WHERE id=?',(d.integer(v['id'],1),));p=d.one(c,'SELECT * FROM plans WHERE id=?',(s['plan_id'],));old=d.mrr(c,s);lines=line_values(c,v['lines'],p);qty=sum(l[3] for l in lines)
 if qty<p['min_qty']:raise d.Error('Quantity is below plan minimum')
 did=d.integer(v.get('discount_id') or 0)
 if did:d.one(c,'SELECT id FROM discount_rules WHERE id=?',(did,))
 expiry=d.date(v['expiry']) if v.get('expiry') else None
 if expiry and expiry<s['start_date']:raise d.Error('Expiry precedes start')
 c.execute('DELETE FROM subscription_lines WHERE subscription_id=?',(s['id'],));c.executemany('INSERT INTO subscription_lines(subscription_id,product_id,variant_id,description,qty,unit_price,tax_rate) VALUES(?,?,?,?,?,?,?)',[(s['id'],*l) for l in lines]);c.execute('UPDATE subscriptions SET qty=?,discount_id=?,expiry=?,terms_days=?,quotation_until=? WHERE id=?',(qty,did or None,expiry,d.integer(v.get('terms_days',15),0,365),d.date(v['quotation_until']),s['id']))
 if s['state']=='Active':
  delta=d.mrr(c,s)-old
  if delta:d.movement(c,s,'expansion' if delta>0 else 'contraction',delta)
 d.audit(c,f'Updated future lines of SUB-{s["id"]}; invoice snapshots unchanged',user['email']);d.bump(c);return {}

def transition(c,v,user):
 s=d.one(c,'SELECT s.*,p.cycle,p.allow_pause,p.allow_close,p.allow_renew FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.id=?',(d.integer(v['id'],1),));state=v['state']
 if user['role']=='customer' and s['email']!=user['email']:raise PermissionError('This subscription belongs to another customer')
 allowed={'Draft':['Quotation'],'Quotation':['Confirmed'],'Confirmed':['Active'],'Active':['Paused','Closed'],'Paused':['Active','Closed'],'Closed':['Active']}
 if state not in allowed.get(s['state'],[]):raise d.Error('Invalid subscription transition')
 if user['role']=='customer' and s['state'] in ['Draft','Quotation','Confirmed']:raise PermissionError('Staff approval required')
 for condition,flag,message in [(state=='Paused','allow_pause','Pausing'),(state=='Closed','allow_close','Early closing'),(s['state']=='Closed','allow_renew','Renewal')]:
  if condition and not s[flag]:raise d.Error(message+' is not permitted by this plan')
 if state=='Confirmed' and s['quotation_until'] and s['quotation_until']<d.today(c):raise d.Error('Quotation expired; extend validity before confirming')
 if state=='Active' and s['expiry'] and s['expiry']<d.today(c):
  expiry=d.date(v.get('expiry',''))
  if expiry<=d.today(c):raise d.Error('Renewal requires a future expiry')
  c.execute('UPDATE subscriptions SET expiry=? WHERE id=?',(expiry,s['id']))
 if s['state']=='Active':d.movement(c,s,'churn' if state=='Closed' else 'contraction',-d.mrr(c,s))
 if state=='Active':
  d.movement(c,s,'new' if s['state']=='Confirmed' else 'expansion',d.mrr(c,s))
  if s['state'] in ['Paused','Closed']:c.execute('UPDATE subscriptions SET due=?,anchor_day=? WHERE id=?',(d.today(c),int(d.today(c)[-2:]),s['id']))
 c.execute('UPDATE subscriptions SET state=? WHERE id=?',(state,s['id']));d.audit(c,f'SUB-{s["id"]}: {s["state"]} to {state}',user['email']);d.bump(c);return {}

def paginate(result,q):
 total=len(result);page=min(max(1,int(q.get('page',1))),max(1,(total+29)//30));return {'rows':result[(page-1)*30:page*30],'total':total,'page':page}

def dashboard(c,user,q):
 scope=' AND email=?' if user['role']=='customer' else '';args=[user['email']] if scope else [];customer_scope=bool(scope);query=q.get('q','').strip();
 if query:scope+=' AND customer LIKE ?';args.append('%'+query+'%')
 start=d.date(q.get('from') or '2026-10-01');end=d.date(q.get('to') or d.today(c))
 if start>end:raise d.Error('Start date must precede end date')
 invoices=d.rows(c,'SELECT *,total-COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0) balance FROM invoices WHERE 1=1'+scope,args);issued=[i for i in invoices if i['state'] in ['Confirmed','Paid']];period=[i for i in issued if start<=i['period']<=end]
 as_of=dt.date.fromisoformat(d.today(c))
 aging={'Not due':0,'1-30 days':0,'31-60 days':0,'61-90 days':0,'90+ days':0};chase=[]
 for i in issued:
  if i['balance']<=0:continue
  days=(as_of-dt.date.fromisoformat(i['due_date'])).days;key='Not due' if days<=0 else '1-30 days' if days<=30 else '31-60 days' if days<=60 else '61-90 days' if days<=90 else '90+ days';aging[key]+=i['balance']
  if days>0 and not i['disputed']:chase.append({**i,'days':days,'score':min(days,90)*2+min(i['balance']//10000,100)})
 move_scope=(' AND email=?' if customer_scope else '')+(' AND subscription_id IN (SELECT id FROM subscriptions WHERE customer LIKE ?)' if query else '');moves=d.rows(c,'SELECT * FROM movements WHERE date<=?'+move_scope,[end]+args);opening=sum(m['amount'] for m in moves if m['date']<start);flows={k:sum(m['amount'] for m in moves if start<=m['date']<=end and m['kind']==k) for k in ['opening','new','expansion','contraction','churn']};closing=opening+sum(flows.values())
 collected=c.execute('SELECT COALESCE(SUM(a.amount),0) FROM allocations a JOIN bank b ON b.id=a.bank_id JOIN invoices i ON i.id=a.invoice_id WHERE b.date BETWEEN ? AND ?'+(' AND i.email=?' if customer_scope else '')+(' AND i.customer LIKE ?' if query else ''),[start,end]+args).fetchone()[0]
 subs=d.rows(c,"SELECT s.*,p.cycle FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE state='Active'"+scope,args);line_totals={x['subscription_id']:x['value'] for x in d.rows(c,'SELECT subscription_id,SUM(qty*unit_price) value FROM subscription_lines GROUP BY subscription_id')};mrr=sum(int((Decimal(line_totals.get(x['id'],0))*{'daily':Decimal(365)/12,'weekly':Decimal(52)/12,'monthly':1,'yearly':Decimal(1)/12}[x['cycle']]).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for x in subs)
 return {'mrr':mrr,'arr':mrr*12,'active':len(subs),'invoiced':sum(i['total'] for i in period),'received':collected,'outstanding':sum(i['balance'] for i in issued),'drafts':sum(i['total'] for i in invoices if i['state']=='Draft'),'aging':aging,'waterfall':{'opening':opening,'baseline':flows['opening'],'new':flows['new'],'expansion':flows['expansion'],'contraction':flows['contraction'],'churn':flows['churn'],'closing':closing},'chase':sorted(chase,key=lambda x:-x['score'])[:15],'from':start,'to':end}

def reconcile(c,q):
 result=[];on=d.today(c)
 for i in d.rehearsal(c)['items']:result.append({'key':'due-'+str(i['id'])+'-'+i['period'],'subscription_id':i['id'],'customer':i['customer'],'period':i['period'],'expected':i['total'],'invoiced':0,'received':0,'status':'Due, not invoiced','action':'bill-one','id':i['id']})
 for i in d.rows(c,'SELECT *,COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0) paid FROM invoices'):
  status='Cancelled' if i['state']=='Cancelled' else 'Draft' if i['state']=='Draft' else 'Amount mismatch' if i['total']!=i['expected'] or i['paid']>i['total'] else 'Paid' if i['paid']==i['total'] else 'Partially paid' if i['paid'] else 'Overdue' if i['due_date']<on else 'Unpaid'
  result.append({'key':'invoice-'+str(i['id']),'subscription_id':i['subscription_id'],'customer':i['customer'],'period':i['period'],'expected':i['expected'],'invoiced':i['total'],'received':i['paid'],'status':status,'action':'invoice','id':i['id']})
 for b in d.rows(c,'SELECT *,amount-COALESCE((SELECT SUM(amount) FROM allocations WHERE bank_id=bank.id),0) available FROM bank'):
  if b['available']>0:result.append({'key':'bank-'+str(b['id']),'customer':b['customer'],'period':b['date'],'expected':None,'invoiced':None,'received':b['available'],'status':'Unmatched bank entry','action':'bank','id':b['id']})
 query=q.get('q','').casefold();status=q.get('status','');start=q.get('from','');end=q.get('to','');result=[r for r in result if query in r['customer'].casefold() and (not status or r['status']==status) and (not start or r['period']>=start) and (not end or r['period']<=end)];result.sort(key=lambda r:(r['period'],r['key']),reverse=True);return paginate(result,q)
def handle(c,path,v,user,q):
 role=user['role'];customer=role=='customer';admin=role=='admin';mutation=v is not None
 if customer and path not in ['me','logout','dashboard','subscriptions','subscription','transition','invoices','invoice','payments']:raise PermissionError('Staff access required')
 if path in ['staff','mailbox-all','automation'] and not admin:raise PermissionError('Admin access required')
 if path in ['products','variants','taxes','plans','discounts','templates','staff']:return catalog(c,path,v,user)
 if path=='me':return {'name':user['name'],'email':user['email'],'role':role,'clock':d.today(c),'mail_mode':__import__('delivery').mode(),'clock_mode':d.one(c,"SELECT value FROM settings WHERE key='clock_mode'")['value']}
 if path=='dashboard':return dashboard(c,user,q)
 if path=='subscription':
  sub=d.one(c,'SELECT * FROM subscriptions WHERE id=?',(d.integer(q['id'],1),))
  if customer and sub['email']!=user['email']:raise PermissionError('Access denied')
  a=d.quote(c,sub,sub['due']);return {**sub,'plan_options':d.one(c,'SELECT allow_pause,allow_close,allow_renew FROM plans WHERE id=?',(sub['plan_id'],)),'lines':a['lines'],'calculation':{k:a[k] for k in ['subtotal','discount','tax','total']},'plan_name':d.one(c,'SELECT name FROM plans WHERE id=?',(sub['plan_id'],))['name']}
 if path=='subscriptions' and mutation:
  if customer:raise PermissionError('Staff access required')
  return subscription_edit(c,v,user) if v.get('id') else subscription_create(c,v,user)
 if path=='transition':return transition(c,v,user)
 if path=='invoice':
  i=d.invoice(c,d.integer(v['id'] if mutation else q['id'],1),user)
  if not mutation:return i
  if customer:raise PermissionError('Staff access required')
  action=v['action']
  if action=='confirm':
   if i['state']!='Draft':raise d.Error('Only draft invoices can be confirmed')
   c.execute('UPDATE invoices SET state=? WHERE id=?',('Paid' if i['total']==0 else 'Confirmed',i['id']))
  elif action=='cancel':
   if i['paid'] or i['state']=='Cancelled':raise d.Error('Paid or cancelled invoices cannot be cancelled')
   c.execute("UPDATE invoices SET state='Cancelled' WHERE id=?",(i['id'],))
  elif action=='dispute':c.execute('UPDATE invoices SET disputed=? WHERE id=?',(int(not i['disputed']),i['id']))
  elif action=='send':
   if i['state'] not in ['Confirmed','Paid']:raise d.Error('Confirm invoice before sending')
   d.mail(c,i['email'],f'Brightloop invoice INV-{i["id"]}',f'Invoice INV-{i["id"]}\nCustomer: {i["customer"]}\nTotal INR {i["total"]/100:.2f}\nBalance INR {i["balance"]/100:.2f}\nDue {i["due_date"]}\nView and print in your customer portal.',invoice_id=i['id'])
  elif action=='remind':return {'queued':len(d.chase(c,i['id']))}
  else:raise d.Error('Invalid invoice action')
  d.audit(c,f'Invoice {i["id"]}: {action}',user['email']);d.bump(c);return {}
 if path in ['subscriptions','invoices']:
  where=' WHERE customer LIKE ?';args=['%'+q.get('q','')+'%']
  if customer:where+=' AND email=?';args.append(user['email'])
  if q.get('status'):where+=' AND state=?';args.append(q['status'])
  col='due' if path=='subscriptions' else 'period'
  for key,op in [('from','>='),('to','<=')]:
   if q.get(key):where+=f' AND {col}{op}?';args.append(d.date(q[key]))
  count=c.execute('SELECT COUNT(*) FROM '+path+where,args).fetchone()[0];page=min(max(1,int(q.get('page',1))),max(1,(count+29)//30));select='SELECT *' if path=='subscriptions' else 'SELECT *,COALESCE((SELECT SUM(amount) FROM allocations WHERE invoice_id=invoices.id),0) paid'
  return {'rows':d.rows(c,select+' FROM '+path+where+' ORDER BY id DESC LIMIT 30 OFFSET ?',args+[(page-1)*30]),'total':count,'page':page}
 if path=='automation':
  if mutation:c.execute("INSERT OR REPLACE INTO settings VALUES('auto_billing',?)",('1' if v.get('enabled') else '0',))
  return {'enabled':bool(c.execute("SELECT 1 FROM settings WHERE key='auto_billing' AND value='1'").fetchone()),'clock_mode':d.one(c,"SELECT value FROM settings WHERE key='clock_mode'")['value']}
 if path=='clock':
  if not admin:raise PermissionError('Admin access required')
  mode=v.get('mode','demo')
  if mode not in ['demo','live']:raise d.Error('Choose demo or live clock')
  if mode=='demo':c.execute("UPDATE settings SET value=? WHERE key='clock'",(d.date(v['date']),))
  c.execute("UPDATE settings SET value=? WHERE key='clock_mode'",(mode,));d.bump(c);return {'queued':len(d.chase(c))}
 if path=='preview':
  p=d.rehearsal(c);return {k:val for k,val in p.items() if k not in ['items','skips']}|{'rows':p['items'][:30],'skips':p['skips'][:30],'skip_count':len(p['skips']),'checks':d.checks(c)}
 if path=='bill':
  if any(not x['passed'] for x in d.checks(c)):raise d.Error('Resolve failed ledger checks before billing')
  return d.billing(c,v.get('revision'),d.integer(v['id'],1) if v.get('id') else None)
 if path=='checks':return {'checks':d.checks(c),'runs':d.rows(c,'SELECT * FROM runs ORDER BY id DESC LIMIT 10'),'audit':d.rows(c,'SELECT * FROM audit ORDER BY id DESC LIMIT 50')}
 if path=='reconcile':return reconcile(c,q)
 if path=='import':
  reader=csv.DictReader(io.StringIO(v['csv'].lstrip('\ufeff')))
  if not {'reference','customer','amount','date'}.issubset(reader.fieldnames or []):raise d.Error('CSV requires reference, customer, amount and date columns')
  count=0;duplicates=0
  for idx,r in enumerate(reader):
   if idx>=10000:raise d.Error('Import at most 10,000 rows')
   ref=d.text(r['reference']);name=d.text(r['customer']);amount=d.money(r['amount']);date=d.date(r['date']);method=r.get('method') or 'NEFT'
   if amount<=0:raise d.Error('Transaction amount must be greater than zero')
   fingerprint=hashlib.sha256(json.dumps([ref.casefold(),date,amount,name.casefold()]).encode()).hexdigest();n=c.execute('INSERT OR IGNORE INTO bank(fingerprint,reference,customer,amount,date,method,note) VALUES(?,?,?,?,?,?,?)',(fingerprint,ref,name,amount,date,method,str(r.get('note',''))[:500])).rowcount;count+=n;duplicates+=1-n
  d.audit(c,f'Imported {count} transactions; {duplicates} duplicates',user['email']);d.bump(c);return {'imported':count,'duplicates':duplicates}
 if path=='bank':
  result=paginate(d.rows(c,'SELECT *,amount-COALESCE((SELECT SUM(amount) FROM allocations WHERE bank_id=bank.id),0) available FROM bank WHERE available>0 AND customer LIKE ? ORDER BY id DESC',('%'+q.get('q','')+'%',)),q)
  for b in result['rows']:b['suggestions']=d.candidates(c,b)
  return result
 if path=='allocate':d.allocate(c,d.integer(v['bank_id'],1),d.integer(v['invoice_id'],1),v['amount']);return {}
 if path=='payments':
  where=' WHERE b.customer LIKE ?';args=['%'+q.get('q','')+'%']
  if customer:where+=' AND EXISTS(SELECT 1 FROM allocations a JOIN invoices i ON i.id=a.invoice_id WHERE a.bank_id=b.id AND i.email=?)';args.append(user['email'])
  if q.get('method'):where+=' AND b.method=?';args.append(q['method'])
  for key,op in [('from','>='),('to','<=')]:
   if q.get(key):where+=f' AND b.date{op}?';args.append(d.date(q[key]))
  count=c.execute('SELECT COUNT(*) FROM bank b'+where,args).fetchone()[0];page=min(max(1,int(q.get('page',1))),max(1,(count+29)//30))
  records=d.rows(c,'SELECT b.* FROM bank b'+where+' ORDER BY b.id DESC LIMIT 30 OFFSET ?',args+[(page-1)*30])
  for b in records:
   alloc=d.rows(c,'SELECT a.invoice_id,a.amount,i.customer,i.email FROM allocations a JOIN invoices i ON i.id=a.invoice_id WHERE bank_id=?'+(' AND i.email=?' if customer else ''),[b['id']]+([user['email']] if customer else []))
   b['allocations']=alloc
   if customer:
    b['amount']=sum(a['amount'] for a in alloc);b['customer']=user.get('name',user['email']);b['reference']='Payment #'+str(b['id']);b['note']='';b['available']=None
   else:b['available']=b['amount']-sum(a['amount'] for a in alloc)
  return {'rows':records,'total':count,'page':page}
 if path=='payment':
  iid=d.integer(v['invoice_id'],1);i=d.invoice(c,iid);amount=d.integer(v['amount'],1);ref=d.text(v['reference']);date=d.date(v['date']);method=v['method']
  if method not in ['UPI','NEFT','Card','Cash','Cheque','Other']:raise d.Error('Invalid payment method')
  fingerprint=hashlib.sha256(json.dumps(['manual',ref.casefold(),date,amount]).encode()).hexdigest()
  if c.execute('SELECT 1 FROM bank WHERE fingerprint=?',(fingerprint,)).fetchone():raise d.Error('Payment already recorded')
  bid=c.execute('INSERT INTO bank(fingerprint,reference,customer,amount,date,method,note) VALUES(?,?,?,?,?,?,?)',(fingerprint,ref,i['customer'],amount,date,method,str(v.get('note',''))[:500])).lastrowid;d.allocate(c,bid,iid,amount);return {'id':bid}
 if path=='recovery':
  if mutation:return {'queued':len(d.chase(c))}
  return {'rows':dashboard(c,user,{})['chase'],'events':d.rows(c,'SELECT r.*,o.recipient,o.status FROM reminder_events r JOIN outbox o ON o.id=r.mail_id ORDER BY mail_id DESC LIMIT 30')}
 if path=='mailbox-all':
  where=" WHERE kind<>'reset'" if path=='mailbox-all' else ' WHERE recipient=?';args=[] if path=='mailbox-all' else [user['email']];return paginate(d.rows(c,'SELECT id,recipient,subject,kind,created,status FROM outbox'+where+' ORDER BY id DESC',args),q)
 raise d.Error('Unknown endpoint')
