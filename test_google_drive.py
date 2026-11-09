import hashlib,base64,json,os,tempfile,time,unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch,Mock
import core,settings,service,drive_auth,google_drive

CLIENT={'installed':{'client_id':'synthetic.apps.googleusercontent.com','client_secret':'synthetic-client-secret','auth_uri':drive_auth.AUTH_URI,'token_uri':drive_auth.TOKEN_URI}}

class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'ARCHIVE_SETTINGS':self.tmp.name+'/settings.json'});self.env.start();drive_auth._pending.clear()
    def tearDown(self):
        drive_auth._pending.clear();self.env.stop();self.tmp.cleanup()
    def test_config_is_private_and_never_returned(self):
        result=drive_auth.configure(CLIENT)
        self.assertEqual(result,{'client_configured':True,'connected':False})
        self.assertEqual(drive_auth._load('google-client.private'),CLIENT)
        if os.name=='nt':self.assertNotIn(b'synthetic-client-secret',(drive_auth.directory()/'google-client.private').read_bytes())
        else:self.assertEqual((drive_auth.directory()/'google-client.private').stat().st_mode&0o777,0o600)
        bad=json.loads(json.dumps(CLIENT));bad['installed']['token_uri']='https://example.test/token'
        with self.assertRaises(ValueError):drive_auth.configure(bad)
    def test_pkce_readonly_scope_and_loopback(self):
        drive_auth.configure(CLIENT)
        result=drive_auth.begin('http://127.0.0.1:54321/oauth2callback');q=parse_qs(urlsplit(result['authorization_url']).query)
        self.assertEqual(q['scope'],drive_auth.SCOPES);self.assertEqual(q['code_challenge_method'],['S256'])
        flow=drive_auth._pending[result['state']][1]
        challenge=base64.urlsafe_b64encode(hashlib.sha256(flow.code_verifier.encode()).digest()).decode().rstrip('=')
        self.assertEqual(q['code_challenge'],[challenge]);self.assertEqual(q['state'],[result['state']]);self.assertEqual(q['access_type'],['offline'])
        for uri in ('https://example.test/oauth2callback','http://127.0.0.1/oauth2callback','http://127.0.0.1:54321/other','http://127.0.0.1:54321/oauth2callback?x=1','http://user@127.0.0.1:54321/oauth2callback'):
            with self.assertRaises(ValueError):drive_auth.begin(uri)
    def test_state_expiry_exchange_and_disconnect(self):
        drive_auth.configure(CLIENT)
        with self.assertRaises(ValueError):drive_auth.complete('wrong','code')
        flow=Mock();flow.credentials.to_json.return_value=json.dumps({'refresh_token':'synthetic-refresh','token':'synthetic-access'})
        flow.oauth2session.token={'scope':' '.join(drive_auth.SCOPES)}
        drive_auth._pending['expired']=(0,flow)
        with self.assertRaises(ValueError):drive_auth.complete('expired','code')
        flow.fetch_token.assert_not_called()
        drive_auth._pending['state']=(time.monotonic()+30,flow)
        result=drive_auth.complete('state','code');flow.fetch_token.assert_called_once_with(code='code',timeout=15)
        self.assertTrue(result['connected']);self.assertNotIn('synthetic',json.dumps(result))
        with self.assertRaises(ValueError):drive_auth.complete('state','code')
        self.assertFalse(drive_auth.disconnect()['connected']);self.assertTrue(drive_auth.status()['client_configured'])
    def test_refresh_stays_on_backend(self):
        creds=Mock(valid=False,token='synthetic-access');creds.to_json.return_value='{"refresh_token":"synthetic-refresh"}'
        with patch.object(drive_auth,'_load',return_value={}),patch('google.oauth2.credentials.Credentials.from_authorized_user_info',return_value=creds),patch.object(drive_auth,'_save') as save:
            self.assertEqual(drive_auth.access_token(),'synthetic-access');creds.refresh.assert_called_once();save.assert_called_once()

