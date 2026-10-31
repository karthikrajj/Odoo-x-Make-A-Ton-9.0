"""Create a fresh, separately named demo database without replacing existing data."""
import datetime,os
from pathlib import Path
import legacy as db
import server
name='demo-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.db'
path=Path(__file__).resolve().parent/name
if path.exists():raise SystemExit('Choose a new timestamp; existing file preserved.')
db.DB=str(path);server.initialize()
launcher=path.with_suffix('.cmd')
launcher.write_text('@echo off\ncd /d "%~dp0"\nset "RENEWSURE_DB='+str(path)+'"\nset "PORT=8767"\npython server.py\npause\n',encoding='utf-8')
print('Created isolated demo: '+str(path))
print('Start with '+str(launcher)+' then visit http://127.0.0.1:8767')
