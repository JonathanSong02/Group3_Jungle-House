import test from 'node:test';
import assert from 'node:assert/strict';
import { formatCooldown, isLockedFor, readRetryAfterSeconds } from './loginCooldown.js';

test('formats the countdown as mm:ss and never goes below zero', () => {
  assert.equal(formatCooldown(900), '15:00');
  assert.equal(formatCooldown(61), '01:01');
  assert.equal(formatCooldown(9), '00:09');
  assert.equal(formatCooldown(0), '00:00');
  assert.equal(formatCooldown(-5), '00:00');
  assert.equal(formatCooldown(undefined), '00:00');
  assert.equal(formatCooldown(59.9), '00:59');
});

test('takes the remaining time from the server: body first, then the Retry-After header', () => {
  assert.equal(readRetryAfterSeconds({ retry_after_seconds: 432 }, { 'retry-after': '900' }), 432);
  assert.equal(readRetryAfterSeconds({}, { 'retry-after': '120' }), 120);
  assert.equal(readRetryAfterSeconds(undefined, { get: (name) => (name === 'retry-after' ? '75' : undefined) }), 75);
  assert.equal(readRetryAfterSeconds({ retry_after_seconds: '300' }, undefined), 300);
});

test('ignores missing or nonsense values instead of inventing a countdown', () => {
  assert.equal(readRetryAfterSeconds({}, {}), null);
  assert.equal(readRetryAfterSeconds(null, null), null);
  assert.equal(readRetryAfterSeconds({ retry_after_seconds: 0 }, { 'retry-after': '-3' }), null);
  assert.equal(readRetryAfterSeconds({ retry_after_seconds: 'soon' }, { 'retry-after': 'later' }), null);
});

test('locks the form only for the account that was locked on this device', () => {
  assert.equal(isLockedFor('manager@junglehouse.com', ' Manager@JungleHouse.com ', 600), true);
  assert.equal(isLockedFor('manager@junglehouse.com', 'staff@junglehouse.com', 600), false);
  assert.equal(isLockedFor('manager@junglehouse.com', 'manager@junglehouse.com', 0), false);
  assert.equal(isLockedFor('', '', 600), false);
  assert.equal(isLockedFor(null, 'manager@junglehouse.com', 600), false);
});
