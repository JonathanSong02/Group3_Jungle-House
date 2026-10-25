"""Real Flask auth/CSRF/routes + isolated SQL; provider and uploads mocked."""
import io
import os
import unittest
from unittest.mock import patch

import test_chat_memory as fixtures


class ChatAPITests(unittest.TestCase):
    def setUp(self):
        fixtures.ChatMemoryTests.setUp(self)
        os.environ['NOTION_AUTO_SYNC_ENABLED'] = 'false'
        os.environ.setdefault('FLASK_SECRET_KEY', 'isolated-test-secret-not-a-real-key-12345')
        import app
        self.backend = app
        with self.store.transaction() as (conn, c):
            c.execute('CREATE TABLE roles(role_id INT,role_name TEXT)')
            c.execute("INSERT INTO roles VALUES(1,'staff'),(2,'teamlead')")
            c.execute('CREATE TABLE users(user_id INT,full_name TEXT,email TEXT,password_hash TEXT,status TEXT,created_at TEXT,role_id INT)')
            c.execute("INSERT INTO users VALUES(1,'Mock Staff','staff@example.test','hash','active','2026-01-01',1),"
                      "(2,'Other Staff','other@example.test','hash','active','2026-01-01',1),"
                      "(3,'Mock Lead','lead@example.test','hash','active','2026-01-01',2)")
            for column in ('manual_answer TEXT', 'handled_by INT', 'created_at TEXT', 'updated_at TEXT',
                           'resolved_at TEXT', 'deleted_at TEXT', 'deleted_by INT'):
                c.execute('ALTER TABLE escalation ADD COLUMN ' + column)
            c.execute('CREATE TABLE review_queue (review_id INT,escalation_id INT,status TEXT,reviewer_comment TEXT,reviewed_at TEXT,published_at TEXT)')
        self.db_patch = patch.object(app, 'get_db_connection', lambda: fixtures.Connection(self.path))
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.provider = patch.object(app.ai_provider_service, 'chat_generator',
                                     return_value=(self.generate, 8192, 1024))
        self.provider.start()
        self.addCleanup(self.provider.stop)
        self.kb = patch.object(app, 'build_ai_chat_context', side_effect=lambda *a, **kw: self.knowledge(a[0]))
        self.kb.start()
        self.addCleanup(self.kb.stop)
        self.approved = patch.object(app, 'search_similar_question', return_value=None)
        self.approved.start()
        self.addCleanup(self.approved.stop)
        self.client = app.app.test_client()
        self.login(1)

    def tearDown(self):
        fixtures.ChatMemoryTests.tearDown(self)

    generate = fixtures.ChatMemoryTests.generate
    knowledge = fixtures.ChatMemoryTests.knowledge

    def login(self, owner):
        with self.client.session_transaction() as session:
            session['user_id'] = owner
            session['password_fingerprint'] = self.backend.password_session_fingerprint('hash')
            session['csrf_token'] = 'mock-csrf'

    def post(self, path, data):
        return self.client.post(path, json=data, headers={'X-CSRF-Token': 'mock-csrf'})

    def test_auth_csrf_employee_isolation_and_relogin_reopen(self):
        path = '/api/chat/sessions/chat-a/messages'
        bad_csrf = self.client.post(path, json={'question': 'x', 'request_id': 'x'})
        self.assertEqual(bad_csrf.status_code, 403)
        result = self.post(path, {'question': 'Ice bin put where when closing?', 'request_id': 'one'})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json['grounded'])
        self.login(2)
        self.assertEqual(self.client.get('/api/chat/sessions/chat-a').status_code, 404)
        self.assertEqual(self.client.get('/api/chat/sessions').json, [])
        self.assertEqual(self.post(path, {'question': 'attack', 'request_id': 'two'}).status_code, 404)
        self.login(1)
        reopened = self.client.get('/api/chat/sessions/chat-a')
        self.assertEqual(reopened.json['turns'][0]['question'], 'Ice bin put where when closing?')
        self.assertEqual(reopened.json['turns'][0]['message_id'], result.json['message_id'])

    def test_teamlead_reads_exact_saved_latest_question_and_fragments(self):
        result = self.post('/api/chat/sessions/chat-a/messages',
                           {'question': 'Where should the plastic bag go when closing?', 'request_id': 'one'})
        self.assertEqual(result.status_code, 200)
        # Staff cannot inspect the Team Lead queue.
        self.assertEqual(self.client.get('/api/escalations').status_code, 403)
        self.login(3)
        queue = self.client.get('/api/escalations')
        self.assertEqual(queue.status_code, 200)
        ticket = queue.json[0]
        self.assertEqual(ticket['question'], 'Where should the plastic bag go when closing?')
        self.assertEqual(ticket['chat_context']['latest_message_id'], result.json['message_id'])
        self.assertEqual(ticket['chat_context']['transcript'][0]['question'], ticket['question'])

    def test_duplicate_api_response_and_cancel_is_owner_scoped(self):
        payload = {'question': 'Where does plastic bag go?', 'request_id': 'one'}
        path = '/api/chat/sessions/chat-a/messages'
        first = self.post(path, payload)
        second = self.post(path, payload)
        self.assertEqual(first.json, second.json)
        pending, _ = self.store.begin(1, 'chat-a', 'two', 'Pending question', first.json['message_id'])
        self.login(2)
        self.assertEqual(self.post('/api/chat/sessions/chat-a/cancel', {'request_id': 'two'}).status_code, 404)
        self.login(1)
        stopped = self.post('/api/chat/sessions/chat-a/cancel', {'request_id': 'two'})
        self.assertEqual(stopped.json['source'], 'cancelled')
        with self.assertRaises(Exception):
            self.store.finish(1, pending, dict(issue_id=pending['message_id']), {}, [], True)

    def test_missing_provider_retains_question_and_exposes_no_secrets(self):
        from chat_memory import ChatError
        with patch.object(self.backend.ai_provider_service, 'chat_generator',
                          side_effect=ChatError('Configure CHAT_CONTEXT_TEST in backend/src/.env.', 503)):
            response = self.post('/api/chat/sessions/chat-a/messages',
                                 {'question': 'Important original question', 'request_id': 'one'})
        self.assertEqual(response.status_code, 503)
        turns = self.store.read(1, 'chat-a')[1]
        self.assertEqual(turns[0]['original_question'], 'Important original question')
        self.assertEqual(turns[0]['status'], 'failed')

    def test_attachment_retry_reuses_saved_file_and_message(self):
        path = '/api/chat/sessions/chat-a/messages'
        with patch.object(self.backend, 'save_chat_image', return_value=('/static/uploads/chat/mock.png', 'image/png')) as upload, \
             patch.object(self.backend, 'get_local_image_path_from_url', return_value=None):
            responses = []
            for _ in range(2):
                responses.append(self.client.post(path, data={'question': 'Where should plastic bag go?', 'request_id': 'image',
                                                              'attachment': (io.BytesIO(b'mock image'), 'mock.png')},
                                                   headers={'X-CSRF-Token': 'mock-csrf'}))
        self.assertEqual(responses[0].status_code, 200)
        self.assertEqual(responses[0].json['message_id'], responses[1].json['message_id'])
        upload.assert_called_once()

    def test_teamlead_stale_answer_is_rejected_after_employee_correction(self):
        first = self.post('/api/chat/sessions/chat-a/messages',
                          {'question': 'Where should plastic bag go?', 'request_id': 'one'}).json
        self.model_resolutions.append(dict(fixtures.resolution('Where should BLUE plastic bag go?'),
                                           relation='correction', same_issue_id=first['issue_id']))
        second = self.post('/api/chat/sessions/chat-a/messages',
                           {'question': 'Correction, the blue bag.', 'request_id': 'two',
                            'parent_message_id': first['message_id']})
        self.assertEqual(second.status_code, 200)
        self.login(3)
        rejected = self.client.put('/api/escalations/' + str(first['escalation_id']) + '/answer',
                                   json={'manual_answer': 'Outdated answer', 'expected_message_id': first['message_id']},
                                   headers={'X-CSRF-Token': 'mock-csrf'})
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.json['code'], 'ESCALATION_STALE')
