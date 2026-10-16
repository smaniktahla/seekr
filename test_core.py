import unittest,tempfile,os
from pathlib import Path
import core

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); core.DB=self.tmp.name+'/test.sqlite';core.ROOT=Path(self.tmp.name)/'archive'
        for s in core.SHARES: (core.ROOT/s).mkdir(parents=True)
        core.init()
        with core.connect() as db:
            db.execute("INSERT INTO files(path,share,category,name,text,state) VALUES(?,?,?,?,?,?)",['Documents/budget.xlsx','Documents','documents','budget.xlsx','Sheet: Tuition\nB12=retirement reconciliation','indexed'])
            db.execute("INSERT INTO files(path,share,category,name,metadata,state) VALUES(?,?,?,?,?,?)",['Music/budget.mp3','Music','music','budget.mp3','Artist: Example','indexed'])
    def tearDown(self): self.tmp.cleanup()
    def test_text_retrieval(self):
        d=core.search_files('retirement reconciliation');self.assertEqual(d['total'],1);self.assertIn('Tuition',core.read_document(d['results'][0]['id'])['text'])
    def test_filter(self):
        self.assertEqual(core.search_files('budget','documents')['total'],1);self.assertEqual(core.search_files('budget',share='Music')['total'],1)
    def test_unc(self): self.assertEqual(core.search_files('retirement')['results'][0]['unc_path'],r'\\truenas\Documents\budget.xlsx')
    def test_fts_update_and_delete(self):
        with core.connect() as db: db.execute("UPDATE files SET text='replaced' WHERE id=1")
        self.assertEqual(core.search_files('retirement')['total'],0)
        self.assertEqual(core.search_files('replaced')['total'],1)
        with core.connect() as db: db.execute('DELETE FROM files WHERE id=1')
        self.assertEqual(core.search_files('replaced')['total'],0)
    def test_traversal(self):
        for p in ['../outside','Documents/../../outside','Documents/node_modules/private.txt']:
            with self.assertRaises(ValueError): core.source(p)
    def test_literal_input(self):
        self.assertEqual(core.search_files('budget OR nonexistent')['total'],0)
        with self.assertRaises(ValueError): core.search_files('***')
    def test_limit(self):
        self.assertEqual(len(core.search_files('budget',limit=1)['results']),1)
        self.assertEqual(core.read_document(1,length=5)['next_offset'],5)
    def test_filename_substrings(self):
        self.assertEqual(core.search_files('udge',mode='filename')['total'],2)
        self.assertEqual(core.search_files('documents udget.xlsx',mode='filename')['total'],1)
        self.assertEqual(core.search_files('retirement',mode='filename')['total'],0)
        self.assertEqual(core.search_files('budget',category_filter='music',mode='filename')['total'],1)
    def test_filename_literal_wildcards(self):
        self.assertEqual(core.search_files('bud%get',mode='filename')['total'],0)
        self.assertEqual(core.search_files('bud_get',mode='filename')['total'],0)

if __name__=='__main__': unittest.main()
