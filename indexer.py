"""Resumable, incremental ingestion. Complete traversals alone authorize pruning."""
import argparse,os,json,time,subprocess,sys,uuid
from pathlib import Path
from core import *
from locking import acquire

def job(db,key,data):
    db.execute('INSERT OR REPLACE INTO jobs VALUES(?,?)',[key,json.dumps(data)]); db.commit()

def inventory():
    run=uuid.uuid4().hex; started=time.time(); count=0; errors=[]; init()
    with connect() as db:
        for configured in sources():
            share=configured['id'];root=Path(configured['path']).resolve(); share_errors=[]
            if not root.is_dir(): errors.append(str(root)+': unavailable'); continue
            for parent,dirs,files in os.walk(root,followlinks=False,onerror=lambda e:share_errors.append(str(e))):
                dirs[:]=[d for d in dirs if d.lower() not in {s.lower() for s in SKIP} and not (Path(parent)/d).is_symlink() and not (hasattr(Path,'is_junction') and (Path(parent)/d).is_junction())]
                for name in files:
                    p=Path(parent)/name
                    if p.is_symlink() or name.startswith('~$'): continue
                    try:
                        s=p.stat(); rel=share+'/'+p.relative_to(root).as_posix(); ext=p.suffix.lower(); cat=category(ext)
                        db.execute('''INSERT INTO files(path,share,category,ext,size,mtime_ns,name,state,seen) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
                        state=CASE WHEN files.size!=excluded.size OR files.mtime_ns!=excluded.mtime_ns THEN 'pending' ELSE files.state END,
                        size=excluded.size,mtime_ns=excluded.mtime_ns,seen=excluded.seen''',[rel,share,cat,ext,s.st_size,s.st_mtime_ns,name,'pending' if cat!='other' else 'metadata_only',run])
                        count+=1
                        if count%2000==0: job(db,'inventory',{'state':'running','files_seen':count,'started':started})
                    except OSError as e: share_errors.append(str(e))
            if not share_errors:
                db.execute('DELETE FROM vectors WHERE id IN (SELECT id FROM files WHERE share=? AND seen!=?)',[share,run]); db.execute('DELETE FROM files WHERE share=? AND seen!=?',[share,run])
            errors+=share_errors
        job(db,'inventory',{'state':'complete' if not errors else 'partial','files_seen':count,'finished':time.time(),'seconds':round(time.time()-started,1),'errors':errors[:20]})
    print(json.dumps({'inventory':count,'errors':len(errors)}),flush=True)

def extract_pending(limit=0):
    init(); n=0; start=time.time()
    with connect() as db:
        while True:
            rows=db.execute("SELECT * FROM files WHERE state='pending' ORDER BY CASE category WHEN 'documents' THEN 0 WHEN 'music' THEN 1 WHEN 'pictures' THEN 2 ELSE 3 END,id LIMIT 100").fetchall()
            if not rows: break
            for row in rows:
                if limit and n>=limit: break
                try:
                    p=source(row['path']); before=p.stat()
                    if before.st_size>200_000_000 and row['category']=='documents': result={'state':'size_limited','error':'Document exceeds 200MB extraction cap','text':'','metadata':''}
                    elif row['category']=='other': result={'state':'metadata_only','text':'','metadata':''}
                    else:
                        proc=subprocess.run([sys.executable,str(Path(__file__).with_name('extract.py')),str(p)],capture_output=True,timeout=35)
                        result=json.loads(proc.stdout)
                    after=p.stat()
                    if (before.st_mtime_ns,before.st_size)!=(after.st_mtime_ns,after.st_size): continue
                    db.execute('UPDATE files SET text=?,metadata=?,state=?,error=? WHERE id=? AND mtime_ns=?',[result.get('text',''),result.get('metadata',''),result['state'],result.get('error'),row['id'],row['mtime_ns']])
                except Exception as e:
                    db.execute("UPDATE files SET state='failed',error=? WHERE id=?",[type(e).__name__+': '+str(e)[:250],row['id']])
                n+=1
                if n%25==0: job(db,'extraction',{'state':'running','processed_this_run':n,'started':start})
            db.commit()
            if limit and n>=limit: break
        pending=db.execute("SELECT count(*) FROM files WHERE state='pending'").fetchone()[0]
        job(db,'extraction',{'state':'complete' if not pending else 'paused','processed_this_run':n,'pending':pending,'finished':time.time()})
    print(json.dumps({'extracted':n,'pending':pending}),flush=True)

def embed_pending(limit=100):
    import numpy as np
    n=0
    with connect() as db:
        rows=db.execute("SELECT f.* FROM files f LEFT JOIN vectors v ON v.id=f.id WHERE f.category='documents' AND f.state='indexed' AND (v.id IS NULL OR v.mtime_ns!=f.mtime_ns) LIMIT ?",[limit]).fetchall()
        for r in rows:
            try:
                v=embed(r['name']+'\n'+r['path']+'\n'+r['metadata']+'\n'+r['text'][:6000]); db.execute('INSERT OR REPLACE INTO vectors VALUES(?,?,?,?)',[r['id'],r['mtime_ns'],'nomic-embed-text',v.tobytes()]); db.commit(); n+=1
            except Exception as e:
                job(db,'embeddings',{'state':'unavailable','error':type(e).__name__,'processed':n,'finished':time.time()}); return
        job(db,'embeddings',{'state':'batch_complete','processed':n,'finished':time.time()})

def hash_pending(limit=25):
    """Hash only size-collision candidates; originals are never altered."""
    if not settings.load(ROOT)['dedupe']['enabled']:return
    processed=0;active=[s['id'] for s in sources()]
    if not active:return
    with connect() as db:
        rows=db.execute('''SELECT * FROM files WHERE size IN (SELECT size FROM files GROUP BY size HAVING count(*)>1)
          AND (sha256 IS NULL OR hash_mtime IS NOT mtime_ns OR hash_size IS NOT size) AND share IN ('''+','.join('?' for _ in active)+') ORDER BY hash_attempted NULLS FIRST,id LIMIT ?',active+[limit]).fetchall()
        for row in rows:
            try:
                path=source(row['path']);before=path.stat()
                if (before.st_size,before.st_mtime_ns)!=(row['size'],row['mtime_ns']):continue
                digest=hashlib.sha256()
                with path.open('rb') as f:
                    while chunk:=f.read(1024*1024):digest.update(chunk)
                after=path.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):continue
                db.execute('UPDATE files SET sha256=?,hash_mtime=?,hash_size=? WHERE id=? AND mtime_ns=? AND size=?',[digest.hexdigest(),after.st_mtime_ns,after.st_size,row['id'],row['mtime_ns'],row['size']]);db.commit();processed+=1
            except (OSError,ValueError):continue
            finally:
                db.execute('UPDATE files SET hash_attempted=? WHERE id=?',[time.time(),row['id']]);db.commit()
        job(db,'dedupe',{'state':'batch_complete','hashed':processed,'finished':time.time()})

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('action',choices=['inventory','extract','embed','hash','cycle']); a.add_argument('--limit',type=int,default=0); args=a.parse_args()
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    with open(str(Path(DB).parent/'indexer.lock'),'a+b') as lock:
        if not acquire(lock):print('Another indexing job is active');sys.exit(0)
        init()
        if args.action in ('inventory','cycle'): inventory()
        if args.action in ('extract','cycle'): extract_pending(args.limit)
        if args.action in ('embed','cycle'): embed_pending(args.limit or 100)
        if args.action in ('hash','cycle'): hash_pending(args.limit or 25)
