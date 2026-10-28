import unittest,tempfile,os,json,importlib
from pathlib import Path
from unittest.mock import patch
import core,settings
try:
    from fastapi.testclient import TestClient
    import server
except ImportError:TestClient=None

@unittest.skipIf(TestClient is None,'Install service requirements to run API checks')
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=(core.DB,core.ROOT);core.DB=self.tmp.name+'/index.sqlite';core.ROOT=Path(self.tmp.name)/'archive'
        self.env=patch.dict(os.environ,{'ARCHIVE_SETTINGS':self.tmp.name+'/settings.json','ARCHIVE_TOKEN':'synthetic-test-token'});self.env.start()
        self.client=TestClient(importlib.reload(server).app);self.client.__enter__();self.headers={'Authorization':'Bearer synthetic-test-token'}
    def tearDown(self):
        self.client.__exit__(None,None,None);self.env.stop();core.DB,core.ROOT=self.old;self.tmp.cleanup()
    def test_auth_and_settings(self):
        self.assertEqual(self.client.get('/api/settings').status_code,401)
        self.assertEqual(self.client.put('/api/settings',json={}).status_code,401)
        config=self.client.get('/api/settings',headers=self.headers).json()
        config['sources']=[]
        response=self.client.put('/api/settings',json=config,headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['sources'],[])
        self.assertEqual(self.client.get('/api/search?q=sample',headers=self.headers).json()['total'],0)
    def test_invalid_roots_rejected(self):
        config={'sources':[{'id':'Local','path':'relative'}]}
        response=self.client.put('/api/settings',json=config,headers=self.headers)
        self.assertEqual(response.status_code,400);self.assertFalse(settings.config_path().exists())

if __name__=='__main__':unittest.main()
