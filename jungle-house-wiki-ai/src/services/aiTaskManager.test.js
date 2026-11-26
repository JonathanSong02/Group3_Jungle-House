import test from 'node:test';
import assert from 'node:assert/strict';
import { createAiTaskManager, isLookingAt } from './aiTaskManager.js';

// "AI keeps running after the page is left": the request runner shared by the
// chat page and the AI quiz page. Fake api / storage / clock, no network.
function memoryStorage() {
  const data = new Map();
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
    data,
  };
}

function setup({ saved = [], get } = {}) {
  let clock = 1_000_000;
  const storage = memoryStorage();
  const gets = [];
  const answers = [...saved];
  const api = {
    get: async (url) => {
      gets.push(url);
      if (get) return get(url);
      const next = answers.length ? answers.shift() : { found: false };
      return { data: next };
    },
  };
  const manager = createAiTaskManager({
    api,
    storage,
    now: () => clock,
    sleep: async (ms) => { clock += ms; },
  });
  return { manager, storage, gets, advance: (ms) => { clock += ms; } };
}

const networkError = () => Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' });
const cancelError = () => Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', name: 'CanceledError' });

test('a normal reply passes straight through, no saved copy is asked for', async () => {
  const { manager, gets, storage } = setup();
  const response = await manager.run({ userId: 7, kind: 'chat', requestId: 'r1', meta: { sessionId: 1 },
    send: async () => ({ data: { reply: 'hi' }, status: 200 }) });
  assert.deepEqual(response.data, { reply: 'hi' });
  assert.deepEqual(gets, []);
  assert.deepEqual(JSON.parse(storage.getItem('jh_ai_tasks_7')), []);
});

test('a server error is shown at once, never polled', async () => {
  const { manager, gets } = setup();
  const error = Object.assign(new Error('500'), { response: { status: 500, data: { message: 'x' } } });
  await assert.rejects(manager.run({ userId: 7, kind: 'chat', requestId: 'r1', send: async () => { throw error; } }),
    (thrown) => thrown === error);
  assert.deepEqual(gets, []);
});

test('pressing Stop is not polled and not announced as done', async () => {
  const { manager, gets } = setup();
  const done = [];
  manager.onDone((event) => done.push(event));
  await assert.rejects(manager.run({ userId: 7, kind: 'chat', requestId: 'r1', send: async () => { throw cancelError(); } }),
    (thrown) => thrown.code === 'ERR_CANCELED');
  assert.deepEqual(gets, []);
  assert.deepEqual(done, []);
});

test('connection lost, then the saved copy is found and used as the reply', async () => {
  const { manager, gets } = setup({ saved: [{ found: false }, { found: true, kind: 'chat', http_status: 200, result: { reply: 'Open cabinet 3' } }] });
  const done = [];
  manager.onDone((event) => done.push(event));
  const response = await manager.run({ userId: 7, kind: 'chat', requestId: 'r 1', meta: { sessionId: 4 },
    send: async () => { throw networkError(); } });
  assert.deepEqual(response, { data: { reply: 'Open cabinet 3' }, status: 200 });
  assert.deepEqual(gets, ['/ai-tasks/r%201', '/ai-tasks/r%201']);
  assert.equal(done.length, 1);
  assert.equal(done[0].ok, true);
  assert.deepEqual(done[0].meta, { sessionId: 4 });
});

test('a saved error copy is returned as that error', async () => {
  const { manager } = setup({ saved: [{ found: true, kind: 'quiz', http_status: 502, result: { message: 'AI busy' } }] });
  await assert.rejects(manager.run({ userId: 7, kind: 'quiz', requestId: 'q1', send: async () => { throw networkError(); } }),
    (thrown) => thrown.response.status === 502 && thrown.response.data.message === 'AI busy');
});

test('connection lost and nothing saved: the original error after 3 minutes of checking every 3 s', async () => {
  const { manager, gets } = setup();
  const original = networkError();
  await assert.rejects(manager.run({ userId: 7, kind: 'chat', requestId: 'r1', send: async () => { throw original; } }),
    (thrown) => thrown === original);
  assert.equal(gets.length, 61); // at 0 s, 3 s, ... 180 s
});

test('quiz generation is waited for longer (4 minutes)', async () => {
  const { manager, gets } = setup();
  await assert.rejects(manager.run({ userId: 7, kind: 'quiz', requestId: 'q1', send: async () => { throw networkError(); } }));
  assert.equal(gets.length, 81);
});

test('running tasks are listed per user and kept in storage until they end', async () => {
  const { manager, storage } = setup();
  let finish;
  const pending = manager.run({ userId: 7, kind: 'chat', requestId: 'r1', meta: { sessionId: 2 },
    send: () => new Promise((resolve) => { finish = resolve; }) });
  assert.equal(manager.runningCount(7), 1);
  assert.equal(manager.runningCount(8), 0);
  assert.deepEqual(manager.getSnapshot().map((task) => task.requestId), ['r1']);
  const stored = JSON.parse(storage.getItem('jh_ai_tasks_7'));
  assert.deepEqual(stored.map((item) => [item.requestId, item.kind, item.meta.sessionId]), [['r1', 'chat', 2]]);
  finish({ data: {}, status: 200 });
  await pending;
  assert.equal(manager.runningCount(7), 0);
  assert.deepEqual(JSON.parse(storage.getItem('jh_ai_tasks_7')), []);
});

