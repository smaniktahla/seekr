"""Read-only source access; SQLite WAL index shared by HTTP, MCP and indexer."""
import os, re, sqlite3, json, time, hashlib, urllib.request
from pathlib import Path

DB = os.getenv('ARCHIVE_DB', '/data/archive.sqlite')
ROOT = Path(os.getenv('ARCHIVE_ROOT', '/archive'))
SHARES = ('Documents', 'Pictures', 'Music', 'Videos')
SKIP = {'.git','node_modules','.venv','venv','__pycache__','.zfs','$recycle.bin','@eaDir'}
DOC = {'.pdf','.doc','.docx','.xlsx','.xls','.xlsm','.ppt','.pptx','.txt','.md','.csv','.rtf','.ods','.odt','.html','.htm','.sql'}
IMAGE = {'.jpg','.jpeg','.png','.heic','.tif','.tiff','.gif','.webp','.cr2','.dng'}
AUDIO = {'.mp3','.flac','.m4a','.ogg','.wav','.wma','.aac','.opus'}
VIDEO = {'.mp4','.mkv','.avi','.mov','.m4v','.mpg','.mpeg','.webm','.3gp'}

class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()

def connect():
    db=sqlite3.connect(DB,timeout=30,factory=ClosingConnection); db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA busy_timeout=30000')
    return db

