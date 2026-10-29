import unittest,tempfile,os,json,hashlib,threading
from pathlib import Path
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,HTTPServer
import core,settings,service,docmost,indexer

class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'ARCHIVE_SETTINGS':self.tmp.name+'/settings.json'});self.env.start()
        self.old=(core.DB,core.ROOT);core.DB=self.tmp.name+'/index.sqlite';core.ROOT=Path(self.tmp.name)/'archive';core.init()
        self.root=Path(self.tmp.name)/'local';self.root.mkdir()
        self.config={'sources':[{'id':'Local','path':str(self.root),'client_path':str(self.root),'enabled':True}],'dedupe':{'enabled':True},'docmost':{'enabled':False}}
        settings.save(self.config)
    def tearDown(self):
        core.DB,core.ROOT=self.old;self.env.stop();self.tmp.cleanup()
    def add(self,name,data):
        p=self.root/name;p.write_bytes(data);s=p.stat()
        with core.connect() as db:
            db.execute("INSERT INTO files(path,share,category,name,text,size,mtime_ns,state) VALUES(?,?,?,?,?,?,?,'indexed')",['Local/'+name,'Local','documents',name,'sample content',s.st_size,s.st_mtime_ns])
    def test_paths_and_inventory(self):
        (self.root/'sample.txt').write_text('example')
        with patch.object(indexer,'DB',core.DB),patch.object(indexer,'ROOT',core.ROOT):indexer.inventory()
        r=core.search_files('sample',share='Local',mode='filename')['results'][0]
        self.assertEqual(r['unc_path'],str(self.root/'sample.txt'));self.assertEqual(core.source(r['path']),(self.root/'sample.txt').resolve())
        with self.assertRaises(ValueError):core.source('Local/../index.sqlite')
    def test_exact_dedupe_and_filter_representative(self):
        self.add('first.txt',b'identical');self.add('second.txt',b'identical');self.add('third.txt',b'different')
        with patch.object(indexer,'DB',core.DB),patch.object(indexer,'ROOT',core.ROOT):indexer.hash_pending()
        self.assertEqual(core.search_files('sample',dedupe=True)['total'],2)
        self.assertEqual(core.search_files('sample',dedupe=False)['total'],3)
        self.assertEqual(core.search_files('second',mode='filename',dedupe=True)['total'],1)
        with core.connect() as db:db.execute("UPDATE files SET mtime_ns=mtime_ns+1 WHERE name='second.txt'")
        self.assertEqual(core.search_files('sample',dedupe=True)['total'],3)
    def test_same_name_size_is_not_exact(self):
        self.add('one.txt',b'aaaa');self.add('two.txt',b'bbbb')
        with patch.object(indexer,'DB',core.DB),patch.object(indexer,'ROOT',core.ROOT):indexer.hash_pending()
        self.assertEqual(core.search_files('sample',dedupe=True)['total'],2)
    def test_disabled_source_hidden_not_deleted(self):
        self.add('sample.txt',b'example');c=settings.load(core.ROOT);c['sources'][0]['enabled']=False;service.save_settings(c)
        self.assertEqual(core.search_files('sample')['total'],0)
        with core.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM files').fetchone()[0],1)
    def test_invalid_settings_do_not_replace_file(self):
        before=settings.config_path().read_bytes();bad=dict(self.config);bad['sources']=[{'id':'bad/id','path':'relative'}]
        with self.assertRaises(ValueError):settings.save(bad)
        self.assertEqual(settings.config_path().read_bytes(),before)
    def test_federated_pagination(self):
        for i in range(6):self.add('sample%s.txt'%i,bytes([i]))
        c=settings.load(core.ROOT);c['docmost']={'enabled':True,'mcp_url':'http://example.test/mcp'};settings.save(c)
        notes=[{'id':'docmost:'+str(i),'source':'docmost'} for i in range(3)]
        with patch.object(docmost,'search',return_value=notes):
            pages=[service.search('sample',limit=3,offset=i,dedupe=False)['results'] for i in (0,3,6)]
        ids=[str(r['id']) for page in pages for r in page];self.assertEqual(len(ids),9);self.assertEqual(len(set(ids)),9)
    def test_docmost_outage_keeps_files(self):
        self.add('sample.txt',b'example');c=settings.load(core.ROOT);c['docmost']={'enabled':True,'mcp_url':'http://example.test/mcp'};settings.save(c)
        with patch.object(docmost,'search',side_effect=TimeoutError):r=service.search('sample')
        self.assertEqual(len(r['results']),1);self.assertIn('unavailable',r['warning'])
    def test_semantic_pagination_beyond_first_hundred(self):
        try:import numpy as np
        except ImportError:self.skipTest('numpy is installed with service requirements')
        with core.connect() as db:
            for i in range(105):
                cur=db.execute("INSERT INTO files(path,share,category,name,mtime_ns,size,state) VALUES(?,'Local','documents',?,0,1,'indexed')",['Local/item%s.txt'%i,'item%s.txt'%i])
                db.execute('INSERT INTO vectors VALUES(?,?,?,?)',[cur.lastrowid,0,'nomic-embed-text',np.asarray([1,0],dtype=np.float32).tobytes()])
        with patch.object(core,'embed',return_value=np.asarray([1,0],dtype=np.float32)):
            r=core.search_files('sample',mode='semantic',offset=100,limit=10)
        self.assertEqual(r['total'],105);self.assertEqual(len(r['results']),5)

class ConnectorTests(unittest.TestCase):
    def test_sse_and_read_only(self):
        calls=[];note='00000000-0000-4000-8000-000000000001'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                calls.append((json.loads(self.rfile.read(int(self.headers['Content-Length']))),self.headers.get('Authorization')))
                text='## Sample\n**ID:** '+note+'\n**Excerpt:** <b>sample</b> text\n'
                data={'jsonrpc':'2.0','id':1,'result':{'content':[{'type':'text','text':text}]}}
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();self.wfile.write(('event: message\ndata: '+json.dumps(data)+'\n\n').encode())
        http=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            c={'mcp_url':'http://127.0.0.1:%s/mcp'%http.server_port,'app_url':'http://example.test'}
            rows=docmost.search(c,'sample');self.assertEqual(rows[0]['id'],'docmost:'+note);self.assertEqual(rows[0]['excerpt'],'sample text\n')
            self.assertIsNone(calls[0][1]);self.assertEqual(calls[0][0]['params']['name'],'search_notes')
            with self.assertRaises(ValueError):docmost.call(c,'update_note',{})
        finally:http.shutdown();http.server_close();thread.join()

if __name__=='__main__':unittest.main()
