// Display and polling rules for the Notion Sync "Check for Updates" run.
//
// The check runs on the server and can take minutes, so the page does not wait
// on one long request; it asks the status route for the latest run instead.
// These pure helpers decide how often to ask and how to describe the run.

// After this many seconds a running sync gets the "taking longer than usual" note.
export const LONG_RUN_SECONDS = 180;

const toSeconds = (value) => {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
};

// Poll often while a run is young, then less often, much less often when the
// tab is hidden, and back off (capped at 30 s) when polls are failing -- a long
// sync must never hammer the server.
export function getPollDelayMs({ elapsedSeconds = 0, hidden = false, failures = 0 } = {}) {
  const elapsed = toSeconds(elapsedSeconds);
  let delay = elapsed < 60 ? 3000 : elapsed < 300 ? 5000 : 10000;

  if (hidden) delay = Math.max(delay, 15000);

  const failed = Math.min(toSeconds(failures), 3);
  if (failed > 0) delay = Math.min(30000, delay * 2 ** failed);

  return delay;
}

export function isLongRunning(run) {
  return run?.state === 'running' && toSeconds(run.elapsedSeconds) >= LONG_RUN_SECONDS;
}

// Whole-number percent for the progress bar, or null when the total is not known yet.
export function progressPercent(progress) {
  const total = toSeconds(progress?.total);
  if (!total) return null;

  const done = Math.min(Math.max(Number(progress.processed) || 0, 0), total);
  return Math.round((done / total) * 100);
}

// 65 -> "1:05"
export function formatElapsed(seconds) {
  const whole = Math.floor(toSeconds(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

// The page keeps asking while a run is going. It ALSO keeps asking (quietly, with
// the same back-off) when the last answer could not be loaded: a missing answer
// is never treated as a failed sync, it just means "try again in a moment".
export function shouldKeepPolling({ state = null, failures = 0 } = {}) {
  return state === 'running' || toSeconds(failures) > 0;
}

// A short reassurance is shown for a run in progress once a few polls in a row failed.
// Nothing is shown while idle, and a failed poll is never shown as a failed sync.
export const RETRY_NOTE_AFTER_FAILURES = 3;

export function shouldShowRetryNote({ state = null, failures = 0 } = {}) {
  return state === 'running' && toSeconds(failures) >= RETRY_NOTE_AFTER_FAILURES;
}
