// The one AI task runner for the whole app (see aiTaskManager.js). It lives in
// this module, not in a page, so it keeps running when the page changes.
import { useSyncExternalStore } from 'react';
import api from './api';
import { createAiTaskManager } from './aiTaskManager';

function browserStorage() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

// Step 2 (phone notifications): the server waits a few seconds before
// notifying. "Seen" tells it the answer is already on screen (or Stop was
// pressed), so no notification is sent. A failed call only means one extra one.
function tellServerSeen(requestId) {
  api.post(`/ai-tasks/${encodeURIComponent(requestId)}/seen`).catch(() => {});
}

export const aiTasks = createAiTaskManager({ api, storage: browserStorage(), onCancel: tellServerSeen });

if (typeof document !== 'undefined') {
  // Phone unlocked / tab shown again: check slow requests at once instead of
  // waiting for the browser to notice a dead connection.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') aiTasks.recheck();
  });
  aiTasks.onDone((event) => {
    if (document.visibilityState === 'visible') tellServerSeen(event.requestId);
  });
}

export function newAiRequestId() {
  return (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Running tasks (all users in this browser; filter by userId).
export function useAiTasks() {
  return useSyncExternalStore(aiTasks.subscribe, aiTasks.getSnapshot, aiTasks.getSnapshot);
}