test('cancel aborts the request signal', async () => {
  const { manager } = setup();
  let signal;
  const pending = manager.run({ userId: 7, kind: 'chat', requestId: 'r1', send: (given) => {
    signal = given;
    return new Promise((resolve, reject) => given.addEventListener('abort', () => reject(cancelError())));
  } });
  manager.cancel('r1');
  assert.equal(signal.aborted, true);
  await assert.rejects(pending, (thrown) => thrown.code === 'ERR_CANCELED');
});

test('after a page reload, a left-over task is finished from its saved copy into the inbox', async () => {
  const { manager, storage } = setup({ saved: [{ found: true, kind: 'chat', http_status: 200, result: { reply: 'later' } }] });
  storage.setItem('jh_ai_tasks_7', JSON.stringify([{ requestId: 'old', kind: 'chat', meta: { sessionId: 3 }, startedAt: 999_000 }]));
  const done = [];
  manager.onDone((event) => done.push(event));
  await manager.resume(7);
  assert.deepEqual(manager.takeInbox(7, 'quiz'), []);
  assert.deepEqual(manager.takeInbox(7, 'chat'), [{ requestId: 'old', kind: 'chat', meta: { sessionId: 3 }, ok: true, status: 200, data: { reply: 'later' } }]);
  assert.deepEqual(manager.takeInbox(7, 'chat'), []); // taken once
  assert.deepEqual(JSON.parse(storage.getItem('jh_ai_tasks_7')), []);
  assert.equal(done.length, 1);
});

test('after a page reload, a task that never finished is reported as unfinished', async () => {
  const { manager, storage } = setup();
  storage.setItem('jh_ai_tasks_7', JSON.stringify([{ requestId: 'old', kind: 'chat', meta: { sessionId: 3 }, startedAt: 0 }]));
  await manager.resume(7);
  assert.deepEqual(manager.takeInbox(7, 'chat'), [{ requestId: 'old', kind: 'chat', meta: { sessionId: 3 }, failed: true }]);
});

test('Stop on a task picked up after reload leaves nothing in the inbox', async () => {
  const { manager, storage } = setup();
  storage.setItem('jh_ai_tasks_7', JSON.stringify([{ requestId: 'old', kind: 'chat', meta: {}, startedAt: 999_000 }]));
  const resumed = manager.resume(7);
  manager.cancel('old');
  await resumed;
  assert.deepEqual(manager.takeInbox(7, 'chat'), []);
  assert.equal(manager.runningCount(7), 0);
});

test('returning to the page checks the saved copy of a slow request at once', async () => {
  const { manager, advance } = setup({ saved: [{ found: true, kind: 'chat', http_status: 200, result: { reply: 'ready' } }] });
  const pending = manager.run({ userId: 7, kind: 'chat', requestId: 'r1', send: () => new Promise(() => {}) });
  advance(15_000);
  await manager.recheck();
  assert.deepEqual((await pending).data, { reply: 'ready' });
  assert.equal(manager.runningCount(7), 0);
});

test('unseen notices are kept per user until marked seen', () => {
  const { manager } = setup();
  manager.addUnseen(7, { kind: 'chat', sessionId: 3, requestId: 'r1' });
  manager.addUnseen(7, { kind: 'quiz', requestId: 'q1' });
  assert.equal(manager.unseen(8).length, 0);
  manager.markSeen(7, (item) => item.kind === 'chat' && item.sessionId === 3);
  assert.deepEqual(manager.unseen(7).map((item) => item.requestId), ['q1']);
});

test('no notice when the staff member is already looking at that chat or the quiz page', () => {
  const chat = { kind: 'chat', meta: { sessionId: 3 } };
  assert.equal(isLookingAt(chat, { pathname: '/chat', activeSessionId: 3 }), true);
  assert.equal(isLookingAt(chat, { pathname: '/chat', activeSessionId: 4 }), false); // another chat is open
  assert.equal(isLookingAt(chat, { pathname: '/knowledge', activeSessionId: 3 }), false);
  assert.equal(isLookingAt({ kind: 'quiz', meta: {} }, { pathname: '/admin/quiz-management' }), true);
  assert.equal(isLookingAt({ kind: 'quiz', meta: {} }, { pathname: '/chat' }), false);
});

test('Stop tells the server not to send a phone notification for that question', async () => {
  const told = [];
  const manager = createAiTaskManager({ api: { get: async () => ({ data: { found: false } }) }, storage: null, onCancel: (id) => told.push(id) });
  const pending = manager.run({ userId: 7, kind: 'chat', requestId: 'r1', send: (signal) =>
    new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(Object.assign(new Error('c'), { code: 'ERR_CANCELED' })))) });
  manager.cancel('r1');
  await assert.rejects(pending);
  assert.deepEqual(told, ['r1']);
});
