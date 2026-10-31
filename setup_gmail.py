"""Interactive Gmail setup. Credentials are entered locally and never printed."""
import getpass, os, ssl, smtplib
from pathlib import Path
from urllib.parse import urlparse

def main():
 print('Connect RenewSure to Gmail. Enable Google 2-Step Verification and create an app password first.')
 print('Google help: https://support.google.com/accounts/answer/185833')
 print('Enter the app password here, never your normal Gmail password or a chat message.')
 default_sender='karthikrajnavodayam@gmail.com'
 sender=(input(f'Sending Gmail address [{default_sender}]: ').strip() or default_sender).lower()
 if '@' not in sender or any(c in sender for c in '\r\n'):raise SystemExit('Enter a valid email address.')
 secret=getpass.getpass('Gmail app password (hidden): ').replace(' ','')
 if len(secret)!=16 or not secret.isalpha():raise SystemExit('A Google app password has 16 letters. Setup was not saved.')
 base=input('Application URL [http://127.0.0.1:8766]: ').strip() or 'http://127.0.0.1:8766'
 parsed=urlparse(base)
 if parsed.scheme not in ['http','https'] or not parsed.netloc or any(c in base for c in '\r\n'):raise SystemExit('Enter a valid application URL.')
 print('Checking encrypted Gmail authentication. No email is sent by this setup check.')
 try:
  with smtplib.SMTP('smtp.gmail.com',587,timeout=20) as smtp:
   smtp.starttls(context=ssl.create_default_context());smtp.login(sender,secret)
 except smtplib.SMTPAuthenticationError:raise SystemExit('Gmail rejected the app password. Check 2-Step Verification and generate a new app password.')
 except (OSError,smtplib.SMTPException):raise SystemExit('Cannot connect to Gmail. Check internet access and try again.')
 path=Path(__file__).resolve().parent/'.env'
 # Preserve unrelated existing settings, replace only the Gmail connection keys.
 settings={}
 if path.exists():
  for line in path.read_text(encoding='utf-8-sig').splitlines():
   if '=' in line and not line.startswith('#'):
    k,v=line.split('=',1);settings[k.strip()]=v.strip()
 settings.update(SMTP_HOST='smtp.gmail.com',SMTP_PORT='587',SMTP_SECURITY='starttls',SMTP_USER=sender,SMTP_PASSWORD=secret,SMTP_FROM=sender,RENEWSURE_BASE_URL=base.rstrip('/'))
 temporary=path.with_suffix('.env.tmp');temporary.write_text('\n'.join(k+'='+v for k,v in settings.items())+'\n',encoding='utf-8');os.replace(temporary,path)
 print('Gmail authentication succeeded. Configuration saved locally. Restart RenewSure to enable delivery.')
 print('Use Forgot password with a real registered address to verify inbox receipt.')
if __name__=='__main__':
 try:main()
 except KeyboardInterrupt:print('\nSetup cancelled; existing configuration preserved.')
