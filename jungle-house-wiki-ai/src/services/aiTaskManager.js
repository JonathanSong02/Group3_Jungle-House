// "AI keeps running after the page is left" (2026-11-26).
//
// Runs AI chat questions and AI quiz generation outside any page, so a reply
// still lands after the staff member switched page, locked the phone or lost
// signal. The request itself is the same one the page always sent -- when it
// answers normally nothing else happens (no extra waiting). Only when it fails
// WITHOUT any server reply (connection lost, page paused by the phone) does
// this ask the server for the saved copy of that reply (GET /api/ai-tasks/<id>)
// every 3 s until the time limit. Server errors and Stop are passed on at once,
// exactly as before.
//
// Running tasks are also written to localStorage, so after the phone reloads
// the page `resume()` can still collect them; those results wait in an "inbox"
// that the chat / quiz page reads.
//
// Plain JavaScript with injected api/storage/clock so node --test can run it.

export const POLL_MS = 3000;
export const WAIT_LIMIT_MS = { chat: 180_000, quiz: 240_000 };
export const RECHECK_AFTER_MS = 10_000;
export const MAX_RUNNING_PER_USER = 2;

const keyFor = {
  pending: (userId) => `jh_ai_tasks_${userId}`,
  inbox: (userId) => `jh_ai_task_inbox_${userId}`,
  unseen: (userId) => `jh_ai_unseen_${userId}`,
};

export const QUIZ_PAGE_PATH = '/admin/quiz-management';

// Is the staff member already looking at this finished task? (Then no notice.)
export function isLookingAt(event, place) {
  if (event.kind === 'chat') {
    return place.pathname === '/chat' && String(place.activeSessionId) === String(event.meta?.sessionId);
  }
  if (event.kind === 'quiz') return place.pathname === QUIZ_PAGE_PATH;
  return false;
}

export function isCancelError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError' || error?.name === 'AbortError';
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function savedCopyOutcome(found) {
  if (found.http_status < 400) {
    return { ok: true, response: { data: found.result, status: found.http_status } };
  }
  const error = new Error(`Request failed with status code ${found.http_status}`);
  error.response = { status: found.http_status, data: found.result };
  return { ok: false, error };
}

