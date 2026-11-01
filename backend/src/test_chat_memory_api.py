"""Real Flask request/JSON integration, SQLite-only storage and synthetic identity.

No main app import; session/CSRF behavior remains covered in test_chat_memory.
"""
import unittest
from unittest.mock import patch
from flask import Flask, g, jsonify, request
from chat_memory_api import register_chat_memory
import test_persistent_chat as fixtures


class ApiTests(unittest.TestCase):
    def setUp(self):
        fixtures.PersistenceTests.setUp(self)
        self.app = Flask(__name__)
        self.app.testing = True
        self.calls = []

        @self.app.before_request
        def identity_fixture():
            # This header is a fixture only, never a production auth mechanism.
            g.owner = int(request.headers.get('X-Test-Owner','1'))

        def generate():
            self.calls.append(list(g.personal_chat_history))
            return jsonify(answer='Synthetic grounded answer', source='kb', context={'title':'Ice bin'})

        self.api_store = register_chat_memory(self.app,lambda:fixtures.Connection(self.path),lambda:g.owner,generate)
        self.client = self.app.test_client()
        self.payload = {'conversation_id':self.cid,'request_id':'r1','question':'orange ice bin storage',
                        'user_id':9999,'history':[{'role':'user','content':'fabricated client history'}]}

    def post(self, payload=None, owner=1):
        return self.client.post('/api/chat',json=payload or self.payload,headers={'X-Test-Owner':str(owner)})

    def test_spoofed_identity_and_client_history_ignored(self):
        response = self.post()
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json['persistence_saved'])
        self.assertEqual(self.calls,[[]])
        self.assertEqual(len(self.store.messages(1,self.cid)),2)
        self.assertIn('no-store',response.headers['Cache-Control'])

    def test_MEM02_followup_passes_server_evidence(self):
        self.post()
        self.post({**self.payload,'request_id':'r2','question':'What about the blue one?'})
        self.assertEqual(self.calls[1][0]['content'],'orange ice bin storage')
        self.assertEqual(self.calls[1][1]['content'],'Synthetic grounded answer')

    def test_MEM24_direct_api_ownership(self):
        for method,path,body in [('get',f'/api/chat/sessions/{self.cid}',None),
                                 ('patch',f'/api/chat/sessions/{self.cid}',{'title':'attack'}),
                                 ('delete',f'/api/chat/sessions/{self.cid}',None),
                                 ('post','/api/chat',self.payload)]:
            response = getattr(self.client,method)(path,json=body,headers={'X-Test-Owner':'2'})
            self.assertEqual(response.status_code,404)
        self.assertEqual(self.calls,[])

    def test_MEM17_duplicate_http_retry_does_not_call_provider(self):
        first = self.post()
        second = self.post()
        self.assertEqual(first.json,second.json)
        self.assertEqual(len(self.calls),1)

    def test_history_is_server_backed(self):
        self.post()
        rows = self.client.get('/api/chat/history').json['history']
        self.assertEqual(rows[0]['question'],self.payload['question'])
        self.assertEqual(self.client.get('/api/chat/history',headers={'X-Test-Owner':'2'}).json['history'],[])

    def test_storage_write_failure_does_not_call_provider_or_claim_saved(self):
        with patch.object(self.api_store,'begin',side_effect=RuntimeError('private SQL detail')):
            response = self.post()
        self.assertEqual(response.status_code,503)
        self.assertFalse(response.json['persistence_saved'])
        self.assertNotIn('private SQL',response.get_data(as_text=True))
        self.assertEqual(self.calls,[])

    def test_final_write_failure_does_not_claim_saved(self):
        with patch.object(self.api_store,'finish',side_effect=RuntimeError('private SQL')):
            response = self.post()
        self.assertEqual(response.status_code,503)
        self.assertFalse(response.json['persistence_saved'])
        self.assertEqual(len(self.store.messages(1,self.cid)),1)

    def test_MEM15_optional_cross_chat_failure(self):
        with patch.object(self.api_store,'recall',side_effect=RuntimeError('private')):
            response = self.post({**self.payload,'question':'what did I ask about ice bin last time'})
        self.assertEqual(response.status_code,200)
        self.assertIn('temporarily unavailable',response.json['answer'])
        self.assertEqual(response.json['memory_evidence'],[])

    def test_pending_after_refresh_and_owner_cancel(self):
        self.store.begin(1,self.cid,'pending','question','f')
        self.assertEqual(self.client.get(f'/api/chat/sessions/{self.cid}').json['pending_requests'],['pending'])
        denied = self.client.post(f'/api/chat/sessions/{self.cid}/requests/pending/cancel',headers={'X-Test-Owner':'2'})
        self.assertEqual(denied.status_code,404)
        response = self.client.post(f'/api/chat/sessions/{self.cid}/requests/pending/cancel')
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get(f'/api/chat/sessions/{self.cid}').json['pending_requests'],[])

    def test_MEM20_empty_recall_all_languages(self):
        for i,(lang,q,expected) in enumerate([('en','what did I ask about ice bin last time','No reliable'),('zh','上次冰桶问了什么','没有找到'),('ms','kali lepas saya tanya tong ais','Tiada')]):
            response = self.post({**self.payload,'request_id':f'lang{i}','language':lang,'question':q})
            self.assertIn(expected,response.json['answer'])


if __name__=='__main__': unittest.main()
