"""T01-T10: SQLite + Flask + actual extracted chat/provider pipeline.

Synthetic data/providers only. Never import app.py, read .env or contact MySQL.
"""
import json
import unittest
from unittest.mock import patch
from flask import Flask, g, jsonify, request
from chat_memory_api import register_chat_memory
from chat_memory_store import select_cross_history, topic_terms
import test_persistent_chat as fixtures
import test_chat_memory as chat_fixture


class ImplicitRecallTests(unittest.TestCase):
    def setUp(self):
        fixtures.PersistenceTests.setUp(self)
        old_scope = chat_fixture.env.copy()
        self.addCleanup(lambda: (chat_fixture.env.clear(), chat_fixture.env.update(old_scope)))
        # Reuse existing AST-extracted production functions and mock dependencies.
        chat_fixture.ChatRouteTests.setUp(self)
        self.scope = chat_fixture.env
        self.app = Flask(__name__)
        self.app.testing = True

        @self.app.before_request
        def identity_fixture():
            g.owner = int(request.headers.get('X-Test-Owner', '1'))

        self.scope.update(g=g, request=request, jsonify=jsonify, current_auth_user_id=lambda:g.owner)
        self.store_api = register_chat_memory(self.app,lambda:fixtures.Connection(self.path),
                                              lambda:g.owner,self.scope['chat'])
        self.client = self.app.test_client()
        self.used = True
        self.prompts = []
        self.set_kb('Ice bin cleaning', 'Current KB: wash with the approved cleaning solution.')

        def provider(prompt, **kwargs):
            self.prompts.append(prompt)
            evidence = list(getattr(g,'personal_chat_cross_history',[]))
            return json.dumps({'answered':True,'answer':self.kb_answer,'sourceTitle':self.kb_title,
                               'memoryMessageIds':[r['message_id'] for r in evidence] if self.used else []})

        self.provider.generate_ai_reply.side_effect = provider
        self.source = self.store.create(1)['id']
        self.seed(self.source,'Where should I store the orange ice bin?')
        self.counter = 0

    def set_kb(self, title, answer):
        self.kb_title, self.kb_answer = title, answer
        self.scope['build_ai_chat_context'].return_value = ('### '+title+'\n'+answer,[{'title':title,'article_id':11}])

    def seed(self, cid, question, rid='seed', owner=1):
        self.store.begin(owner,cid,rid,question,rid)
        self.store.finish(owner,cid,rid,{'answer':'OUTDATED AI POLICY: never clean equipment.','source':'old_ai'})

    def ask(self, question, owner=1, **extra):
        self.counter += 1
        return self.client.post('/api/chat',json={'conversation_id':self.cid,'request_id':f'test{self.counter}',
            'question':question,**extra},headers={'X-Test-Owner':str(owner)})

    def test_T01_explicit_recall_keeps_original_evidence(self):
        response = self.ask('What did I ask about the ice bin last time?')
        self.assertEqual(response.status_code,200)
        self.assertIn('Where should I store the orange ice bin?',response.json['answer'])
        self.provider.generate_ai_reply.assert_not_called()

    def test_T02_implicit_topic_reaches_actual_grounded_provider(self):
        response = self.ask('How should I clean the ice bin?')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['answer'],self.kb_answer)
        self.assertEqual(response.json['memory_diagnostics']['cross_chat_candidates'],1)
        self.assertEqual(response.json['memory_diagnostics']['cross_chat_messages'],1)
        self.assertTrue(response.json['memory_context_used'])
        self.assertIn('Where should I store the orange ice bin?',self.prompts[0])
        self.assertEqual(self.scope['process_question'].call_args.kwargs['search_question'],'How should I clean the ice bin?')
        self.assertEqual(self.scope['process_question'].call_args.kwargs['context']['title'],'')
        self.provider.generate_ai_reply.assert_called_once()
        self.provider._call_ai_provider_once.assert_not_called()  # no extra resolver call

    def test_T03_membership_does_not_inject_ice_bin(self):
        self.set_kb('Member registration','Current KB: use the member registration form.')
        response = self.ask('How do I register a member?')
        self.assertEqual(response.json['memory_diagnostics']['cross_chat_candidates'],0)
        self.assertNotIn('orange ice bin',self.prompts[0])
        self.assertNotIn('memory_evidence',response.json)
        self.assertEqual(response.json['answer'],self.kb_answer)

    def test_T04_unrelated_current_turn_does_not_hide_old_topic(self):
        self.set_kb('Member registration','Current KB: use the member registration form.')
        self.ask('How do I register a member?')
        self.set_kb('Ice bin cleaning','Current KB: clean using the approved solution.')
        response = self.ask('How should I clean the ice bin?')
        self.assertEqual(response.json['memory_diagnostics']['cross_chat_candidates'],1)
        self.assertEqual(response.json['memory_evidence'][0]['conversation_id'],self.source)
        # The same-chat resolver sees only this chat, never automatically spliced old chats.
        self.assertEqual(self.scope['process_question'].call_args.kwargs['question'],'How should I clean the ice bin?')

    def test_T05_different_equipment_or_colour_is_not_same_object(self):
        for question in ['How should I clean the ice machine?', 'How should I clean the blue ice bin?',
                         'How should I clean the ice bucket?', 'How should I clean it?']:
            with self.subTest(question=question):
                self.assertEqual(self.store.recall(1,self.cid,question),[])

    def test_T06_other_staff_cannot_retrieve_candidates(self):
        other = self.store.create(2)['id']
        self.assertEqual(self.store.recall(2,other,'How should I clean the ice bin?'),[])
        denied = self.ask('How should I clean the ice bin?',owner=2)
        self.assertEqual(denied.status_code,404)

    def test_T07_delete_invalidates_implicit_derived_answer(self):
        self.ask('How should I clean the ice bin?')
        self.store.delete(1,self.source)
        self.assertEqual([r['role'] for r in self.store.messages(1,self.cid)],['user'])
        self.assertEqual(self.store.recall(1,self.cid,'How should I clean the ice bin?'),[])

    def test_T08_old_AI_never_enters_prompt_and_KB_wins(self):
        response = self.ask('How should I clean the ice bin?')
        self.assertEqual(response.json['answer'],self.kb_answer)
        self.assertNotIn('OUTDATED AI POLICY',self.prompts[0])
        self.assertIn('current Knowledge Base is the only authority',self.prompts[0])
        self.assertIn('Do not assume an earlier\nissue was resolved',self.prompts[0])

    def test_T09_EN_ZH_BM_topics_find_same_original_question(self):
        for question in ['How should I clean the ice bin?', '冰桶应该怎么清洗？', '冰桶要怎样清理？',
                         'Bagaimana cara membersihkan tong ais?', 'Macam mana nak cuci tong ais?']:
            with self.subTest(question=question):
                matches = self.store.recall(1,self.cid,question)
                self.assertEqual(len(matches),1)
                self.assertEqual(matches[0]['conversation_id'],self.source)

    def test_T10_retrieval_failure_falls_back_to_normal_KB_answer(self):
        with patch.object(self.store_api,'recall',side_effect=RuntimeError('private storage detail')):
            response = self.ask('How should I clean the ice bin?')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['answer'],self.kb_answer)
        self.assertEqual(response.json['memory_diagnostics']['cross_chat_status'],'unavailable')
        self.assertNotIn('PREVIOUS_CHAT_USER_DATA',self.prompts[0])
        self.assertNotIn('private storage detail',response.get_data(as_text=True))

    def test_candidates_can_be_ignored_for_self_contained_answer(self):
        self.used = False
        response = self.ask('How should I clean the ice bin?')
        self.assertEqual(response.json['memory_diagnostics']['cross_chat_candidates'],1)
        self.assertEqual(response.json['memory_diagnostics']['cross_chat_messages'],0)
        self.assertNotIn('memory_context_used',response.json)
        self.assertNotIn('memory_evidence',response.json)

    def test_competing_equipment_candidates_are_not_silently_chosen(self):
        for i in range(4): self.seed(self.source,'Where should I store the orange ice bin?',rid=f'orange{i}')
        self.seed(self.source,'Where should I store the blue ice bin?',rid='blue')
        candidates = self.store.recall(1,self.cid,'How should I clean the ice bin?')
        self.assertTrue(candidates)
        self.assertEqual(select_cross_history(candidates,'How should I clean the ice bin?'),[])
        response = self.ask('How should I clean the ice bin?')
        self.assertNotIn('PREVIOUS_CHAT_USER_DATA',self.prompts[0])
        self.assertNotIn('memory_context_used',response.json)

    def test_new_chat_subjectless_question_does_not_inherit_active_topic(self):
        self.assertEqual(topic_terms('How should I clean it?'),set())
        self.assertEqual(self.store.recall(1,self.cid,'How should I clean it?'),[])

    def test_topics_are_not_limited_to_ice_bin(self):
        for i,(original,question) in enumerate([
            ('Where should I store honey?','What are the benefits of honey?'),
            ('Where is the receipt printer?','How should I clean the receipt printer?'),
            ('How should I open the kiosk?','How should I clean the kiosk?'),
        ]):
            with self.subTest(question=question):
                self.seed(self.source,original,rid=f'topic{i}')
                matches = self.store.recall(1,self.cid,question)
                self.assertTrue(matches)
                self.assertEqual(matches[0]['content'],original)
        self.assertEqual(self.store.recall(1,self.cid,'How should I clean the label printer?'),[])

    def test_automatic_rejection_ticket_does_not_copy_cross_chat_details(self):
        self.set_kb('Ice bin cleaning','Current KB answer with a PRIVATE OLD CHAT QUOTATION.')
        response = self.ask('How should I clean the ice bin?')
        self.assertTrue(response.json['memory_context_used'])
        self.ask('not this')
        self.scope['create_escalation'].assert_called_once()
        ticket_result = self.scope['create_escalation'].call_args.args[1]
        self.assertNotIn('PRIVATE OLD CHAT QUOTATION',json.dumps(ticket_result))

    def test_deletion_during_implicit_generation_prevents_late_commit(self):
        original_provider = self.provider.generate_ai_reply.side_effect
        def delete_source(prompt, **kwargs):
            answer = original_provider(prompt, **kwargs)
            self.store.delete(1,self.source)
            return answer
        self.provider.generate_ai_reply.side_effect = delete_source
        response = self.ask('How should I clean the ice bin?')
        self.assertEqual(response.status_code,404)
        self.assertFalse(response.json['persistence_saved'])
        self.assertEqual([r['role'] for r in self.store.messages(1,self.cid)],['user'])

    def test_provider_cannot_fabricate_memory_ID_or_KB_source(self):
        candidates = self.store.recall(1,self.cid,'How should I clean the ice bin?')
        with self.app.test_request_context('/api/chat'):
            g.personal_chat, g.personal_chat_cross_history = True, candidates
            for extra in [{'sourceTitle':'Invented source','memoryMessageIds':[]},
                          {'sourceTitle':self.kb_title,'memoryMessageIds':['invented-message']},
                          {'sourceTitle':self.kb_title,'memoryMessageIds':'invalid'}]:
                with self.subTest(extra=extra):
                    g.personal_chat_cross_used = []
                    self.provider.generate_ai_reply.side_effect = lambda *a,**kw:json.dumps({'answered':True,'answer':'untrusted',**extra})
                    self.assertIsNone(self.scope['answer_question_with_ai_provider']('How should I clean the ice bin?'))
                    self.assertEqual(g.personal_chat_cross_used,[])


if __name__=='__main__': unittest.main()
