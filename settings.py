"""Private runtime configuration. No source files or credentials belong in Git."""
import copy,json,os,re,tempfile
from pathlib import Path
from urllib.parse import urlsplit

def config_path():
    return Path(os.getenv('ARCHIVE_SETTINGS',str(Path(os.getenv('ARCHIVE_DB','/data/archive.sqlite')).parent/'settings.json')))

def defaults(root):
    return {'version':1,'sources':[{'id':s,'path':str(root/s),'client_path':'\\\\truenas\\'+s,'enabled':True} for s in ('Documents','Pictures','Music','Videos')],
            'dedupe':{'enabled':False},'docmost':{'enabled':False,'mcp_url':'','semantic_url':'','app_url':'','page_url_template':''}}

def load(root):
    base=defaults(root)
    if config_path().exists():
        saved=json.loads(config_path().read_text(encoding='utf-8-sig'))
        base.update(saved)
    return base

def validate(data):
    clean={'version':1,'sources':[],'dedupe':{'enabled':bool(data.get('dedupe',{}).get('enabled',False))},'docmost':{}}
    used=set()
    if not isinstance(data.get('sources'),list) or len(data['sources'])>100: raise ValueError('Provide up to 100 index folders')
    for item in data['sources']:
        ident=str(item.get('id','')).strip(); path=str(item.get('path','')).strip(); client=str(item.get('client_path','')).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',ident) or ident.casefold() in used: raise ValueError('Each folder needs a unique ID using letters, digits, hyphens or underscores')
        if ident.casefold() in ('all','docmost'):raise ValueError('Folder ID is reserved for a search filter')
        if not Path(path).is_absolute(): raise ValueError('Index paths must be absolute paths on the selected service machine')
        allowed=os.getenv('ARCHIVE_ALLOWED_ROOT')
        if allowed and not Path(path).resolve().is_relative_to(Path(allowed).resolve()):raise ValueError('Index folder must be inside the service allowed root')
        if any(c in path+client for c in ('\r','\n','\x00')):raise ValueError('Invalid folder path')
        if client and not (client.startswith('\\\\') or re.match(r'^[A-Za-z]:[\\/]',client) or Path(client).is_absolute()):raise ValueError('Open path must be an absolute folder or SMB path, not a URL or command')
        used.add(ident.casefold());clean['sources'].append({'id':ident,'path':path,'client_path':client,'enabled':bool(item.get('enabled',True))})
    dm=data.get('docmost',{});clean['docmost']['enabled']=bool(dm.get('enabled',False))
    for key in ('mcp_url','semantic_url','app_url'):
        value=str(dm.get(key,'')).strip().rstrip('/')
        if value:
            u=urlsplit(value)
            if u.scheme not in ('http','https') or not u.netloc or u.username or u.password or u.fragment: raise ValueError('DocMost URLs must be HTTP(S) URLs without credentials or fragments')
        clean['docmost'][key]=value
    template=str(dm.get('page_url_template','')).strip()
    if template:
        u=urlsplit(template)
        if u.scheme not in ('http','https') or not u.netloc or u.username or u.password or '{id}' not in template:raise ValueError('Page URL template must be HTTP(S), contain {id}, and omit credentials')
    clean['docmost']['page_url_template']=template
    if clean['docmost']['enabled'] and not clean['docmost']['mcp_url']:raise ValueError('DocMost MCP URL is required when enabled')
    return clean

def save(data):
    clean=validate(data);p=config_path();p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.settings-',suffix='.json')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(clean,f,indent=2)
        os.replace(tmp,p)
        try:p.chmod(0o600)
        except OSError:pass
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return clean
