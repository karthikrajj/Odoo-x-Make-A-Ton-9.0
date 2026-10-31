from pathlib import Path
p=Path('domain.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("def today(c): return c.execute(\"SELECT value FROM settings WHERE key='clock'\").fetchone()[0]",'''def today(c):
 mode=c.execute("SELECT value FROM settings WHERE key='clock_mode'").fetchone()
 if mode and mode[0]=='live':return str(dt.datetime.now(dt.timezone(dt.timedelta(hours=5,minutes=30))).date())
 return c.execute("SELECT value FROM settings WHERE key='clock'").fetchone()[0]''')
s=s.replace("c.execute(\"INSERT OR IGNORE INTO settings VALUES('revision','1')\")",'''c.execute("INSERT OR IGNORE INTO settings VALUES('revision','1')")
  c.execute("INSERT OR IGNORE INTO settings VALUES('clock_mode','demo')")
  c.execute("INSERT OR IGNORE INTO settings VALUES('auto_billing','0')")
  c.execute('CREATE INDEX IF NOT EXISTS ix_bank_date ON bank(date)')
  c.execute('CREATE INDEX IF NOT EXISTS ix_sub_email ON subscriptions(email)')
  c.execute('CREATE INDEX IF NOT EXISTS ix_outbox_recipient ON outbox(recipient,id)')''')
s=s.replace("def quote(c,s,period,used=None,legacy_used=None):\n lines=rows(c,'SELECT * FROM subscription_lines WHERE subscription_id=? ORDER BY id',(s['id'],));", "def quote(c,s,period,used=None,legacy_used=None,line_cache=None,rule_cache=None):\n lines=line_cache.get(s['id'],[]) if line_cache is not None else rows(c,'SELECT * FROM subscription_lines WHERE subscription_id=? ORDER BY id',(s['id'],));")
s=s.replace("rule=one(c,'SELECT * FROM discount_rules WHERE id=?',(s['discount_id'],));", "rule=rule_cache[s['discount_id']] if rule_cache is not None else one(c,'SELECT * FROM discount_rules WHERE id=?',(s['discount_id'],));")
s=s.replace("exists={(r['subscription_id']", "line_cache={}\n for l in rows(c,'SELECT * FROM subscription_lines ORDER BY id'):line_cache.setdefault(l['subscription_id'],[]).append(l)\n rule_cache={r['id']:r for r in rows(c,'SELECT * FROM discount_rules')}\n exists={(r['subscription_id']")
s=s.replace("a=quote(c,s,period,used,legacy_count)","a=quote(c,s,period,used,legacy_count,line_cache,rule_cache)")
s=s.replace("one(c,'SELECT used FROM discount_rules WHERE id=?',(a['discount_id'],))['used']", "rule_cache[a['discount_id']]['used']")
p.write_text(s,encoding='utf-8')
p=Path('services.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("'invoices','invoice','mailbox']", "'invoices','invoice','mailbox','payments']")
s=s.replace("'mail_mode':'Local demo mailbox'", "'mail_mode':__import__('delivery').mode(),'clock_mode':d.one(c,\"SELECT value FROM settings WHERE key='clock_mode'\")['value']")
s=s.replace("return {**sub,'lines':d.rows(c,'SELECT * FROM subscription_lines WHERE subscription_id=?',(sub['id'],))}", "a=d.quote(c,sub,sub['due']);return {**sub,'lines':a['lines'],'calculation':{k:a[k] for k in ['subtotal','discount','tax','total']},'plan_name':d.one(c,'SELECT name FROM plans WHERE id=?',(sub['plan_id'],))['name']}")
s=s.replace("return {'enabled':bool(c.execute(\"SELECT 1 FROM settings WHERE key='auto_billing' AND value='1'\").fetchone())}", "return {'enabled':bool(c.execute(\"SELECT 1 FROM settings WHERE key='auto_billing' AND value='1'\").fetchone()),'clock_mode':d.one(c,\"SELECT value FROM settings WHERE key='clock_mode'\")['value']}")
s=s.replace("c.execute(\"UPDATE settings SET value=? WHERE key='clock'\",(d.date(v['date']),));d.bump(c);return", "mode=v.get('mode','demo')\n  if mode not in ['demo','live']:raise d.Error('Choose demo or live clock')\n  if mode=='demo':c.execute(\"UPDATE settings SET value=? WHERE key='clock'\",(d.date(v['date']),))\n  c.execute(\"UPDATE settings SET value=? WHERE key='clock_mode'\",(mode,));d.bump(c);return")
needle=" if path=='payment':"
insert=''' if path=='payments':
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
    b['amount']=sum(a['amount'] for a in alloc);b['customer']=user['name'];b['reference']='Payment #'+str(b['id']);b['note']='';b['available']=None
   else:b['available']=b['amount']-sum(a['amount'] for a in alloc)
  return {'rows':records,'total':count,'page':page}
'''
s=s.replace(needle,insert+needle)
# Avoid thousands of per-contract SQL requests in dashboard.
s=s.replace("mrr=sum(d.mrr(c,x) for x in subs)","line_totals={x['subscription_id']:x['value'] for x in d.rows(c,'SELECT subscription_id,SUM(qty*unit_price) value FROM subscription_lines GROUP BY subscription_id')};mrr=sum(int((__import__('decimal').Decimal(line_totals.get(x['id'],0))*{'daily':__import__('decimal').Decimal(365)/12,'weekly':__import__('decimal').Decimal(52)/12,'monthly':1,'yearly':__import__('decimal').Decimal(1)/12}[x['cycle']]).quantize(__import__('decimal').Decimal('1'),rounding=__import__('decimal').ROUND_HALF_UP)) for x in subs)")
p.write_text(s,encoding='utf-8')
