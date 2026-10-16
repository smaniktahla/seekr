"""Low-priority background ingestion, automatically resumed after container restart."""
import subprocess,time,os,json
from core import init,connect
os.nice(10)
init()
while True:
    try:
        with connect() as db:
            r=db.execute("SELECT value FROM jobs WHERE key='inventory'").fetchone()
        last=json.loads(r[0]).get('finished',0) if r else 0
        if time.time()-last>6*3600:
            subprocess.run(['python','/app/indexer.py','inventory'],check=True)
        subprocess.run(['python','/app/indexer.py','extract','--limit','250'],check=True)
        subprocess.run(['python','/app/indexer.py','embed','--limit','25'],check=True)
    except Exception as e: print('Worker error: '+str(e),flush=True)
    time.sleep(30)
