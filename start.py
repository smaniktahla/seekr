import subprocess,os,sys,signal
from pathlib import Path
root=Path(__file__).resolve().parent
worker=subprocess.Popen([sys.executable,str(root/'worker.py')],creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
if os.name!='nt':os.execv(sys.executable,[sys.executable,str(root/'server.py')])
try:
    subprocess.call([sys.executable,str(root/'server.py')])
except KeyboardInterrupt:pass
finally:
    if worker.poll() is None:
        worker.send_signal(signal.CTRL_BREAK_EVENT)
        try:worker.wait(timeout=10)
        except subprocess.TimeoutExpired:worker.kill()
