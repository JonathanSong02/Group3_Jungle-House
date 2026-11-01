"""Opt-in integration against an explicitly disposable LOCAL MySQL 8 server.

Never reads the application's .env / MYSQL_* / DB_* configuration.
Creates and drops only a random jh_memory_test_<uuid> database.
"""
import os
import re
import sys
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from chat_memory_store import ChatMemoryStore, MemoryError


@unittest.skipUnless(os.getenv('JH_MEMORY_TEST_SERVER_IS_DISPOSABLE')=='YES', 'Explicit disposable local MySQL opt-in not provided')
class MySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mysql.connector
        cls.driver = mysql.connector
        cls.config = dict(host='127.0.0.1',port=int(os.environ.get('JH_MEMORY_TEST_MYSQL_PORT','3306')),
                          user=os.environ['JH_MEMORY_TEST_MYSQL_USER'],password=os.environ['JH_MEMORY_TEST_MYSQL_PASSWORD'])
        cls.db = 'jh_memory_test_'+uuid.uuid4().hex
        with cls.driver.connect(**cls.config) as conn:
            with conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE `{cls.db}` CHARACTER SET utf8mb4')
        cls.addClassCleanup(cls.drop_database)
        cls.config['database'] = cls.db
        sql = (Path(__file__).resolve().parents[2]/'mysql'/'20261101_chat_memory.sql').read_text(encoding='utf-8')
        sql = '\n'.join(line for line in sql.splitlines() if not line.strip().startswith('--'))
        with cls.driver.connect(**cls.config) as conn:
            with conn.cursor() as cur:
                for statement in sql.split(';'):
                    if statement.strip():
                        assert statement.strip().startswith('CREATE TABLE IF NOT EXISTS staff_chat_')
                        cur.execute(statement)
        cls.store = ChatMemoryStore(lambda:cls.driver.connect(**cls.config))

    @classmethod
    def drop_database(cls):
        assert re.fullmatch(r'jh_memory_test_[0-9a-f]{32}',cls.db)
        config = {k:v for k,v in cls.config.items() if k!='database'}
        with cls.driver.connect(**config) as conn:
            with conn.cursor() as cur: cur.execute(f'DROP DATABASE `{cls.db}`')

    def test_real_row_lock_rejects_concurrent_turns(self):
        cid = self.store.create(1)['id']
        def claim(rid):
            try:
                self.store.begin(1,cid,rid,'synthetic question',rid)
                return 'accepted'
            except MemoryError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim,['one','two']))
        self.assertCountEqual(results,['accepted','CHAT_BUSY'])

    def test_real_json_invalidation_and_reconnect(self):
        source = self.store.create(1)['id']
        dest = self.store.create(1)['id']
        self.store.begin(1,source,'one','orange ice bin','f')
        self.store.finish(1,source,'one',{'answer':'synthetic KB'})
        other = ChatMemoryStore(lambda:self.driver.connect(**self.config))
        self.assertEqual(len(other.messages(1,source)),2)
        evidence = other.recall(1,dest,'what did I ask about ice bin last time')
        self.store.begin(1,dest,'recall','earlier question','r')
        self.store.finish(1,dest,'recall',{'answer':'copied question','source':'personal_chat_recall','memory_evidence':evidence})
        self.store.delete(1,source)
        self.assertEqual([r['role'] for r in other.messages(1,dest)],['user'])


if __name__=='__main__': unittest.main()
