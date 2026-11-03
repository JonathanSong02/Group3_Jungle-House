import test from 'node:test';
import assert from 'node:assert/strict';
import {
  LONG_RUN_SECONDS,
  formatElapsed,
  getPollDelayMs,
  isLongRunning,
  progressPercent,
  shouldKeepPolling,
  shouldShowRetryNote,
} from './notionSyncRun.js';

test('polls often at first, then slows down as a run keeps going', () => {
  assert.equal(getPollDelayMs({ elapsedSeconds: 0 }), 3000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 59 }), 3000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 60 }), 5000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 299 }), 5000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 300 }), 10000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 3600 }), 10000);
});

test('polls much less while the tab is hidden', () => {
  assert.equal(getPollDelayMs({ elapsedSeconds: 0, hidden: true }), 15000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 600, hidden: true }), 15000);
});

test('backs off after failed polls and never goes above 30 seconds', () => {
  assert.equal(getPollDelayMs({ elapsedSeconds: 0, failures: 1 }), 6000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 0, failures: 2 }), 12000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 0, failures: 3 }), 24000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 0, failures: 50 }), 24000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 400, failures: 3 }), 30000);
});

test('missing or odd input still gives a sane delay', () => {
  assert.equal(getPollDelayMs(), 3000);
  assert.equal(getPollDelayMs({ elapsedSeconds: null, failures: undefined }), 3000);
  assert.equal(getPollDelayMs({ elapsedSeconds: 'abc' }), 3000);
});

test('"taking longer than usual" only for a run that is still going', () => {
  assert.equal(LONG_RUN_SECONDS, 180);
  assert.equal(isLongRunning({ state: 'running', elapsedSeconds: 179 }), false);
  assert.equal(isLongRunning({ state: 'running', elapsedSeconds: 180 }), true);
  assert.equal(isLongRunning({ state: 'done', elapsedSeconds: 900 }), false);
  assert.equal(isLongRunning({ state: 'failed', elapsedSeconds: 900 }), false);
  assert.equal(isLongRunning(null), false);
  assert.equal(isLongRunning({ state: 'running' }), false);
});

test('progress percentage is clamped and absent when unknown', () => {
  assert.equal(progressPercent({ processed: 120, total: 300 }), 40);
  assert.equal(progressPercent({ processed: 0, total: 300 }), 0);
  assert.equal(progressPercent({ processed: 300, total: 300 }), 100);
  assert.equal(progressPercent({ processed: 999, total: 300 }), 100);
  assert.equal(progressPercent({ processed: -5, total: 300 }), 0);
  assert.equal(progressPercent({ processed: 1, total: 3 }), 33);
  assert.equal(progressPercent({ processed: 0, total: 0 }), null);
  assert.equal(progressPercent({ processed: 5 }), null);
  assert.equal(progressPercent(null), null);
});

test('elapsed time reads as m:ss', () => {
  assert.equal(formatElapsed(0), '0:00');
  assert.equal(formatElapsed(9), '0:09');
  assert.equal(formatElapsed(65), '1:05');
  assert.equal(formatElapsed(600), '10:00');
  assert.equal(formatElapsed(3725), '62:05');
  assert.equal(formatElapsed(-4), '0:00');
  assert.equal(formatElapsed(null), '0:00');
  assert.equal(formatElapsed('x'), '0:00');
});

test('keeps polling while a run is going, and retries quietly when the last status could not be loaded', () => {
  assert.equal(shouldKeepPolling({ state: 'running', failures: 0 }), true);
  assert.equal(shouldKeepPolling({ state: 'done', failures: 0 }), false);
  assert.equal(shouldKeepPolling({ state: 'failed', failures: 0 }), false);
  assert.equal(shouldKeepPolling({ state: null, failures: 0 }), false);
  // The status could not be loaded: keep trying, whatever we knew before. A missing answer is not a failed sync.
  assert.equal(shouldKeepPolling({ state: null, failures: 1 }), true);
  assert.equal(shouldKeepPolling({ state: 'done', failures: 2 }), true);
  assert.equal(shouldKeepPolling({ state: 'running', failures: 9 }), true);
  assert.equal(shouldKeepPolling(), false);
});

test('the "lost contact" note appears only for a run in progress, and only after several failed polls', () => {
  assert.equal(shouldShowRetryNote({ state: 'running', failures: 1 }), false);
  assert.equal(shouldShowRetryNote({ state: 'running', failures: 2 }), false);
  assert.equal(shouldShowRetryNote({ state: 'running', failures: 3 }), true);
  assert.equal(shouldShowRetryNote({ state: 'done', failures: 8 }), false);
  assert.equal(shouldShowRetryNote({ state: null, failures: 8 }), false);
});
