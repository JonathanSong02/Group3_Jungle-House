import { test } from 'node:test';
import assert from 'node:assert/strict';
import { updateSessionMessages, mergeEarlierMessages, hasLegacyChats } from './persistentChatState.js';
import { buildIssueContext } from './chatIssueContext.js';

test('MEM-18 reply after a chat switch updates only the initiating conversation', () => {
  const sessions = [{ id: 'a', messages: ['old'] }, { id: 'b', messages: ['independent'] }];
  const result = updateSessionMessages(sessions, 'a', ['saved reply'], new Set());
  assert.deepEqual(result[0].messages, ['saved reply']);
  assert.strictEqual(result[1], sessions[1]);
  assert.deepEqual(sessions[0].messages, ['old']);
});

test('MEM-11 late replies cannot resurrect a deleted conversation', () => {
  const sessions = [{ id: 'b', messages: [] }];
  assert.strictEqual(updateSessionMessages(sessions, 'a', ['late'], new Set(['a'])), sessions);
});

test('paginated messages retain order without duplicate boundary messages', () => {
  assert.deepEqual(mergeEarlierMessages([{ id: 1 }, { id: 2 }], [{ id: 2 }, { id: 3 }]), [{ id: 1 }, { id: 2 }, { id: 3 }]);
});

test('MEM-23 legacy detection never writes, erases or uploads another history', () => {
  const original = JSON.stringify([{ messages: [{ text: 'question' }, { text: 'answer' }] }]);
  const storage = { getItem: (key) => key === 'jh_ai_chat_sessions_7' ? original : null,
    setItem: () => assert.fail('must not write'), removeItem: () => assert.fail('must not erase') };
  assert.equal(hasLegacyChats(storage, 'jh_ai_chat_sessions_v2_7'), true);
  assert.equal(hasLegacyChats(storage, 'jh_ai_chat_sessions_v2_8'), false);
  assert.equal(storage.getItem('jh_ai_chat_sessions_7'), original);
  assert.equal(hasLegacyChats({ getItem: () => '{bad' }, 'key'), false);
});

test('MEM-22 cross-chat recalled text is excluded from automatic ticket evidence', () => {
  const context = buildIssueContext([
    { id: 'u1', sender: 'user', text: 'ice bin storage' },
    { id: 'a1', sender: 'ai', source: 'personal_chat_recall', text: 'Private quotation from a different chat' },
    { id: 'u2', sender: 'user', text: 'ice bin not this' },
  ], 'ice bin not this', 'main-synthetic');
  assert.ok(context);
  assert.ok(context.messages.every((m) => !m.content.includes('Private quotation')));
});

test('implicit cross-chat personal evidence is also excluded from automatic tickets', () => {
  const context = buildIssueContext([
    { id: 'u1', sender: 'user', text: 'ice bin cleaning' },
    { id: 'a1', sender: 'ai', source: 'ai_provider_answer', memory_context_used: true,
      text: 'Private previous-chat detail used in this answer' },
    { id: 'u2', sender: 'user', text: 'ice bin not this' },
  ], 'ice bin not this', 'main-synthetic');
  assert.ok(context);
  assert.ok(context.messages.every((m) => !m.content.includes('Private previous-chat')));
});