def init():
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY,path TEXT UNIQUE NOT NULL,share TEXT,category TEXT,ext TEXT,size INTEGER,mtime_ns INTEGER,name TEXT,metadata TEXT DEFAULT '',text TEXT DEFAULT '',state TEXT DEFAULT 'pending',error TEXT,seen TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(name,path,metadata,text,content='files',content_rowid='id',tokenize='unicode61 remove_diacritics 2');
        CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN INSERT INTO search(rowid,name,path,metadata,text) VALUES(new.id,new.name,new.path,new.metadata,new.text); END;
        CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN INSERT INTO search(search,rowid,name,path,metadata,text) VALUES('delete',old.id,old.name,old.path,old.metadata,old.text); END;
        CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE OF name,path,metadata,text ON files BEGIN
          INSERT INTO search(search,rowid,name,path,metadata,text) VALUES('delete',old.id,old.name,old.path,old.metadata,old.text);
          INSERT INTO search(rowid,name,path,metadata,text) VALUES(new.id,new.name,new.path,new.metadata,new.text); END;
        CREATE TABLE IF NOT EXISTS vectors(id INTEGER PRIMARY KEY REFERENCES files(id),mtime_ns INTEGER,model TEXT,vector BLOB);
        CREATE TABLE IF NOT EXISTS jobs(key TEXT PRIMARY KEY,value TEXT);
        CREATE INDEX IF NOT EXISTS files_state ON files(state);
        CREATE INDEX IF NOT EXISTS files_share ON files(share);
        CREATE INDEX IF NOT EXISTS files_names ON files(category,share,path,name);
        ''')

def category(ext):
    return 'documents' if ext in DOC else 'pictures' if ext in IMAGE else 'music' if ext in AUDIO else 'videos' if ext in VIDEO else 'other'

def source(path):
    root=ROOT.resolve(); p=(root/path).resolve()
    if not any(p.is_relative_to((root/s).resolve()) for s in SHARES): raise ValueError('Path outside configured shares')
    if any(x.lower() in {s.lower() for s in SKIP} for x in p.relative_to(root).parts): raise ValueError('Excluded path')
    return p

def public(row, excerpt=''):
    d=dict(row); p=d['path']; d.pop('text',None); d.pop('seen',None); d.pop('mtime_ns',None)
    d['unc_path']='\\\\truenas\\'+p.replace('/','\\'); d['excerpt']=excerpt
    return d

def embed(text, query=False):
    import numpy as np
    prefix='search_query: ' if query else 'search_document: '
    req=urllib.request.Request(os.getenv('EMBEDDING_URL','http://localhost:11434')+'/api/embed',data=json.dumps({'model':'nomic-embed-text','input':prefix+text,'truncate':True,'keep_alive':'2m'}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=12) as r: v=np.asarray(json.load(r)['embeddings'][0],dtype=np.float32)
    return v/max(float(np.linalg.norm(v)),1e-12)

def search_files(query,category_filter='all',share='all',limit=10,mode='keyword',offset=0):
    started=time.perf_counter(); limit=max(1,min(int(limit),50)); offset=max(0,min(int(offset),10000))
    if not query.strip() or len(query)>1000: raise ValueError('Query must contain 1â€“1000 characters')
    if category_filter not in ('all','documents','pictures','music','videos','other'): raise ValueError('Unknown category')
    if share not in ('all',)+SHARES: raise ValueError('Unknown share')
    if mode not in ('filename','keyword','semantic','hybrid'): raise ValueError('Unknown search mode')
    clauses=[]; args=[]
    if category_filter!='all': clauses.append('f.category=?'); args.append(category_filter)
    if share!='all': clauses.append('f.share=?'); args.append(share)
    where=(' AND '+' AND '.join(clauses)) if clauses else ''
    terms=re.findall(r'[^\W_]+',query,flags=re.UNICODE)
    if not terms: raise ValueError('Query must contain searchable words or numbers')
    expression=' AND '.join('"'+x+'"' for x in terms)
    warning=None; results=[]; total=0
    with connect() as db:
        if mode=='filename':
            # Literal substrings, ANDed across the path. Escape SQL wildcard characters.
            fragments=query.strip().replace('\\','/').split()
            matches=[]; patterns=[]
            for fragment in fragments:
                matches.append("lower(f.path) LIKE ? ESCAPE '\\'")
                patterns.append('%'+fragment.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
            condition=' AND '.join(matches)+where
            total=db.execute('SELECT count(*) FROM files f INDEXED BY files_names WHERE '+condition,patterns+args).fetchone()[0]
            found=db.execute('SELECT f.* FROM files f INDEXED BY files_names WHERE '+condition+' ORDER BY f.name COLLATE NOCASE,f.path LIMIT ? OFFSET ?',patterns+args+[limit,offset]).fetchall()
            results=[public(r,r['path']) for r in found]
        if mode in ('keyword','hybrid'):
            total=db.execute('SELECT count(*) FROM search JOIN files f ON f.id=search.rowid WHERE search MATCH ?'+where,[expression]+args).fetchone()[0]
            rows=db.execute("SELECT f.*,snippet(search,-1,'','', ' â€¦ ',40) AS excerpt FROM search JOIN files f ON f.id=search.rowid WHERE search MATCH ?"+where+' ORDER BY bm25(search,10,4,3,1) LIMIT ? OFFSET ?',[expression]+args+[limit if mode=='keyword' else 100,offset if mode=='keyword' else 0]).fetchall()
            results=[public(r,r['excerpt']) for r in rows]
        if mode in ('semantic','hybrid'):
            try:
                import numpy as np
                q=embed(query,True); scored=[]
                cur=db.execute('SELECT v.id,v.vector FROM vectors v JOIN files f ON f.id=v.id WHERE v.mtime_ns=f.mtime_ns AND v.model=?'+where,['nomic-embed-text']+args)
                while batch:=cur.fetchmany(512):
                    vectors=np.stack([np.frombuffer(r['vector'],dtype=np.float32) for r in batch]); scores=vectors@q
                    scored.extend((float(s),r['id']) for s,r in zip(scores,batch))
                scored.sort(reverse=True); ranks={r['id']:1/(60+i) for i,r in enumerate(results)}
                for i,(_,fid) in enumerate(scored[:100]): ranks[fid]=ranks.get(fid,0)+1/(60+i)
                ids=[i for i,_ in sorted(ranks.items(),key=lambda x:-x[1])][offset:offset+limit]
                results=[public(r,r['text'][:700]) for fid in ids if (r:=db.execute('SELECT * FROM files WHERE id=?',[fid]).fetchone())]
                total=max(total,len(scored)); warning='Semantic vectors cover filenames, metadata and the opening 6000 characters, not every passage. Check index status for coverage.'
            except Exception as e:
                warning='Semantic search unavailable; keyword results returned. '+type(e).__name__
                results=results[offset:offset+limit] if mode=='hybrid' else []
        return {'query':query,'mode':mode,'total':total,'results':results,'elapsed_ms':round((time.perf_counter()-started)*1000,1),'warning':warning}

def read_document(file_id,offset=0,length=12000):
    with connect() as db: r=db.execute('SELECT * FROM files WHERE id=?',[int(file_id)]).fetchone()
    if not r: raise ValueError('Unknown file ID')
    source(r['path']); offset=max(0,int(offset)); length=max(1,min(int(length),30000))
    d=public(r); d.update(text=r['text'][offset:offset+length],offset=offset,total_characters=len(r['text']),next_offset=offset+length if offset+length<len(r['text']) else None)
    return d

def status():
    with connect() as db:
        return {'files':db.execute('SELECT count(*) FROM files').fetchone()[0],'by_share':[dict(r) for r in db.execute('SELECT share,count(*) AS files,sum(size) AS bytes FROM files GROUP BY share')],'by_state':[dict(r) for r in db.execute('SELECT state,count(*) AS files FROM files GROUP BY state')],'semantic_vectors':db.execute('SELECT count(*) FROM vectors v JOIN files f ON f.id=v.id WHERE v.mtime_ns=f.mtime_ns').fetchone()[0],'jobs':{r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM jobs')}}
