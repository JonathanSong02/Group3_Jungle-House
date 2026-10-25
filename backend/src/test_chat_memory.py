"""Isolated SQL + mocked AI integration tests. No real staff, APIs or MySQL.

python -m unittest discover -s src -p test_chat_memory.py -v
"""
import json
import re
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from chat_memory import ChatStore, ChatEngine, ChatError, dumps, loads, reply, units, pack_memory


class Cursor:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        sql = sql.replace('%s', '?').replace(' FOR UPDATE', '').replace('INSERT IGNORE', 'INSERT OR IGNORE')
        self.raw.execute(sql, params)
        return self

    def fetchone(self):
        row = self.raw.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.raw.fetchall()]

    @property
    def lastrowid(self):
        return self.raw.lastrowid

    @property
    def rowcount(self):
        return self.raw.rowcount

    def close(self):
        self.raw.close()


class Connection:
    def __init__(self, path):
        self.raw = sqlite3.connect(path)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute('PRAGMA foreign_keys=ON')
        self.raw.execute('BEGIN IMMEDIATE')

    def cursor(self, dictionary=True):
        return Cursor(self.raw.cursor())

    def start_transaction(self):
        pass  # SQLite test adapter starts its transaction when connected.

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def resolution(question, **extra):
    return dict(relation='new', question=question, search_query=question,
                topic='', same_issue_id=None, background_ids=[], ambiguous=False,
                clarification='Which plastic bag, and are you asking where to put it during closing?', **extra)


class ChatMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'test.db')
        db = sqlite3.connect(self.path)
        db.executescript('CREATE TABLE escalation (escalation_id INTEGER PRIMARY KEY AUTOINCREMENT,'
                         'question TEXT,ai_answer TEXT,ai_score REAL,ai_source TEXT,asked_by INT,status TEXT,is_deleted INT DEFAULT 0,image_url TEXT,image_type TEXT);')
        migration = (Path(__file__).resolve().parents[2] / 'mysql/chat_memory.sql').read_text(encoding='utf-8')
        migration = re.sub(r'^\s*INDEX [^\n]+\n', '', migration, flags=re.M)
        migration = re.sub(r'UNIQUE KEY \w+ ', 'UNIQUE ', migration)
        migration = migration.replace(' CHARACTER SET utf8mb4', '')
        migration = re.sub(r',\s*\)', '\n)', migration)
        db.executescript(migration)
        db.close()
        self.store = ChatStore(lambda: Connection(self.path))
        self.store.create(1, 'chat-a')
        self.prompts, self.searches = [], []
        self.model_resolutions = []

    def tearDown(self):
        self.temp.cleanup()

    def generate(self, prompt):
        self.prompts.append(prompt)
        if 'LATEST EMPLOYEE QUESTION:' in prompt:
            question = prompt.split('LATEST EMPLOYEE QUESTION:\n')[-1]
            return dumps(self.model_resolutions.pop(0) if self.model_resolutions else resolution(question))
        # An AI stub answers ice-bin only if the live KB explicitly supports it.
        if 'CURRENT QUESTION:\nIce bin' in prompt and 'Ice bin stays under the counter.' in prompt:
            return dumps(dict(answered=True, answer='Keep it under the counter.', sourceTitle='Closing',
                              confidence=0.85, evidence='Ice bin stays under the counter.'))
        return '{"answered":false}'

    def knowledge(self, query):
        self.searches.append(query)
        return '### Closing\nIce bin stays under the counter.', [{'title': 'Closing', 'article_id': 7}]

    def engine(self, **options):
        return ChatEngine(self.store, self.generate, self.knowledge, **options)

    def send(self, question, rid, chat='chat-a', owner=1, **data):
        parent = self.store.read(owner, chat)[0]['latest_message_id']
        return self.engine().send(owner, chat, dict(question=question, request_id=rid,
                                                  parent_message_id=parent, **data))

    def tickets(self):
        with self.store.transaction() as (_, c):
            c.execute('SELECT * FROM escalation ORDER BY escalation_id')
            return c.fetchall()

    def test_closing_scenario_latest_plastic_bag_is_main_issue(self):
        ice = self.send('Ice bin put where when closing?', 'one')
        self.assertTrue(ice['grounded'])
        self.model_resolutions.append(dict(resolution('Must the cabinet near the storeroom backside door move during closing?'),
                                           relation='followup', background_ids=[ice['message_id']]))
        cabinet = self.send('How about the cabinet near the storeroom backside door?', 'two')
        self.assertTrue(cabinet['escalation_id'])
        self.model_resolutions.append(dict(resolution('Plastic bag during closing'), ambiguous=True,
                                           background_ids=[ice['message_id'], cabinet['message_id']]))
        bag = self.send('How about the plastic bag?', 'three')
        self.assertEqual(bag['source'], 'clarification')
        self.assertEqual(len(self.tickets()), 1)
        self.model_resolutions.append(dict(resolution('Where should the plastic bag be placed during closing?'),
                                           relation='clarification', same_issue_id=bag['issue_id'],
                                           background_ids=[ice['message_id'], cabinet['message_id']]))
        clarified = self.send('The spare plastic bag: where should I put it at closing?', 'four')
        ticket = self.tickets()[-1]
        self.assertIn('plastic bag', ticket['question'])
        details = self.store.escalation_details([ticket['escalation_id']])[ticket['escalation_id']]
        self.assertEqual([x['message_id'] for x in details['transcript']], [bag['message_id'], clarified['message_id']])
        self.assertEqual(details['original_question'], 'The spare plastic bag: where should I put it at closing?')
        self.assertEqual(len(details['background']), 2)
        self.assertEqual(details['latest_message_id'], clarified['message_id'])
        self.assertIn('closing', self.searches[-1])

    def test_new_chat_has_zero_history_and_other_employee_is_denied(self):
        old = self.send('Ice bin put where when closing?', 'one')
        self.store.create(1, 'chat-b')
        self.send('What is the promotion?', 'two', chat='chat-b')
        self.assertNotIn(old['message_id'], self.prompts[-2])
        for action in (lambda: self.store.read(2, 'chat-a'), lambda: self.store.create(2, 'chat-a'),
                       lambda: self.store.hide(2, 'chat-a'),
                       lambda: self.engine().send(2, 'chat-a', {'request_id': 'x', 'question': 'test'})):
            with self.assertRaises(ChatError) as error:
                action()
            self.assertEqual(error.exception.status, 404)
        self.assertEqual(self.store.list(2), [])

    def test_reopen_new_store_preserves_full_originals(self):
        original = '冰桶 closing 要放哪里？'
        self.send(original, 'one')
        reopened = ChatStore(lambda: Connection(self.path))
        self.assertEqual(reopened.read(1, 'chat-a')[1][0]['original_question'], original)
        self.assertEqual(len(reopened.list(1)), 1)

    def test_switch_topic_and_explicit_return(self):
        ice = self.send('Ice bin put where when closing?', 'one')
        self.send('How do I register attendance?', 'two')
        self.assertEqual(self.searches[-1], 'How do I register attendance?')
        self.model_resolutions.append(dict(resolution('Ice bin location during closing'), relation='return',
                                           background_ids=[ice['message_id']]))
        self.send('Back to the ice bin, where does it go?', 'three')
        self.assertEqual(self.searches[-1], 'Ice bin location during closing')
        self.assertIn(ice['message_id'], self.prompts[-2])

    def test_correction_updates_same_issue_ticket_and_retains_original(self):
        first = self.send('Where do bags go at closing?', 'one')
        self.model_resolutions.append(dict(resolution('Where does the BLUE plastic bag go at closing?'),
                                           relation='correction', same_issue_id=first['issue_id']))
        corrected = self.send('Correction: blue plastic bag, not the red bag.', 'two')
        self.assertEqual(first['escalation_id'], corrected['escalation_id'])
        self.assertEqual(len(self.tickets()), 1)
        self.assertIn('BLUE', self.tickets()[0]['question'])
        raw = self.store.read(1, 'chat-a')[1]
        self.assertEqual(raw[0]['original_question'], 'Where do bags go at closing?')

    def test_duplicate_request_is_cached_and_conflicting_body_rejected(self):
        result = self.send('Where does the plastic bag go?', 'same')
        count = len(self.prompts)
        duplicate = self.send('Where does the plastic bag go?', 'same')
        self.assertEqual(result, duplicate)
        self.assertEqual(len(self.prompts), count)
        self.assertEqual(len(self.tickets()), 1)
        with self.assertRaises(ChatError):
            self.send('Different question', 'same')

    def test_async_busy_stale_parent_and_stale_worker_cannot_publish(self):
        turn, _ = self.store.begin(1, 'chat-a', 'one', 'Old question', None)
        with self.assertRaises(ChatError):
            self.store.begin(1, 'chat-a', 'one', 'Old question', None)
        with self.assertRaises(ChatError):
            self.store.begin(1, 'chat-a', 'two', 'New question', turn['message_id'])
        self.store.fail(1, turn)
        new, _ = self.store.begin(1, 'chat-a', 'two', 'New question', turn['message_id'])
        with self.assertRaises(ChatError):
            self.store.finish(1, turn, dict(issue_id=turn['message_id']), reply('old', 'test'), [])
        self.store.finish(1, new, dict(issue_id=new['message_id']), reply('new', 'test'), [])
        with self.assertRaises(ChatError):
            self.store.begin(1, 'chat-a', 'three', 'Stale tab', None)
        self.assertEqual(self.tickets(), [])

    def test_long_chat_compacts_but_recalls_raw_detail_and_latest_correction(self):
        originals = []
        for i in range(90):
            question = f'Message {i}: ' + ('ordinary background ' * 35)
            if i == 0:
                question += ' secret-cabinet-location'
            originals.append(question)
            turn, _ = self.store.begin(1, 'chat-a', f'r{i}', question,
                                       self.store.read(1, 'chat-a')[0]['latest_message_id'])
            self.store.finish(1, turn, dict(issue_id=turn['message_id'], question=question), reply('not policy', 'test'), [])
        correction = self.send('Correction: closing bag is BLUE.', 'correction')
        _, turns = self.store.read(1, 'chat-a')
        memory, index = pack_memory(turns, 'secret-cabinet-location', 4000)
        self.assertLess(sum(units(dumps(x)) for x in memory), 4001)
        self.assertTrue(any('secret-cabinet-location' in x['question'] for x in memory))
        self.assertTrue(any(x['message_id'] == correction['message_id'] for x in memory))
        self.assertEqual(len(index), 91)
        self.assertEqual(turns[0]['original_question'], originals[0])

    def test_no_ai_history_as_kb_and_latest_active_kb_is_read_again(self):
        first = self.send('Ice bin put where when closing?', 'one')
        with patch.object(self, 'knowledge', return_value=('', [])) as current:
            response = self.send('Ice bin put where when closing?', 'two')
        self.assertTrue(first['grounded'])
        self.assertTrue(response['escalation_id'])
        self.assertNotIn('grounded', response)
        current.assert_called_once()

    def test_unquoted_or_invented_source_cannot_answer(self):
        original = self.generate
        def bad(prompt):
            if 'LATEST EMPLOYEE QUESTION:' in prompt:
                return original(prompt)
            return dumps(dict(answered=True, answer='Move cabinet', sourceTitle='Closing', evidence='Move the cabinet.'))
        engine = ChatEngine(self.store, bad, self.knowledge)
        result = engine.send(1, 'chat-a', dict(question='Move cabinet?', request_id='one'))
        self.assertTrue(result['escalation_id'])

    def test_quote_without_question_confidence_cannot_answer(self):
        original = self.generate
        def uncertain(prompt):
            parsed = loads(original(prompt))
            if 'CURRENT_KNOWLEDGE:' in prompt:
                parsed['confidence'] = 0.4
            return dumps(parsed)
        result = ChatEngine(self.store, uncertain, self.knowledge).send(
            1, 'chat-a', dict(question='Ice bin put where when closing?', request_id='one'))
        self.assertTrue(result['escalation_id'])

    def test_resolved_issue_is_not_overwritten_by_a_new_supplement(self):
        first = self.send('Where does the plastic bag go?', 'one')
        with self.store.transaction() as (_, c):
            c.execute("UPDATE escalation SET status='resolved' WHERE escalation_id=%s", (first['escalation_id'],))
        self.model_resolutions.append(dict(resolution('Where does the BLUE plastic bag go?'),
                                           relation='correction', same_issue_id=first['issue_id']))
        later = self.send('Correction, the blue plastic bag.', 'two')
        self.assertNotEqual(later['escalation_id'], first['escalation_id'])
        self.assertEqual(self.tickets()[0]['status'], 'resolved')
        self.assertEqual(len(self.tickets()), 2)

    def test_same_question_different_employee_does_not_share_ticket(self):
        first = self.send('Where does the plastic bag go?', 'one')
        self.store.create(2, 'other-chat')
        other = self.send('Where does the plastic bag go?', 'one', chat='other-chat', owner=2)
        self.assertNotEqual(first['escalation_id'], other['escalation_id'])

    def test_budget_reserves_output_and_stores_oversize_original(self):
        text = '长问题' * 3000
        response = self.engine(context_limit=4096).send(1, 'chat-a', dict(question=text, request_id='one'))
        self.assertEqual(response['source'], 'context_budget')
        self.assertEqual(self.prompts, [])
        self.assertEqual(self.store.read(1, 'chat-a')[1][0]['original_question'], text)

    def test_failed_ticket_save_rolls_back_and_retry_is_safe(self):
        real = Cursor.execute
        def fail_ticket(cursor, sql, params=()):
            if sql.startswith('INSERT INTO escalation '):
                raise RuntimeError('mock database failure')
            return real(cursor, sql, params)
        with patch.object(Cursor, 'execute', fail_ticket):
            with self.assertRaises(RuntimeError):
                self.send('Where does plastic bag go?', 'one')
        self.assertEqual(self.tickets(), [])
        self.assertIsNone(self.store.read(1, 'chat-a')[1][0]['response_json'])
        retried = self.send('Where does plastic bag go?', 'one')
        self.assertTrue(retried['escalation_id'])
        self.assertEqual(len(self.tickets()), 1)

    def test_cancelled_turn_never_creates_ticket(self):
        result = self.engine(cancelled=lambda _: True).send(1, 'chat-a', dict(question='Unknown question', request_id='one'))
        self.assertEqual(result['source'], 'cancelled')
        self.assertFalse(result['escalation_ready'])
        self.assertEqual(self.tickets(), [])

    def test_multilingual_resolution_and_ambiguous_pronoun(self):
        for i, question in enumerate(['那个呢？', 'macam mana dengan itu?', 'How about it?']):
            self.model_resolutions.append(dict(resolution(question), ambiguous=True, clarification='Which item?'))
            result = self.send(question, str(i))
            self.assertEqual(result['source'], 'clarification')
        self.model_resolutions.append(dict(resolution('塑料袋 closing 要放哪里？'), search_query='closing plastic bag placement'))
        self.send('塑料袋 closing 要放哪里？', 'mixed')
        self.assertEqual(self.searches[-1], 'closing plastic bag placement')

    def test_import_is_owner_scoped_once_and_ai_answers_are_untrusted(self):
        messages = [dict(sender='user', text='Original old question'), dict(sender='ai', text='Old unsupported claim', grounded=True)]
        self.store.import_local(1, 'chat-a', messages, 'Old chat')
        self.store.import_local(1, 'chat-a', messages, 'Duplicate')
        turns = self.store.read(1, 'chat-a')[1]
        self.assertEqual(len(turns), 1)
        self.assertFalse(loads(turns[0]['response_json'])['grounded'])
        with self.assertRaises(ChatError):
            self.store.import_local(2, 'chat-a', messages, 'Attack')

    def test_old_chinese_detail_is_recalled_without_whitespace_word_boundaries(self):
        turns = []
        for i in range(30):
            turns.append(dict(message_id=str(i), sequence_no=i, original_question=(
                '冰桶应该放在哪里' if i == 0 else 'unrelated staff attendance ' * 15),
                resolution_json=None, response_json=None))
        packed, _ = pack_memory(turns, '回到之前的冰桶问题', 2000)
        self.assertTrue(any(x['message_id'] == '0' for x in packed))

    def test_expired_worker_cannot_publish_after_same_request_is_reclaimed(self):
        old, _ = self.store.begin(1, 'chat-a', 'one', 'Question', None)
        with patch('chat_memory.time.time', return_value=time.time() + 181):
            reclaimed, _ = self.store.begin(1, 'chat-a', 'one', 'Question', None)
        self.assertNotEqual(old['lease_id'], reclaimed['lease_id'])
        with self.assertRaises(ChatError):
            self.store.finish(1, old, dict(issue_id=old['message_id']), reply('', 'test'), [], True)
        result = self.store.finish(1, reclaimed, dict(issue_id=reclaimed['message_id'], question='Question'), reply('', 'test'), [], True)
        self.assertTrue(result['escalation_id'])
        self.assertEqual(len(self.tickets()), 1)

    def test_relevant_full_ai_original_can_be_recalled_but_is_labelled_not_policy(self):
        turns = [dict(message_id='old', sequence_no=0, original_question='Old steps', resolution_json=None,
                      response_json=dumps({'answer': 'background ' * 100 + 'special-step-twelve'}))]
        for i in range(15):
            turns.append(dict(message_id=str(i), sequence_no=i + 1, original_question='Unrelated attendance question',
                              resolution_json=None, response_json=dumps({'answer': 'Unrelated answer'})))
        packed, _ = pack_memory(turns, 'special-step-twelve', 2000)
        old = next(x for x in packed if x['message_id'] == 'old')
        self.assertIn('special-step-twelve', old['earlier_ai_answer_not_policy'])


if __name__ == '__main__':
    unittest.main()
