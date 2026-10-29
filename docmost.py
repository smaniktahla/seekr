"""Read-only DocMost adapter. Never logs in, writes notes, or forwards archive auth."""
import html,json,re,uuid,urllib.request
from urllib.parse import urlsplit

ALLOWED_TOOLS=frozenset({'search_notes','get_note'})

def request_json(url,payload):
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
    with urllib.request.urlopen(req,timeout=8) as response:
        if 'text/event-stream' not in response.headers.get('Content-Type',''):
            return json.loads(response.read(4_000_000))
        data=[];size=0
        for raw in response:
            size+=len(raw)
            if size>4_000_000:raise ValueError('DocMost response exceeds size limit')
            line=raw.decode('utf-8').rstrip('\r\n')
            if line.startswith('data:'):data.append(line[5:].lstrip())
            elif not line and data:return json.loads('\n'.join(data))
        if data:return json.loads('\n'.join(data))
        raise ValueError('DocMost returned no result')

def call(config,tool,arguments):
    if tool not in ALLOWED_TOOLS:raise ValueError('Only read-only DocMost tools are supported')
    result=request_json(config['mcp_url'],{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':tool,'arguments':arguments}})
    if 'error' in result:raise ValueError('DocMost MCP returned an error')
    result=result.get('result',{})
    if result.get('isError'):raise ValueError('DocMost lookup failed')
    return '\n'.join(c.get('text','') for c in result.get('content',[]) if c.get('type')=='text')

def plain(text):return html.unescape(re.sub(r'<[^>]+>','',text))

def search(config,query,limit=10,mode='keyword'):
    limit=min(max(int(limit),1),20)
    if mode=='semantic' and config.get('semantic_url'):
        url=config['semantic_url'].rstrip('/')
        if not url.endswith('/search'):url+='/search'
        payload=request_json(url,{'query':query,'limit':limit})
        items=[{'id':x.get('note_id'),'name':x.get('note_title','Untitled'),'excerpt':x.get('content','')} for x in payload.get('results',[])]
    else:
        text=call(config,'search_notes',{'query':query,'limit':limit});items=[]
        for part in re.split(r'\n---\n',text):
            title=re.search(r'^## (.+)$',part,re.M);ident=re.search(r'\*\*(?:Note )?ID:\*\*\s*([0-9a-fA-F-]{36})',part)
            excerpt=re.search(r'\*\*Excerpt:\*\*\s*([\s\S]*)',part)
            if title and ident:items.append({'id':ident.group(1),'name':title.group(1),'excerpt':excerpt.group(1) if excerpt else ''})
    out=[];seen=set()
    for item in items:
        try:ident=str(uuid.UUID(str(item['id'])))
        except ValueError:continue
        if ident in seen:continue
        seen.add(ident);template=config.get('page_url_template','')
        out.append({'id':'docmost:'+ident,'name':plain(item['name']),'share':'DocMost','category':'documents','ext':'.note','state':'live' if mode!='semantic' else 'hourly_index','excerpt':plain(item['excerpt']),'unc_path':'','open_url':template.replace('{id}',ident) if template else config.get('app_url',''),'source':'docmost','path':'DocMost/'+ident,'metadata':'DocMost note; read-only connector'})
    return out[:limit]

def read(config,ident,offset=0,length=12000):
    ident=str(uuid.UUID(ident));text=call(config,'get_note',{'page_id':ident});offset=max(int(offset),0);length=min(max(int(length),1),30000)
    return {'id':'docmost:'+ident,'name':text.splitlines()[0].lstrip('# ') if text else 'DocMost note','text':text[offset:offset+length],'metadata':'DocMost note','unc_path':'','offset':offset,'next_offset':offset+length if offset+length<len(text) else None,'total_characters':len(text)}
