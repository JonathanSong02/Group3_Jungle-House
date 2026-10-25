import { test } from 'node:test';
import assert from 'node:assert/strict';
import { hydrateChat, mergeBoundReply, reconcileHydration } from './chatSessions.js';

test('reload hydrates full server transcript and message/request binding', () => {
  const result = hydrateChat({ chat_id: 'old-chat', title: 'Old', latest_message_id: 'm1', turns: [
    { message_id: 'm1', request_id: 'r1', question: 'Plastic bag?', response: { answer: 'Which bag?', issue_id: 'm1' } },
  ] }, (data) => ({ sender: 'ai', text: data.answer }), []);
  assert.equal(result.messages[0].text, 'Plastic bag?');
  assert.equal(result.messages[0].request_id, 'r1');
  assert.equal(result.messages[1].server_message_id, 'm1');
  assert.equal(result.latest_message_id, 'm1');
});

test('late result updates only originating chat while another chat is selected', () => {
  const chats = [{ id: 'a', messages: [{ sender: 'user', request_id: 'ra', text: 'A' }] },
    { id: 'b', messages: [{ sender: 'user', request_id: 'rb', text: 'B' }] }];
  const result = mergeBoundReply(chats, 'a', 'ra', chats[0].messages[0], { sender: 'ai', text: 'A answer' }, 'ma');
  assert.equal(result[0].messages[1].text, 'A answer');
  assert.deepEqual(result[1], chats[1]);
});

test('duplicate reply replaces the same result instead of adding another bubble', () => {
  const original = [{ id: 'a', messages: [{ sender: 'user', request_id: 'r' }] }];
  const once = mergeBoundReply(original, 'a', 'r', original[0].messages[0], { text: 'answer' }, 'm');
  const twice = mergeBoundReply(once, 'a', 'r', original[0].messages[0], { text: 'answer' }, 'm');
  assert.deepEqual(once, twice);
});

test('out-of-order reply cannot replace the latest message pointer', () => {
  const original = [{ id: 'a', latest_message_id: 'new', messages: [
    { sender: 'user', request_id: 'old-r', text: 'older' },
    { sender: 'user', request_id: 'new-r', server_message_id: 'new', text: 'latest' },
  ] }];
  const result = mergeBoundReply(original, 'a', 'old-r', original[0].messages[0], { text: 'old reply' }, 'old');
  assert.equal(result[0].latest_message_id, 'new');
  assert.equal(result[0].messages[2].text, 'latest');
});

test('reply for a deleted chat is discarded', () => {
  assert.deepEqual(mergeBoundReply([], 'deleted', 'r', {}, {}, 'm'), []);
});

test('late reload cannot roll back a completed reply or newer turn', () => {
  const current = { latest_message_id: 'm2', messages: [{ sender: 'ai', server_message_id: 'm2', reply_to_request_id: 'r2', text: 'saved answer' }] };
  assert.equal(reconcileHydration(current, { latest_message_id: 'm1', turns: [{ message_id: 'm1' }], messages: [] }), current);
  const incoming = { latest_message_id: 'm2', turns: [{ message_id: 'm2' }], messages: [{ pending_request: 'r2' }] };
  assert.equal(reconcileHydration(current, incoming).messages[0].text, 'saved answer');
});
