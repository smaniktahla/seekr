"""Authenticated stdio-to-stateless-HTTP bridge; credentials never appear in argv."""
import argparse,json,sys,urllib.request,urllib.error
from pathlib import Path

def decrypt_windows(path):
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    raw=Path(path).read_bytes(); buf=ctypes.create_string_buffer(raw); source=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte))); out=Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source),None,None,None,None,0,ctypes.byref(out)): raise OSError('Cannot decrypt archive credential for this Windows user')
    try:return ctypes.string_at(out.pbData,out.cbData).decode().strip()
    finally:ctypes.windll.kernel32.LocalFree(out.pbData)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--url',default='http://localhost:8093/mcp'); g=p.add_mutually_exclusive_group(required=True);g.add_argument('--token-file');g.add_argument('--dpapi-file'); a=p.parse_args()
    token=decrypt_windows(a.dpapi_file) if a.dpapi_file else Path(a.token_file).read_text().strip(); version=None
    for line in sys.stdin:
        request=None
        try:
            request=json.loads(line); headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
            if version:headers['MCP-Protocol-Version']=version
            req=urllib.request.Request(a.url,data=json.dumps(request).encode(),headers=headers)
            with urllib.request.urlopen(req,timeout=60) as response:
                raw=response.read()
            if raw:
                result=json.loads(raw)
                if request.get('method')=='initialize':version=result.get('result',{}).get('protocolVersion')
                if 'id' in request: print(json.dumps(result),flush=True)
        except Exception as e:
            if isinstance(request,dict) and 'id' in request:
                print(json.dumps({'jsonrpc':'2.0','id':request['id'],'error':{'code':-32603,'message':'Archive connection failed: '+type(e).__name__}}),flush=True)
            else:print('Archive transport: '+type(e).__name__,file=sys.stderr)

if __name__=='__main__':main()
