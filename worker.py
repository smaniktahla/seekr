"""Low-priority background ingestion, automatically resumed after container restart."""
import subprocess,time,os,json,sys
from pathlib import Path
from core import init,connect
if hasattr(os,'nice'):os.nice(10)
script=str(Path(__file__).with_name('indexer.py'))
init()
while True:
    try:
        with connect() as db:
            r=db.execute("SELECT value FROM jobs WHERE key='inventory'").fetchone()
        last=json.loads(r[0]).get('finished',0) if r else 0
        with connect() as db:
            requested=db.execute("SELECT value FROM jobs WHERE key='scan_requested'").fetchone()
        if time.time()-last>6*3600 or (requested and json.loads(requested[0])>last):
            subprocess.run([sys.executable,script,'inventory'],check=True)
        subprocess.run([sys.executable,script,'extract','--limit','250'],check=True)
        subprocess.run([sys.executable,script,'embed','--limit','25'],check=True)
        subprocess.run([sys.executable,script,'hash','--limit','25'],check=True)
    except Exception as e: print('Worker error: '+str(e),flush=True)
    time.sleep(30)
