import test from 'node:test';
import assert from 'node:assert/strict';
import {
  inboxEntryToMessage, notifyChatStorageChanged, readSavedList, subscribeChatStorage, withSessionMessages,
} from './chatSessionStore.js';

// "AI keeps running": a reply that arrives after the chat page was left is
// written straight into the saved chats, so it is there when the page opens.
function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return { getItem: (key) => (data.has(key) ? data.get(key) : null), setItem: (key, value) => data.set(key, value) };
}

test('the saved list is read fresh from storage; missing or broken gives null', () => {
  const storage = memoryStorage({ a: JSON.stringify([{ id: 1 }]), broken: '{', notList: '{"x":1}' });
  assert.deepEqual(readSavedList(storage, 'a'), [{ id: 1 }]);
  assert.equal(readSavedList(storage, 'missing'), null);
  assert.equal(readSavedList(storage, 'broken'), null);
  assert.equal(readSavedList(storage, 'notList'), null);
  assert.equal(readSavedList(null, 'a'), null);
});

test('a reply lands in its own chat even when another chat is open', () => {
  const sessions = [
    { id: 1, title: 'Opening', messages: [{ id: 'a' }], updated_at: 'old' },
    { id: 2, title: 'New Chat', messages: [{ id: 'b' }], updated_at: 'old' },
  ];
  const result = withSessionMessages(sessions, 2, [{ id: 'b' }, { id: 'reply' }], 'Closing steps', 'now');
  assert.deepEqual(result[0], sessions[0]);
  assert.deepEqual(result[1], { id: 2, title: 'Closing steps', messages: [{ id: 'b' }, { id: 'reply' }], updated_at: 'now' });
});

test('an existing chat title is kept', () => {
  const sessions = [{ id: 1, title: 'Opening', messages: [], updated_at: 'old' }];
  assert.equal(withSessionMessages(sessions, 1, [], 'Something else', 'now')[0].title, 'Opening');
});

test('a deleted chat is simply not found', () => {
  const sessions = [{ id: 1, title: 'Opening', messages: [], updated_at: 'old' }];
  assert.deepEqual(withSessionMessages(sessions, 99, [{ id: 'x' }], 'q', 'now'), sessions);
});

test('inbox entries become chat messages: answer, server error, unfinished', () => {
  const build = (data) => ({ sender: 'ai', text: data.reply });
  const texts = { unfinished: 'Not finished. Please ask again.', unavailable: 'AI unavailable' };
  assert.deepEqual(inboxEntryToMessage({ ok: true, data: { reply: 'Open cabinet 3' } }, build, texts),
    { sender: 'ai', text: 'Open cabinet 3' });
  const error = inboxEntryToMessage({ ok: false, status: 500, data: { message: 'Server busy' } }, build, texts);
  assert.equal(error.text, 'Server busy');
  assert.equal(error.source, 'frontend_request_error');
  const unfinished = inboxEntryToMessage({ failed: true }, build, texts);
  assert.equal(unfinished.text, 'Not finished. Please ask again.');
  assert.equal(unfinished.source, 'ai_task_unfinished');
  assert.equal(inboxEntryToMessage({ ok: false, data: {} }, build, texts).text, 'AI unavailable');
});

test('open chat pages are told when the saved chats change', () => {
  const seen = [];
  const stop = subscribeChatStorage((key) => seen.push(key));
  notifyChatStorageChanged('jh_ai_chat_sessions_7');
  stop();
  notifyChatStorageChanged('jh_ai_chat_sessions_7');
  assert.deepEqual(seen, ['jh_ai_chat_sessions_7']);
});