class DriveTests(unittest.TestCase):
    def setUp(self):google_drive.clear_cache()
    def test_query_escaping_and_cache(self):
        item={'id':'synthetic-id','name':'Report','mimeType':'application/vnd.google-apps.document','webViewLink':'https://docs.google.com/document/d/synthetic/edit'}
        with patch.object(google_drive,'request',return_value=json.dumps({'files':[item]}).encode()) as request:
            rows=google_drive.search({'include_shared':False},"O'Brien \\test",mode='filename')
            query=request.call_args.args[1]['q'];self.assertIn("name contains 'O\\'Brien \\\\test'",query);self.assertIn("'me' in owners",query)
            self.assertEqual(rows[0]['id'],'gdrive:synthetic-id');self.assertEqual(rows[0]['ext'],'.document')
            google_drive.search({'include_shared':False},"O'Brien \\test",mode='filename');self.assertEqual(request.call_count,1)
    def test_preview_and_restricted_content(self):
        item={'id':'synthetic','name':'Sheet','mimeType':'application/vnd.google-apps.spreadsheet','capabilities':{'canDownload':True}}
        with patch.object(google_drive,'request',side_effect=[json.dumps(item).encode(),b'a,b\n1,2']) as request:
            row=google_drive.read('synthetic');self.assertIn('first sheet only',row['text']);self.assertEqual(request.call_args.args[0],'files/synthetic/export')
        item['capabilities']['canDownload']=False
        with patch.object(google_drive,'request',return_value=json.dumps(item).encode()) as request:
            self.assertIn('restricted',google_drive.read('synthetic')['text']);self.assertEqual(request.call_count,1)
        with self.assertRaises(ValueError):google_drive.read('../bad')
    def test_links_and_http_are_read_only(self):
        self.assertEqual(google_drive.public({'id':'x','webViewLink':'https://example.test/steal'})['open_url'],'')
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=b'{}'
        opener=Mock();opener.open.return_value=response
        with patch.object(drive_auth,'access_token',return_value='synthetic'),patch('urllib.request.build_opener',return_value=opener):
            google_drive.request('files',{'q':'test'})
        req=opener.open.call_args.args[0];self.assertEqual(req.get_method(),'GET');self.assertEqual(urlsplit(req.full_url).hostname,'www.googleapis.com')
        self.assertIsNone(google_drive.NoRedirect().redirect_request(None,None,None,None,None,None))

class FederationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'ARCHIVE_SETTINGS':self.tmp.name+'/settings.json'});self.env.start()
        settings.save({'sources':[],'google_drive':{'enabled':True},'docmost':{'enabled':True,'mcp_url':'http://example.test/mcp'}})
    def tearDown(self):self.env.stop();self.tmp.cleanup();google_drive.clear_cache()
    def test_three_provider_pagination_and_filename_behavior(self):
        files=[{'id':i} for i in range(7)];notes=[{'id':'docmost:'+str(i)} for i in range(2)];drive=[{'id':'gdrive:'+str(i)} for i in range(4)]
        def search(q,c,s,limit,mode,offset,dedupe):return {'total':len(files),'results':files[offset:offset+limit]}
        with patch.object(core,'search_files',side_effect=search),patch.object(service.docmost,'search',return_value=notes) as dm,patch.object(google_drive,'search',return_value=drive) as gd:
            rows=[r for start in range(0,13,3) for r in service.search('sample',limit=3,offset=start)['results']]
            self.assertEqual(len(rows),13);self.assertEqual(len({str(r['id']) for r in rows}),13)
            dm.reset_mock();gd.reset_mock();service.search('sample',mode='filename');dm.assert_not_called();gd.assert_not_called()
            self.assertEqual(service.search('sample',share='GoogleDrive',mode='filename')['total'],4);gd.assert_called_once()
    def test_outage_and_disabled_reads(self):
        with patch.object(core,'search_files',return_value={'total':1,'results':[{'id':1}]}),patch.object(service.docmost,'search',return_value=[]),patch.object(google_drive,'search',side_effect=TimeoutError):
            result=service.search('sample');self.assertEqual(result['results'],[{'id':1}]);self.assertIn('unavailable',result['warning'])
        config=settings.load(core.ROOT);config['google_drive']['enabled']=False;settings.save(config)
        with self.assertRaises(ValueError):service.read('gdrive:synthetic')

if __name__=='__main__':unittest.main()
