"""Synthetic SQLite transaction fixtures; no app import, network or .env.

SQLite adapter tests application transactions, not MySQL dialect/lock semantics.
Run: python -m unittest discover -s backend/src -p test_persistent_chat.py
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from chat_memory_store import ChatMemoryStore, MemoryError, select_history, is_recall, request_fingerprint


class Cursor:
    def __init__(self, conn):
        self.cur = conn.cursor()

    def execute(self, sql, args=()):
        sql = sql.replace('%s','?').replace(' FOR UPDATE','').replace('UTC_TIMESTAMP(6)', 'CURRENT_TIMESTAMP')
        sql = sql.replace("IF(title='New Chat',?,title)", "CASE WHEN title='New Chat' THEN ? ELSE title END")
        sql = sql.replace('LEFT(m.content,1000)','substr(m.content,1,1000)')
        return self.cur.execute(sql,args)

    def fetchone(self):
        row = self.cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(r) for r in self.cur.fetchall()]

    def close(self):
        self.cur.close()


class Connection:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        def json_search(value, mode, needle, *path):
            if not value: return None
            data = json.loads(value)
            return '$' if any(e.get('conversation_id')==needle for e in data.get('memory_evidence',[])) else None
        self.conn.create_function('JSON_SEARCH', -1, json_search)

    def cursor(self, **kwargs):
        return Cursor(self.conn)

    def commit(self): self.conn.commit()
    def rollback(self): self.conn.rollback()
    def close(self): self.conn.close()


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name)/'memory.db')
        with closing(sqlite3.connect(self.path)) as c:
            c.executescript('''
            CREATE TABLE staff_chat_session(conversation_id TEXT PRIMARY KEY,owner_id INTEGER,title TEXT,next_sequence INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,deleted_at TEXT);
            CREATE TABLE staff_chat_request(conversation_id TEXT,request_id TEXT,fingerprint TEXT,status TEXT,response_json TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(conversation_id,request_id));
            CREATE TABLE staff_chat_message(message_id TEXT PRIMARY KEY,conversation_id TEXT,sequence_no INTEGER,request_id TEXT,role TEXT,content TEXT,metadata_json TEXT,provenance TEXT DEFAULT 'server_original',created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(conversation_id,sequence_no),UNIQUE(conversation_id,request_id,role));
            CREATE TABLE escalation_evidence(snapshot TEXT);
            CREATE TABLE staff_chat_attachment(path TEXT PRIMARY KEY,conversation_id TEXT);
            CREATE TABLE escalation(escalation_id INTEGER PRIMARY KEY,image_url TEXT,asked_by INTEGER);
            CREATE TABLE escalation_context(escalation_id INTEGER,context_json TEXT);
            INSERT INTO escalation_evidence VALUES ('immutable original');
            ''')
            c.commit()
        self.store = ChatMemoryStore(lambda: Connection(self.path))
        self.cid = self.store.create(1)['id']

    def turn(self, question='orange ice bin storage', rid='r1', answer='Use latest KB'):
        self.store.begin(1,self.cid,rid,question,request_fingerprint(question,{}))
        payload = {'answer':answer,'source':'kb','context':{'title':'Ice bin'}}
        self.store.finish(1,self.cid,rid,payload)
        return payload

    def test_MEM09_restart_and_MEM10_other_device(self):
        self.turn()
        other = ChatMemoryStore(lambda: Connection(self.path))
        self.assertEqual(len(other.messages(1,self.cid)),2)
        self.assertEqual(other.list(1)['sessions'][0]['id'],self.cid)

    def test_MEM08_and_MEM24_owner_checks(self):
        self.turn()
        for operation in [lambda:self.store.messages(2,self.cid),lambda:self.store.rename(2,self.cid,'attack'),lambda:self.store.delete(2,self.cid),lambda:self.store.begin(2,self.cid,'evil','x','x'),lambda:self.store.recall(2,self.cid,'what did I ask about ice bin last time')]:
            with self.subTest(operation=operation), self.assertRaises(MemoryError) as error:
                operation()
            self.assertEqual(error.exception.status,404)
        self.assertEqual(self.store.list(2)['sessions'],[])

    def test_MEM11_delete_and_MEM12_independent_snapshot(self):
        self.turn()
        other = self.store.create(1)['id']
        self.store.delete(1,self.cid)
        self.assertEqual(self.store.recall(1,other,'what did I ask about ice bin last time'),[])
        with self.assertRaises(MemoryError): self.store.messages(1,self.cid)
        with closing(sqlite3.connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM staff_chat_message').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT snapshot FROM escalation_evidence').fetchone()[0],'immutable original')

    def test_MEM17_idempotent_retry(self):
        payload = self.turn()
        self.assertEqual(self.store.begin(1,self.cid,'r1','orange ice bin storage',request_fingerprint('orange ice bin storage',{})),payload)
        self.assertEqual(len(self.store.messages(1,self.cid)),2)

    def test_changed_retry_conflicts(self):
        self.turn()
        with self.assertRaises(MemoryError): self.store.begin(1,self.cid,'r1','different','different')

    def test_MEM19_concurrent_request_rejected(self):
        self.store.begin(1,self.cid,'r1','first','f')
        with self.assertRaises(MemoryError) as error: self.store.begin(1,self.cid,'r2','second','s')
        self.assertEqual(error.exception.code,'CHAT_BUSY')

    def test_MEM16_failure_stores_no_fabricated_assistant(self):
        self.store.begin(1,self.cid,'r1','question','f')
        self.store.finish(1,self.cid,'r1',{},'failed')
        self.assertEqual([r['role'] for r in self.store.messages(1,self.cid)],['user'])

    def test_cancel_releases_busy_without_late_commit(self):
        self.store.begin(1,self.cid,'r1','question','f')
        self.store.finish(1,self.cid,'r1',{},'cancelled')
        with self.assertRaises(MemoryError): self.store.finish(1,self.cid,'r1',{'answer':'late'})
        self.store.begin(1,self.cid,'r2','next','n')

    def test_delete_inflight_does_not_resurrect(self):
        self.store.begin(1,self.cid,'r1','question','f')
        self.store.delete(1,self.cid)
        with self.assertRaises(MemoryError): self.store.finish(1,self.cid,'r1',{'answer':'late'})
        with self.assertRaises(MemoryError): self.store.begin(1,self.cid,'r2','question','f')

    def test_delete_invalidates_copied_recall_and_retry(self):
        self.turn()
        dest = self.store.create(1)['id']
        evidence = self.store.recall(1,dest,'what did I ask about ice bin last time')
        self.store.begin(1,dest,'recall','what did I ask','f')
        self.store.finish(1,dest,'recall',{'answer':'copied private question','source':'personal_chat_recall','memory_evidence':evidence})
        self.store.delete(1,self.cid)
        self.assertEqual([r['role'] for r in self.store.messages(1,dest)],['user'])
        with self.assertRaises(MemoryError): self.store.begin(1,dest,'recall','what did I ask','f')

    def test_delete_source_while_recall_inflight(self):
        self.turn()
        dest = self.store.create(1)['id']
        evidence = self.store.recall(1,dest,'what did I ask about ice bin last time')
        self.store.begin(1,dest,'recall','what did I ask','f')
        self.store.delete(1,self.cid)
        with self.assertRaises(MemoryError):
            self.store.finish(1,dest,'recall',{'answer':'late','memory_evidence':evidence})

    def test_MEM05_new_chat_has_no_active_context(self):
        self.turn()
        self.assertEqual(self.store.messages(1,self.store.create(1)['id']),[])

    def test_MEM06_recall_and_MEM07_unrelated(self):
        self.turn()
        other = self.store.create(1)['id']
        evidence = self.store.recall(1,other,'what did I ask about ice bin last time')
        self.assertEqual(evidence[0]['content'],'orange ice bin storage')
        self.assertEqual(self.store.recall(1,other,'membership question'),[])
        self.assertEqual(self.store.recall(1,other,'what did I ask about membership last time'),[])

    def test_MEM14_missing_memory_is_empty(self):
        self.assertEqual(self.store.recall(1,self.cid,'what did I ask about ice bin last time'),[])

    def test_chronological_sequence(self):
        self.turn(rid='1'); self.turn(rid='2')
        self.assertEqual([r['sequence_no'] for r in self.store.messages(1,self.cid)],[1,2,3,4])

    def test_title_update(self):
        self.store.rename(1,self.cid,'renamed')
        self.assertEqual(self.store.list(1)['sessions'][0]['title'],'renamed')

    def test_MEM21_attachment_metadata(self):
        self.store.begin(1,self.cid,'r1','image','f')
        self.store.finish(1,self.cid,'r1',{'answer':'step','uploaded_image_url':'/static/uploads/chat/synthetic.png','steps':['step 1']})
        rows = self.store.messages(1,self.cid)
        self.assertEqual(json.loads(rows[0]['metadata_json'])['image_files'],['/static/uploads/chat/synthetic.png'])
        self.assertEqual(json.loads(rows[1]['metadata_json'])['steps'],['step 1'])

    def test_attachment_ownership_and_independent_ticket_access(self):
        path = '/static/uploads/chat/memory_synthetic.png'
        self.store.attach(1,self.cid,path)
        self.assertTrue(self.store.attachment_allowed(1,path))
        self.assertFalse(self.store.attachment_allowed(2,path))
        self.assertFalse(self.store.attachment_allowed(2,path,approver=True))
        self.store.delete(1,self.cid)
        self.assertFalse(self.store.attachment_allowed(1,path))
        with self.store.transaction() as cur:
            cur.execute('INSERT INTO escalation(escalation_id,image_url,asked_by) VALUES (%s,%s,%s)', (1,path,1))
        self.assertTrue(self.store.attachment_allowed(1,path))
        self.assertFalse(self.store.attachment_allowed(2,path))
        self.assertTrue(self.store.attachment_allowed(2,path,approver=True))

    def test_MEM20_cross_chat_evidence_matches_each_language(self):
        dest = self.store.create(1)['id']
        for i,(question,recall) in enumerate([('冰桶存放','上次冰桶问了什么'),('tong ais oren','kali lepas saya tanya tong ais')]):
            self.turn(question=question,rid=f'language{i}')
            self.assertTrue(self.store.recall(1,dest,recall))


class SelectionTests(unittest.TestCase):
    def test_MEM01_older_relevant_evidence(self):
        rows = [{'sequence_no':i,'role':'user','content':'ice bin' if i==1 else 'membership'} for i in range(1,60)]
        self.assertEqual(select_history(rows,'ice bin')[0]['content'],'ice bin')
        self.assertLessEqual(len(select_history(rows,'ice bin')),16)

    def test_MEM20_recall_languages(self):
        for text in ['what did I ask last time','上次冰桶问了什么','kali lepas saya tanya tong ais']:
            self.assertTrue(is_recall(text))

    def test_budget(self):
        rows = [{'sequence_no':i,'role':'user','content':'x'*2000} for i in range(20)]
        history = select_history(rows,'x',2000)
        self.assertLessEqual(sum(len(r['content']) for r in history),2000)


if __name__=='__main__': unittest.main()
