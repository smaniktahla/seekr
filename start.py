import subprocess,os,sys
worker=subprocess.Popen([sys.executable,'/app/worker.py'])
os.execv(sys.executable,[sys.executable,'/app/server.py'])