export function createAiTaskManager({
  api,
  storage,
  now = () => Date.now(),
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  onCancel = () => {},
}) {
  const live = new Map();
  const changeListeners = new Set();
  const doneListeners = new Set();
  let snapshot = [];

  const readList = (key) => {
    try {
      const value = JSON.parse(storage?.getItem(key) || '[]');
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  };
  const writeList = (key, list) => {
    try {
      storage?.setItem(key, JSON.stringify(list));
    } catch {
      // Storage full or blocked: the live task still works, only reload-recovery is lost.
    }
  };

  const changed = () => {
    snapshot = [...live.values()].map(({ userId, kind, requestId, meta, startedAt }) => ({ userId, kind, requestId, meta, startedAt }));
    changeListeners.forEach((listener) => listener());
  };
  const announce = (event) => doneListeners.forEach((listener) => {
    try { listener(event); } catch (error) { console.error('AI task listener error:', error); }
  });

  const removePending = (userId, requestId) =>
    writeList(keyFor.pending(userId), readList(keyFor.pending(userId)).filter((item) => item.requestId !== requestId));

  const checkSavedCopy = async (requestId) => {
    try {
      const response = await api.get(`/ai-tasks/${encodeURIComponent(requestId)}`);
      return response?.data?.found ? response.data : null;
    } catch {
      return null;
    }
  };

  const waitForSavedCopy = async (task) => {
    const deadline = task.startedAt + (WAIT_LIMIT_MS[task.kind] || WAIT_LIMIT_MS.chat);
    for (;;) {
      if (task.cancelled) return null;
      const found = await checkSavedCopy(task.requestId);
      if (found) return found;
      if (now() >= deadline) return null;
      await sleep(POLL_MS);
    }
  };

  const finish = (task, ok) => {
    live.delete(task.requestId);
    removePending(task.userId, task.requestId);
    changed();
    if (!task.cancelled) {
      announce({ type: 'done', userId: task.userId, kind: task.kind, requestId: task.requestId, meta: task.meta, ok });
    }
  };

  async function run({ userId, kind, requestId, meta = {}, send }) {
    const controller = new AbortController();
    const task = { userId, kind, requestId, meta, startedAt: now(), controller, early: deferred(), cancelled: false };
    live.set(requestId, task);
    writeList(keyFor.pending(userId), [
      ...readList(keyFor.pending(userId)).filter((item) => item.requestId !== requestId),
      { requestId, kind, meta, startedAt: task.startedAt },
    ]);
    changed();

    try {
      const response = await Promise.race([send(controller.signal), task.early.promise]);
      finish(task, true);
      return response;
    } catch (error) {
      if (isCancelError(error)) task.cancelled = true;
      if (task.cancelled || error?.response) {
        finish(task, false);
        throw error;
      }
      const found = await waitForSavedCopy(task);
      if (!found) {
        finish(task, false);
        throw error;
      }
      const outcome = savedCopyOutcome(found);
      finish(task, outcome.ok);
      if (outcome.ok) return outcome.response;
      throw outcome.error;
    }
  }

  function cancel(requestId) {
    const task = live.get(requestId);
    if (!task) return;
    task.cancelled = true;
    task.controller?.abort();
    try { onCancel(requestId); } catch { /* only a "don't notify" hint */ }
  }

  // Back on the page after a while: a request that is still "waiting" may
  // have lost its connection silently. One look at the saved copy settles it.
  async function recheck() {
    const slow = [...live.values()].filter((task) => task.controller && !task.cancelled && now() - task.startedAt >= RECHECK_AFTER_MS);
    await Promise.all(slow.map(async (task) => {
      const found = await checkSavedCopy(task.requestId);
      if (!found || !live.has(task.requestId)) return;
      const outcome = savedCopyOutcome(found);
      if (outcome.ok) task.early.resolve(outcome.response);
      else task.early.reject(outcome.error);
      task.controller.abort();
    }));
  }

  // After a page reload: collect tasks this page load did not start.
  async function resume(userId) {
    const leftOver = readList(keyFor.pending(userId)).filter((item) => item?.requestId && !live.has(item.requestId));
    await Promise.all(leftOver.map(async (item) => {
      const task = { userId, kind: item.kind, requestId: item.requestId, meta: item.meta || {},
        startedAt: Number(item.startedAt) || 0, controller: null, cancelled: false };
      live.set(task.requestId, task);
      changed();
      const found = await waitForSavedCopy(task);
      if (task.cancelled) {
        finish(task, false);
        return;
      }
      const entry = found
        ? (() => {
            const outcome = savedCopyOutcome(found);
            return { requestId: task.requestId, kind: task.kind, meta: task.meta, ok: outcome.ok, status: found.http_status, data: found.result };
          })()
        : { requestId: task.requestId, kind: task.kind, meta: task.meta, failed: true };
      writeList(keyFor.inbox(userId), [...readList(keyFor.inbox(userId)), entry]);
      finish(task, Boolean(entry.ok));
    }));
  }

  function takeInbox(userId, kind) {
    const all = readList(keyFor.inbox(userId));
    const taken = all.filter((item) => item.kind === kind);
    if (taken.length) writeList(keyFor.inbox(userId), all.filter((item) => item.kind !== kind));
    return taken;
  }

  return {
    run,
    cancel,
    recheck,
    resume,
    takeInbox,
    runningCount: (userId) => [...live.values()].filter((task) => task.userId === userId).length,
    getSnapshot: () => snapshot,
    subscribe: (listener) => { changeListeners.add(listener); return () => changeListeners.delete(listener); },
    onDone: (listener) => { doneListeners.add(listener); return () => doneListeners.delete(listener); },
    unseen: (userId) => readList(keyFor.unseen(userId)),
    addUnseen: (userId, item) => {
      writeList(keyFor.unseen(userId), [...readList(keyFor.unseen(userId)).filter((old) => old.requestId !== item.requestId), item]);
      changed();
    },
    markSeen: (userId, predicate) => {
      const list = readList(keyFor.unseen(userId));
      const rest = list.filter((item) => !predicate(item));
      if (rest.length !== list.length) {
        writeList(keyFor.unseen(userId), rest);
        changed();
      }
    },
  };
}
