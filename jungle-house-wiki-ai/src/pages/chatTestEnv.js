// Test-only helper for the Chat.*.test.js files, which compile Chat.jsx with
// its imports removed and pass every imported name in by hand. These are the
// names the "AI keeps running" task runner added (2026-11-26). The runner uses
// the test's fake api and a fake clock, so a lost connection is retried
// instantly instead of for three real minutes.
import { createAiTaskManager, MAX_RUNNING_PER_USER } from '../services/aiTaskManager.js';
import * as chatSessionStore from '../utils/chatSessionStore.js';

export function aiTaskTestEnv(React, api, storage = globalThis.localStorage) {
  let clock = 0;
  const aiTasks = createAiTaskManager({
    api: { get: async (url) => (api.get ? api.get(url) : { data: { found: false } }) },
    storage,
    now: () => clock,
    sleep: async (ms) => { clock += ms; },
  });
  let count = 0;
  return {
    aiTasks,
    MAX_RUNNING_PER_USER,
    newAiRequestId: () => `test-request-${(count += 1)}`,
    useAiTasks: () => React.useSyncExternalStore(aiTasks.subscribe, aiTasks.getSnapshot, aiTasks.getSnapshot),
    ...chatSessionStore,
  };
}
