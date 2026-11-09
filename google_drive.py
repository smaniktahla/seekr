"""Read-only live Drive search. No files are uploaded, updated or deleted."""
import json,re,time,threading,urllib.request
from urllib.parse import urlencode,quote,urlsplit
from pathlib import PurePosixPath
import drive_auth

FIELDS='id,name,mimeType,webViewLink,description,size,modifiedTime,capabilities(canDownload)'
_cache={};_lock=threading.Lock();_generation=0

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def request(path,params):
    # Never follow a redirect with an OAuth Authorization header.
    url='https://www.googleapis.com/drive/v3/'+path+'?'+urlencode(params)
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+drive_auth.access_token()})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=12) as response:
        data=response.read(2_000_001)
        if len(data)>2_000_000:raise ValueError('Drive preview exceeds the 2 MB limit; use Open Original')
        return data

def category(mime):
    for prefix,cat in (('image/','pictures'),('audio/','music'),('video/','videos')):
        if mime.startswith(prefix):return cat
    if mime.startswith(('text/','application/vnd.google-apps.')) or any(s in mime for s in ('pdf','word','excel','spreadsheet','presentation','powerpoint','opendocument','rtf')):return 'documents'
    return 'other'

def public(item):
    mime=item.get('mimeType','');link=item.get('webViewLink','');u=urlsplit(link)
    if u.scheme!='https' or u.username or u.password or u.hostname not in ('drive.google.com','docs.google.com'):link=''
    ext=PurePosixPath(item.get('name','')).suffix
    if mime.startswith('application/vnd.google-apps.'):ext='.'+mime.rsplit('.',1)[-1]
    metadata='Google Drive; '+mime+'; modified '+item.get('modifiedTime','unknown')
    return {'id':'gdrive:'+item['id'],'name':item.get('name','Untitled'),'share':'GoogleDrive','category':category(mime),'ext':ext,'state':'live','excerpt':item.get('description','')[:800],'unc_path':'','open_url':link,'source':'gdrive','path':'GoogleDrive/'+item['id'],'metadata':metadata}

def clear_cache():
    global _generation
    with _lock:
        _generation+=1;_cache.clear()

def search(config,query,limit=50,mode='keyword',category_filter='all'):
    with _lock:
        key=(_generation,query,mode,category_filter,bool(config.get('include_shared',True)))
        cached=_cache.get(key)
        if cached and cached[0]>time.monotonic():return cached[1][:limit]
    field='name' if mode=='filename' else 'fullText'
    parts=[query.strip()] if mode=='filename' else query.split()
    terms=[s.replace('\\','\\\\').replace("'","\\'") for s in parts]
    clauses=['trashed = false',"mimeType != 'application/vnd.google-apps.folder'"]+[field+" contains '"+s+"'" for s in terms]
    if not config.get('include_shared',True):clauses.append("'me' in owners")
    # Apply category filtering before the bounded result window.
    media="(mimeType contains 'image/' or mimeType contains 'audio/' or mimeType contains 'video/')"
    docs="(mimeType contains 'text/' or mimeType contains 'application/vnd.google-apps.' or mimeType contains 'pdf' or mimeType contains 'word' or mimeType contains 'excel' or mimeType contains 'spreadsheet' or mimeType contains 'presentation' or mimeType contains 'powerpoint' or mimeType contains 'opendocument' or mimeType contains 'rtf')"
    if category_filter in ('pictures','music','videos'):clauses.append("mimeType contains '"+{'pictures':'image/','music':'audio/','videos':'video/'}[category_filter]+"'")
    elif category_filter=='documents':clauses.append(docs)
    elif category_filter=='other':clauses.extend(['not '+media,'not '+docs])
    params={'q':' and '.join(clauses),'pageSize':50,'fields':'nextPageToken,incompleteSearch,files('+FIELDS+')','orderBy':'modifiedTime desc,name','supportsAllDrives':'true','includeItemsFromAllDrives':'true'}
    items=[];token=None
    # Empty/partial pages are legal. Bound both total results and network work.
    for _ in range(3):
        if token:params['pageToken']=token
        data=json.loads(request('files',params));items.extend(data.get('files',[]));token=data.get('nextPageToken')
        if len(items)>=50 or not token:break
    rows=[public(x) for x in items[:50]]
    with _lock:
        if len(_cache)>100:_cache.clear()
        _cache[key]=(time.monotonic()+30,rows)
    return rows[:limit]

def read(ident,offset=0,length=12000):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',ident):raise ValueError('Invalid Drive file ID')
    path='files/'+quote(ident,safe='');item=json.loads(request(path,{'fields':FIELDS,'supportsAllDrives':'true'}));row=public(item)
    text=row['metadata']+'\n'+item.get('description','');mime=item.get('mimeType','')
    if item.get('capabilities',{}).get('canDownload',False):
        exports={'application/vnd.google-apps.document':'text/plain','application/vnd.google-apps.spreadsheet':'text/csv','application/vnd.google-apps.presentation':'text/plain'}
        if mime in exports:
            text=request(path+'/export',{'mimeType':exports[mime]}).decode('utf-8',errors='replace')
            if mime.endswith('spreadsheet'):text='CSV preview: first sheet only.\n'+text
        elif mime.startswith('text/') and int(item.get('size',0))<=2_000_000:
            text=request(path,{'alt':'media','supportsAllDrives':'true'}).decode('utf-8',errors='replace')
        else:text+='\nUse Open Original to view this file.'
    else:text+='\nContent download is restricted; use Open Original.'
    offset=max(int(offset),0);length=min(max(int(length),1),30000)
    row.update(text=text[offset:offset+length],offset=offset,next_offset=offset+length if offset+length<len(text) else None,total_characters=len(text))
    return row
