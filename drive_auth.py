"""Desktop Google OAuth: loopback callback, PKCE, private backend credentials.

Only public flow data leaves this module. Do not log token responses or exceptions.
"""
import json,os,tempfile,threading,time
from urllib.parse import urlsplit
import settings

SCOPES=['https://www.googleapis.com/auth/drive.readonly']
AUTH_URI='https://accounts.google.com/o/oauth2/auth'
TOKEN_URI='https://oauth2.googleapis.com/token'
_lock=threading.RLock()
_pending={}

def directory():return settings.config_path().parent/'credentials'

def _crypt(data,decrypt=False):
    if os.name!='nt':return data
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));out=Blob()
    dll=ctypes.windll.crypt32
    ok=dll.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(out)) if decrypt else dll.CryptProtectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(out))
    if not ok:raise ValueError('Cannot access private Google credentials for this service account')
    try:return ctypes.string_at(out.data,out.size)
    finally:ctypes.windll.kernel32.LocalFree(out.data)

def _save(name,data):
    root=directory();root.mkdir(parents=True,exist_ok=True);root.chmod(0o700)
    raw=json.dumps(data).encode();raw=b'DPAPI\0'+_crypt(raw) if os.name=='nt' else raw
    fd,tmp=tempfile.mkstemp(dir=root,prefix='.google-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw)
        os.chmod(tmp,0o600);os.replace(tmp,root/name)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def _load(name):
    raw=(directory()/name).read_bytes()
    if raw.startswith(b'DPAPI\0'):raw=_crypt(raw[6:],True)
    return json.loads(raw)

def status():
    return {'client_configured':(directory()/'google-client.private').exists(),'connected':(directory()/'google-token.private').exists()}

def configure(data):
    client=data.get('installed',{})
    if not isinstance(client,dict) or not str(client.get('client_id','')).endswith('.apps.googleusercontent.com') or not client.get('client_secret'):
        raise ValueError('Import the Google OAuth client JSON for a Desktop app')
    if client.get('auth_uri')!=AUTH_URI or client.get('token_uri')!=TOKEN_URI:
        raise ValueError('OAuth client must use the official Google authorization and token endpoints')
    with _lock:
        _save('google-client.private',{'installed':{k:client[k] for k in ('client_id','client_secret','auth_uri','token_uri')}})
        disconnect()
    return status()

def begin(redirect_uri):
    u=urlsplit(redirect_uri)
    try:port=u.port
    except ValueError:port=None
    if u.scheme!='http' or u.hostname!='127.0.0.1' or not port or u.username or u.password or u.path!='/oauth2callback' or u.query or u.fragment:
        raise ValueError('OAuth callback must be http://127.0.0.1:<port>/oauth2callback')
    from google_auth_oauthlib.flow import Flow
    with _lock:
        now=time.monotonic()
        for key in list(_pending):
            if _pending[key][0]<now:del _pending[key]
        if len(_pending)>=8:raise ValueError('Too many pending sign-ins; wait a few minutes')
        flow=Flow.from_client_config(_load('google-client.private'),scopes=SCOPES,redirect_uri=redirect_uri,autogenerate_code_verifier=True)
        url,state=flow.authorization_url(access_type='offline',prompt='consent')
        _pending[state]=(now+300,flow)
        return {'authorization_url':url,'state':state}

def complete(state,code):
    with _lock:
        pending=_pending.pop(state,None)
        if not pending or pending[0]<time.monotonic():raise ValueError('Sign-in expired or state is invalid; connect again')
        if not isinstance(code,str) or not 1<=len(code)<=4096:raise ValueError('Invalid authorization code')
        flow=pending[1]
        flow.fetch_token(code=code,timeout=15)
        info=json.loads(flow.credentials.to_json())
        if not info.get('refresh_token'):raise ValueError('Google did not grant offline access; connect again')
        granted=set(flow.oauth2session.token.get('scope',' '.join(SCOPES)).split())
        if set(SCOPES)!=granted:raise ValueError('Google Drive read-only permission must be granted')
        _save('google-token.private',info)
    return status()

def access_token():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    with _lock:
        creds=Credentials.from_authorized_user_info(_load('google-token.private'),SCOPES)
        if not creds.valid:
            transport=Request()
            def bounded_request(*args,**kwargs):
                kwargs['timeout']=12
                return transport(*args,**kwargs)
            creds.refresh(bounded_request);_save('google-token.private',json.loads(creds.to_json()))
        return creds.token

def disconnect():
    """Forget local credentials. Google account revocation is a separate user action."""
    with _lock:
        _pending.clear()
        (directory()/'google-token.private').unlink(missing_ok=True)
    return status()
