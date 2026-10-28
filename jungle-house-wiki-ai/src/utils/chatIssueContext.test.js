import test from 'node:test';
import assert from 'node:assert/strict';
import { buildIssueContext, getClarificationToken } from './chatIssueContext.js';

const user = (id, value, extra = {}) => ({ id, sender: 'user', type: 'text', text: value, ...extra });
const ai = (id, value, extra = {}) => ({ id, sender: 'ai', type: 'text', text: value, ...extra });
const build = (messages, question, offerId) => buildIssueContext(messages, question, 'main-test', offerId);
const discussion = [user(1, 'Where do I store the iPad when closing?'), ai(2, 'Keep the iPad in the cabinet.'),
  user(3, 'Honey shelf life'), ai(4, 'Honey answer'), user(5, 'The iPad cabinet is locked'), ai(6, 'Still unresolved')];

test('returning to iPad includes original discussion and excludes honey', () => {
  const result = build(discussion, 'The iPad cabinet is locked');
  assert.deepEqual(result.messages.map((item) => item.id), ['1', '2', '5', '6']);
  assert.equal(result.issue_id, '1');
  assert(!JSON.stringify(result).includes('Honey'));
});

test('finds an older issue beyond a recent-message window', () => {
  const messages = [...discussion.slice(0, 2), ...Array.from({ length: 12 }, (_, index) => user(20 + index, `Honey question ${index}`)), discussion[4]];
  assert(build(messages, discussion[4].text).messages.some((item) => item.id === '1'));
});

test('corrections remain with the issue in order and supplement description', () => {
  const messages = [user(1, 'iPad at Spring'), ai(2, 'Prior answer'), user(3, 'Correction, I mean ST3.'), user(4, 'Honey price'), user(5, 'iPad cabinet locked')];
  const result = build(messages, messages[4].text);
  assert.deepEqual(result.messages.map((item) => item.id), ['1', '2', '3', '5']);
  assert(result.description.includes('ST3'));
});

test('different subjects sharing an attribute do not merge', () => {
  const result = build([user(1, 'iPad price'), user(2, 'Honey price')], 'Honey price');
  assert.deepEqual(result.messages.map((item) => item.id), ['2']);
});

test('explicit standalone topic change is separate', () => {
  const result = build([user(1, 'iPad closing'), user(2, 'What about honey shelf life?')], 'What about honey shelf life?');
  assert.deepEqual(result.messages.map((item) => item.id), ['2']);
});

test('English deictic follow-up keeps product context', () => {
  const result = build([user(1, 'Golden Passion honey price'), user(2, 'And its benefits?')], 'And its benefits?');
  assert.equal(result.messages.length, 2);
});

test('subjectless opening returns to a unique operational issue instead of honey', () => {
  const result = build([user(1, 'ST3 kiosk closing'), user(2, 'Honey shelf life'), user(3, 'How about opening?')], 'How about opening?');
  assert.deepEqual(result.messages.map((item) => item.id), ['1', '3']);
});

test('Chinese follow-up keeps its issue', () => {
  const result = build([user(1, '平板电脑放在哪里'), user(2, '那它呢？')], '那它呢？');
  assert.equal(result.messages.length, 2);
});

test('Malay follow-up keeps its issue', () => {
  const result = build([user(1, 'madu Golden Passion'), user(2, 'Khasiat dia?')], 'Khasiat dia?');
  assert.equal(result.messages.length, 2);
});

test('offer anchors the original issue even after another topic', () => {
  const result = build(discussion, discussion[0].text, 2);
  assert.equal(result.issue_id, '1');
  assert(!JSON.stringify(result.messages).includes('Honey'));
});

test('old timestamps stay unknown and new timestamps are preserved', () => {
  const result = build([user(1, 'iPad'), ai(2, 'iPad answer', { created_at: '2026-10-26T01:00:00.000Z' })], 'iPad');
  assert.equal(result.messages[0].timestamp, null);
  assert.equal(result.messages[1].timestamp, '2026-10-26T01:00:00.000Z');
});

test('only private attachment references are included; no image data', () => {
  const result = build([user(1, 'iPad', { image_files: ['blob:abc', 'data:image/png,x', 'https://example.invalid/photo.png', '/static/uploads/chat/123_ipad.png'] })], 'iPad');
  assert.deepEqual(result.messages[0].attachments, ['/static/uploads/chat/123_ipad.png']);
});

test('bounds excerpts and reports omissions without changing saved messages', () => {
  const messages = Array.from({ length: 60 }, (_, index) => user(index, 'iPad ' + 'x'.repeat(3000)));
  const before = JSON.stringify(messages);
  const result = build(messages, messages[59].text);
  assert(result.messages.length <= 40);
  assert(result.messages.every((item) => item.content.length <= 2000 && item.truncated));
  assert(result.messages.reduce((sum, item) => sum + item.content.length, 0) <= 40000);
  assert(result.omitted_messages > 0);
  assert.equal(result.messages[0].id, '0');
  assert.equal(result.messages.at(-1).id, '59');
  assert.equal(JSON.stringify(messages), before);
});

test('no transcript is invented for an empty session or missing trigger', () => {
  assert.equal(build([], 'iPad'), null);
  assert.equal(build([user(1, 'Honey')], 'iPad'), null);
});

test('loading, failed responses and stopped output are excluded', () => {
  const result = build([user(1, 'iPad'), ai(2, 'error', { source: 'frontend_request_error' }), ai(3, 'stopped', { source: 'user_stopped_generation' })], 'iPad');
  assert.deepEqual(result.messages.map((item) => item.id), ['1']);
});

test('a rejection follows the immediately preceding issue rather than an older answer', () => {
  const result = build([user(1, 'Ice delivery payment how much?'), ai(2, 'Ice answer'),
    user(3, 'Daily Jungle Heart information'), ai(4, 'Daily information'), user(5, 'I think this is not what I want')], 'I think this is not what I want');
  assert.deepEqual(result.messages.map((item) => item.id), ['3', '4', '5']);
});

test('clarification state is sent only for the same issue, including after another answer', () => {
  const messages = [ai(1, 'Please clarify', { clarification_token: 'test-flow-state', clarification_issue_id: 'ice' }), ai(2, 'Another answer')];
  assert.equal(getClarificationToken(messages, { issue_id: 'ice' }), 'test-flow-state');
  assert.equal(getClarificationToken(messages, { issue_id: 'daily' }), '');
  assert.equal(getClarificationToken(messages, null), '');
});
