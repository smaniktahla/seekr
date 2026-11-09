"""Settings and search federation, shared by REST and MCP."""
import itertools,json,time
from pathlib import Path
import core,settings,docmost,google_drive,drive_auth

def get_settings():
    result=settings.load(core.ROOT)
    result['source_status']=[{'id':s['id'],'accessible':Path(s['path']).is_dir()} for s in result['sources']]
    result['google_drive_status']=drive_auth.status()
    return result

def save_settings(data):
    old=settings.load(core.ROOT)
    clean=settings.validate({'google_drive':old['google_drive'],**data})
    changed={s['id'] for s in old['sources'] if not any(n['id']==s['id'] and n['path']==s['path'] for n in clean['sources'])}
    core.init()
    with core.connect() as db:
        for ident in changed:
            db.execute('DELETE FROM vectors WHERE id IN (SELECT id FROM files WHERE share=?)',[ident])
            db.execute('DELETE FROM files WHERE share=?',[ident])
        settings.save(clean)
        db.execute('INSERT OR REPLACE INTO jobs VALUES(?,?)',['scan_requested',json.dumps(time.time())])
    return get_settings()

def search(query,category_filter='all',share='all',limit=20,mode='keyword',offset=0,dedupe=None,include_docmost=True,include_google_drive=True):
    started=time.perf_counter()
    if not query.strip() or len(query)>1000:raise ValueError('Query must contain 1-1000 characters')
    if mode not in ('filename','keyword','hybrid','semantic'):raise ValueError('Unknown search mode')
    if category_filter not in ('all','documents','pictures','music','videos','other'):raise ValueError('Unknown category')
    config=settings.load(core.ROOT);dm=config['docmost'];gd=config['google_drive'];limit=min(max(int(limit),1),50);offset=max(0,min(int(offset),10000))
    remote_only=share in ('DocMost','GoogleDrive')
    use_notes=include_docmost and dm['enabled'] and category_filter in ('all','documents') and share in ('all','DocMost') and (mode!='filename' or remote_only)
    use_drive=include_google_drive and gd['enabled'] and share in ('all','GoogleDrive') and (mode!='filename' or remote_only)
    if not (use_notes or use_drive or remote_only):return core.search_files(query,category_filter,share,limit,mode,offset,dedupe)
    providers={};warnings=[]
    if use_notes:
        try:providers['docmost']=docmost.search(dm,query,20,'semantic' if mode=='semantic' else 'keyword')
        except Exception:warnings.append('DocMost unavailable; file results remain available.')
        if len(providers.get('docmost',[]))==20:warnings.append('DocMost results are limited to 20 notes per query.')
    if use_drive:
        try:
            providers['gdrive']=google_drive.search(gd,query,50,mode,category_filter)
            if len(providers['gdrive'])==50:warnings.append('Google Drive results are limited to 50 files per query.')
            if mode in ('semantic','hybrid'):warnings.append('Google Drive results use keyword matching.')
        except Exception:warnings.append('Google Drive unavailable; check its connection in Settings. File results remain available.')
    files={'total':0,'results':[]}
    if not remote_only:files=core.search_files(query,category_filter,share,1,mode,0,dedupe)
    # Round-robin providers with stable pagination and no skipped file rows.
    counts={'files':files['total'],**{k:len(v) for k,v in providers.items()}}
    def order():
        for indices in itertools.zip_longest(*(range(n) for n in counts.values())):
            for origin,i in zip(counts,indices):
                if i is not None:yield origin,i
    page=list(itertools.islice(order(),offset,offset+limit));indices=[i for origin,i in page if origin=='files'];found={}
    if indices:
        batch=core.search_files(query,category_filter,share,len(indices),mode,min(indices),dedupe)
        found={min(indices)+i:r for i,r in enumerate(batch['results'])}
    result=[found[i] if origin=='files' else providers[origin][i] for origin,i in page if origin!='files' or i in found]
    if files.get('warning'):warnings.append(files['warning'])
    return {'query':query,'mode':mode,'total':sum(counts.values()),'results':result,'elapsed_ms':round((time.perf_counter()-started)*1000,1),'warning':' '.join(warnings) or None,'docmost_limit':20,'google_drive_limit':50}

def read(ident,offset=0,length=12000):
    if str(ident).startswith('gdrive:'):
        if not settings.load(core.ROOT)['google_drive']['enabled']:raise ValueError('Google Drive connector is disabled')
        try:return google_drive.read(str(ident)[7:],offset,length)
        except Exception:raise ValueError('Google Drive preview unavailable; reconnect in Settings or use Open Original') from None
    if str(ident).startswith('docmost:'):
        config=settings.load(core.ROOT)['docmost']
        if not config['enabled']:raise ValueError('DocMost connector is disabled')
        return docmost.read(config,str(ident)[8:],offset,length)
    return core.read_document(int(ident),offset,length)
