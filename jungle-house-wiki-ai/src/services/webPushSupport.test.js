import test from 'node:test';
import assert from 'node:assert/strict';
import { pushSupport, keyBytes } from './webPushSupport.js';

// Which notification help each device gets (2026-11-26, step 2).
const iphone = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1';
const android = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36';

function env({ ua = android, standalone = false, push = true, platform = 'Linux', touch = 5 } = {}) {
  const navigator = { userAgent: ua, platform, maxTouchPoints: touch, standalone, ...(push ? { serviceWorker: {} } : {}) };
  const window = {
    matchMedia: (query) => ({ matches: standalone && query.includes('standalone') }),
    ...(push ? { PushManager: function PushManager() {}, Notification: function Notification() {} } : {}),
  };
  return { navigator, window };
}

test('Android and computers can turn notifications on directly', () => {
  assert.equal(pushSupport(env()), 'supported');
  assert.equal(pushSupport(env({ ua: 'Mozilla/5.0 (Windows NT 10.0) Chrome/126', platform: 'Win32', touch: 0 })), 'supported');
});

test('iPhone in Safari first has to add the site to the Home Screen', () => {
  assert.equal(pushSupport(env({ ua: iphone, push: false, platform: 'iPhone' })), 'ios-install');
});

test('iPhone opened from the Home Screen can turn them on', () => {
  assert.equal(pushSupport(env({ ua: iphone, standalone: true, platform: 'iPhone' })), 'supported');
});

test('an iPad that says it is a Mac is still treated as an iPad', () => {
  const ipad = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15';
  assert.equal(pushSupport(env({ ua: ipad, push: false, platform: 'MacIntel', touch: 5 })), 'ios-install');
});

test('old browsers without push are told it is not available', () => {
  assert.equal(pushSupport(env({ push: false })), 'unsupported');
  assert.equal(pushSupport({}), 'unsupported');
});

test('the server key is turned into bytes for the browser', () => {
  assert.deepEqual([...keyBytes('AQID_-8')], [1, 2, 3, 255, 239]);
});
