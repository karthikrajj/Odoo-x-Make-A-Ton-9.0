"""Send one connection-check email to the configured sender, without exposing credentials."""
import os,json
from pathlib import Path
import delivery,domain as d,legacy as db

def main():
 delivery.load_config()
 if not delivery.configured():raise SystemExit('Gmail setup is incomplete.')
 recipient=os.environ['SMTP_FROM'];subject='RenewSure email connection test'
 with db.conn() as c:
  previous=c.execute("SELECT id,status FROM outbox WHERE recipient=? AND subject=? AND status IN ('Sent','Sending','Delivery needs review') ORDER BY id DESC LIMIT 1",(recipient,subject)).fetchone()
  if previous:mid=previous['id']
  else:mid=d.mail(c,recipient,subject,'Your RenewSure application successfully connected to Gmail.\n\nPassword reset links, invoices and reminders can now be sent using this account.\nThis is a connection test, not a charge or invoice.','connection-test')
 delivery.deliver_pending()
 with db.conn() as c:status=c.execute('SELECT status FROM outbox WHERE id=?',(mid,)).fetchone()[0]
 result={'message_id':mid,'status':status,'smtp_accepted':status=='Sent','inbox_receipt_confirmed':False}
 Path('email-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result))
if __name__=='__main__':main()
