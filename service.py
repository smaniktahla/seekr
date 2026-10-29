"""Settings and search federation, shared by REST and MCP."""
import itertools,json,time
from pathlib import Path
import core,settings,docmost

def get_settings():
    result=settings.load(core.ROOT)
    result['source_status']=[{'id':s['id'],'accessible':Path(s['path']).is_dir()} for s in result['sources']]
    return result

def save_settings(data):
    clean=settings.validate(data);old=settings.load(core.ROOT)
    changed={s['id'] for s in old['sources'] if not any(n['id']==s['id'] and n['path']==s['path'] for n in clean['sources'])}
    core.init()
    with core.connect() as db:
        for ident in changed:
            db.execute('DELETE FROM vectors WHERE id IN (SELECT id FROM files WHERE share=?)',[ident])
            db.execute('DELETE FROM files WHERE share=?',[ident])
        settings.save(clean)
        db.execute('INSERT OR REPLACE INTO jobs VALUES(?,?)',['scan_requested',json.dumps(time.time())])
    return get_settings()

def search(query,category_filter='all',share='all',limit=20,mode='keyword',offset=0,dedupe=None,include_docmost=True):
    started=time.perf_counter()
    if not query.strip() or len(query)>1000:raise ValueError('Query must contain 1-1000 characters')
    if mode not in ('filename','keyword','hybrid','semantic'):raise ValueError('Unknown search mode')
    config=settings.load(core.ROOT);dm=config['docmost'];limit=min(max(int(limit),1),50);offset=max(0,min(int(offset),10000))
    only_notes=share=='DocMost'
    use_notes=include_docmost and dm['enabled'] and category_filter in ('all','documents') and (only_notes or share=='all') and (mode!='filename' or only_notes)
    if not use_notes and not only_notes:return core.search_files(query,category_filter,share,limit,mode,offset,dedupe)
    notes=[];warning=None
    try:
        if dm['enabled']:notes=docmost.search(dm,query,20,'semantic' if mode=='semantic' else 'keyword')
    except Exception as e:warning='DocMost unavailable ('+type(e).__name__+'); file results remain available.'
    if only_notes:
        return {'query':query,'mode':mode,'total':len(notes),'results':notes[offset:offset+limit],'elapsed_ms':round((time.perf_counter()-started)*1000,1),'warning':warning,'docmost_limit':20}
    # Alternate file/note results, with stable pagination and no skipped file rows.
    files=core.search_files(query,category_filter,share,1,mode,0,dedupe)
    def order():
        for f,n in itertools.zip_longest(range(files['total']),range(len(notes))):
            if f is not None:yield ('files',f)
            if n is not None:yield ('docmost',n)
    page=list(itertools.islice(order(),offset,offset+limit));indices=[i for origin,i in page if origin=='files'];found={}
    if indices:
        batch=core.search_files(query,category_filter,share,len(indices),mode,min(indices),dedupe)
        found={min(indices)+i:r for i,r in enumerate(batch['results'])}
    result=[notes[i] if origin=='docmost' else found[i] for origin,i in page if origin=='docmost' or i in found]
    if len(notes)==20:warning=(warning+' ' if warning else '')+'DocMost results are limited to 20 notes per query.'
    return {'query':query,'mode':mode,'total':files['total']+len(notes),'results':result,'elapsed_ms':round((time.perf_counter()-started)*1000,1),'warning':warning or files.get('warning'),'docmost_limit':20}

def read(ident,offset=0,length=12000):
    if str(ident).startswith('docmost:'):
        config=settings.load(core.ROOT)['docmost']
        if not config['enabled']:raise ValueError('DocMost connector is disabled')
        return docmost.read(config,str(ident)[8:],offset,length)
    return core.read_document(int(ident),offset,length)
