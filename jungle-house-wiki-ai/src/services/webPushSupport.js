// What a device can do about AI-ready notifications (2026-11-26, step 2).
// Plain functions (no browser globals read at import) so node --test can run them.
//   'supported'   - can ask for permission now
//   'ios-install' - iPhone / iPad in the browser: Apple only allows notifications
//                   after "Add to Home Screen" and opening the site from there
//   'unsupported' - this browser has no web push

export function pushSupport({ navigator, window } = {}) {
  if (!navigator || !window) return 'unsupported';
  const ua = String(navigator.userAgent || '');
  const ios = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const standalone = navigator.standalone === true || Boolean(window.matchMedia?.('(display-mode: standalone)')?.matches);
  if (ios && !standalone) return 'ios-install';
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return 'unsupported';
  return 'supported';
}

export function keyBytes(base64Url) {
  const base64 = String(base64Url).replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}
